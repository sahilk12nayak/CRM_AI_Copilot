"""Aggregation logic for the Email Conversations module."""
import re

from time_utils import this_week_range, last_month_range

# Statuses that count as "delivered successfully" for this dataset.
# Anything outside this set (bounced, failed, ...) is surfaced by
# emails_not_delivered(). Documented here since the raw schema doesn't
# encode success/failure explicitly.
SUCCESS_STATUSES = {"sent", "delivered"}


def emails_sent_by_this_week(db, sender: str):
    start, end = this_week_range()
    cursor = db.email_conversations.find(
        {"sender": sender, "timestamp": {"$gte": start, "$lte": end}},
        {"_id": 0},
    ).sort("timestamp", -1)
    results = list(cursor)
    return {
        "question": f"List all emails sent by {sender} this week.",
        "sender": sender,
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "count": len(results),
        "results": results,
    }


def emails_with_subject_keyword_last_month(db, keyword: str = "onboarding"):
    start, end = last_month_range()
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    count = db.email_conversations.count_documents({
        "subject": {"$regex": pattern},
        "timestamp": {"$gte": start, "$lte": end},
    })
    return {
        "question": f"How many emails had '{keyword}' in the subject last month?",
        "keyword": keyword,
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "count": count,
    }


def emails_not_delivered(db):
    cursor = db.email_conversations.find(
        {"status": {"$nin": list(SUCCESS_STATUSES)}},
        {"_id": 0},
    ).sort("timestamp", -1)
    results = list(cursor)
    return {
        "question": "Show emails that were not delivered successfully.",
        "considered_successful_statuses": sorted(SUCCESS_STATUSES),
        "count": len(results),
        "results": results,
    }
