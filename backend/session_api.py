"""Phone conversations backed by the same Gateway RPCs as OpenClaw's TUI.

This surface never creates Ceviz jobs, copies transcript context into prompts,
changes the Watch target, or retries a possibly accepted message.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import subprocess
import unicodedata
import uuid
from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from http_transport import RequestReadError, read_request_body


class SessionError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, *, uncertain: bool = False):
        super().__init__(message)
        self.code, self.status, self.uncertain = code, status, uncertain


@dataclass
class Submission:
    session_key: str
    session_id: str
    fingerprint: str
    reply: dict | None = None
    terminal_result: dict | None = None


class SubmissionStore:
    """Ceviz-owned metadata journal; no transcripts or OpenClaw database access."""
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connection(self):
        connection = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.close(descriptor)
            except FileExistsError:
                pass
            # Python's bundled SQLite is the storage owner for this standalone
            # helper. Parameterized writes commit before any external dispatch.
            connection = sqlite3.connect(self.path, timeout=3)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("""CREATE TABLE IF NOT EXISTS conversation_submissions (
                request_id TEXT PRIMARY KEY, session_key TEXT NOT NULL,
                session_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                reply_status TEXT, terminal_status TEXT
                    CHECK (terminal_status IN ('completed', 'failed', 'aborted'))
            )""")
            with connection:
                yield connection
        except (OSError, sqlite3.Error) as exc:
            raise SessionError("tracking_unavailable",
                               "Message tracking is unavailable. Check the conversation before sending again.", 503) from exc
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def submission(row: sqlite3.Row | None) -> Submission | None:
        if row is None:
            return None
        reply = None if row["reply_status"] is None else {
            "run_id": row["request_id"], "status": row["reply_status"],
            "delivery_confirmed": row["reply_status"] in {"started", "pending", "in_flight", "ok"},
        }
        terminal = None if row["terminal_status"] is None else {
            "run_id": row["request_id"], "status": row["terminal_status"], "detail": None,
        }
        return Submission(row["session_key"], row["session_id"], row["fingerprint"], reply, terminal)

    def get(self, run_id: str) -> Submission | None:
        with self.connection() as database:
            return self.submission(database.execute(
                "SELECT * FROM conversation_submissions WHERE request_id = ?", (run_id,),
            ).fetchone())

    def reserve(self, run_id: str, submission: Submission) -> Submission | None:
        with self.connection() as database:
            # Serialize competing helper processes: checking then inserting in
            # separate transactions would admit the same external action twice.
            database.execute("BEGIN IMMEDIATE")
            previous = self.submission(database.execute(
                "SELECT * FROM conversation_submissions WHERE request_id = ?", (run_id,),
            ).fetchone())
            if previous is not None:
                return previous
            if database.execute("SELECT count(*) FROM conversation_submissions").fetchone()[0] >= 512:
                raise SessionError("request_capacity", "Message tracking is full. No command was sent.", 503)
            database.execute("""INSERT INTO conversation_submissions
                (request_id, session_key, session_id, fingerprint) VALUES (?, ?, ?, ?)""",
                (run_id, submission.session_key, submission.session_id, submission.fingerprint))
        return None

    def forget_unsent(self, run_id: str) -> None:
        with self.connection() as database:
            database.execute("DELETE FROM conversation_submissions WHERE request_id = ?", (run_id,))

    def record_reply(self, run_id: str, status: str) -> dict:
        with self.connection() as database:
            database.execute("UPDATE conversation_submissions SET reply_status = ? WHERE request_id = ?",
                             (status, run_id))
        return {"run_id": run_id, "status": status,
                "delivery_confirmed": status in {"started", "pending", "in_flight", "ok"}}

    def record_terminal(self, run_id: str, status: str) -> dict:
        with self.connection() as database:
            database.execute("""UPDATE conversation_submissions SET terminal_status = ?
                WHERE request_id = ? AND terminal_status IS NULL""", (status, run_id))
            row = database.execute("SELECT terminal_status FROM conversation_submissions WHERE request_id = ?",
                                   (run_id,)).fetchone()
        return {"run_id": run_id, "status": row[0], "detail": None}


# Public Gateway control-text contract in OpenClaw v2026.9.1,
# src/auto-reply/reply/abort-primitives.ts. These are not queued chat messages.
ABORT_TRIGGERS = frozenset({
    "stop", "esc", "abort", "exit", "interrupt", "detente", "deten", "detén", "arrete", "arrête",
    "停止", "停下来", "暂停", "やめて", "止めて", "रुको", "توقف", "стоп", "остановись", "останови",
    "остановить", "прекрати", "halt", "anhalten", "aufhören", "hoer auf", "stopp", "pare",
    "stop openclaw", "openclaw stop", "stop action", "stop current action", "stop run", "stop current run",
    "stop agent", "stop the agent", "stop don't do anything", "stop dont do anything",
    "stop do not do anything", "stop doing anything", "do not do that", "please stop", "stop please",
})


def is_session_control(body: str) -> bool:
    # The Gateway NFC-normalizes before control detection; JS whitespace also
    # includes BOM. Inspect that projection without rewriting the user's text.
    normalized = unicodedata.normalize("NFC", body).replace("\ufeff", " ")
    normalized = " ".join(normalized.lower().replace("’", "'").replace("`", "'").split())
    normalized = normalized.rstrip(".!?！？…,，。;；:：'\"’”)]}").strip()
    return normalized.startswith("/") or normalized in ABORT_TRIGGERS


def call_gateway(method: str, params: dict) -> dict:
    """Reuse the operator's configured CLI/auth; never expose CLI diagnostics."""
    sending = method == "chat.send"
    try:
        process = subprocess.run(
            ["openclaw", "gateway", "call", method, "--params", json.dumps(params),
             "--json", "--timeout", "8000"],
            capture_output=True, text=True, encoding="utf-8", timeout=12, check=False,
        )
    except FileNotFoundError as exc:
        raise SessionError("gateway_unavailable", "OpenClaw is not available on this server.", 503) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise SessionError("gateway_unavailable", "The Gateway response could not be confirmed.",
                           503, uncertain=sending) from exc
    try:
        result = json.loads(process.stdout)
    except (TypeError, ValueError) as exc:
        raise SessionError("gateway_response_invalid", "The Gateway response could not be read.",
                           502, uncertain=sending) from exc
    if process.returncode or not isinstance(result, dict):
        # A send can fail after admission. Even a structured CLI error is not
        # permission to submit the user's action again with a new identity.
        raise SessionError("gateway_rejected", "OpenClaw could not confirm this request. Refresh the conversation.",
                           502, uncertain=sending)
    return result


def text_value(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def session_owner(key: Any) -> tuple[str, str]:
    if not isinstance(key, str) or key != key.strip() or len(key) > 512:
        raise SessionError("invalid_session", "Choose a conversation from the list.")
    parts = key.split(":", 2)
    if len(parts) != 3 or parts[0] != "agent" or not parts[1] or not parts[2] or any(ord(c) < 32 for c in key):
        raise SessionError("invalid_session", "The conversation must identify its assistant explicitly.")
    return parts[1], parts[2]


def timestamp_ms(value: Any) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return int(value)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo:
                return int(parsed.timestamp() * 1000)
        except ValueError:
            pass
    return None


def session_row(row: dict, key: str | None = None) -> dict:
    key = key or row.get("key")
    agent_id, short_key = session_owner(key)
    title = text_value(row.get("derivedTitle")) or text_value(row.get("displayName")) or short_key
    return {
        "session_key": key, "session_id": text_value(row.get("sessionId")) or None,
        "agent_id": agent_id, "title": title,
        "preview": text_value(row.get("lastMessagePreview")),
        "updated_at_ms": timestamp_ms(row.get("updatedAt")),
        "is_running": row.get("hasActiveRun") is True,
        "archived": row.get("archived") is True,
        "status": text_value(row.get("status")) or None,
        "active_leaf_entry_id": row.get("activeLeafEntryId"),
        "can_send": "activeLeafEntryId" in row and row.get("archived") is not True,
    }


def history_messages(rows: list) -> list[dict]:
    messages = []
    occurrences: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("role") not in {"user", "assistant"}:
            continue
        content = row.get("content")
        other = False
        if isinstance(content, str):
            body = content
        elif isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                    parts.append(part["text"])
                else:
                    other = True
            body = "\n\n".join(parts)
        else:
            body, other = "", True
        metadata = row.get("__openclaw")
        metadata = metadata if isinstance(metadata, dict) else {}
        identity = text_value(metadata.get("id")) or text_value(row.get("id"))
        if not identity:
            identity = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        occurrence = occurrences.get(identity, 0)
        occurrences[identity] = occurrence + 1
        messages.append({
            "id": f"{identity}:{occurrence}", "role": row["role"], "text": body,
            "timestamp_ms": timestamp_ms(row.get("timestamp")), "has_other_content": other,
        })
    return messages


def query_offset(query: dict[str, list[str]]) -> int:
    try:
        offset = int(query.get("offset", ["0"])[0])
    except (ValueError, TypeError) as exc:
        raise SessionError("invalid_request", "Invalid page offset.") from exc
    if offset < 0 or offset > 1_000_000:
        raise SessionError("invalid_request", "Invalid page offset.")
    return offset


def page_fields(result: dict) -> dict:
    has_more = result.get("hasMore") is True
    offset = result.get("nextOffset")
    return {"has_more": has_more, "next_offset": offset if has_more and isinstance(offset, int) else None}


class OpenClawSessions:
    def __init__(self, state_path: Path | None = None):
        state_dir = Path(os.environ.get("WATCH_CEVIZ_STATE_DIR", str(Path.home() / ".openclaw" / "ceviz-state")))
        self.store = SubmissionStore(state_path if state_path is not None else state_dir / "conversations.sqlite")

    @staticmethod
    def replay(run_id: str, previous: Submission, fingerprint: str) -> dict:
        if previous.fingerprint != fingerprint:
            raise SessionError("message_identity_conflict", "This message identity already belongs to another request.", 409)
        return previous.reply or {"run_id": run_id, "status": "unconfirmed", "delivery_confirmed": False}

    def list_sessions(self, query: dict[str, list[str]]) -> dict:
        older = query.get("older", ["false"])[0]
        if older not in {"true", "false"}:
            raise SessionError("invalid_request", "Invalid conversation window.")
        params = {
            "limit": 50, "offset": query_offset(query), "includeGlobal": False,
            "includeUnknown": False, "includeDerivedTitles": True, "includeLastMessage": True,
        }
        if older == "false":
            params["activeMinutes"] = 7 * 24 * 60
        agent_id = query.get("agent_id", [""])[0].strip()
        if agent_id:
            params["agentId"] = agent_id
        search = query.get("search", [""])[0].strip()
        if len(search) > 200:
            raise SessionError("invalid_request", "Search is limited to 200 characters.")
        if search:
            params["search"] = search
        result = call_gateway("sessions.list", params)
        catalog = call_gateway("agents.list", {})
        rows = result.get("sessions")
        if not isinstance(rows, list):
            raise SessionError("gateway_response_invalid", "The conversation list could not be read.", 502)
        sessions = [session_row(row) for row in rows if isinstance(row, dict)]
        agents = {row["agent_id"]: row["agent_id"] for row in sessions}
        for agent in catalog.get("agents", []):
            if isinstance(agent, dict) and text_value(agent.get("id")):
                agents[agent["id"]] = text_value(agent.get("name")) or agent["id"]
        paging = page_fields(result)
        if paging["has_more"] and paging["next_offset"] is None:
            paging["next_offset"] = params["offset"] + len(rows)
        return {"sessions": sessions, "agents": [{"id": key, "name": name} for key, name in agents.items()], **paging}

    def snapshot(self, key: str, *, offset: int = 0, limit: int = 100, run_id: str | None = None) -> dict:
        agent_id, _ = session_owner(key)
        params = {"sessionKey": key, "agentId": agent_id, "limit": limit, "offset": offset}
        if run_id:
            params["inputRunIds"] = [run_id]
        result = call_gateway("chat.history", params)
        if result.get("sessionKey") != key or not isinstance(result.get("sessionInfo"), dict):
            raise SessionError("session_changed", "The conversation changed. Refresh before sending.", 409)
        if not text_value(result.get("sessionId")):
            raise SessionError("session_missing", "This conversation is no longer available.", 404)
        return result

    def history(self, query: dict[str, list[str]]) -> dict:
        key = query.get("session_key", [""])[0]
        result = self.snapshot(key, offset=query_offset(query))
        row = dict(result["sessionInfo"], sessionId=result["sessionId"])
        pending = result.get("pendingInputs") or {}
        return {
            "session": session_row(row, key), "messages": history_messages(result.get("messages") or []),
            **page_fields(result), "active_run_ids": row.get("activeRunIds") or [],
            "pending_count": pending.get("total", 0),
        }

    def send_message(self, payload: Any) -> dict:
        if not isinstance(payload, dict):
            raise SessionError("invalid_request", "A conversation message is required.")
        key = payload.get("session_key")
        agent_id, _ = session_owner(key)
        body = text_value(payload.get("text"))
        if not body or len(body) > 16000 or any((ord(c) < 32 and c not in "\t\r\n") or ord(c) == 127 for c in body):
            raise SessionError("invalid_message", "Enter a message of at most 16,000 characters.")
        if is_session_control(body):
            raise SessionError("unsupported_control", "Use OpenClaw for slash commands and session controls.")
        run_id = valid_run_id(payload.get("request_id"))
        expected_session = text_value(payload.get("session_id"))
        leaf = payload.get("expected_leaf_entry_id")
        if (not expected_session or "expected_leaf_entry_id" not in payload
                or (leaf is not None and (not isinstance(leaf, str) or not leaf or len(leaf) > 512))):
            raise SessionError("session_changed", "Reload the conversation before sending.", 409)
        fingerprint = hashlib.sha256(json.dumps(
            [key, expected_session, leaf, body], ensure_ascii=False,
        ).encode()).hexdigest()
        previous = self.store.get(run_id)
        if previous:
            return self.replay(run_id, previous, fingerprint)
        current = self.snapshot(key, limit=1)
        if current["sessionId"] != expected_session:
            raise SessionError("session_changed", "The conversation was reset. Review its history before sending.", 409)
        if current["sessionInfo"].get("archived") is True:
            raise SessionError("session_archived", "This conversation is archived and read-only.", 409)
        submission = Submission(key, expected_session, fingerprint)
        previous = self.store.reserve(run_id, submission)
        if previous:
            return self.replay(run_id, previous, fingerprint)
        # The Gateway checks both physical session and branch ancestry again
        # at admission. Preserve explicit null: omission disables its guard.
        try:
            result = call_gateway("chat.send", {
                "sessionKey": key, "agentId": agent_id, "sessionId": expected_session,
                "expectedLeafEntryId": leaf, "message": body, "idempotencyKey": run_id,
                "queueMode": "followup",
            })
        except SessionError as exc:
            if not exc.uncertain:
                self.store.forget_unsent(run_id)
            raise
        if result.get("runId") != run_id:
            raise SessionError("gateway_response_invalid", "Message acceptance could not be confirmed.",
                               502, uncertain=True)
        status = text_value(result.get("status"))
        status = status if status in {"started", "pending", "in_flight", "ok"} else "unconfirmed"
        try:
            return self.store.record_reply(run_id, status)
        except SessionError as exc:
            # Admission may have happened. The pre-dispatch identity remains
            # durable even if recording the acknowledgment fails or we crash.
            exc.uncertain = True
            raise

    def run_status(self, query: dict[str, list[str]]) -> dict:
        key = query.get("session_key", [""])[0]
        run_id = valid_run_id(query.get("run_id", [""])[0])
        submission = self.store.get(run_id)
        if submission and submission.session_key != key:
            raise SessionError("message_identity_conflict", "This message belongs to a different conversation.", 409)
        if submission and submission.terminal_result is not None:
            return submission.terminal_result
        current = self.snapshot(key, limit=1, run_id=run_id)
        if submission and submission.session_id != current["sessionId"]:
            return {"run_id": run_id, "status": "unconfirmed", "detail": None}
        active_ids = current["sessionInfo"].get("activeRunIds") or []
        receipts = current.get("inputReceipts") or []
        receipt = next((item for item in receipts if isinstance(item, dict) and item.get("runId") == run_id), None)
        in_flight = current.get("inFlightRun") or {}
        scoped = submission is not None or receipt is not None or run_id in active_ids or in_flight.get("runId") == run_id
        if not scoped:
            return {"run_id": run_id, "status": "unconfirmed", "detail": None}
        # A receipt establishes the session/run association, not completion or
        # replay safety. Poll timeout also means unknown after restart/expiry.
        result = call_gateway("agent.wait", {"runId": run_id, "timeoutMs": 0})
        if result.get("runId") != run_id:
            raise SessionError("gateway_response_invalid", "The run response did not match this message.", 502)
        terminal = result.get("terminalReceipt") or {}
        if terminal and (terminal.get("runId") != run_id or terminal.get("sessionId") != current["sessionId"]):
            return {"run_id": run_id, "status": "unconfirmed", "detail": None}
        state = result.get("status")
        ended_at = result.get("endedAt")
        has_ended = type(ended_at) in (int, float) and math.isfinite(ended_at)
        if state == "pending":
            status = "queued"
        elif state == "ok" and has_ended:
            status = "completed"
        elif state in {"error", "timeout"} and has_ended:
            status = "aborted" if state == "error" and result.get("stopReason") in {"aborted", "restart", "superseded", "rpc", "stop"} else "failed"
        elif run_id in active_ids or in_flight.get("runId") == run_id:
            status = "running"
        else:
            status = "unconfirmed"
        response = {"run_id": run_id, "status": status, "detail": None}
        if submission and status in {"completed", "failed", "aborted"}:
            return self.store.record_terminal(run_id, status)
        return response


def valid_run_id(value: Any) -> str:
    if not isinstance(value, str) or len(value) != 36:
        raise SessionError("invalid_request", "A valid message identity is required.")
    try:
        if str(uuid.UUID(value)) != value.lower():
            raise ValueError("noncanonical UUID")
    except ValueError as exc:
        raise SessionError("invalid_request", "A valid message identity is required.") from exc
    return value


sessions_api = OpenClawSessions()


def handle_session_request(handler: BaseHTTPRequestHandler, method: str, path: str, query: dict) -> None:
    """Called only after the existing Ceviz bearer authorization gate."""
    try:
        if method == "GET" and path == "/api/v1/sessions":
            payload = sessions_api.list_sessions(query)
        elif method == "GET" and path == "/api/v1/sessions/history":
            payload = sessions_api.history(query)
        elif method == "GET" and path == "/api/v1/sessions/run":
            payload = sessions_api.run_status(query)
        elif method == "POST" and path == "/api/v1/sessions/message":
            try:
                body = json.loads(read_request_body(handler, 96_000))
            except RequestReadError as exc:
                # Keep the shipped conversation size-error status; timeout is
                # distinct and never grants permission to replay an identity.
                raise SessionError("invalid_request", str(exc), 400 if exc.status == 413 else exc.status) from exc
            except (TypeError, ValueError, UnicodeDecodeError) as exc:
                raise SessionError("invalid_request", "A bounded JSON message is required.") from exc
            payload = sessions_api.send_message(body)
        else:
            raise SessionError("not_found", "Conversation endpoint not found.", 404)
        status = 200
    except SessionError as exc:
        status = exc.status
        payload = {"error": str(exc), "code": exc.code, "delivery_uncertain": exc.uncertain}
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    # Especially on rejected oversized bodies, EOF may be a TCP reset rather
    # than a graceful close. Frame the response by its exact UTF-8 byte count.
    handler.send_header("Content-Length", str(len(encoded)))
    handler.send_header("Connection", "close")
    handler.end_headers()
    handler.close_connection = True
    handler.wfile.write(encoded)
