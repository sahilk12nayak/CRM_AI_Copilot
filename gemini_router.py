"""
NL routing engine backed by Gemini (gemini-2.0-flash by default) using
function calling.

Design choices, both driven by real failures seen in testing:

1. AUTO mode, not forced ANY. Forcing a function call means the model
   *must* map every question to one of the 12 intents even when none of
   them actually fits -- which silently produces a wrong answer instead
   of admitting the data doesn't support the question (e.g. "how many
   emails from a named person?" when the email schema has no per-person
   field at all, only generic sender/receiver addresses). In AUTO mode
   the model can also just return text explaining why it can't answer,
   which we surface as `note` instead of guessing.

2. Multiple function calls per turn. Gemini's function calling supports
   calling more than one function in a single response when the question
   genuinely needs it. We collect *all* function_call parts, not just the
   first, so a compound question like "how many times did X contact via
   WhatsApp, and how many via email?" can route to two intents (or one
   intent + an explanatory note for the unsupported half) in one pass.

As with before, the model can only ever select pre-approved, read-only
intents already defined in REGISTRY -- it's doing intent classification +
slot-filling, not deciding what queries exist.
"""
import os
from dotenv import load_dotenv 
from registry import REGISTRY

load_dotenv()  # so GEMINI_API_KEY can be read from a local .env file

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

# Flagged explicitly in the tool description so the model doesn't force-map
# person-based questions onto email data that can't answer them.
SCHEMA_NOTES = (
    "Important schema limitation: email_conversations records have NO agent "
    "or customer NAME field -- only generic role-based 'sender' addresses "
    "(e.g. support@crm.io, sales@crm.io) and generic 'receiver' addresses "
    "(e.g. customer1@example.com). If a question asks how many emails a "
    "named person sent or received, do not call any function for that part "
    "-- there is no way to answer it from this data. Only call "
    "emails_sent_by_this_week if the question specifies a sender ADDRESS, "
    "not a person's name."
)


def _function_declaration():
    return {
        # Schema for calling the tool 'run_crm_query' by gemini.
        "name": "run_crm_query",
        "description": "Run one of the CRM copilot's supported read-only queries. "
                        "Call this once per distinct question being asked -- if the "
                        "user asks a compound question, call it multiple times, once "
                        "per sub-question that a listed intent can actually answer. "
                        f"{SCHEMA_NOTES}",
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": list(REGISTRY.keys()),
                    "description": "\n".join(
                        f"{k}: {v['description']}" for k, v in REGISTRY.items()
                    ),
                },
                "agent": {"type": "string", "description": "Agent full name, if relevant."},
                "customer": {"type": "string", "description": "Customer full name, if relevant."},
                "sender": {"type": "string", "description": "Email sender address, if relevant."},
                "keyword": {"type": "string", "description": "Subject-line keyword to search for, if relevant."},
            },
            "required": ["intent"],
        },
    }


def _client():
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "No Gemini API key found. Set GEMINI_API_KEY, "
            "e.g. in a .env file: GEMINI_API_KEY=your_key"
        )
    return genai.Client(api_key=api_key)


def gemini_route_multi(question: str, db=None):
    """Returns {"routes": [...], "note": str|None, "engine": "gemini"}.

    Multiple routes are returned when the question needs more than one
    query; `note` carries the model's own explanation for any part it
    couldn't map to a supported intent."""
    from google.genai import types

    client = _client()
    tool = types.Tool(function_declarations=[_function_declaration()])
    config = types.GenerateContentConfig(
        tools=[tool],
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.AUTO,
            )
        ),
    )

    resp = client.models.generate_content(
        model=MODEL,
        contents=(
            "Answer this CRM question by calling run_crm_query once per "
            "sub-question it actually contains. If any part of the question "
            "can't be answered by any of the listed intents (for example, "
            "because the data doesn't track what's being asked), do not "
            "guess an intent for that part -- instead briefly explain why "
            "in your text response.\n\n"
            f"Question: {question}"
        ),
        config=config,
    )

    routes, seen, notes = [], set(), []
    for candidate in resp.candidates or []:
        for part in (candidate.content.parts or []):
            fc = getattr(part, "function_call", None)
            if fc and fc.name == "run_crm_query":
                args = dict(fc.args or {})
                intent = args.pop("intent", None)
                entry = REGISTRY.get(intent, {})
                params = {p: args[p] for p in entry.get("params", []) if args.get(p)}
                key = (intent, tuple(sorted(params.items())))
                if intent and key not in seen:
                    seen.add(key)
                    routes.append({"intent": intent, "params": params, "confidence": 1.0})
            text = getattr(part, "text", None)
            if text and text.strip():
                notes.append(text.strip())

    return {
        "routes": routes,
        "note": " ".join(notes) if notes else None,
        "engine": "gemini",
    }


def gemini_route(question: str, db=None):
    """Backward-compatible single-route wrapper."""
    result = gemini_route_multi(question, db)
    if result["routes"]:
        r = dict(result["routes"][0])
        r["engine"] = "gemini"
        return r
    return {"intent": None, "params": {}, "confidence": 0.0,
            "engine": "gemini", "note": result.get("note")}
