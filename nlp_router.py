"""
Turns a free-text question into one or more registry `intent` + params, so
the copilot can answer arbitrary phrasings of the supported questions,
including compound questions that need more than one underlying query
("how many times did X contact via WhatsApp, and how many via email?").

Two engines:

1. Gemini router (default when USE_LLM_ROUTER=1): Uses function calling
   against a schema built from REGISTRY, in AUTO mode -- meaning Gemini
   can (a) call one function, (b) call several functions in the same turn
   if the question genuinely needs more than one query, or (c) call none
   and instead return an explanatory text note when nothing in the
   registry actually answers the question (e.g. "emails aren't tracked
   per-person in this dataset"). This is the only LLM backend used, per
   explicit requirement -- no other-provider fallback.

2. Rule-based router (fallback only, used if Gemini errors or no API key
   is set): deterministic keyword matching, with a light compound-question
   split for "X and Y" phrasing.

Both return the same shape:
    {"routes": [{"intent": str, "params": dict, "confidence": float}, ...],
     "note": str | None,
     "engine": "gemini" | "rule_based"}

`route()` is kept as a thin backward-compatible wrapper that returns the
single best route (or a no-match dict) for any older caller that only
expects one intent.
"""
import os
import re
from difflib import get_close_matches
from dotenv import load_dotenv
from registry import REGISTRY

load_dotenv()  # so GEMINI_API_KEY can be read from a local .env file

# Keyword groups: an intent must match at least one keyword from EACH group.
RULES = {
    "calls_by_agent_this_week": [{"call"}, {"week"}, {"how many", "count", "number"}],
    "failed_calls_last_7_days": [{"call"}, {"failed", "fail"}],
    "avg_duration_completed_calls": [{"call"}, {"average", "avg", "mean"}, {"duration"}],
    "confirmed_appointments_today": [{"appointment"}, {"confirmed"}, {"today"}],
    "appointments_by_agent_this_week": [{"appointment"}, {"week"}, {"how many", "count", "number"}],
    "missed_appointments_last_7_days": [{"appointment"}, {"missed", "miss"}],
    "emails_sent_by_this_week": [{"email"}, {"sent", "send"}, {"week"}],
    "emails_with_subject_keyword_last_month": [{"email"}, {"subject"}, {"month"}],
    "emails_not_delivered": [{"email"}, {"not delivered", "undelivered", "bounced", "failed"}],
    "whatsapp_messages_by_agent_today": [{"whatsapp", "message"}, {"today"}],
    "whatsapp_total_messages_by_agent": [{"whatsapp", "message"},
                                          {"contact", "contacted", "many times", "how many"}],
    "whatsapp_delivered_vs_failed_last_3_days": [{"whatsapp", "message"}, {"delivered"}, {"failed"}],
    "whatsapp_latest_message_to_customer": [{"whatsapp", "message"}, {"latest", "last", "recent"}],
}

PREP_NAME_RE = re.compile(
    r"\b(?:by|for|to|from)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)"
)
# Fallback for phrasings with no preposition ("did Neha Sharma contact...").
# Deliberately generic -- it's only used once known-DB-value matching and the prepositional pattern have both failed, specifically so an 
# unkknown or misspelled name still gets extracted (and can then be reported by the query layer as "not a known agent") instead of silently vanishing.
GENERIC_NAME_RE = re.compile(r"\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b")
QUOTED_RE = re.compile(r"['\"]([^'\"]+)['\"]")


def _known_names(db, collection, field):
    try:
        return set(db[collection].distinct(field))
    except Exception:
        return set()


def _extract_entity(question: str, db, agent_fields=(), customer_fields=(), sender_fields=()):
    """Best-effort extraction of a proper-noun entity, preferring a direct
    match against real DB values (covers phrasings without a preposition,
    e.g. "did Priya Sharma make"), falling back to prepositional-phrase
    regex, then fuzzy matching. If nothing in the DB matches at all, the
    raw candidate is still returned so downstream query functions can
    surface a clear "not a known agent/customer" error instead of the
    router silently dropping the question."""
    known = set()
    for coll, field in list(agent_fields) + list(customer_fields) + list(sender_fields):
        known |= _known_names(db, coll, field)

    for name in sorted(known, key=len, reverse=True):
        if isinstance(name, str) and name and name.lower() in question.lower():
            return name

    candidates = [m.strip() for m in PREP_NAME_RE.findall(question)]
    for cand in candidates:
        if cand in known:
            return cand
    for cand in candidates:
        close = get_close_matches(cand, known, n=1, cutoff=0.75)
        if close:
            return close[0]
    if candidates:
        return candidates[0]

    # Last resort: any Title-Case two-word span, even without a preposition.
    generic_candidates = GENERIC_NAME_RE.findall(question)
    return generic_candidates[0] if generic_candidates else None


def _score(question_lower: str, groups) -> int:
    score = 0
    for group in groups:
        if any(kw in question_lower for kw in group):
            score += 1
        else:
            return -1  # missing a required group disqualifies this intent
    return score


def _rule_based_single(question: str, db=None):
    q = question.lower()
    best_intent, best_score = None, 0
    for intent, groups in RULES.items():
        score = _score(q, groups)
        if score > best_score:
            best_intent, best_score = intent, score

    if best_intent is None:
        return None

    entry = REGISTRY[best_intent]
    params = {}
    if "agent" in entry["params"]:
        params["agent"] = _extract_entity(
            question, db,
            agent_fields=[("call_logs", "agent"), ("appointments", "agent"),
                          ("whatsapp_conversations", "agent")],
        ) if db is not None else (PREP_NAME_RE.findall(question) or [None])[0]
    if "sender" in entry["params"]:
        m = re.search(r"\bby\s+([\w.@]+@[\w.]+|\S+@\S+)", question)
        params["sender"] = m.group(1) if m else (
            _extract_entity(question, db, sender_fields=[("email_conversations", "sender")])
            if db is not None else None
        )
    if "customer" in entry["params"]:
        params["customer"] = _extract_entity(
            question, db, customer_fields=[("whatsapp_conversations", "customer")]
        ) if db is not None else (PREP_NAME_RE.findall(question) or [None])[0]
    if "keyword" in entry["params"]:
        quoted = QUOTED_RE.findall(question)
        if quoted:
            params["keyword"] = quoted[0]
        else:
            m = re.search(r"'([A-Za-z]+)'|\"([A-Za-z]+)\"|had ([A-Za-z]+) in", question)
            params["keyword"] = next((g for g in (m.groups() if m else []) if g), "onboarding")

    max_possible = len(RULES[best_intent])
    confidence = round(best_score / max_possible, 2) if max_possible else 0.0
    return {"intent": best_intent, "params": params, "confidence": confidence}


_DOMAIN_SIGNAL_RE = re.compile(
    r"\b(call|appointment|email|whatsapp|message|how many|what|which|find|list|show)\b",
    re.IGNORECASE,
)


def _looks_like_a_data_request(clause: str) -> bool:
    """Filters out filler ('please', 'thanks') left over from splitting on commas/and, so trailing pleasantries don't get reported as an
    unanswerable sub-question."""
    return bool(_DOMAIN_SIGNAL_RE.search(clause))


def rule_based_route_multi(question: str, db=None):
    """Splits on conjunctions first (when there's more than one clause) so
    a match on one part of a compound question doesn't silently hide an
    unmatched second part; falls back to matching the whole question as a
    single unit when there's nothing to split. A clause that matches
    nothing is reported in `note` only if it actually looks like a data
    request (mentions a module or question word) -- filler like "please"
    left over from a stray comma is silently ignored."""
    clauses = [c.strip() for c in re.split(r"\band\b|;|,", question) if c.strip()]

    if len(clauses) <= 1:
        whole = _rule_based_single(question, db)
        if whole:
            return {"routes": [whole], "note": None, "engine": "rule_based"}
        return {"routes": [], "note": "No rule matched this question.", "engine": "rule_based"}

    routes, seen, unmatched = [], set(), []
    for clause in clauses:
        r = _rule_based_single(clause, db)
        if r:
            key = (r["intent"], tuple(sorted(r["params"].items())))
            if key not in seen:
                seen.add(key)
                routes.append(r)
        elif _looks_like_a_data_request(clause):
            unmatched.append(clause)

    note = None
    if unmatched:
        note = ("Couldn't match this part of the question to any supported query "
                 f"(it may ask for something this dataset doesn't track): {'; '.join(unmatched)}")

    if routes:
        return {"routes": routes, "note": note, "engine": "rule_based"}
    return {"routes": [], "note": note or "No rule matched this question.", "engine": "rule_based"}


def rule_based_route(question: str, db=None):
    """Backward-compatible single-route shape."""
    result = rule_based_route_multi(question, db)
    if result["routes"]:
        return result["routes"][0]
    return {"intent": None, "params": {}, "confidence": 0.0, "note": result["note"]}


def route_multi(question: str, db=None):
    """Primary entry point. Gemini is the only LLM backend (per
    requirement) and is used whenever USE_LLM_ROUTER=1; otherwise, and on
    any Gemini failure, falls back to the rule-based router so the app
    never hard-depends on an external service."""
    if os.environ.get("USE_LLM_ROUTER") == "1":
        try:
            from gemini_router import gemini_route_multi
            result = gemini_route_multi(question, db)
            if result.get("routes") or result.get("note"):
                return result
        except Exception as exc:  # noqa: BLE001
            print(f"[nlp_router] Gemini router unavailable ({exc}); "
                  "falling back to rule-based router.")
    return rule_based_route_multi(question, db)


def route(question: str, db=None):
    """Backward-compatible single-route wrapper around route_multi()."""
    result = route_multi(question, db)
    if result["routes"]:
        return result["routes"][0]
    return {"intent": None, "params": {}, "confidence": 0.0, "note": result.get("note")}
