"""Aggregation logic for the Call Logs module."""
from time_utils import this_week_range, last_n_days_range


def calls_by_agent_this_week(db, agent: str):
    known = sorted(db.call_logs.distinct("agent"))
    if agent not in known:
        return {
            "question": f"How many calls did {agent} make this week?",
            "agent": agent,
            "count": None,
            "error": f"'{agent}' is not a known agent in the call logs. Known agents: {known}",
        }
    start, end = this_week_range()
    count = db.call_logs.count_documents({
        "agent": agent,
        "call_time": {"$gte": start, "$lte": end},
    })
    return {
        "question": f"How many calls did {agent} make this week?",
        "agent": agent,
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "count": count,
    }


def failed_calls_last_7_days(db):
    start, end = last_n_days_range(7)
    cursor = db.call_logs.find(
        {"call_status": "failed", "call_time": {"$gte": start, "$lte": end}},
        {"_id": 0},
    ).sort("call_time", -1)
    results = list(cursor)
    return {
        "question": "List all failed calls in the last 7 days.",
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "count": len(results),
        "results": results,
    }


def avg_duration_completed_calls(db):
    pipeline = [
        {"$match": {"call_status": "completed"}},
        {"$group": {"_id": None, "avg_duration": {"$avg": "$duration_minutes"},
                     "num_calls": {"$sum": 1}}},
    ]
    agg = list(db.call_logs.aggregate(pipeline))
    avg = round(agg[0]["avg_duration"], 2) if agg else 0
    num_calls = agg[0]["num_calls"] if agg else 0
    return {
        "question": "What is the average call duration for completed calls?",
        "avg_duration_minutes": avg,
        "based_on_calls": num_calls,
    }
