"""
FastAPI backend for the CRM AI Copilot.

Two ways to consume it:
- POST /ask               {"question": "..."}   <- the "AI Copilot" NL entrypoint
- GET  /<explicit routes> for each of the 12 supported questions, useful
  for direct integration, dashboards, or debugging without going through
  the NL layer.

Run with:
    uvicorn api:app --reload
"""
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from db import get_db
from nlp_router import route_multi
from registry import REGISTRY, run_intent

app = FastAPI(
    title="CRM AI Copilot",
    description="Ask natural-language or structured questions over Call Logs, "
                 "Appointments, Email, and WhatsApp CRM data.",
    version="1.0.0",
)


class AskRequest(BaseModel):
    question: str


@app.get("/")
def root():
    return {"status": "ok", "supported_intents": list(REGISTRY.keys())}


@app.get("/intents")
def list_intents():
    return {name: {"params": v["params"], "description": v["description"]}
            for name, v in REGISTRY.items()}


@app.post("/ask")
def ask(req: AskRequest):
    """Supports compound questions: `routed_as` may contain more than one
    route, and `answers` has one entry per route in the same order. `note`
    carries an explanation for any part of the question that couldn't be
    matched to a supported query (e.g. asking about a person's emails when
    the email schema only tracks generic sender/receiver addresses)."""
    db = get_db()
    routed = route_multi(req.question, db)
    routes = routed.get("routes", [])

    if not routes:
        raise HTTPException(
            status_code=422,
            detail=routed.get("note") or
            "Could not understand the question. See GET /intents for supported questions.",
        )

    answers = []
    for r in routes:
        try:
            answers.append(run_intent(db, r["intent"], **r["params"]))
        except ValueError as exc:
            answers.append({"error": str(exc)})

    return {"routed_as": routes, "note": routed.get("note"), "answers": answers}


# ---- Explicit routes (one per assignment question) -------------------

@app.get("/calls/agent/{agent}/this-week")
def calls_by_agent_this_week(agent: str):
    return run_intent(get_db(), "calls_by_agent_this_week", agent=agent)


@app.get("/calls/failed/last-7-days")
def failed_calls_last_7_days():
    return run_intent(get_db(), "failed_calls_last_7_days")


@app.get("/calls/average-duration")
def avg_duration_completed_calls():
    return run_intent(get_db(), "avg_duration_completed_calls")


@app.get("/appointments/confirmed/today")
def confirmed_appointments_today():
    return run_intent(get_db(), "confirmed_appointments_today")


@app.get("/appointments/agent/{agent}/this-week")
def appointments_by_agent_this_week(agent: str):
    return run_intent(get_db(), "appointments_by_agent_this_week", agent=agent)


@app.get("/appointments/missed/last-7-days")
def missed_appointments_last_7_days():
    return run_intent(get_db(), "missed_appointments_last_7_days")


@app.get("/emails/sender/{sender}/this-week")
def emails_sent_by_this_week(sender: str):
    return run_intent(get_db(), "emails_sent_by_this_week", sender=sender)


@app.get("/emails/subject-keyword/last-month")
def emails_with_subject_keyword_last_month(keyword: str = Query("onboarding")):
    return run_intent(get_db(), "emails_with_subject_keyword_last_month", keyword=keyword)


@app.get("/emails/not-delivered")
def emails_not_delivered():
    return run_intent(get_db(), "emails_not_delivered")


@app.get("/whatsapp/agent/{agent}/today")
def whatsapp_messages_by_agent_today(agent: str):
    return run_intent(get_db(), "whatsapp_messages_by_agent_today", agent=agent)


@app.get("/whatsapp/agent/{agent}/total")
def whatsapp_total_messages_by_agent(agent: str):
    return run_intent(get_db(), "whatsapp_total_messages_by_agent", agent=agent)


@app.get("/whatsapp/delivered-vs-failed/last-3-days")
def whatsapp_delivered_vs_failed_last_3_days():
    return run_intent(get_db(), "whatsapp_delivered_vs_failed_last_3_days")


@app.get("/whatsapp/customer/{customer}/latest-message")
def whatsapp_latest_message_to_customer(customer: str):
    return run_intent(get_db(), "whatsapp_latest_message_to_customer", customer=customer)
