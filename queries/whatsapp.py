"""Aggregation logic for the WhatsApp Business Conversations module."""
from time_utils import today_range, last_n_days_range


def known_agents(db):
    return sorted(db.whatsapp_conversations.distinct("agent"))


def messages_by_agent_today(db, agent: str):
    known = known_agents(db)
    if agent not in known:
        return {
            "question": f"List all WhatsApp messages sent by {agent} today.",
            "agent": agent,
            "count": None,
            "error": f"'{agent}' is not a known agent in the WhatsApp data. Known agents: {known}",
        }
    start, end = today_range()
    cursor = db.whatsapp_conversations.find(
        {"agent": agent, "timestamp": {"$gte": start, "$lte": end}},
        {"_id": 0},
    ).sort("timestamp", -1)
    results = list(cursor)
    return {
        "question": f"List all WhatsApp messages sent by {agent} today.",
        "agent": agent,
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "count": len(results),
        "results": results,
    }


def total_messages_by_agent(db, agent: str):
    """All-time count, unlike messages_by_agent_today which is scoped to
    today. Used for open-ended "how many times has X contacted via
    WhatsApp?" style questions with no explicit time window."""
    known = known_agents(db)
    if agent not in known:
        return {
            "question": f"How many times did {agent} contact customers via WhatsApp?",
            "agent": agent,
            "count": None,
            "error": f"'{agent}' is not a known agent in the WhatsApp data. "
                      f"Known agents: {known}",
        }
    count = db.whatsapp_conversations.count_documents({"agent": agent})
    return {
        "question": f"How many times did {agent} contact customers via WhatsApp?",
        "agent": agent,
        "count": count,
    }


def delivered_vs_failed_last_3_days(db):
    start, end = last_n_days_range(3)
    pipeline = [
        {"$match": {"timestamp": {"$gte": start, "$lte": end}}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    agg = list(db.whatsapp_conversations.aggregate(pipeline))
    breakdown = {row["_id"]: row["count"] for row in agg}
    return {
        "question": "How many messages were delivered vs failed in the last 3 days?",
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "delivered": breakdown.get("delivered", 0),
        "failed": breakdown.get("failed", 0),
        "full_status_breakdown": breakdown,
    }


def latest_message_to_customer(db, customer: str):
    doc = db.whatsapp_conversations.find(
        {"customer": customer}, {"_id": 0}
    ).sort("timestamp", -1).limit(1)
    doc = list(doc)
    result = doc[0] if doc else None
    return {
        "question": f"Find the latest message sent to {customer}.",
        "customer": customer,
        "result": result,
    }
