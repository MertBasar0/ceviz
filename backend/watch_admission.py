"""Durable voice admission, never an audio/transcript store or replay queue.

The SQLite reservation commits before STT/process startup. A reservation whose
live owner was lost is unknown forever, not a license to repeat an action.
"""
from contextlib import contextmanager
from datetime import datetime
import hashlib
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid

from session_api import SessionError, SubmissionStore


MAX_CAPTURE_AGE = 900
MAX_FUTURE_SKEW = 30
MAX_SUBMISSIONS = 512
IDENTITY_FIELDS = ("ledger_id", "command_id", "audio_digest", "client_timestamp", "continue_job_id")


def audio_fingerprint(payload):
    material = payload["audio_data"]
    if "continue_job_id" in payload:
        material += "\ncontinue_job_id=" + payload["continue_job_id"]
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def identity_metadata(payload):
    if not isinstance(payload, dict):
        raise SessionError("invalid_identity", "Expected Watch command metadata.")
    for key in IDENTITY_FIELDS[:4]:
        if not isinstance(payload.get(key), str):
            raise SessionError("invalid_identity", "Watch command identity is incomplete.")
    try:
        for key in ("ledger_id", "command_id"):
            if str(uuid.UUID(payload[key])) != payload[key].lower():
                raise ValueError()
        if not re.fullmatch(r"[a-f0-9]{64}", payload["audio_digest"]):
            raise ValueError()
        if len(payload["client_timestamp"]) > 40:
            raise ValueError()
        captured = datetime.fromisoformat(payload["client_timestamp"].replace("Z", "+00:00"))
        if captured.tzinfo is None:
            raise ValueError()
        captured.timestamp()
        if "continue_job_id" in payload and (not isinstance(payload["continue_job_id"], str)
                or not re.fullmatch(r"job-[A-Za-z0-9-]{1,120}", payload["continue_job_id"])):
            raise ValueError()
    except (ValueError, OverflowError) as exc:
        raise SessionError("invalid_identity", "Watch command identity is invalid.") from exc
    return {key: payload[key] for key in IDENTITY_FIELDS if key in payload}


def capture_is_current(identity):
    captured = datetime.fromisoformat(identity["client_timestamp"].replace("Z", "+00:00")).timestamp()
    return -MAX_FUTURE_SKEW <= time.time() - captured <= MAX_CAPTURE_AGE


class WatchAdmission:
    def __init__(self, path: Path):
        self.path = path
        # One owner for legacy and versioned audio dedupe -> STT -> job receipt.
        # Status never takes this lock; only the short active-set lock below.
        self.lock = threading.Lock()
        self._active_lock = threading.Lock()
        self._active = set()

    def capabilities(self):
        # Reuse existing Ceviz file permissions/transaction/bootstrap ownership.
        # Ordinary /capabilities and legacy commands do not initialize a ledger.
        with SubmissionStore(self.path).connection() as database:
            # DELETE-journal commits also need their directory entry synced;
            # FULL alone can lose the last transaction after power failure.
            database.execute("PRAGMA synchronous=EXTRA")
            database.execute("PRAGMA fullfsync=ON")
            database.execute("""CREATE TABLE IF NOT EXISTS watch_ledger (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1), ledger_id TEXT NOT NULL)""")
            database.execute("""CREATE TABLE IF NOT EXISTS watch_submissions (
                command_id TEXT PRIMARY KEY, audio_digest TEXT NOT NULL,
                audio_fingerprint TEXT NOT NULL, parent_job_id TEXT,
                client_timestamp TEXT NOT NULL, expires_at REAL NOT NULL,
                target_agent_id TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('reserved', 'accepted')),
                job_id TEXT, CHECK(state = 'reserved' OR job_id IS NOT NULL))""")
            database.execute("INSERT OR IGNORE INTO watch_ledger VALUES (1, ?)", (str(uuid.uuid4()),))
            ledger = database.execute("SELECT ledger_id FROM watch_ledger WHERE singleton = 1").fetchone()[0]
        return {"watch_command_recovery_v1": True, "watch_command_ledger_id": ledger}

    @contextmanager
    def connection(self, *, readonly=True):
        database = None
        try:
            if self.path.exists():
                database = sqlite3.connect(self.path.resolve().as_uri() + ("?mode=ro" if readonly else "?mode=rw"), timeout=3, uri=True)
                database.row_factory = sqlite3.Row
                if not readonly:
                    database.execute("PRAGMA synchronous=EXTRA")
                    database.execute("PRAGMA fullfsync=ON")
                if not database.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='watch_ledger'").fetchone():
                    database.close()
                    database = None
            if database is None:
                yield None
            else:
                with database:
                    yield database
        except (OSError, sqlite3.Error) as exc:
            raise SessionError("tracking_unavailable", "Voice delivery tracking is unavailable. Check Jobs before retrying.", 503, uncertain=True) from exc
        finally:
            if database is not None:
                database.close()

    @staticmethod
    def matching_ledger(database, identity):
        if database is None:
            return False
        row = database.execute("SELECT ledger_id FROM watch_ledger WHERE singleton = 1").fetchone()
        return row is not None and row[0] == identity["ledger_id"].lower()

    @staticmethod
    def check_identity(row, identity, target):
        if row is not None and (row["audio_digest"] != identity["audio_digest"]
                or row["parent_job_id"] != identity.get("continue_job_id")
                or row["client_timestamp"] != identity["client_timestamp"]
                or row["target_agent_id"] != target):
            raise SessionError("identity_conflict", "This voice identity belongs to a different command or target. Check Jobs.", 409, uncertain=True)

    def projection(self, identity, row):
        result = {**identity, "delivery_state": "unknown"}
        if row is not None:
            if row["state"] == "accepted":
                result.update(delivery_state="accepted", job_id=row["job_id"])
            else:
                with self._active_lock:
                    if identity["command_id"].lower() in self._active:
                        result["delivery_state"] = "in_flight"
        return result

    def status(self, payload, target):
        identity = identity_metadata(payload)
        if set(payload) - set(IDENTITY_FIELDS):
            raise SessionError("invalid_identity", "Delivery status accepts metadata only.")
        with self.connection() as database:
            if database is not None:
                # The ledger and its absence proof must come from one snapshot.
                database.execute("BEGIN")
            if not self.matching_ledger(database, identity):
                return self.projection(identity, None)
            row = database.execute("SELECT * FROM watch_submissions WHERE command_id = ?",
                                   (identity["command_id"].lower(),)).fetchone()
            self.check_identity(row, identity, target)
            result = self.projection(identity, row)
            if row is None and capture_is_current(identity):
                result["delivery_state"] = "not_submitted"
            return result

    def reserve(self, identity, fingerprint, target):
        with self.connection(readonly=False) as database:
            if database is None:
                return None, False
            database.execute("BEGIN IMMEDIATE")
            if not self.matching_ledger(database, identity):
                return None, False
            row = database.execute("SELECT * FROM watch_submissions WHERE command_id = ?",
                                   (identity["command_id"].lower(),)).fetchone()
            self.check_identity(row, identity, target)
            if row is not None:
                return row, False
            if not capture_is_current(identity):
                return None, False
            if database.execute("SELECT count(*) FROM watch_submissions").fetchone()[0] >= MAX_SUBMISSIONS:
                database.execute("DELETE FROM watch_submissions WHERE state='accepted' AND expires_at < ?", (time.time(),))
                if database.execute("SELECT count(*) FROM watch_submissions").fetchone()[0] >= MAX_SUBMISSIONS:
                    raise SessionError("request_capacity", "Voice tracking is full. Check unresolved commands before sending.", 503, uncertain=True)
            duplicate = database.execute("SELECT * FROM watch_submissions WHERE audio_fingerprint = ? ORDER BY state DESC LIMIT 1",
                                         (fingerprint,)).fetchone()
            # New UUIDs and older clients cannot evade a possibly dispatched
            # audio+parent identity. An accepted alias keeps only its job ID.
            state = "accepted" if duplicate is not None and duplicate["state"] == "accepted" and duplicate["target_agent_id"] == target else "reserved"
            job_id = duplicate["job_id"] if state == "accepted" else None
            expires = datetime.fromisoformat(identity["client_timestamp"].replace("Z", "+00:00")).timestamp() + MAX_CAPTURE_AGE
            database.execute("""INSERT INTO watch_submissions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                             (identity["command_id"].lower(), identity["audio_digest"], fingerprint,
                              identity.get("continue_job_id"), identity["client_timestamp"], expires, target, state, job_id))
            row = database.execute("SELECT * FROM watch_submissions WHERE command_id = ?",
                                   (identity["command_id"].lower(),)).fetchone()
        return row, duplicate is None

    def record_accepted(self, identity, job_id):
        with self.connection(readonly=False) as database:
            if not self.matching_ledger(database, identity):
                raise SessionError("ledger_changed", "Delivery tracking changed. Check Jobs before retrying.", 503, uncertain=True)
            updated = database.execute("UPDATE watch_submissions SET state='accepted', job_id=? WHERE command_id=? AND state='reserved'",
                                       (job_id, identity["command_id"].lower()))
            if updated.rowcount != 1:
                raise SessionError("tracking_unavailable", "The voice receipt could not be saved. Check Jobs.", 503, uncertain=True)

    def legacy_job(self, fingerprint, target):
        with self.connection() as database:
            if database is None:
                return None
            row = database.execute("SELECT * FROM watch_submissions WHERE audio_fingerprint=? ORDER BY state DESC LIMIT 1", (fingerprint,)).fetchone()
            if row is None:
                return None
            if row["state"] != "accepted" or row["target_agent_id"] != target:
                raise SessionError("delivery_unknown", "This audio may already have been sent. Check Jobs before recording another command.", 409, uncertain=True)
            return row["job_id"]

    def submit(self, payload, target, execute):
        identity = identity_metadata(payload)
        if set(payload) - set(IDENTITY_FIELDS) - {"audio_data", "format", "locale"}:
            raise SessionError("invalid_audio", "Submit only the original Watch capture and its identity.")
        if (not isinstance(payload.get("audio_data"), str) or not payload["audio_data"]
                or payload.get("format") not in {"m4a", "aac"}
                or ("locale" in payload and (not isinstance(payload["locale"], str) or len(payload["locale"]) > 35))):
            raise SessionError("invalid_audio", "Expected a Watch audio capture.")
        material = identity["client_timestamp"] + "\n" + payload["audio_data"]
        if "continue_job_id" in identity:
            material += "\ncontinue_job_id=" + identity["continue_job_id"]
        if hashlib.sha256(material.encode("utf-8")).hexdigest() != identity["audio_digest"]:
            raise SessionError("identity_conflict", "Audio does not match its original identity.", 409, uncertain=True)
        if not self.lock.acquire(timeout=1):
            return 503, self.status(identity, target)
        try:
            row, fresh = self.reserve(identity, audio_fingerprint(payload), target)
            if not fresh:
                return (200 if row is not None else 409), self.projection(identity, row)
            with self._active_lock:
                self._active.add(identity["command_id"].lower())
            try:
                job_id = execute(payload)
                self.record_accepted(identity, job_id)
                return 200, {**identity, "delivery_state": "accepted", "job_id": job_id}
            except Exception:
                # Neither a model error nor a failed receipt commit proves the
                # action was not dispatched. Leave the durable reservation.
                return 503, {**identity, "delivery_state": "unknown", "code": "delivery_unknown"}
            finally:
                with self._active_lock:
                    self._active.discard(identity["command_id"].lower())
        finally:
            self.lock.release()
