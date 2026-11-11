"""Record real responses from https://mcp.galaxus.ch/ into tests/fixtures/.

Run by hand (needs network):  py tests/record_fixtures.py
Each file holds one raw HTTP exchange: {"status", "headers", "body"}.
"""
import json
import pathlib
import urllib.error
import urllib.request

URL = "https://mcp.galaxus.ch/"
OUT = pathlib.Path(__file__).parent / "fixtures"
ACCEPT = "application/json, text/event-stream"
PROTOCOL = "2025-06-18"


def exchange(payload, headers):
    req = urllib.request.Request(
        URL, json.dumps(payload).encode("utf-8"),
        {"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status, hdrs, body = r.status, r.headers, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        status, hdrs, body = e.code, e.headers, e.read().decode("utf-8")
    return {"status": status, "headers": {k.lower(): v for k, v in hdrs.items()}, "body": body}


def call(query, **args):
    arguments = {"query": query, "agentInfo": "galaxus-skill/fixture-recorder", "language": "en", **args}
    return {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "search_products", "arguments": arguments}}


def main():
    OUT.mkdir(exist_ok=True)
    init = exchange({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": PROTOCOL, "capabilities": {},
                                "clientInfo": {"name": "galaxus-skill", "version": "fixture-recorder"}}},
                    {"Accept": ACCEPT})
    sid = init["headers"]["mcp-session-id"]
    session = {"Accept": ACCEPT, "Mcp-Session-Id": sid, "MCP-Protocol-Version": PROTOCOL}
    records = {
        "init": init,
        "initialized": exchange({"jsonrpc": "2.0", "method": "notifications/initialized"}, session),
        "success": exchange(call("Redmi 17", first=3), session),
        "is_error": exchange(call("Redmi 17", minPrice=5, maxPrice=2), session),
        "error_message": exchange(call("x", first=1), session),
        "http_400_no_session": exchange(call("Redmi 17", first=1), {"Accept": ACCEPT}),
        "http_406_bad_accept": exchange(call("Redmi 17", first=1),
                                        {"Mcp-Session-Id": sid, "MCP-Protocol-Version": PROTOCOL}),
    }
    for name, rec in records.items():
        (OUT / f"{name}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        print(name, rec["status"], rec["headers"].get("content-type"))


if __name__ == "__main__":
    main()
