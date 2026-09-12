#!/usr/bin/python3
"""External CLI boundary for the isolated helper lifecycle proof, never a Gateway."""
import json
import os
from pathlib import Path
import sys
import time


def main():
    arguments = sys.argv[1:]
    if arguments[:2] != ["gateway", "call"] or len(arguments) < 3:
        raise SystemExit("Isolated fixture refuses non-RPC commands")
    method = arguments[2]
    allowed = {"sessions.list", "agents.list", "chat.history", "chat.send", "agent.wait"}
    if method not in allowed:
        raise SystemExit("Isolated fixture refuses this RPC")
    params = json.loads(arguments[arguments.index("--params") + 1]) if "--params" in arguments else {}
    state = Path.home() / "fixture"
    with (state / "calls.jsonl").open("a", encoding="utf-8") as output:
        output.write(json.dumps({"method": method, "params": params}) + "\n")
    row = {"key": "agent:fixture:upgrade", "sessionId": "fixture-session",
           "derivedTitle": "Isolated upgrade proof", "activeLeafEntryId": "fixture-leaf",
           "hasActiveRun": False, "updatedAt": int(time.time() * 1000)}
    if method == "sessions.list":
        reply = {"sessions": [row], "hasMore": False}
    elif method == "agents.list":
        reply = {"agents": [{"id": "fixture", "name": "Fixture"}]}
    elif method == "chat.history":
        reply = {"sessionKey": row["key"], "sessionId": row["sessionId"],
                 "sessionInfo": row, "messages": [{"id": "saved", "role": "assistant",
                 "content": "Saved fixture history."}], "hasMore": False}
    elif method == "chat.send":
        reply = {"runId": params["idempotencyKey"], "status": "started"}
    else:
        reply = {"runId": params["runId"], "status": "ok", "endedAt": int(time.time() * 1000),
                 "terminalReceipt": {"runId": params["runId"], "sessionId": row["sessionId"]}}
    print(json.dumps(reply))


if __name__ == "__main__":
    main()
