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
- **Bounded**: a request body size, a number of sessions, an idle time per session and a time per
  request.

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
IDLE_SECONDS = 900
REQUEST_SECONDS = 120
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
        self._buffer = b""
        self._internal = 0

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
                    and message.get("id") == request_id
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
            {"jsonrpc": "2.0", "id": f"bridge-{self._internal}", "method": "tools/list"}, timeout
        )
        tools = (reply or {}).get("result", {}).get("tools", [])
        self.read_only_tools = {
            tool["name"]
            for tool in tools
            if tool.get("annotations", {}).get("readOnlyHint") is True
        }

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


class Bridge(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], token: str, origins: set[str], command: list[str]):
        super().__init__(address, Handler)
        self.token = token
        self.origins = origins
        self.command = command
        self.sessions: dict[str, Session] = {}
        self.sessions_lock = threading.Lock()

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
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._reply(413 if length > MAX_BODY else 400, {"error": "bad body length"}, close=True)
            return
        try:
            message = json.loads(self.rfile.read(length))
        except ValueError:
            self._reply(400, _error(None, -32700, "parse error"))
            return
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            self._reply(400, _error(None, -32600, "one JSON-RPC 2.0 message per request"))
            return
        method, request_id = message.get("method"), message.get("id")
        if method is None:  # a response from the client: this server sends no requests
            self._reply(202)
            return
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
        self._reply(200, reply, {"Mcp-Session-Id": key})

    def _relay(self, session: Session, message: Message) -> None:
        request_id, method = message["id"], message["method"]
        if method == "tools/call":
            session.ensure_tool_list(REQUEST_SECONDS)
            name = (message.get("params") or {}).get("name")
            if name not in (session.read_only_tools or set()):
                self._reply(
                    200, _error(request_id, -32602, f"tool {name!r} is not a read-only tool")
                )
                return
        reply = session.request(message, REQUEST_SECONDS)
        if reply is None:
            self._reply(504, _error(request_id, -32603, "the server did not answer in time"))
            return
        if method == "tools/list" and "result" in reply:
            tools = [
                tool
                for tool in reply["result"].get("tools", [])
                if tool.get("annotations", {}).get("readOnlyHint") is True
            ]
            reply["result"]["tools"] = tools
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
