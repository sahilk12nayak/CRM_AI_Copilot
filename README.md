# CRM_AI_Copilot

A prototype backend that answers business questions over four CRM data
modules — **Call Logs**, **Appointments**, **Email Conversations**, and
**WhatsApp Business Conversations** — stored in MongoDB, exposed through
both a **CLI** and a **API**, and queryable either with exact
commands or in **plain English**.

## Why it's built this way

The project asks for two things: (1) precise
aggregation logic for specific business questions, and (2) an "AI
Copilot" framing, implying free-text input. 


## Project layout

```
crm_ai_copilot/
├── data/*.json             # sample dataset
├── tests/test_queries.py   # unit tests for every aggregation (mongomock)
├── queries/
│   ├── call_logs.py
│   ├── appointments.py
│   ├── emails.py
│   └── whatsapp.py
├── db.py                   # Mongo connection (real Mongo, falls back to mongomock)
├── loader.py               # loads JSON → MongoDB, creates indexes
├── registry.py             # intent -> function/params/description table
├── nlp_router.py           # default rule-based NL → intent router
├── gemini_router.py        # Gemini-based NL → intent router
├── cli.py                  # CLI: `ask` (NL) and `run` (exact) modes
├── api.py                  # FastAPI: POST /ask + 12 explicit REST routes
└── time_utils.py           # shared "this week" / "last N days" / last week definitions
```

- **`queries/`** — one MongoDB aggregation/find pipeline per business
  question, correct and testable in isolation, with no NLP involved.
- **`registry.py`** — a single table mapping a stable `intent` name to a
  query function, its required params, and a human description. This is
  the seam everything else is built on: REST routes, CLI commands, and
  the NL router, so a new question only gets added once.
- **`nlp_router.py`** — turns free text into `(intent, params)`. Default
  engine is a deterministic keyword/regex matcher (`RULES` + entity
  extraction against real values in the DB) — no external dependency, no
  cost, fully unit-testable, and honestly the *correct* tool for a fixed,
  known question set.
- **`gemini_router.py`** — Same interface as
  the rule router, but asks an LLM (via function/tool-calling, constrained
  to the same 12 intents) to do the routing. 

  LLM router falls back to it on any error (missing key, network issue, etc.), so the app never hard-depends
  on an external service:

  ```powershell
  $env:USE_MOCK_DB="1"
  $env:FIXED_NOW="2025-03-28T13:00:00+00:00"
  $env:GEMINI_API_KEY=...
  python cli.py ask "what's Amit's WhatsApp delivery rate this week vs failed?"
  ```

This means the "copilot" layer is provably a thin, swappable routing
layer on top of correct, independently-tested aggregation logic — not the
other way around.

## Data

`data/*.json` contains the actual sample dataset for this
project, — `call_logs.json`, `appointments.json`,
`email_conversations.json`,
`whatsapp_conversations.json`.

One schema quirk worth flagging: the provided timestamps have no UTC
offset (e.g. `2025-03-21T19:15:18.434066`). `loader.py`
treats any offset-naive timestamp as UTC on load — otherwise range
queries would crash comparing naive vs. timezone-aware datetimes. This is
called out explicitly in `loader.py` rather than silently assumed.

## Setup

```bash
pip install -r requirements.txt
```

### Clone the Repository
```bash
git clone https://github.com/sahilk12nayak/CRM_AI_Copilot.git
cd CRM_AI_Copilot
```

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Start the API Server
```bash
uvicorn api:app --reload
```
The API will be available at:
```
http://127.0.0.1:8000
```

### Access the Interactive API Documentation
Open your browser and visit:
```
http://127.0.0.1:8000/docs
```
This launches the Swagger UI, where you can test the CRM AI Copilot endpoints interactively.
## Results:
<img width="500" height="281" alt="Screenshot 2026-07-16 194306" src="https://github.com/user-attachments/assets/f376779e-ff38-44f5-9bb8-f95cc7d26d13" />
<img width="500" height="281" alt="Screenshot 2026-07-16 194342" src="https://github.com/user-attachments/assets/cef1115d-fee4-4de7-a126-7db04daf63ef" />



### Option A — real MongoDB (production path)

```bash
export MONGO_URI="mongodb://localhost:27017"   # or Atlas connection string
python loader.py --wipe
uvicorn api:app --reload
```

### Option B — zero-setup demo (no MongoDB required)

`db.py` transparently falls back to **mongomock** (an in-memory,
pymongo-compatible database) if it can't reach `MONGO_URI`, and
auto-seeds the bundled sample dataset the first time it's used. This is
purely a demo/dev convenience — the query code itself is 100% standard
pymongo and doesn't know or care which backend it's talking to.

```bash
python cli.py list-intents
python cli.py ask "How many calls did Priya Sharma make this week?"
```

> Note: mongomock is in-process memory, so each CLI invocation is a fresh
> process/fresh DB. That's fine for one-shot queries (auto-seed handles
> it), but for the API server you'll want either a real `MONGO_URI`, or
> to just leave `uvicorn` running as one long process (it seeds once on
> first request and stays populated for the life of that process).

> The sample dataset's latest timestamp is `2025-03-28T12:15:18`. If
> you're running the demo well after that date, "today"/"this week"
> style questions will legitimately return empty results (there's no
> data that recent). To get non-trivial answers when replaying old data,
> set `FIXED_NOW` to a moment shortly after the dataset's max timestamp,
> e.g. `export FIXED_NOW=2025-03-28T13:00:00+00:00` — `time_utils.get_now()`
> reads this instead of the real clock when set. Omit it in production;
> it exists purely to make an aging demo dataset still answerable.

## Usage

**CLI — natural language:**
```bash
python cli.py ask "List all failed calls in the last 7 days"
python cli.py ask "How many emails had 'onboarding' in the subject last month?"
python cli.py ask "Find the latest message sent to Vikram Das"
python cli.py ask          # interactive REPL, no arg needed
```

**CLI — exact command (bypasses NL layer entirely):**
```bash
python cli.py run calls_by_agent_this_week --param agent="Priya Sharma"
```
<img width="500" height="281" alt="Screenshot 2026-07-16 193841" src="https://github.com/user-attachments/assets/4c7bb180-bbcf-4c68-b5c9-03571c0308a6" />
<img width="500" height="281" alt="Screenshot 2026-07-16 193929" src="https://github.com/user-attachments/assets/8295d0cf-7bcf-42f7-a5ca-d980a6335e29" />

**REST API:**
```bash
uvicorn api:app --reload
curl -X POST localhost:8000/ask -H "Content-Type: application/json" \
     -d '{"question": "How many appointments has Neha Kapoor had this week?"}'
curl localhost:8000/whatsapp/customer/Vikram%20Das/latest-message
```

## Design decisions worth flagging

- **Time windows** (`time_utils.py`): "this week" = current ISO calendar
  week, Monday 00:00 → now (how BI tools and business users usually mean
  it). "Last N days" is a rolling window (now − N days → now). "Last
  month" is treated as a rolling 30 days rather than the previous
  calendar month, as the simplest, least surprising reading of a
  relative query — documented in code as an explicit assumption, easy to
  swap to calendar-month if the business wants that instead.
- **"Not delivered successfully" (emails)**: the schema doesn't have an
  explicit success flag, so `sent`/`delivered` are treated as success and
  everything else (`bounced`, `failed`, ...) as not — defined as a named
  constant (`SUCCESS_STATUSES`) in `queries/emails.py` rather than buried
  in a query, so it's a one-line change if the definition is wrong.
- **Timestamps stored as native `datetime`**, not strings, so range
  queries and aggregations work directly without runtime parsing.
- **Indexes**: compound indexes on `(agent, time_field)` and
  `(status/customer, time_field)` per module — the two access patterns
  every supported question actually uses.
- **Synthetic data isn't uniformly random**: `data_generator.py` weights
  timestamps toward recency (today / 3d / 7d / 30d) so the demo dataset
  reliably produces non-trivial answers instead of empty results by
  chance.


## What I'd add with more time

- Pagination/cursor support on the list-style endpoints (currently return
  full result sets; fine for this data volume, not for scale).
- Auth on the API (currently open, fine for a local prototype).
- A calendar-month toggle for "last month", and week-start config
  (Mon vs Sun) if this needs to serve non-Indian/US locales.
- Swap the demo's rolling "last month" for a real calendar-month
  aggregation if the business specifically wants that semantic.
- Multi-turn conversation support in the LLM router (currently
  single-shot per question).
