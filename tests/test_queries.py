"""
Automated correctness tests, run against mongomock so no live MongoDB is
needed. Seeds a small, hand-crafted dataset with known answers (rather
than the bulk generated data) so assertions are exact, not just "count > 0".
"""
import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ["USE_MOCK_DB"] = "1"

from db import reset_db  # noqa: E402
from queries import appointments, call_logs, emails, whatsapp  # noqa: E402

NOW = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
os.environ["FIXED_NOW"] = NOW.isoformat()


@pytest.fixture
def db():
    return reset_db()


def dt(days_ago=0, hours_ago=0):
    return NOW - timedelta(days=days_ago, hours=hours_ago)


# ---- Call Logs ---------------------------------------------------------

def test_calls_by_agent_this_week(db):
    monday_this_week = NOW - timedelta(days=NOW.weekday())
    db.call_logs.insert_many([
        {"call_id": "1", "agent": "Priya Sharma", "customer": "A",
         "call_time": monday_this_week + timedelta(hours=1), "duration_minutes": 3, "call_status": "completed"},
        {"call_id": "2", "agent": "Priya Sharma", "customer": "B",
         "call_time": dt(hours_ago=2), "duration_minutes": 4, "call_status": "completed"},
        {"call_id": "3", "agent": "Priya Sharma", "customer": "C",
         "call_time": monday_this_week - timedelta(days=1), "duration_minutes": 2, "call_status": "completed"},  # last week
        {"call_id": "4", "agent": "Someone Else", "customer": "D",
         "call_time": dt(hours_ago=1), "duration_minutes": 5, "call_status": "completed"},
    ])
    result = call_logs.calls_by_agent_this_week(db, "Priya Sharma")
    assert result["count"] == 2


def test_failed_calls_last_7_days(db):
    db.call_logs.insert_many([
        {"call_id": "1", "agent": "A", "customer": "X", "call_time": dt(days_ago=2),
         "duration_minutes": 0, "call_status": "failed"},
        {"call_id": "2", "agent": "A", "customer": "X", "call_time": dt(days_ago=10),
         "duration_minutes": 0, "call_status": "failed"},  # outside window
        {"call_id": "3", "agent": "A", "customer": "X", "call_time": dt(days_ago=1),
         "duration_minutes": 5, "call_status": "completed"},
    ])
    result = call_logs.failed_calls_last_7_days(db)
    assert result["count"] == 1
    assert result["results"][0]["call_id"] == "1"


def test_avg_duration_completed_calls(db):
    db.call_logs.insert_many([
        {"call_id": "1", "agent": "A", "customer": "X", "call_time": dt(),
         "duration_minutes": 10, "call_status": "completed"},
        {"call_id": "2", "agent": "A", "customer": "X", "call_time": dt(),
         "duration_minutes": 20, "call_status": "completed"},
        {"call_id": "3", "agent": "A", "customer": "X", "call_time": dt(),
         "duration_minutes": 999, "call_status": "failed"},  # excluded
    ])
    result = call_logs.avg_duration_completed_calls(db)
    assert result["avg_duration_minutes"] == 15.0
    assert result["based_on_calls"] == 2


# ---- Appointments --------------------------------------------------------

def test_confirmed_appointments_today(db):
    db.appointments.insert_many([
        {"appointment_id": "1", "agent": "A", "customer": "X", "appointment_time": dt(hours_ago=1),
         "status": "confirmed", "notes": ""},
        {"appointment_id": "2", "agent": "A", "customer": "X", "appointment_time": dt(days_ago=1),
         "status": "confirmed", "notes": ""},  # yesterday
        {"appointment_id": "3", "agent": "A", "customer": "X", "appointment_time": dt(hours_ago=2),
         "status": "cancelled", "notes": ""},
    ])
    result = appointments.confirmed_appointments_today(db)
    assert result["count"] == 1
    assert result["results"][0]["appointment_id"] == "1"


def test_missed_appointments_last_7_days(db):
    db.appointments.insert_many([
        {"appointment_id": "1", "agent": "A", "customer": "X", "appointment_time": dt(days_ago=3),
         "status": "missed", "notes": ""},
        {"appointment_id": "2", "agent": "A", "customer": "X", "appointment_time": dt(days_ago=9),
         "status": "missed", "notes": ""},
    ])
    result = appointments.missed_appointments_last_7_days(db)
    assert result["count"] == 1


# ---- Emails ---------------------------------------------------------------

def test_emails_with_subject_keyword_last_month(db):
    db.email_conversations.insert_many([
        {"email_id": "1", "sender": "support@crm.io", "receiver": "a@b.com",
         "subject": "Onboarding Help", "timestamp": dt(days_ago=5), "status": "sent"},
        {"email_id": "2", "sender": "support@crm.io", "receiver": "a@b.com",
         "subject": "ONBOARDING checklist", "timestamp": dt(days_ago=20), "status": "sent"},
        {"email_id": "3", "sender": "support@crm.io", "receiver": "a@b.com",
         "subject": "Invoice", "timestamp": dt(days_ago=5), "status": "sent"},
        {"email_id": "4", "sender": "support@crm.io", "receiver": "a@b.com",
         "subject": "Onboarding Help", "timestamp": dt(days_ago=40), "status": "sent"},  # outside 30d
    ])
    result = emails.emails_with_subject_keyword_last_month(db, "onboarding")
    assert result["count"] == 2  # case-insensitive match, within 30 days


def test_emails_not_delivered(db):
    db.email_conversations.insert_many([
        {"email_id": "1", "sender": "s", "receiver": "r", "subject": "x",
         "timestamp": dt(), "status": "sent"},
        {"email_id": "2", "sender": "s", "receiver": "r", "subject": "x",
         "timestamp": dt(), "status": "bounced"},
        {"email_id": "3", "sender": "s", "receiver": "r", "subject": "x",
         "timestamp": dt(), "status": "failed"},
    ])
    result = emails.emails_not_delivered(db)
    assert result["count"] == 2


# ---- WhatsApp ---------------------------------------------------------------

def test_delivered_vs_failed_last_3_days(db):
    db.whatsapp_conversations.insert_many([
        {"message_id": "1", "agent": "A", "customer": "X", "timestamp": dt(days_ago=1),
         "message": "m", "status": "delivered"},
        {"message_id": "2", "agent": "A", "customer": "X", "timestamp": dt(days_ago=1),
         "message": "m", "status": "delivered"},
        {"message_id": "3", "agent": "A", "customer": "X", "timestamp": dt(days_ago=2),
         "message": "m", "status": "failed"},
        {"message_id": "4", "agent": "A", "customer": "X", "timestamp": dt(days_ago=5),
         "message": "m", "status": "failed"},  # outside window
    ])
    result = whatsapp.delivered_vs_failed_last_3_days(db)
    assert result["delivered"] == 2
    assert result["failed"] == 1


def test_latest_message_to_customer(db):
    db.whatsapp_conversations.insert_many([
        {"message_id": "1", "agent": "A", "customer": "Vikram Das", "timestamp": dt(days_ago=2),
         "message": "old", "status": "delivered"},
        {"message_id": "2", "agent": "A", "customer": "Vikram Das", "timestamp": dt(hours_ago=1),
         "message": "newest", "status": "delivered"},
    ])
    result = whatsapp.latest_message_to_customer(db, "Vikram Das")
    assert result["result"]["message"] == "newest"


def test_total_messages_by_agent(db):
    db.whatsapp_conversations.insert_many([
        {"message_id": "1", "agent": "Amit Verma", "customer": "X", "timestamp": dt(days_ago=40),
         "message": "m", "status": "delivered"},
        {"message_id": "2", "agent": "Amit Verma", "customer": "X", "timestamp": dt(hours_ago=1),
         "message": "m", "status": "delivered"},
        {"message_id": "3", "agent": "Someone Else", "customer": "X", "timestamp": dt(),
         "message": "m", "status": "delivered"},
    ])
    result = whatsapp.total_messages_by_agent(db, "Amit Verma")
    assert result["count"] == 2  # unbounded by date, unlike messages_by_agent_today


def test_total_messages_by_unknown_agent_returns_error_not_zero(db):
    db.whatsapp_conversations.insert_many([
        {"message_id": "1", "agent": "Amit Verma", "customer": "X", "timestamp": dt(),
         "message": "m", "status": "delivered"},
    ])
    result = whatsapp.total_messages_by_agent(db, "Neha Sharma")  # not a real agent
    assert result["count"] is None
    assert "not a known agent" in result["error"]


def test_calls_by_unknown_agent_returns_error_not_zero(db):
    db.call_logs.insert_many([
        {"call_id": "1", "agent": "Priya Sharma", "customer": "X", "call_time": dt(),
         "duration_minutes": 5, "call_status": "completed"},
    ])
    result = call_logs.calls_by_agent_this_week(db, "Neha Sharma")
    assert result["count"] is None
    assert "not a known agent" in result["error"]
