"""
registry.py
-----------
Single source of truth mapping a stable `intent` id -> (module, function,
required params, human description). Everything else in the app (REST
routes, CLI commands, the NL router, tests) is built on top of this table
so a new question only has to be added in one place.
"""
from queries import appointments, call_logs, emails, whatsapp

REGISTRY = {
    "calls_by_agent_this_week": {
        "fn": call_logs.calls_by_agent_this_week,
        "params": ["agent"],
        "description": "How many calls did <agent> make this week?",
    },
    "failed_calls_last_7_days": {
        "fn": call_logs.failed_calls_last_7_days,
        "params": [],
        "description": "List all failed calls in the last 7 days.",
    },
    "avg_duration_completed_calls": {
        "fn": call_logs.avg_duration_completed_calls,
        "params": [],
        "description": "What is the average call duration for completed calls?",
    },
    "confirmed_appointments_today": {
        "fn": appointments.confirmed_appointments_today,
        "params": [],
        "description": "List all confirmed appointments for today.",
    },
    "appointments_by_agent_this_week": {
        "fn": appointments.appointments_by_agent_this_week,
        "params": ["agent"],
        "description": "How many appointments has <agent> had this week?",
    },
    "missed_appointments_last_7_days": {
        "fn": appointments.missed_appointments_last_7_days,
        "params": [],
        "description": "Find missed appointments in the last 7 days.",
    },
    "emails_sent_by_this_week": {
        "fn": emails.emails_sent_by_this_week,
        "params": ["sender"],
        "description": "List all emails sent by <sender> this week.",
    },
    "emails_with_subject_keyword_last_month": {
        "fn": emails.emails_with_subject_keyword_last_month,
        "params": ["keyword"],
        "description": "How many emails had '<keyword>' in the subject last month?",
    },
    "emails_not_delivered": {
        "fn": emails.emails_not_delivered,
        "params": [],
        "description": "Show emails that were not delivered successfully.",
    },
    "whatsapp_messages_by_agent_today": {
        "fn": whatsapp.messages_by_agent_today,
        "params": ["agent"],
        "description": "List all WhatsApp messages sent by <agent> today.",
    },
    "whatsapp_total_messages_by_agent": {
        "fn": whatsapp.total_messages_by_agent,
        "params": ["agent"],
        "description": "How many times has <agent> contacted customers via WhatsApp (all time, no date filter)?",
    },
    "whatsapp_delivered_vs_failed_last_3_days": {
        "fn": whatsapp.delivered_vs_failed_last_3_days,
        "params": [],
        "description": "How many messages were delivered vs failed in the last 3 days?",
    },
    "whatsapp_latest_message_to_customer": {
        "fn": whatsapp.latest_message_to_customer,
        "params": ["customer"],
        "description": "Find the latest message sent to <customer>.",
    },
}


def run_intent(db, intent: str, **kwargs):
    if intent not in REGISTRY:
        raise KeyError(f"Unknown intent '{intent}'. Known intents: {list(REGISTRY)}")
    entry = REGISTRY[intent]
    missing = [p for p in entry["params"] if p not in kwargs or kwargs[p] in (None, "")]
    if missing:
        raise ValueError(f"Intent '{intent}' is missing required params: {missing}")
    call_kwargs = {p: kwargs[p] for p in entry["params"]}
    return entry["fn"](db, **call_kwargs)
