"""Bounded cleanup for HTTP bodies rejected before application parsing."""

import time
from http.server import BaseHTTPRequestHandler


def discard_rejected_body(handler: BaseHTTPRequestHandler) -> None:
    # An unread upload can reset the connection before the peer receives even
    # framed response headers. Never let rejected input hold the service open.
    try:
        remaining = min(max(int(handler.headers.get("Content-Length", "0")), 0), 96_001)
    except ValueError:
        return
    if not remaining:
        return
    previous_timeout = handler.connection.gettimeout()
    try:
        deadline = time.monotonic() + 0.5
        while remaining:
            budget = deadline - time.monotonic()
            if budget <= 0:
                break
            handler.connection.settimeout(budget)
            chunk = handler.rfile.read1(remaining)
            if not chunk:
                break
            remaining -= len(chunk)
    except OSError:
        pass
    finally:
        handler.connection.settimeout(previous_timeout)
