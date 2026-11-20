"""Serve the read-only ``ops`` MCP server over Streamable HTTP, for clients that cannot run stdio.

ChatGPT connects to remote MCP servers over HTTPS only; Codex, the ChatGPT desktop app and the
OpenAI API can also use an HTTP endpoint. This bridge runs the plugin's own verified launcher
(``ops-mcp``, one process per MCP session) and relays JSON-RPC to it. Standard library only.

It is deliberately narrow:

- **A bearer token is always required**, read from an owner-only file (``--token-file``) and
  compared in constant time. ChatGPT itself authenticates with OAuth, which belongs to the HTTPS
  gateway or tunnel in front of this bridge; that gateway sends this token.
- **Loopback by default** (``127.0.0.1``). A request whose ``Origin`` is not allowed is refused,
  against DNS rebinding.
- **Read-only, enforced here too**: only the protocol's read methods pass, and only tools the
  server itself annotates ``readOnlyHint: true`` are listed or callable.
- **Bounded**: a request body size, a number of sessions, an idle time per session, a time per
  request, a number of open connections and a time to read each request from its socket.
- **Strict about what it relays**: one JSON-RPC 2.0 message per POST, as ``application/json``;
  a string ``method``, an object ``params``, an ``id`` that is a string or an integer (never a
  boolean, a float or null, and never one of the bridge's own); ``initialize`` only as a request;
  the ``MCP-Protocol-Version`` header, when sent, equal to the version the session negotiated.
  Anything else is refused before it reaches the server, and the server's own tool list is read
  defensively: a tool it does not describe as read-only, in the shape the protocol gives, is
  neither listed nor callable.

Usage::

    python3 -I bin/ops_mcp_http.py --init-token ~/.config/apexai-ops/mcp-http.token
    python3 -I bin/ops_mcp_http.py --token-file ~/.config/apexai-ops/mcp-http.token [--port 8765]

The endpoint is ``http://127.0.0.1:8765/mcp``. Diagnostics go to stderr; the token never does.
"""

from __future__ import annotations

import argparse
import hmac
import ipaddress
import json
import os
import secrets
import select
import stat
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

Message = dict[str, Any]
LAUNCHER = Path(__file__).resolve().with_name("ops-mcp")
PATH = "/mcp"
MAX_BODY = 1 << 20
MAX_SESSIONS = 8
MAX_CONNECTIONS = 32
IDLE_SECONDS = 900
REQUEST_SECONDS = 120
SOCKET_SECONDS = 30
INTERNAL_PREFIX = "bridge-"
READ_METHODS = frozenset(
    {
        "initialize",
        "ping",
        "tools/list",
        "tools/call",
        "resources/list",
        "resources/templates/list",
        "resources/read",
        "prompts/list",
        "prompts/get",
        "notifications/initialized",
        "notifications/cancelled",
    }
)


def _log(message: str) -> None:
    print(f"apexai-ops mcp-http: {message}", file=sys.stderr, flush=True)


def read_token(path: Path) -> str:
    """The bearer token, refused unless the file is this account's own and private."""

    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode):
        raise SystemExit(f"apexai-ops mcp-http: {path} is not a regular file")
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise SystemExit(f"apexai-ops mcp-http: {path} must be yours and mode 0600")
    token = path.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise SystemExit(f"apexai-ops mcp-http: the token in {path} is shorter than 32 characters")
    return token


def init_token(path: Path) -> None:
    """Create a new random token file, mode 0600; never overwrite one."""

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(secrets.token_urlsafe(32) + "\n")
    _log(f"created {path} (mode 0600); give its contents to your client or gateway")


class Session:
    """One ``ops-mcp`` process and the read-only tool names it advertised."""

    def __init__(self, command: list[str]) -> None:
        self.process = subprocess.Popen(  # noqa: S603 - the plugin's own launcher, no shell
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0
        )
        self.lock = threading.Lock()
        self.used = time.monotonic()
        self.read_only_tools: set[str] | None = None
        self.protocol_version: str | None = None
        self._buffer = b""
        self._internal = 0
        # The bridge's own request ids: a client may not use the prefix, nor guess the rest.
        self._internal_tag = f"{INTERNAL_PREFIX}{secrets.token_hex(8)}-"

    def send(self, message: Message) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(message).encode() + b"\n")
        self.process.stdin.flush()

    def answer(self, request_id: object, deadline: float) -> Message | None:
        """The child's response to ``request_id``; other lines (its notifications) are dropped."""

        assert self.process.stdout is not None
        while True:
            while b"\n" in self._buffer:
                line, self._buffer = self._buffer.split(b"\n", 1)
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                if (
                    isinstance(message, dict)
                    and _same_id(message.get("id"), request_id)
                    and ("result" in message or "error" in message)
                ):
                    return message
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            ready, _, _ = select.select([self.process.stdout], [], [], remaining)
            if not ready:
                return None
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                return None
            self._buffer += chunk

    def request(self, message: Message, timeout: float) -> Message | None:
        self.send(message)
        return self.answer(message["id"], time.monotonic() + timeout)

    def ensure_tool_list(self, timeout: float) -> None:
        if self.read_only_tools is not None:
            return
        self._internal += 1
        reply = self.request(
            {
                "jsonrpc": "2.0",
                "id": f"{self._internal_tag}{self._internal}",
                "method": "tools/list",
            },
            timeout,
        )
        self.read_only_tools = {tool["name"] for tool in read_only_tools(reply)}

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()


def _error(request_id: object, code: int, message: str) -> Message:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _same_id(answered: object, asked: object) -> bool:
    """The same JSON-RPC id, type and value: ``True`` is not ``1`` and ``1.0`` is not ``1``."""

    return type(answered) is type(asked) and answered == asked


def _valid_id(value: object) -> bool:
    """A request id the bridge relays: a string or an integer, never a boolean or a bridge id."""

    if isinstance(value, str):
        return not value.startswith(INTERNAL_PREFIX)
    return type(value) is int


def read_only_tools(reply: object) -> list[Message]:
    """The tools a ``tools/list`` reply describes as read-only, read defensively.

    A reply, result, tool list, tool or annotation of any other shape than the protocol's
    contributes nothing: what the server does not plainly describe as read-only is not.
    """

    result = reply.get("result") if isinstance(reply, dict) else None
    tools = result.get("tools") if isinstance(result, dict) else None
    if not isinstance(tools, list):
        return []
    return [
        tool
        for tool in tools
        if isinstance(tool, dict)
        and isinstance(tool.get("name"), str)
        and isinstance(tool.get("annotations"), dict)
        and tool["annotations"].get("readOnlyHint") is True
    ]


def _media_type(value: str | None) -> str:
    return (value or "").split(";", 1)[0].strip().lower()


def _accepts_json(value: str | None) -> bool:
    """Whether an ``Accept`` header admits ``application/json`` (absent: anything is accepted)."""

    if value is None:
        return True
    ranges = {_media_type(part) for part in value.split(",")}
    return bool(ranges & {"application/json", "application/*", "*/*"})


def _invalid(message: Message) -> Message | None:
    """The JSON-RPC error for a message the bridge does not relay, or ``None`` for one it may."""

    if "id" in message and not _valid_id(message["id"]):
        return _error(None, -32600, "the id must be a string or an integer")
    answer_id = message.get("id")
    if not isinstance(message.get("method"), str):
        return _error(answer_id, -32600, "the method must be a string")
    if "params" in message and not isinstance(message["params"], dict):
        return _error(answer_id, -32602, "params must be an object")
    method = message["method"]
    if method == "initialize" and "id" not in message:
        return _error(None, -32600, "initialize is a request: it needs an id")
    return None


class Bridge(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], token: str, origins: set[str], command: list[str]):
        super().__init__(address, Handler)
        self.token = token
        self.origins = origins
        self.command = command
        self.sessions: dict[str, Session] = {}
        self.sessions_lock = threading.Lock()
        self._connections = threading.BoundedSemaphore(MAX_CONNECTIONS)

    def process_request(self, request: Any, client_address: Any) -> None:
        """A thread per connection, at most ``MAX_CONNECTIONS``; one more is closed unanswered."""

        if not self._connections.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._connections.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connections.release()

    def reap(self) -> None:
        while True:
            time.sleep(30)
            now = time.monotonic()
            with self.sessions_lock:
                idle = [k for k, s in self.sessions.items() if now - s.used > IDLE_SECONDS]
                for key in idle:
                    self.sessions.pop(key).close()
            for _ in idle:
                _log("closed an idle session")


class Handler(BaseHTTPRequestHandler):
    server: Bridge
    protocol_version = "HTTP/1.1"
    # Each read from the socket, the request line and headers included: a client that stops
    # sending loses its connection instead of holding a thread.
    timeout = SOCKET_SECONDS

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - the base signature
        _log(f"{self.address_string()} {format % args}")

    def _reply(
        self,
        status: int,
        body: Message | None = None,
        headers: dict[str, str] | None = None,
        *,
        close: bool = False,
    ) -> None:
        """Answer; ``close`` when the request body was left unread, so it is never parsed next."""

        data = b"" if body is None else json.dumps(body).encode()
        self.send_response(status)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        if close:
            self.send_header("Connection", "close")
            self.close_connection = True
        if body is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _admitted(self) -> bool:
        if self.path.split("?", 1)[0] != PATH:
            self._reply(404, {"error": "not found"}, close=True)
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in self.server.origins:
            self._reply(403, {"error": "origin not allowed"}, close=True)
            return False
        supplied = self.headers.get("Authorization", "")
        expected = f"Bearer {self.server.token}"
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            self._reply(401, {"error": "unauthorized"}, {"WWW-Authenticate": "Bearer"}, close=True)
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802 - the base handler's naming
        if self._admitted():
            self._reply(405, {"error": "no server-initiated stream"}, {"Allow": "POST, DELETE"})

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._admitted():
            return
        key = self.headers.get("Mcp-Session-Id", "")
        with self.server.sessions_lock:
            session = self.server.sessions.pop(key, None)
        if session is None:
            self._reply(404, {"error": "unknown session"})
            return
        session.close()
        self._reply(204)

    def do_POST(self) -> None:  # noqa: N802
        if not self._admitted():
            return
        declared = (self.headers.get("Content-Length") or "").strip()
        if not (declared.isascii() and declared.isdigit()):
            self._reply(400, {"error": "bad body length"}, close=True)
            return
        length = int(declared)
        if length <= 0 or length > MAX_BODY:
            self._reply(413 if length > MAX_BODY else 400, {"error": "bad body length"}, close=True)
            return
        if _media_type(self.headers.get("Content-Type")) != "application/json":
            self._reply(415, {"error": "the body must be application/json"}, close=True)
            return
        if not _accepts_json(self.headers.get("Accept")):
            self._reply(406, {"error": "the answer is application/json"}, close=True)
            return
        try:
            message = json.loads(self.rfile.read(length))
        except (ValueError, RecursionError):
            self._reply(400, _error(None, -32700, "parse error"))
            return
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            self._reply(400, _error(None, -32600, "one JSON-RPC 2.0 message per request"))
            return
        if "method" not in message:  # a response from the client: this server sends no requests
            self._reply(202)
            return
        refusal = _invalid(message)
        if refusal is not None:
            self._reply(400, refusal)
            return
        method, request_id = message["method"], message.get("id")
        if method not in READ_METHODS:
            if request_id is None:
                self._reply(202)
            else:
                self._reply(200, _error(request_id, -32601, f"{method} is not allowed (read-only)"))
            return
        if method == "initialize":
            self._initialize(message)
            return
        key = self.headers.get("Mcp-Session-Id", "")
        with self.server.sessions_lock:
            session = self.server.sessions.get(key)
        if session is None:
            self._reply(404 if key else 400, {"error": "unknown or missing Mcp-Session-Id"})
            return
        version = self.headers.get("MCP-Protocol-Version")
        if version is not None and version != session.protocol_version:
            self._reply(
                400, _error(request_id, -32600, "MCP-Protocol-Version is not this session's")
            )
            return
        with session.lock:
            session.used = time.monotonic()
            if request_id is None:
                session.send(message)
                self._reply(202)
                return
            self._relay(session, message)

    def _initialize(self, message: Message) -> None:
        with self.server.sessions_lock:
            if len(self.server.sessions) >= MAX_SESSIONS:
                self._reply(503, {"error": "too many sessions"})
                return
            key = secrets.token_urlsafe(24)
            session = Session(self.server.command)
            self.server.sessions[key] = session
        with session.lock:
            reply = session.request(message, REQUEST_SECONDS)
        if reply is None:
            with self.server.sessions_lock:
                self.server.sessions.pop(key, None)
            session.close()
            self._reply(502, _error(message.get("id"), -32603, "the server did not start"))
            return
        result = reply.get("result")
        version = result.get("protocolVersion") if isinstance(result, dict) else None
        session.protocol_version = version if isinstance(version, str) else None
        self._reply(200, reply, {"Mcp-Session-Id": key})

    def _relay(self, session: Session, message: Message) -> None:
        request_id, method = message["id"], message["method"]
        if method == "tools/call":
            session.ensure_tool_list(REQUEST_SECONDS)
            name = message.get("params", {}).get("name")
            if not isinstance(name, str) or name not in (session.read_only_tools or set()):
                self._reply(
                    200, _error(request_id, -32602, f"tool {name!r} is not a read-only tool")
                )
                return
        reply = session.request(message, REQUEST_SECONDS)
        if reply is None:
            self._reply(504, _error(request_id, -32603, "the server did not answer in time"))
            return
        if method == "tools/list" and "result" in reply:
            tools = read_only_tools(reply)
            result = reply["result"] if isinstance(reply["result"], dict) else {}
            reply["result"] = {**result, "tools": tools}
            session.read_only_tools = {tool["name"] for tool in tools}
        self._reply(200, reply)


def _loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ops_mcp_http.py", description="The read-only ops MCP server over Streamable HTTP."
    )
    parser.add_argument("--token-file", type=Path, help="the bearer token file (mode 0600)")
    parser.add_argument("--init-token", type=Path, help="create a new token file and exit")
    parser.add_argument("--host", default="127.0.0.1", help="the address to listen on")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--allow-origin", action="append", default=[], help="an Origin to accept (repeatable)"
    )
    args = parser.parse_args(argv)
    if args.init_token is not None:
        init_token(args.init_token)
        return 0
    if args.token_file is None:
        parser.error("--token-file is required (create one with --init-token)")
    token = read_token(args.token_file)
    if not _loopback(args.host):
        _log(f"listening on {args.host}, not loopback: put TLS and access control in front of it")
    bridge = Bridge((args.host, args.port), token, set(args.allow_origin), [str(LAUNCHER)])
    threading.Thread(target=bridge.reap, daemon=True).start()
    _log(f"serving http://{args.host}:{bridge.server_address[1]}{PATH}")
    try:
        bridge.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        with bridge.sessions_lock:
            for session in bridge.sessions.values():
                session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
