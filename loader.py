"""
Loads the JSON datasets into MongoDB collections and creates indexes that matter for the query
patterns we expose (agent/customer lookups + time-range scans are the
hot paths, so we index those fields).

Usage:
    python loader.py            # loads all 4 modules
"""
import argparse
import json
import os
from datetime import timezone
from dateutil import parser as dtparser
from db import get_db

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

MODULES = {
    "call_logs": {
        "file": "call_logs.json",
        "time_field": "call_time",
        "indexes": [[("agent", 1), ("call_time", -1)], [("call_status", 1)]],
    },
    "appointments": {
        "file": "appointments.json",
        "time_field": "appointment_time",
        "indexes": [[("agent", 1), ("appointment_time", -1)], [("status", 1)]],
    },
    "email_conversations": {
        "file": "email_conversations.json",
        "time_field": "timestamp",
        "indexes": [[("sender", 1), ("timestamp", -1)], [("status", 1)]],
    },
    "whatsapp_conversations": {
        "file": "whatsapp_conversations.json",
        "time_field": "timestamp",
        "indexes": [[("agent", 1), ("timestamp", -1)], [("customer", 1), ("timestamp", -1)]],
    },
}


def load_module(db, name, cfg, wipe=False):
    coll = db[name]
    if wipe:
        coll.delete_many({})

    path = os.path.join(DATA_DIR, cfg["file"])
    with open(path) as f:
        records = json.load(f)

    # Store the time field as a real datetime (not a string) so range queries and $dateTrunc-style aggregations work natively in Mongo.
    # Source data may or may not include a UTC offset ('...Z' vs a bare ISO string); if it's naive, we treat it as UTC rather than leaving
    # it ambiguous, since get_now() always returns a tz-aware UTC value and naive/aware datetimes can't be compared.
    time_field = cfg["time_field"]
    for r in records:
        parsed = dtparser.isoparse(r[time_field])
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        r[time_field] = parsed

    if records:
        coll.insert_many(records)

    for index in cfg["indexes"]:
        coll.create_index(index)

    print(f"Loaded {len(records)} records into '{name}' "
          f"(indexes: {[dict(i) if isinstance(i, list) else i for i in cfg['indexes']]})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wipe", action="store_true", help="Clear collections before loading")
    args = parser.parse_args()

    db = get_db()
    for name, cfg in MODULES.items():
        load_module(db, name, cfg, wipe=args.wipe)


if __name__ == "__main__":
    main()
