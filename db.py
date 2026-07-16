"""
Central place for obtaining a database handle.

Design decision: the copilot is written entirely against the standard
pymongo API. In production it talks to a real MongoDB deployment (set
MONGO_URI). For local development, demos, and the automated test suite
(where a live mongod is inconvenient), it transparently falls back to
`mongomock`, an in-memory pymongo-compatible implementation. Because both
libraries expose the same interface, none of the query/aggregation code
has to know or care which one it's talking to.

Priority order:
1. USE_MOCK_DB=1  -> force mongomock (used by tests)
2. MONGO_URI set and reachable -> real MongoDB
3. otherwise -> fall back to mongomock with a warning, so the CLI/API
   still works out of the box with zero infrastructure setup.
"""
import os
import sys

DB_NAME = os.environ.get("MONGO_DB_NAME", "crm_copilot")
_client = None
_db = None


def get_db():
    global _client, _db
    if _db is not None:
        return _db

    force_mock = os.environ.get("USE_MOCK_DB") == "1"

    if not force_mock:
        try:
            from pymongo import MongoClient
            uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
            client = MongoClient(uri, serverSelectionTimeoutMS=1500)
            client.admin.command("ping")  # fail fast if unreachable
            _client = client
            _db = client[DB_NAME]
            print(f"[db] Connected to live MongoDB at {uri}", file=sys.stderr)
            return _db
        except Exception as exc:  # noqa: BLE001 - intentional broad fallback
            print(
                f"[db] Could not reach a live MongoDB ({exc.__class__.__name__}: {exc}). "
                "Falling back to in-memory mongomock so the app still runs. "
                "Set MONGO_URI to point at a real instance for production use.",
                file=sys.stderr,
            )

    import mongomock
    _client = mongomock.MongoClient()
    _db = _client[DB_NAME]
    _auto_seed_if_empty(_db)
    return _db


def _auto_seed_if_empty(db):
    """mongomock is in-process and in-memory, so a fresh CLI invocation
    (a new process each time) would otherwise start with an empty DB.
    To keep the CLI/tests usable out of the box with zero setup, we
    transparently load the bundled demo dataset the first time the mock
    DB is used and its collections are empty. This never runs against a
    real MongoDB -- that path is left exactly as the caller configured it."""
    if os.environ.get("SKIP_AUTOSEED") == "1":
        return
    try:
        if db.call_logs.estimated_document_count() > 0:
            return
        import loader
        for name, cfg in loader.MODULES.items():
            loader.load_module(db, name, cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"[db] Auto-seed skipped: {exc}", file=sys.stderr)


def reset_db():
    """Used by tests to get a completely fresh, empty in-memory database
    (no demo-data auto-seeding, since tests insert their own fixtures)."""
    global _client, _db
    _client = None
    _db = None
    os.environ["USE_MOCK_DB"] = "1"
    os.environ["SKIP_AUTOSEED"] = "1"
    return get_db()
