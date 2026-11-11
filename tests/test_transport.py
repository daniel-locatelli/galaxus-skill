import email.message
import io
import json
import urllib.error
from pathlib import Path

import pytest

from galaxus_lib import transport

FIX = Path(__file__).parent / "fixtures"


def rec(name):
    return json.loads((FIX / f"{name}.json").read_text("utf-8"))


def synthetic(status, body="", headers=None):
    return {"status": status, "headers": headers or {"content-type": "application/json"}, "body": body}


class FakeResponse:
    def __init__(self, r):
        self.status = r["status"]
        self.headers = r["headers"]
        self._body = r["body"].encode("utf-8")

    def read(self):
        return self._body

    def close(self):
        pass


class FakeOpener:
    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def __call__(self, req, timeout):
        self.requests.append(req)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if item["status"] >= 400:
            hdrs = email.message.Message()
            for k, v in item["headers"].items():
                hdrs[k] = v
            raise urllib.error.HTTPError(req.full_url, item["status"], "error", hdrs,
                                         io.BytesIO(item["body"].encode("utf-8")))
        return FakeResponse(item)

    def bodies(self):
        return [json.loads(r.data) for r in self.requests]


def client(script):
    sleeps = []
    opener = FakeOpener(script)
    return transport.Client("galaxus-skill/test", opener=opener, sleep=sleeps.append), opener, sleeps


HANDSHAKE = ["init", "initialized"]


def test_parse_sse_joins_data_lines_and_splits_events():
    body = 'event: message\ndata: {"a":\ndata: 1}\n\nevent: message\ndata: {"b":2}\n\n'
    assert transport.parse_sse(body) == [{"a": 1}, {"b": 2}]


def test_parse_body_by_content_type():
    assert transport.parse_body("application/json", '{"x": 1}') == [{"x": 1}]
    assert transport.parse_body("text/event-stream", 'data: {"x": 2}\n\n') == [{"x": 2}]
    assert transport.parse_body(None, "") == []


def test_initialize_handshake_sets_session_and_headers():
    c, op, _ = client([rec(n) for n in HANDSHAKE])
    c.initialize()
    assert c.session_id == rec("init")["headers"]["mcp-session-id"]
    first, second = op.requests
    assert first.get_header("Accept") == "application/json, text/event-stream"
    assert first.get_header("Mcp-session-id") is None
    assert second.get_header("Mcp-session-id") == c.session_id
    assert second.get_header("Mcp-protocol-version") == "2025-06-18"
    assert op.bodies()[1]["method"] == "notifications/initialized"


def test_search_success_returns_payload_and_meta():
    c, op, _ = client([rec(n) for n in HANDSHAKE + ["success"]])
    out = c.search_products("Redmi 17", "en", first=3)
    assert out["payload"]["totalCount"] > 0
    assert 1 <= len(out["payload"]["products"]) <= 3
    assert isinstance(out["meta"], dict)
    args = op.bodies()[2]["params"]["arguments"]
    assert args == {"query": "Redmi 17", "agentInfo": "galaxus-skill/test", "language": "en", "first": 3}


def test_is_error_raises_tool_input_error():
    c, _, _ = client([rec(n) for n in HANDSHAKE + ["is_error"]])
    with pytest.raises(transport.ToolInputError, match="Invalid price range"):
        c.search_products("Redmi 17", "en", min_price=5, max_price=2)


def test_error_message_is_passed_through():
    c, _, _ = client([rec(n) for n in HANDSHAKE + ["error_message"]])
    out = c.search_products("x", "en", first=1)
    assert out["payload"]["errorMessage"].startswith("The request failed")
    assert out["payload"]["totalCount"] == 0


def test_missing_session_reinitialises_once():
    script = [rec(n) for n in HANDSHAKE + ["http_400_no_session"] + HANDSHAKE + ["success"]]
    c, op, _ = client(script)
    assert c.search_products("Redmi 17", "en")["payload"]["totalCount"] > 0
    assert [b.get("method") for b in op.bodies()].count("initialize") == 2


def test_second_400_raises():
    script = [rec(n) for n in HANDSHAKE + ["http_400_no_session"] + HANDSHAKE + ["http_400_no_session"]]
    c, _, _ = client(script)
    with pytest.raises(transport.TransportError, match="HTTP 400"):
        c.search_products("Redmi 17", "en")


def test_406_raises_without_retry():
    c, op, _ = client([rec(n) for n in HANDSHAKE + ["http_406_bad_accept"]])
    status = rec("http_406_bad_accept")["status"]
    with pytest.raises(transport.TransportError, match=f"HTTP {status}"):
        c.search_products("Redmi 17", "en")
    assert len(op.requests) == 3


def test_5xx_retries_twice_with_backoff():
    c, _, sleeps = client([rec(n) for n in HANDSHAKE] + [synthetic(503), synthetic(503), rec("success")])
    c.search_products("Redmi 17", "en")
    assert sleeps == [1, 4]
    c2, _, _ = client([rec(n) for n in HANDSHAKE] + [synthetic(503)] * 3)
    with pytest.raises(transport.TransportError, match="HTTP 503"):
        c2.search_products("Redmi 17", "en")


def test_429_honours_retry_after():
    throttled = synthetic(429, headers={"content-type": "text/plain", "retry-after": "7"})
    c, _, sleeps = client([rec(n) for n in HANDSHAKE] + [throttled, rec("success")])
    c.search_products("Redmi 17", "en")
    assert sleeps == [7.0]


@pytest.mark.parametrize("value,expected", [("120", 30.0), ("-5", 0.0), ("30", 30.0), ("2.5", 2.5)])
def test_retry_after_is_clamped_to_0_30(value, expected):
    throttled = synthetic(429, headers={"content-type": "text/plain", "retry-after": value})
    c, _, sleeps = client([rec(n) for n in HANDSHAKE] + [throttled, rec("success")])
    c.search_products("Redmi 17", "en")
    assert sleeps == [expected]


def test_network_error_retries_then_raises():
    down = urllib.error.URLError("connection refused")
    c, _, sleeps = client([rec(n) for n in HANDSHAKE] + [down, down, rec("success")])
    c.search_products("Redmi 17", "en")
    assert sleeps == [1, 4]
    c2, _, _ = client([down, down, down])
    with pytest.raises(transport.TransportError, match="network error"):
        c2.initialize()


def test_delay_between_tool_calls():
    second = rec("success")
    second["body"] = second["body"].replace('"id":2', '"id":3')  # fixture was recorded as call id 2
    c, _, sleeps = client([rec(n) for n in HANDSHAKE + ["success"]] + [second])
    c.search_products("Redmi 17", "en")
    c.search_products("Redmi 17", "en")
    assert sleeps == [0.2]
    assert c.calls == 2


def sse_result(rid, text):
    msg = {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": text}]}}
    return {"status": 200, "headers": {"content-type": "text/event-stream"},
            "body": "event: message\ndata: " + json.dumps(msg) + "\n\n"}


def test_invalid_json_in_sse_raises_transport_error():
    bad = {"status": 200, "headers": {"content-type": "text/event-stream"}, "body": "data: {not json\n\n"}
    c, _, _ = client([rec(n) for n in HANDSHAKE] + [bad])
    with pytest.raises(transport.TransportError, match="malformed"):
        c.search_products("x", "en")


def test_non_utf8_body_raises_transport_error():
    class BadResponse(FakeResponse):
        def read(self):
            return b"\xff\xfe\xfa"

    class Op(FakeOpener):
        def __call__(self, req, timeout):
            item = self.script[0]
            if isinstance(item, dict) and item.get("bad"):
                self.script.pop(0)
                self.requests.append(req)
                return BadResponse(item)
            return super().__call__(req, timeout)

    op = Op([rec(n) for n in HANDSHAKE] + [dict(synthetic(200), bad=True)])
    c = transport.Client("galaxus-skill/test", opener=op, sleep=lambda s: None)
    with pytest.raises(transport.TransportError, match="UTF-8"):
        c.search_products("x", "en")


def test_non_json_tool_text_raises_transport_error():
    c, _, _ = client([rec(n) for n in HANDSHAKE] + [sse_result(2, "not json at all")])
    with pytest.raises(transport.TransportError, match="not JSON"):
        c.search_products("x", "en")


def test_non_dict_message_is_skipped():
    arr = {"status": 200, "headers": {"content-type": "application/json"}, "body": "[1, 2]"}
    c, _, _ = client([rec(n) for n in HANDSHAKE] + [arr])
    with pytest.raises(transport.TransportError, match="no JSON-RPC response"):
        c.search_products("x", "en")


def test_parse_sse_keeps_unicode_line_separators_inside_data():
    body = 'data: {"a": "x y\u0085z"}\n\n'
    assert transport.parse_sse(body) == [{"a": "x y\u0085z"}]
