"""Aggregation logic for the Appointments module."""
from time_utils import today_range, this_week_range, last_n_days_range


def confirmed_appointments_today(db):
    start, end = today_range()
    cursor = db.appointments.find(
        {"status": "confirmed", "appointment_time": {"$gte": start, "$lte": end}},
        {"_id": 0},
    ).sort("appointment_time", 1)
    results = list(cursor)
    return {
        "question": "List all confirmed appointments for today.",
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "count": len(results),
        "results": results,
    }


def appointments_by_agent_this_week(db, agent: str):
    known = sorted(db.appointments.distinct("agent"))
    if agent not in known:
        return {
            "question": f"How many appointments has {agent} had this week?",
            "agent": agent,
            "count": None,
            "error": f"'{agent}' is not a known agent in the appointments data. Known agents: {known}",
        }
    start, end = this_week_range()
    count = db.appointments.count_documents({
        "agent": agent,
        "appointment_time": {"$gte": start, "$lte": end},
    })
    return {
        "question": f"How many appointments has {agent} had this week?",
        "agent": agent,
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "count": count,
    }


def missed_appointments_last_7_days(db):
    start, end = last_n_days_range(7)
    cursor = db.appointments.find(
        {"status": "missed", "appointment_time": {"$gte": start, "$lte": end}},
        {"_id": 0},
    ).sort("appointment_time", -1)
    results = list(cursor)
    return {
        "question": "Find missed appointments in the last 7 days.",
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "count": len(results),
        "results": results,
    }
