"""HTTP transport for the Galaxus MCP endpoint (stdlib only).

Contract (probed 2026-11-11): POST-only root path; responses are SSE;
`Mcp-Session-Id` is required after initialize but not validated; tool
results carry JSON text in result.content[0].text; invalid input comes back
as an isError result, not as a JSON-RPC error.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

URL = "https://mcp.galaxus.ch/"
PROTOCOL_VERSION = "2025-06-18"
TIMEOUT_S = 30
CALL_DELAY_S = 0.2
BACKOFF_S = (1, 4)
ACCEPT = "application/json, text/event-stream"


class TransportError(Exception):
    """The endpoint could not be reached, or kept failing after retries."""


class ToolInputError(Exception):
    """The server rejected the tool input (isError result or JSON-RPC error)."""


def parse_sse(body: str) -> list[dict]:
    messages, data = [], []
    for line in body.splitlines():
        if line.startswith("data:"):
            value = line[5:]
            data.append(value[1:] if value.startswith(" ") else value)
        elif line == "" and data:
            messages.append(json.loads("\n".join(data)))
            data = []
    if data:
        messages.append(json.loads("\n".join(data)))
    return messages


def parse_body(content_type: str | None, body: str) -> list[dict]:
    if not body.strip():
        return []
    if content_type and "text/event-stream" in content_type:
        return parse_sse(body)
    return [json.loads(body)]


def _retry_after(headers, default: float) -> float:
    value = headers.get("Retry-After") if headers is not None else None
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _error_text(err: urllib.error.HTTPError) -> str:
    try:
        return err.read().decode("utf-8", "replace")[:300]
    except Exception:  # body may be unreadable; the status code is enough
        return ""


class Client:
    def __init__(self, agent_info: str, url: str = URL, opener=urllib.request.urlopen, sleep=time.sleep):
        self.agent_info = agent_info
        self.url = url
        self._open = opener
        self._sleep = sleep
        self.session_id: str | None = None
        self.calls = 0
        self._last_id = 0

    def _next_id(self) -> int:
        self._last_id += 1
        return self._last_id

    def _request(self, payload: dict) -> tuple[dict, str]:
        headers = {"Content-Type": "application/json", "Accept": ACCEPT}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
            headers["MCP-Protocol-Version"] = PROTOCOL_VERSION
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode("utf-8"),
                                     headers=headers, method="POST")
        resp = self._open(req, timeout=TIMEOUT_S)
        try:
            body = resp.read().decode("utf-8")
            lowered = {k.lower(): v for k, v in resp.headers.items()}
        finally:
            resp.close()
        return lowered, body

    def _send(self, payload: dict, allow_reinit: bool = True) -> tuple[dict, list[dict]]:
        failures = throttles = 0
        reinitialised = not allow_reinit
        while True:
            try:
                headers, body = self._request(payload)
                return headers, parse_body(headers.get("content-type"), body)
            except urllib.error.HTTPError as err:
                if err.code == 429 and throttles < len(BACKOFF_S):
                    self._sleep(_retry_after(err.headers, BACKOFF_S[throttles]))
                    throttles += 1
                    continue
                if err.code >= 500 and failures < len(BACKOFF_S):
                    self._sleep(BACKOFF_S[failures])
                    failures += 1
                    continue
                if err.code in (400, 404) and not reinitialised:
                    reinitialised = True
                    self.initialize()
                    continue
                raise TransportError(f"HTTP {err.code}: {_error_text(err)}") from err
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as err:
                if failures < len(BACKOFF_S):
                    self._sleep(BACKOFF_S[failures])
                    failures += 1
                    continue
                raise TransportError(f"network error: {err}") from err

    def initialize(self) -> None:
        self.session_id = None
        version = self.agent_info.rsplit("/", 1)[-1]
        headers, _ = self._send({
            "jsonrpc": "2.0", "id": self._next_id(), "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                       "clientInfo": {"name": "galaxus-skill", "version": version}},
        }, allow_reinit=False)
        session = headers.get("mcp-session-id")
        if not session:
            raise TransportError("initialize returned no Mcp-Session-Id header")
        self.session_id = session
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"}, allow_reinit=False)

    def search_products(self, query: str, language: str, first: int = 50,
                        min_price: int | None = None, max_price: int | None = None) -> dict:
        if self.session_id is None:
            self.initialize()
        if self.calls:
            self._sleep(CALL_DELAY_S)
        args = {"query": query, "agentInfo": self.agent_info, "language": language, "first": first}
        if min_price is not None:
            args["minPrice"] = min_price
        if max_price is not None:
            args["maxPrice"] = max_price
        rid = self._next_id()
        _, messages = self._send({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                                  "params": {"name": "search_products", "arguments": args}})
        self.calls += 1
        msg = next((m for m in messages if m.get("id") == rid), None)
        if msg is None:
            raise TransportError("no JSON-RPC response for the tool call")
        if "error" in msg:
            raise ToolInputError(msg["error"].get("message", str(msg["error"])))
        result = msg.get("result") or {}
        text = "".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
        if result.get("isError"):
            raise ToolInputError(text)
        return {"payload": json.loads(text), "meta": result.get("_meta")}
