"""Ceviz HTTP ingress: bounded connections, bytes and total receive time."""

import io
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn


MAX_CONNECTIONS = 8
INGRESS_SECONDS = 10
MAX_HEADER_BYTES = 64 * 1024
# A 15s mono 16kbps Watch capture is normally ~30KB before Base64. Leave ample
# encoder/container headroom without accepting arbitrary-sized JSON uploads.
MAX_BODY_BYTES = 1024 * 1024


class RequestReadError(OSError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class _DeadlineSocket(io.RawIOBase):
    def __init__(self, connection):
        self.connection = connection
        self.deadline = time.monotonic() + INGRESS_SECONDS

    def readable(self):
        return True

    def readinto(self, buffer):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise RequestReadError(408, "The request upload timed out. No command was dispatched.")
        # Rejected-body draining may impose an even shorter budget. Incoming
        # bytes never renew either deadline, including during header readline.
        timeout = self.connection.gettimeout()
        self.connection.settimeout(min(remaining, timeout) if timeout is not None else remaining)
        try:
            return self.connection.recv_into(buffer)
        except TimeoutError as exc:
            raise RequestReadError(408, "The request upload timed out. No command was dispatched.") from exc


class _RequestReader(io.BufferedReader):
    header_bytes = 0
    reading_headers = True

    def readline(self, size=-1):
        if not self.reading_headers:
            return super().readline(size)
        remaining = MAX_HEADER_BYTES - self.header_bytes
        data = super().readline(min(size, remaining + 1) if size >= 0 else remaining + 1)
        self.header_bytes += len(data)
        if self.header_bytes > MAX_HEADER_BYTES:
            raise RequestReadError(431, "Request headers are too large.")
        return data


class BoundedHTTPRequestHandler(BaseHTTPRequestHandler):
    timeout = INGRESS_SECONDS

    def setup(self):
        super().setup()
        self.rfile.close()
        self.rfile = _RequestReader(_DeadlineSocket(self.connection))

    def handle_one_request(self):
        self.requestline, self.request_version, self.command = "", "HTTP/1.0", None
        try:
            super().handle_one_request()
        except RequestReadError as exc:
            self.send_input_error(exc)
        except (ConnectionError, socket.timeout):
            self.close_connection = True

    def parse_request(self):
        parsed = super().parse_request()
        self.rfile.reading_headers = False
        self.close_connection = True  # One bounded request owns each connection.
        return parsed

    def send_input_error(self, failure):
        data = json.dumps({"error": str(failure), "code": "invalid_request", "delivery_uncertain": False}).encode()
        self.close_connection = True
        self.connection.settimeout(1)
        try:
            self.send_response(failure.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            pass  # An abandoned peer cannot prevent the worker's release.


class BoundedHTTPServer(ThreadingMixIn, HTTPServer):
    def __init__(self, *args, **kwargs):
        self._connections = threading.BoundedSemaphore(MAX_CONNECTIONS)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._connections.acquire(blocking=False):
            # Do not spawn an unbounded waiting thread or touch application
            # state. The framed refusal has never reached dispatch.
            data = b'{"error":"Ceviz is busy. Try again shortly.","code":"server_busy","delivery_uncertain":false}'
            try:
                request.settimeout(0.5)
                request.sendall(b"HTTP/1.0 503 Service Unavailable\r\nContent-Type: application/json\r\n"
                                b"Connection: close\r\nContent-Length: " + str(len(data)).encode() + b"\r\n\r\n" + data)
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._connections.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connections.release()


def read_request_body(handler, maximum=MAX_BODY_BYTES):
    lengths = handler.headers.get_all("Content-Length", [])
    if handler.headers.get("Transfer-Encoding") or len(lengths) > 1:
        raise RequestReadError(400, "Use one Content-Length and no Transfer-Encoding.")
    value = lengths[0] if lengths else "0"
    if not value.isascii() or not value.isdecimal() or len(value) > 10:
        raise RequestReadError(400, "Invalid request length.")
    length = int(value)
    if length > maximum:
        discard_rejected_body(handler)
        raise RequestReadError(413, "The request body is too large. No command was dispatched.")
    data = handler.rfile.read(length)
    if len(data) != length:
        raise RequestReadError(400, "The request body was incomplete. No command was dispatched.")
    handler.connection.settimeout(INGRESS_SECONDS)
    return data


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
