# Galaxus Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `galaxus` agent skill: a `SKILL.md`, a stdlib-only Python CLI that searches the Galaxus MCP endpoint exhaustively and extracts specs, the reference docs, tests, evals and distribution files.

**Architecture:** `skills/galaxus/scripts/galaxus.py` is the CLI entry point. It puts its own directory on `sys.path` and imports the small `galaxus_lib` package next to it: `transport` (HTTP + SSE + retries), `meta` (the only reader of the undocumented `_meta`), `search` (price-band splitting, coverage), `specs` (extraction), `variants`, `report` (JSON document + text report), `filtering`, `compare`. The search algorithm takes a `fetch(lo, hi, first) -> Page` callable, so tests drive it with a fake catalogue and never touch the network.

**Tech Stack:** Python ≥ 3.10 standard library only (`urllib`, `json`, `re`, `argparse`, `dataclasses`); pytest for tests; GitHub Actions for CI.

**Source of truth:** `docs/superpowers/specs/2026-11-11-galaxus-skill-design.md` (approved, rev 2). Read its "Server contract" before Task 3.

## Global Constraints

- Script: Python ≥ 3.10, **standard library only**. pytest is a dev dependency only.
- Endpoint `https://mcp.galaxus.ch/`, POST only, protocol version `2025-06-18`, headers `Content-Type: application/json`, `Accept: application/json, text/event-stream`, `Mcp-Session-Id` + `MCP-Protocol-Version: 2025-06-18` after initialize.
- `agentInfo` is `galaxus-skill/<version>`. Never send `userIntent`.
- Every search call uses `first: 50` (count-only calls may use `first: 1`).
- Per-request timeout 30 s. Strictly sequential calls, 0.2 s delay between tool calls. 429: honour `Retry-After`, else back off 1 s / 4 s. 5xx / network errors: two retries, backoff 1 s / 4 s. 400/404: re-initialise once.
- Defaults: `--lang en`, `--max-calls 60`, `--top 15`, range `[1, 1000000]`.
- Exit codes: 0 ok (also for "infeasible"), 2 endpoint unreachable at start, 3 invalid input, 4 `errorMessage` or failure mid-run (partial report printed).
- stdout and stderr forced to UTF-8.
- Languages: `en de fr it nl`.
- Version `0.1.0` in `galaxus.py` (`__version__`), `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and the `SKILL.md` frontmatter (`metadata.version`); a test asserts they match.
- Licence MIT. Do not create the GitHub repo or push without Daniel's go-ahead.
- Windows dev machine: run Python as `py` (CI uses `python`). Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Plan decisions beyond the spec (flagged for Daniel)

1. **`filter` subcommand** (`filter --from FILE --where FIELD>=N --type T`). The spec's output rule ("none confirmed among X checked; Y have unknown OS") needs counts over hundreds of products; the agent should not compute them by reading JSON.
2. **`compare --lookup ID=BRAND NAME@PRICE`.** Probed 2026-11-11: searching by bare product id returns 0 results, and an id that is not in FILE has no stored brand, name or price. The spec's lookup "by brand + name within a narrow price band around the stored price" therefore needs those values passed in.
3. **Code split into `galaxus_lib/`** next to `galaxus.py`, so each file has one job. Still stdlib only, still copied as one `skills/galaxus/` folder.
4. **`android_version` field**, stated from "Android N" or inferred from a hand-kept base table (HyperOS 2→15, HyperOS 3→16, One UI 7→15, One UI 8→16).
5. **Budget accounting:** the unfiltered-total call (default range only) and a final re-count call (for the drift note) each cost one call and run only if budget is left.
6. **argparse usage errors exit 3**, not argparse's default 2, because SKILL.md reads exit 2 as "endpoint unreachable".
7. **`.claude-plugin/marketplace.json`** added, so `/plugin marketplace add` works on the repo.
8. **Manual path has no `_meta`.** Checked 2026-11-11 in Claude Code: a `search_products` tool result shows the model only the JSON text (`correctedSearchTerm`, `totalCount`, `products`), so availability and discounts are not available on the manual path.

## File Structure

```
galaxus-skill/
├── .claude-plugin/plugin.json          # plugin manifest (version)
├── .claude-plugin/marketplace.json     # single-plugin marketplace (version)
├── .github/workflows/test.yml          # CI: 3.10/3.13 × ubuntu/windows, offline tests
├── .gitignore
├── LICENSE                             # MIT
├── README.md                           # install + use for Claude Code, claude.ai, others
├── pyproject.toml                      # pytest config only
├── evals/cases.md                      # fixed eval prompts + pass criteria
├── skills/galaxus/
│   ├── SKILL.md                        # trigger, path choice, query rules, output rules
│   ├── references/manual-search.md     # MCP-tool-only procedure
│   ├── references/spec-fields.md       # schemas, states, ceilings, filter semantics
│   ├── references/page-check.md        # browser product-page check
│   └── scripts/
│       ├── galaxus.py                  # CLI entry, __version__, exit codes
│       └── galaxus_lib/
│           ├── __init__.py
│           ├── transport.py            # Client, parse_sse, errors
│           ├── meta.py                 # product_extras(_meta)
│           ├── search.py               # Page, Band, SearchResult, search()
│           ├── specs.py                # Spec, parse_properties, extract_description, extract
│           ├── variants.py             # merge_variants
│           ├── report.py               # build_document, coverage_lines, format_report, format_row
│           ├── filtering.py            # parse_where, run_filter, format_filter_report
│           └── compare.py              # parse_lookup, lookup, comparison_table
└── tests/
    ├── conftest.py                     # puts scripts/ on sys.path
    ├── fakes.py                        # make_product, FakeCatalogue, FakeClient
    ├── record_fixtures.py              # records real responses (run by hand)
    ├── fixtures/*.json                 # recorded real HTTP exchanges
    ├── test_version.py
    ├── test_transport.py
    ├── test_meta.py
    ├── test_search.py
    ├── test_specs.py
    ├── test_report.py
    ├── test_filter_compare.py
    ├── test_cli.py
    └── test_live.py                    # opt-in, GALAXUS_LIVE=1
```

---

### Task 1: Scaffold, version, packaging manifests

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `LICENSE`, `tests/conftest.py`, `tests/test_version.py`, `skills/galaxus/scripts/galaxus.py`, `skills/galaxus/scripts/galaxus_lib/__init__.py`, `skills/galaxus/SKILL.md` (frontmatter stub), `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`

**Interfaces:**
- Produces: `galaxus.__version__ == "0.1.0"`; `tests/conftest.py` makes `import galaxus` and `import galaxus_lib` work in every test.

- [ ] **Step 1: Write config and the failing version test**

`pyproject.toml`:
```toml
# pytest configuration only; the skill script itself has no dependencies.
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

`.gitignore`:
```
__pycache__/
.pytest_cache/
*.pyc
*.tmp
```

`tests/conftest.py`:
```python
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "galaxus" / "scripts"
sys.path.insert(0, str(SCRIPTS))
```

`tests/test_version.py`:
```python
import json
import re
from pathlib import Path

import galaxus

ROOT = Path(__file__).resolve().parents[1]


def test_versions_match():
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text("utf-8"))
    skill = (ROOT / "skills" / "galaxus" / "SKILL.md").read_text("utf-8")
    m = re.search(r'^  version: "([^"]+)"$', skill, re.M)
    assert m, "SKILL.md frontmatter needs metadata.version"
    assert galaxus.__version__ == plugin["version"] == market["plugins"][0]["version"] == m.group(1)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `py -m pytest tests/test_version.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'galaxus'`.

- [ ] **Step 3: Write the minimal files**

`skills/galaxus/scripts/galaxus_lib/__init__.py`:
```python
"""Library modules for galaxus.py (stdlib only)."""
```

`skills/galaxus/scripts/galaxus.py` (Task 10 replaces it with the full CLI):
```python
#!/usr/bin/env python3
"""Exhaustive product search on Galaxus (galaxus.ch) through its public MCP endpoint."""
from __future__ import annotations

import argparse
import sys

__version__ = "0.1.0"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="galaxus.py")
    parser.add_argument("--version", action="version", version=f"galaxus-skill {__version__}")
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`skills/galaxus/SKILL.md` (Task 12 writes the body):
```markdown
---
name: galaxus
description: Use when the user wants to search, filter, compare or price products sold on Galaxus (galaxus.ch), or asks for a thorough product search in CHF on the Swiss Galaxus shop. Not for general buying advice without Galaxus, other shops, or non-Swiss markets.
license: MIT
metadata:
  version: "0.1.0"
---

# Galaxus product search
```

`.claude-plugin/plugin.json`:
```json
{
  "name": "galaxus",
  "version": "0.1.0",
  "description": "Exhaustive Galaxus (galaxus.ch) product search with coverage reporting and spec extraction, via the official Galaxus MCP endpoint.",
  "author": { "name": "Daniel Locatelli" },
  "license": "MIT",
  "repository": "https://github.com/daniel-locatelli/galaxus-skill",
  "keywords": ["galaxus", "shopping", "switzerland", "mcp", "skill"]
}
```

`.claude-plugin/marketplace.json`:
```json
{
  "name": "galaxus-skill",
  "owner": { "name": "Daniel Locatelli" },
  "plugins": [
    {
      "name": "galaxus",
      "source": "./",
      "description": "Exhaustive Galaxus product search with coverage reporting and spec extraction.",
      "version": "0.1.0"
    }
  ]
}
```

`LICENSE`: the standard MIT licence text, first line `MIT License`, then `Copyright (c) 2026 Daniel Locatelli`, then the usual two paragraphs ("Permission is hereby granted, free of charge, …" and "THE SOFTWARE IS PROVIDED "AS IS", …") verbatim from https://opensource.org/license/mit.

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_version.py && py skills/galaxus/scripts/galaxus.py --version`
Expected: `1 passed`, then `galaxus-skill 0.1.0`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore LICENSE tests/conftest.py tests/test_version.py skills .claude-plugin
git commit -m "Scaffold galaxus skill package and version check"
```

---

### Task 2: Record real fixtures

**Files:**
- Create: `tests/record_fixtures.py`, `tests/fixtures/{init,initialized,success,is_error,error_message,http_400_no_session,http_406_bad_accept}.json`

**Interfaces:**
- Produces: each fixture is `{"status": int, "headers": {lowercase-name: value}, "body": str}` (raw HTTP body, SSE text for 200s). Task 3 replays them.

- [ ] **Step 1: Write the recorder**

`tests/record_fixtures.py`:
```python
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
```

- [ ] **Step 2: Record**

Run: `py tests/record_fixtures.py`
Expected (one line each):
```
init 200 text/event-stream
initialized 202 ...
success 200 text/event-stream
is_error 200 text/event-stream
error_message 200 text/event-stream
http_400_no_session 400 application/json; charset=utf-8
http_406_bad_accept 406 ...
```
Then check content: `success.json` body contains `"totalCount"`; `is_error.json` contains `Invalid price range`; `error_message.json` contains `errorMessage` (a single-character query produced it on 2026-11-11); `http_400_no_session.json` contains `Session ID required`. If `http_406_bad_accept` is not 406, write down the status it gave and use that status in Task 3's 406 test (the test name stays).

- [ ] **Step 3: Commit**

```bash
git add tests/record_fixtures.py tests/fixtures
git commit -m "Record real Galaxus MCP fixtures"
```

---

### Task 3: Transport

**Files:**
- Create: `skills/galaxus/scripts/galaxus_lib/transport.py`
- Test: `tests/test_transport.py`

**Interfaces:**
- Produces:
  - `class TransportError(Exception)`, `class ToolInputError(Exception)`
  - `parse_sse(body: str) -> list[dict]`, `parse_body(content_type: str | None, body: str) -> list[dict]`
  - `Client(agent_info: str, url: str = URL, opener=urllib.request.urlopen, sleep=time.sleep)` with `.initialize() -> None`, `.search_products(query: str, language: str, first: int = 50, min_price: int | None = None, max_price: int | None = None) -> {"payload": dict, "meta": dict | None}`, attributes `.session_id`, `.calls`.

- [ ] **Step 1: Write the failing tests**

`tests/test_transport.py`:
```python
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


def test_network_error_retries_then_raises():
    down = urllib.error.URLError("connection refused")
    c, _, sleeps = client([rec(n) for n in HANDSHAKE] + [down, down, rec("success")])
    c.search_products("Redmi 17", "en")
    assert sleeps == [1, 4]
    c2, _, _ = client([down, down, down])
    with pytest.raises(transport.TransportError, match="network error"):
        c2.initialize()


def test_delay_between_tool_calls():
    c, _, sleeps = client([rec(n) for n in HANDSHAKE + ["success", "success"]])
    c.search_products("Redmi 17", "en")
    c.search_products("Redmi 17", "en")
    assert sleeps == [0.2]
    assert c.calls == 2
```

- [ ] **Step 2: Run them to verify they fail**

Run: `py -m pytest tests/test_transport.py`
Expected: FAIL, `ImportError: cannot import name 'transport'`.

- [ ] **Step 3: Implement**

`skills/galaxus/scripts/galaxus_lib/transport.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_transport.py`
Expected: `13 passed`.

- [ ] **Step 5: Commit**

```bash
git add skills/galaxus/scripts/galaxus_lib/transport.py tests/test_transport.py
git commit -m "Add MCP transport with SSE parsing and retries"
```

---

### Task 4: `_meta` accessor

**Files:**
- Create: `skills/galaxus/scripts/galaxus_lib/meta.py`
- Test: `tests/test_meta.py`

**Interfaces:**
- Consumes: `Client.search_products(...)["meta"]` (Task 3).
- Produces: `product_extras(meta: dict | None) -> dict[int, {"availability": str | None, "labels": list[str], "insteadOf": {"type": str, "rebate": float, "price": float} | None}]`, keyed by product id (`trackingId`).

- [ ] **Step 1: Write the failing tests**

`tests/test_meta.py`:
```python
import json
from pathlib import Path

from galaxus_lib import meta, transport

FIX = Path(__file__).parent / "fixtures"

SAMPLE = {"response": {"data": {"serverToolShopSearch": {"products": {"edges": [
    {"node": {"trackingId": 73036751, "labels": ["DISCOUNT"],
              "insteadOfPrice": {"type": "SALES_PRICE_BEFORE", "rebate": 8, "price": {"amountInclusive": 178}},
              "availability": {"availabilityClassification": "TICK", "id": "x"}}},
    {"node": {"trackingId": 2, "labels": None, "insteadOfPrice": None, "availability": None}},
]}}}}}


def test_extracts_availability_labels_and_discount():
    assert meta.product_extras(SAMPLE) == {
        73036751: {"availability": "TICK", "labels": ["DISCOUNT"],
                   "insteadOf": {"type": "SALES_PRICE_BEFORE", "rebate": 8, "price": 178}},
        2: {"availability": None, "labels": [], "insteadOf": None},
    }


def test_missing_or_changed_meta_degrades_to_empty():
    assert meta.product_extras(None) == {}
    assert meta.product_extras({}) == {}
    assert meta.product_extras({"response": {"data": None}}) == {}


def test_real_fixture_covers_every_product():
    body = json.loads((FIX / "success.json").read_text("utf-8"))["body"]
    result = transport.parse_sse(body)[-1]["result"]
    payload = json.loads(result["content"][0]["text"])
    extras = meta.product_extras(result["_meta"])
    assert {p["id"] for p in payload["products"]} <= set(extras)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `py -m pytest tests/test_meta.py`
Expected: FAIL, `ImportError: cannot import name 'meta'`.

- [ ] **Step 3: Implement**

`skills/galaxus/scripts/galaxus_lib/meta.py`:
```python
"""The only reader of the undocumented `result._meta` payload.

`_meta` repeats the raw GraphQL response. It is undocumented and may vanish;
every accessor degrades to "not available". Only enum-like fields are read,
so the mis-encoded strings seen in `_meta` (e.g. "Â ") do not matter here.
"""
from __future__ import annotations


def product_extras(meta: dict | None) -> dict[int, dict]:
    try:
        edges = meta["response"]["data"]["serverToolShopSearch"]["products"]["edges"]
    except (KeyError, TypeError):
        return {}
    out: dict[int, dict] = {}
    for edge in edges or []:
        node = (edge or {}).get("node") or {}
        pid = node.get("trackingId")
        if pid is None:
            continue
        availability = (node.get("availability") or {}).get("availabilityClassification")
        instead = node.get("insteadOfPrice")
        instead_of = None
        if instead:
            instead_of = {"type": instead.get("type"), "rebate": instead.get("rebate"),
                          "price": (instead.get("price") or {}).get("amountInclusive")}
        out[pid] = {"availability": availability, "labels": list(node.get("labels") or []),
                    "insteadOf": instead_of}
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_meta.py`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add skills/galaxus/scripts/galaxus_lib/meta.py tests/test_meta.py
git commit -m "Add _meta accessor for availability and discounts"
```

---

### Task 5: Exhaustive search algorithm

**Files:**
- Create: `skills/galaxus/scripts/galaxus_lib/search.py`, `tests/fakes.py`
- Test: `tests/test_search.py`

**Interfaces:**
- Produces:
  - `Page(total: int, products: list[dict], corrected: str | None = None, error: str | None = None, extras: dict = {})`
  - `Band(lo: int, hi: int, count: int | None, status: str)`, status ∈ `complete | capped | drifted | uncovered | histogram`
  - `SearchResult` fields: `lo, hi, max_calls, status` (`running | complete | partial | infeasible | failed`), `root_total, final_total, unfiltered_total, corrected, calls, estimated_calls, error, bands: list[Band], histogram: list[Band], products: dict[int, dict], extras: dict[int, dict]`
  - `class SearchFailed(Exception)` with `.partial: SearchResult`
  - `split_point(lo: int, hi: int, products: list[dict]) -> int`
  - `search(fetch, lo=1, hi=1_000_000, max_calls=60, on_update=None) -> SearchResult`, where `fetch(lo: int | None, hi: int | None, first: int) -> Page`. Errors from the root call propagate unchanged; any later error becomes `SearchFailed`.
  - `tests/fakes.py`: `make_product(pid, price, name=None, ptype="Smartphones", brand="Acme", description=None, properties="")`, `FakeCatalogue(products, seed=0, order="shuffle", error_on_call=None, raise_on_call=None, drift=None, priceless=())` (callable as `fetch`, records `.calls`), `FakeClient(catalogue)` with `search_products(query, language, first=50, min_price=None, max_price=None)`.

- [ ] **Step 1: Write the fakes and failing tests**

`tests/fakes.py`:
```python
"""Simulated Galaxus catalogue for offline tests."""
import random

from galaxus_lib.search import Page

ERROR_TEXT = "The request failed unexpectedly. No products are returned. Please try again later."


def make_product(pid, price, name=None, ptype="Smartphones", brand="Acme", description=None, properties=""):
    return {
        "id": pid,
        "name": name or f"Phone {pid}",
        "brand": brand,
        "productType": ptype,
        "description": description if description is not None else f"Phone {pid}.",
        "properties": properties,
        "priceIfAvailable": None if price is None else {"amountInclusive": price, "currency": "CHF"},
        "pageUrl": f"https://www.galaxus.ch/en/s1/product/{pid}",
        "ratingSummaryIfAvailable": None,
    }


class FakeCatalogue:
    """Callable like search.Fetch. Bounds are inclusive and compare the real (cent) price."""

    def __init__(self, products, seed=0, order="shuffle", error_on_call=None, raise_on_call=None,
                 drift=None, priceless=()):
        self.products = list(products)
        self.priceless = list(priceless)
        self.rng = random.Random(seed)
        self.order = order
        self.error_on_call = error_on_call
        self.raise_on_call = raise_on_call
        self.drift = dict(drift or {})
        self.calls = []

    def __call__(self, lo, hi, first):
        self.calls.append((lo, hi, first))
        n = len(self.calls)
        if n == self.raise_on_call:
            raise RuntimeError("connection reset")
        if n == self.error_on_call:
            return Page(total=0, products=[], error=ERROR_TEXT)
        if lo is None and hi is None:
            hits = self.products + self.priceless
        else:
            a = 1 if lo is None else lo
            b = 1_000_000 if hi is None else hi
            hits = [p for p in self.products
                    if p["priceIfAvailable"] and a <= p["priceIfAvailable"]["amountInclusive"] <= b]
        if self.order == "asc":
            hits = sorted(hits, key=lambda p: (p["priceIfAvailable"] or {}).get("amountInclusive", 0))
        else:
            hits = self.rng.sample(hits, len(hits))
        total = len(hits) + self.drift.pop((lo, hi), 0)
        return Page(total=total, products=hits[:first])


class FakeClient:
    """Stands in for transport.Client in CLI tests."""

    def __init__(self, catalogue):
        self.catalogue = catalogue

    def search_products(self, query, language, first=50, min_price=None, max_price=None):
        page = self.catalogue(min_price, max_price, first)
        payload = {"correctedSearchTerm": None, "totalCount": page.total, "products": page.products}
        if page.error:
            payload["errorMessage"] = page.error
        return {"payload": payload, "meta": None}
```

`tests/test_search.py`:
```python
import random

import pytest

from fakes import FakeCatalogue, make_product
from galaxus_lib.search import Page, SearchFailed, search, split_point


def catalogue(prices, **kw):
    return FakeCatalogue([make_product(i, p) for i, p in enumerate(prices, 1)], **kw)


def test_small_band_is_complete_in_one_band_call():
    fake = catalogue([10.0 + i for i in range(30)])
    res = search(fake, lo=1, hi=1000)
    assert res.status == "complete"
    assert len(res.products) == 30
    assert [b.status for b in res.bands] == ["complete"]


def test_cent_prices_between_integers_are_not_lost():
    fake = catalogue([round(100 + i * 0.37, 2) for i in range(300)], seed=3)
    res = search(fake)
    assert res.status == "complete"
    assert len(res.products) == 300


def test_children_share_the_split_endpoint():
    fake = catalogue([float(p) for p in range(1, 121)], order="asc")
    search(fake, lo=1, hi=1000)
    (_, _, _), (a1, b1, _), (a2, b2, _) = fake.calls[:3]
    assert a1 == 1 and b1 == a2 and b2 == 1000


def test_coverage_counts_unique_ids_not_band_sums():
    fake = catalogue([float(p) for p in range(1, 101)], order="asc")
    res = search(fake, lo=1, hi=1000)
    assert res.status == "complete"
    assert len(res.products) == 100
    assert sum(b.count for b in res.bands) > 100  # shared endpoints double-count


def test_more_than_50_at_one_price_is_capped():
    prices = [163.0] * 165 + [100.0 + i for i in range(40)]
    res = search(catalogue(prices))
    assert res.status == "partial"
    capped = [b for b in res.bands if b.status == "capped"]
    assert capped and all(b.hi - b.lo <= 1 and b.lo <= 163 <= b.hi for b in capped)
    others = {i for i, p in enumerate(prices, 1) if p != 163.0}
    assert others <= set(res.products)


def test_budget_leaves_uncovered_bands():
    fake = catalogue([float(p) for p in range(1, 281)], order="asc")
    res = search(fake, max_calls=12)
    assert res.estimated_calls <= 12  # the gate did not fire
    assert res.status == "partial"
    assert res.calls == 12
    assert any(b.status == "uncovered" for b in res.bands)


def test_drift_in_wide_band_is_split_again():
    fake = catalogue([10.0 + i for i in range(30)], drift={(1, 1000): 1})
    res = search(fake, lo=1, hi=1000)
    assert res.status == "complete"
    assert len(res.products) == 30
    assert res.calls >= 3


def test_drift_in_narrow_band_is_marked_drifted():
    fake = catalogue([5.0] * 30, drift={(5, 6): 1})
    res = search(fake, lo=5, hi=6)
    assert res.status == "partial"
    assert [b.status for b in res.bands] == ["drifted"]


def test_feasibility_gate_returns_histogram():
    calls = []

    def huge(lo, hi, first):
        calls.append((lo, hi, first))
        return Page(total=471_800, products=[make_product(i, 100.0 + i) for i in range(50)])

    res = search(huge)
    assert res.status == "infeasible"
    assert res.estimated_calls == 18_872
    assert len(res.histogram) == 8
    assert res.histogram[0].lo == 1 and res.histogram[-1].hi == 1_000_000
    assert res.calls == 9
    assert all(first == 1 for _, _, first in calls[1:])


def test_unfiltered_total_reveals_priceless_products():
    fake = FakeCatalogue([make_product(i, 10.0 + i) for i in range(30)],
                         priceless=[make_product(900 + i, None) for i in range(3)])
    res = search(fake)
    assert res.root_total == 30
    assert res.unfiltered_total == 33


def test_final_recount_records_drift():
    class Growing(FakeCatalogue):
        def __call__(self, lo, hi, first):
            if len(self.calls) == 1:
                self.products.append(make_product(999, 50.0))
            return super().__call__(lo, hi, first)

    res = search(Growing([make_product(i, 10.0 + i) for i in range(30)]), lo=1, hi=1000)
    assert res.root_total == 30
    assert res.final_total == 31


def test_checkpoint_after_every_band_call():
    snapshots = []
    fake = catalogue([float(p) for p in range(1, 121)], order="asc")
    res = search(fake, lo=1, hi=1000, on_update=lambda r: snapshots.append(len(r.products)))
    assert snapshots == sorted(snapshots)
    assert snapshots[-1] == len(res.products) == 120
    assert len(snapshots) >= 3


def test_error_message_mid_run_raises_with_partial():
    fake = catalogue([float(p) for p in range(1, 121)], error_on_call=2)
    with pytest.raises(SearchFailed) as info:
        search(fake, lo=1, hi=1000)
    assert info.value.partial.status == "failed"
    assert len(info.value.partial.products) == 50
    assert "request failed" in info.value.partial.error


def test_exception_mid_run_raises_with_partial():
    fake = catalogue([float(p) for p in range(1, 121)], raise_on_call=2)
    with pytest.raises(SearchFailed) as info:
        search(fake, lo=1, hi=1000)
    assert "connection reset" in info.value.partial.error


def test_error_message_at_root_is_a_failed_search():
    fake = catalogue([10.0], error_on_call=1)
    with pytest.raises(SearchFailed) as info:
        search(fake)
    assert info.value.partial.products == {}


def test_split_point_median_then_geometric_mean():
    prices = [make_product(i, p) for i, p in enumerate([10.0, 20.0, 30.0], 1)]
    assert split_point(1, 1000, prices) == 20
    assert split_point(1, 100, [make_product(1, None)]) == 10
    assert split_point(163, 1000, [make_product(1, 163.0)]) == 164
    assert split_point(1, 163, [make_product(1, 163.0)]) == 162


@pytest.mark.parametrize("seed", range(20))
def test_terminates_on_messy_catalogues(seed):
    rng = random.Random(seed)
    prices = [rng.choice([5.0, 5.5, 99.99, 100.0, 250.0, 999.0]) for _ in range(rng.randint(50, 400))]
    res = search(catalogue(prices, seed=seed), max_calls=500)
    assert res.calls <= 500
    assert res.status in ("complete", "partial")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `py -m pytest tests/test_search.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'galaxus_lib.search'`.

- [ ] **Step 3: Implement**

`skills/galaxus/scripts/galaxus_lib/search.py`:
```python
"""Exhaustive search over price bands. Spec: "Search algorithm".

A band [a, b] holding more than 50 products splits at m into [a, m] and
[m, b]. The shared endpoint keeps products priced between two integers
(193.97) reachable. Coverage counts unique product ids, never band sums.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Callable, Optional

PAGE_SIZE = 50
HISTOGRAM_CALLS = 8
FULL_RANGE = (1, 1_000_000)


@dataclass
class Page:
    total: int
    products: list
    corrected: Optional[str] = None
    error: Optional[str] = None
    extras: dict = field(default_factory=dict)


Fetch = Callable[[Optional[int], Optional[int], int], Page]


@dataclass
class Band:
    lo: int
    hi: int
    count: Optional[int]
    status: str  # complete | capped | drifted | uncovered | histogram


@dataclass
class SearchResult:
    lo: int
    hi: int
    max_calls: int
    status: str = "running"  # running | complete | partial | infeasible | failed
    root_total: int = 0
    final_total: Optional[int] = None
    unfiltered_total: Optional[int] = None
    corrected: Optional[str] = None
    calls: int = 0
    estimated_calls: int = 0
    error: Optional[str] = None
    bands: list = field(default_factory=list)
    histogram: list = field(default_factory=list)
    products: dict = field(default_factory=dict)
    extras: dict = field(default_factory=dict)


class SearchFailed(Exception):
    def __init__(self, message: str, partial: SearchResult):
        super().__init__(message)
        self.partial = partial


def split_point(lo: int, hi: int, products: list) -> int:
    """Median of the returned prices, else the geometric mean; clamped to lo < m < hi."""
    prices = [p["priceIfAvailable"]["amountInclusive"] for p in products if p.get("priceIfAvailable")]
    m = round(statistics.median(prices)) if prices else round(math.sqrt(lo * hi))
    return min(max(m, lo + 1), hi - 1)


def search(fetch: Fetch, lo: int = 1, hi: int = 1_000_000, max_calls: int = 60,
           on_update: Optional[Callable[[SearchResult], None]] = None) -> SearchResult:
    res = SearchResult(lo=lo, hi=hi, max_calls=max_calls)

    def notify():
        if on_update:
            on_update(res)

    def call(a, b, first=PAGE_SIZE) -> Page:
        page = fetch(a, b, first)
        res.calls += 1
        return page

    def collect(page: Page):
        for p in page.products:
            res.products[p["id"]] = p
        res.extras.update(page.extras)
        notify()

    def fail(message: str, cause: Optional[BaseException] = None):
        res.status = "failed"
        res.error = message
        notify()
        raise SearchFailed(message, res) from cause

    root = call(lo, hi)  # errors here propagate unchanged: nothing found yet
    res.root_total = root.total
    res.corrected = root.corrected
    if root.error:
        fail(root.error)
    collect(root)

    res.estimated_calls = math.ceil(2 * root.total / PAGE_SIZE)
    if res.estimated_calls > max_calls:
        res.status = "infeasible"
        _histogram(call, res)
        notify()
        return res

    try:
        _split(call, collect, fail, res, root)
        if (lo, hi) == FULL_RANGE and res.calls < max_calls:
            res.unfiltered_total = call(None, None, 1).total
        if res.calls < max_calls:
            res.final_total = call(lo, hi, 1).total
    except SearchFailed:
        raise
    except Exception as exc:  # any mid-run failure keeps the partial result
        fail(f"{type(exc).__name__}: {exc}", exc)
    notify()
    return res


def _split(call, collect, fail, res: SearchResult, root: Page) -> None:
    pending = [(res.lo, res.hi, root)]
    while pending:
        a, b, page = pending.pop(0)
        if page is None:
            if res.calls >= res.max_calls:
                res.bands.append(Band(a, b, None, "uncovered"))
                continue
            page = call(a, b)
            if page.error:
                fail(page.error)
            collect(page)
        can_split = b - a > 1 and res.calls < res.max_calls
        if page.total <= PAGE_SIZE and len(page.products) == page.total:
            res.bands.append(Band(a, b, page.total, "complete"))
        elif can_split:
            m = split_point(a, b, page.products)
            pending[0:0] = [(a, m, None), (m, b, None)]  # ascending order, left first
        elif page.total <= PAGE_SIZE:
            res.bands.append(Band(a, b, page.total, "drifted"))
        elif b - a <= 1:
            res.bands.append(Band(a, b, page.total, "capped"))
        else:
            res.bands.append(Band(a, b, page.total, "uncovered"))
    res.bands.sort(key=lambda band: (band.lo, band.hi))
    res.status = "complete" if all(band.status == "complete" for band in res.bands) else "partial"


def _histogram(call, res: SearchResult) -> None:
    n = min(HISTOGRAM_CALLS, res.max_calls - res.calls)
    if n < 1:
        return
    ratio = res.hi / res.lo
    edges = sorted({round(res.lo * ratio ** (i / n)) for i in range(n + 1)})
    for a, b in zip(edges, edges[1:]):
        try:
            page = call(a, b, 1)
        except Exception:  # a histogram is a hint; stop on the first failure
            break
        if page.error:
            break
        res.histogram.append(Band(a, b, page.total, "histogram"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_search.py`
Expected: `36 passed` (16 tests + 20 seeds of the termination test).
If `test_budget_leaves_uncovered_bands` reports `calls < 12`, the fake is returning a non-ascending page; check that `order="asc"` reaches `FakeCatalogue`.

- [ ] **Step 5: Commit**

```bash
git add skills/galaxus/scripts/galaxus_lib/search.py tests/fakes.py tests/test_search.py
git commit -m "Add exhaustive price-band search with coverage and feasibility gate"
```

---

### Task 6: Spec extraction, part 1 (numbers and `properties`)

**Files:**
- Create: `skills/galaxus/scripts/galaxus_lib/specs.py`
- Test: `tests/test_specs.py`

**Interfaces:**
- Produces: `STATED`, `INFERRED`, `FIELD_ORDER: tuple[str, ...]`, `Spec(value: str, state: str, source: str, ceiling: bool = False, conflict: str | None = None)` with `.to_dict()`, `parse_number(text: str, lang: str) -> float`, `fmt(x: float) -> str`, `first_number(value: str) -> float | None`, `schema_for(product_type: str) -> str | None` (`phone | laptop | monitor | None`), `parse_properties(properties: str, product_type: str) -> dict[str, str]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_specs.py`:
```python
import pytest

from galaxus_lib import specs


@pytest.mark.parametrize("text, lang, value", [
    ("6,99", "de", 6.99),
    ("6.90", "en", 6.9),
    ("8,340", "en", 8340),
    ("2,600", "en", 2600),
    ("3.840", "de", 3840),
    ("8'340", "de", 8340),
    ("1.500", "en", 1.5),
    ("6,830", "de", 6.83),
])
def test_parse_number_by_language(text, lang, value):
    assert specs.parse_number(text, lang) == value


def test_fmt_drops_trailing_zeros():
    assert specs.fmt(6.90) == "6.9"
    assert specs.fmt(256.0) == "256"
    assert specs.fmt(15.6) == "15.6"


def test_phone_properties():
    out = specs.parse_properties('256 GB, Dark Blue, 6.90", Hybrid Dual SIM, 4G', "Smartphones")
    assert out == {"storage": "256 GB", "colour": "Dark Blue", "screen": '6.9"',
                   "sim": "Hybrid Dual SIM", "network": "4G"}


def test_phone_properties_with_two_colour_tokens_and_no_sim():
    out = specs.parse_properties('256 GB, Black, Schwarz, 6.90", 5G', "Smartphone")
    assert out["colour"] == "Black / Schwarz"
    assert "sim" not in out


def test_laptop_properties_storage_before_ram():
    out = specs.parse_properties('15.60", 512 GB, 32 GB, CH, Intel Core Ultra 7 255U', "Notebooks")
    assert out == {"screen": '15.6"', "storage": "512 GB", "ram": "32 GB",
                   "keyboard": "CH", "cpu": "Intel Core Ultra 7 255U"}


def test_laptop_apple_cpu():
    assert specs.parse_properties('13.60", 512 GB, 16 GB, CH, M5', "Notebooks")["cpu"] == "M5"


def test_monitor_properties_en_and_de():
    assert specs.parse_properties('2560 x 1440 pixels, 27"', "Monitor") == {
        "resolution": "2560 x 1440", "screen": '27"'}
    assert specs.parse_properties('3840 x 2160 Pixel, 27"', "Monitor")["resolution"] == "3840 x 2160"


def test_unknown_type_uses_generic_patterns_only():
    assert specs.parse_properties("Black, 128 GB", "Phone cases") == {}
    assert specs.parse_properties("", "Smartphones") == {}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `py -m pytest tests/test_specs.py`
Expected: FAIL, `ImportError: cannot import name 'specs'`.

- [ ] **Step 3: Implement**

`skills/galaxus/scripts/galaxus_lib/specs.py`:
```python
"""Spec extraction from Galaxus product records. Spec: "Spec extraction".

A field in the result is *stated* (from `properties`, or from `description`
next to a field keyword) or *inferred* (derived). A missing field is unknown.
Field list, schemas and keyword tables: ../../references/spec-fields.md.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

STATED, INFERRED = "stated", "inferred"

FIELD_ORDER = ("os", "android_version", "cpu", "ram", "storage", "screen", "resolution",
               "refresh", "panel", "brightness", "response", "battery", "charging", "camera",
               "weight", "network", "sim", "ip", "ports", "keyboard", "colour")


@dataclass
class Spec:
    value: str
    state: str          # stated | inferred
    source: str         # properties | description | name
    ceiling: bool = False
    conflict: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- numbers

# A number not glued to a preceding digit/separator: thousands-grouped ("8,340",
# "3.840", "8'340") or plain with optional decimals ("6,99", "6.90", "120").
NUM = r"(?<![\d.,'’])(\d{1,3}(?:[,.'’]\d{3})+(?!\d)|\d+(?:[.,]\d+)?)"


def parse_number(text: str, lang: str) -> float:
    s = text.replace("'", "").replace("’", "")
    if re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+", s):
        sep = s[-4]
        if s.count(sep) > 1 or (sep == "," and lang == "en") or (sep == "." and lang != "en"):
            return float(s.replace(sep, ""))
    return float(s.replace(",", "."))


def fmt(x: float) -> str:
    x = float(x)
    return str(int(x)) if x.is_integer() else f"{x:.2f}".rstrip("0").rstrip(".")


def first_number(value: str) -> float | None:
    m = re.search(r"\d+(?:\.\d+)?", value)
    return float(m.group(0)) if m else None


# ------------------------------------------------------------- properties

_PROP = {
    "resolution": re.compile(r"^(\d{3,5}) x (\d{3,5})(?: \w+)?$"),
    "screen": re.compile(r'^(\d+(?:[.,]\d+)?)"$'),
    "size": re.compile(r"^(\d+(?:[.,]\d+)?) (GB|TB)$"),
    "network": re.compile(r"^(?:2G|3G|4G|5G|LTE)$"),
    "sim": re.compile(r"SIM"),
    "keyboard": re.compile(r"^(?:CH|DE|FR|IT|US|UK|NL|ES|INT|Nordic)$"),
    "cpu": re.compile(r"^(?:Intel|AMD|Apple|Snapdragon|Qualcomm|MediaTek|M\d)\b"),
}

# Positional schemas (seen 2026-11-11). Patterns decide; position breaks ties.
SCHEMAS = {
    "phone": ("storage", "colour", "screen", "sim", "network"),
    "laptop": ("screen", "storage", "ram", "keyboard", "cpu"),
    "monitor": ("resolution", "screen"),
}
_TYPE_WORDS = (
    ("phone", ("smartphone", "handy", "téléphone", "telefono", "telefoon")),
    ("laptop", ("notebook", "laptop", "ordinateur portable", "portatile")),
    ("monitor", ("monitor", "moniteur", "écran")),
)


def schema_for(product_type: str) -> str | None:
    t = product_type.lower()
    for schema, words in _TYPE_WORDS:
        if any(w in t for w in words):
            return schema
    return None


def _size_gb(token: str) -> float:
    number, unit = token.split(" ")
    return float(number) * (1000 if unit == "TB" else 1)


def parse_properties(properties: str, product_type: str) -> dict[str, str]:
    tokens = [t.strip() for t in properties.split(", ") if t.strip()]
    schema = schema_for(product_type)
    out: dict[str, str] = {}
    sizes: list[str] = []
    leftovers: list[str] = []
    for tok in tokens:
        if m := _PROP["resolution"].match(tok):
            out.setdefault("resolution", f"{m[1]} x {m[2]}")
        elif m := _PROP["screen"].match(tok):
            out.setdefault("screen", fmt(float(m[1].replace(",", "."))) + '"')
        elif m := _PROP["size"].match(tok):
            sizes.append(f"{fmt(float(m[1].replace(',', '.')))} {m[2]}")
        elif _PROP["network"].match(tok):
            out.setdefault("network", tok)
        elif _PROP["sim"].search(tok):
            out.setdefault("sim", tok)
        elif _PROP["keyboard"].match(tok):
            out.setdefault("keyboard", tok)
        elif _PROP["cpu"].match(tok):
            out.setdefault("cpu", tok)
        else:
            leftovers.append(tok)
    if schema is None:
        return out
    fields = SCHEMAS[schema]
    size_fields = [f for f in fields if f in ("storage", "ram")]
    if size_fields and len(sizes) == len(size_fields):
        out.update(zip(size_fields, sizes))
    elif size_fields and len(sizes) == 1:
        is_storage = "ram" not in size_fields or _size_gb(sizes[0]) >= 128
        out["storage" if is_storage else "ram"] = sizes[0]
    if "colour" in fields and leftovers:
        out["colour"] = " / ".join(leftovers)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_specs.py`
Expected: `15 passed`.

- [ ] **Step 5: Commit**

```bash
git add skills/galaxus/scripts/galaxus_lib/specs.py tests/test_specs.py
git commit -m "Add number parsing and properties schemas for spec extraction"
```

---

### Task 7: Spec extraction, part 2 (descriptions, ceilings, conflicts)

**Files:**
- Modify: `skills/galaxus/scripts/galaxus_lib/specs.py` (append)
- Test: `tests/test_specs.py` (append)

**Interfaces:**
- Consumes: Task 6 names.
- Produces: `extract_description(text: str, lang: str) -> dict[str, tuple[str, bool]]` (value, is_ceiling), `infer_android(os_value: str) -> str | None`, `extract(product: dict, lang: str) -> dict[str, Spec]` (ordered by `FIELD_ORDER`).

- [ ] **Step 1: Append the failing tests**

Append to `tests/test_specs.py` (these descriptions were copied verbatim from the live catalogue on 2026-11-11):
```python
REDMI17_EN = {
    "id": 73036751, "name": "Redmi 17", "brand": "Xiaomi", "productType": "Smartphones",
    "properties": '256 GB, Dark Blue, 6.90", Hybrid Dual SIM, 4G',
    "description": """The Xiaomi Redmi 17 is a powerful smartphone equipped with a 6.99-inch display and a resolution of 1600 x 720 pixels. Powered by a MediaTek Helio G91 Ultra processor and 4 GB of RAM, it offers smooth performance for everyday applications and multitasking. With an impressive internal storage capacity of 256 GB, users have plenty of space for photos, videos, and apps. The 50 MP rear camera allows for high-resolution image capture, while the 7500 mAh battery ensures long usage time. The device also supports modern features such as NFC and a fingerprint sensor, making it a practical choice for tech-savvy users.

- Powerful MediaTek Helio G91 Ultra processor
- 50 MP rear camera for high-quality photos
- 7500 mAh battery for long-lasting performance
- 256 GB internal storage for extensive use.""",
}

REDMI17_5G_DE = {
    "id": 74647549, "name": "Redmi 17", "brand": "Xiaomi", "productType": "Smartphone",
    "properties": '128 GB, Vivid Orange, 6.90", Hybrid Dual SIM, 5G',
    "description": """Das Xiaomi Redmi 17 5G ist ein leistungsstarkes Smartphone, das mit einem 6,9 Zoll grossen Display und einer Auflösung von 1600 x 720 Pixeln ausgestattet ist. Angetrieben von einem Snapdragon 4 Gen 5 Prozessor mit einer Taktfrequenz von bis zu 2,4 GHz und 4 GB RAM bietet es eine flüssige Benutzererfahrung. Die Dual-Kamera mit 50 MP auf der Rückseite ermöglicht beeindruckende Fotos, während die 7500 mAh Batterie eine lange Nutzungsdauer gewährleistet. Mit 128 GB internem Speicher, der auf bis zu 2048 GB erweiterbar ist, bietet das Gerät ausreichend Platz für Apps und Medien. Das Smartphone unterstützt 5G-Konnektivität und ist mit Dual-SIM-Funktionalität ausgestattet, was es zu einer flexiblen Wahl für moderne Nutzer macht.

- Leistungsstarker Snapdragon 4 Gen 5 Prozessor
- Dual-Kamera mit 50 MP für hochwertige Fotos
- 7500 mAh Akku für lange Laufzeit
- Erweiterbarer Speicher bis zu 2048 GB.""",
}

NOTE17PRO_DE = {
    "id": 76154192, "name": "Redmi Note 17 Pro", "brand": "Xiaomi", "productType": "Smartphone",
    "properties": '512 GB, Black, 6.83", Dual SIM, 5G',
    "description": """Das Redmi Note 17 Pro 5G vereint ein brillantes 1,5K CrystalRes AMOLED-Display, ein fortschrittliches Kamerasystem und einen aussergewöhnlich langlebigen Akku in einem robusten, zertifizierten Design. Sein 6,83-Zoll-AMOLED-Display bietet eine Auflösung von 2772 x 1280 mit einer Bildwiederholfrequenz von bis zu 120 Hz, einer maximalen Helligkeit von bis zu 3500 Nits und TUV-zertifiziertem, augenschonendem, flimmerfreiem Licht, geschützt durch Corning Gorilla Glass Victus 2 mit SGS-zertifizierter Fallfestigkeit von 3 Metern. Die 50-Megapixel-OIS-Hauptkamera mit einem 8-Megapixel-Ultraweitwinkelobjektiv und einer 16-Megapixel-Frontkamera, unterstützt von einem KI-gestützten Ultra-Klar-Bildsystem, ermöglicht detaillierte Fotos und lebensechte Porträts. Angetrieben vom Qualcomm Snapdragon 6s Gen 4, der im 4-nm-Prozess gefertigt ist, ist das Gerät in mehreren Speicherkonfigurationen mit bis zu 12 GB RAM und 512 GB Speicher erhältlich und läuft mit Xiaomi HyperOS 3, das KI-Tools wie Google Gemini und ein 60-monatiges, neuwertiges Softwareerlebnis umfasst. Ein 8340 mAh Siliziumkarbon-Akku mit 67W HyperCharge unterstützt mehr als zwei Tage Nutzung, während die IP66- und IP68-Zertifizierung für Wasser- und Staubschutz bis zu 2 Meter und 72 Stunden gewährleistet. Ein im Display integrierter Fingerabdrucksensor, KI-gestütztes Gesichtserkennung, ein 300 Prozent lauterer Klang mit Dolby Atmos und Hi-Res Audio sowie Dual-Band-WiFi mit NFC runden dieses leistungsstarke 5G-Smartphone ab, das für anspruchsvolle Alltagsnutzung konzipiert ist.""",
}

MONITOR_DE = {
    "id": 53920915, "name": "27UP850K-W", "brand": "LG Electronics", "productType": "Monitor",
    "properties": '3840 x 2160 Pixel, 27"',
    "description": """Ob Produktivität oder Unterhaltung – der 27UP850K-W von LG Electronics ist der ideale Monitor für alle Lebenslagen. Der IPS-Bildschirm mit einer Bilddiagonalen von 27 Zoll (68,4 Zentimeter) stellt sämtliche Inhalte in nativer 4K-Auflösung von 3.840 x 2.160 Pixeln absolut brillant dar. Seine 95-prozentige Abdeckung des DCI-P3-Farbraums garantiert eine präzise Farbwiedergabe. Die Spitzenhelligkeit von 400 cd/m² sorgt im Zusammenspiel mit DisplayHDR 400 für die Sichtbarkeit sämtlicher Details mit beeindruckender Detailschärfe. Die 5 Millisekunden Reaktionsgeschwindigkeit mit Unterstützung für AMD FreeSync machen ihn auch für Gaming-Fans interessant. Abgerundet wird das Profil des 27UP850K-W als echter Allrounder durch seine Anschlussvielfalt – neben Anschlüssen für HDMI und DisplayPort bietet der 4K-Monitor auch USB-C-Konnektivität, inklusive 90 Watt Ladeleistung für Notebooks. Mehr Monitor geht nicht. Mit dem ergonomischen Edge-ArcLine Standfuss ist er das Glanzstück auf jedem Schreibtisch.""",
}

FLIP8_EN = {
    "id": 72284580, "name": "Galaxy Z Flip8", "brand": "Samsung", "productType": "Smartphones",
    "properties": '256 GB, Graphite, 6.90", Dual SIM, 5G',
    "description": """The Galaxy Z Flip8 impresses with its compact and elegant flip design. With a depth of just 6.1 mm and a slim profile, it fits perfectly in the hand and is easy to carry around. The flexible display ensures a seamless experience when opening and closing the device. With a robust build featuring Corning Gorilla Glass Victus 2 and Advanced Armour Aluminium, as well as IP48 water resistance, the Galaxy Z Flip8 is not only stylish but also durable and ready for everyday use.

Available in the elegant colours Pink, Graphite and Cream, the Galaxy Z Flip8 combines innovative design with powerful technology for an unrivalled user experience.

Galaxy Z Flip8 highlights
• 6.7" Dynamic Display with up to 2,600 nits brightness and a 4.1" HD Super Cover Screen
• Compact and elegant flip design, just 6.1 mm thick.
• 50 MP / 12 MP dual camera, 10 MP front camera
• Smart Switch: Seamless switching between iOS and Android
• Samsung Exynos 2600 processor
• 4,300 mAh battery life and 25W fast charging""",
}


def values(product, lang):
    return {f: s.value for f, s in specs.extract(product, lang).items()}


def test_redmi17_en_ram_storage_and_screen_conflict():
    out = specs.extract(REDMI17_EN, "en")
    assert out["ram"].value == "4 GB" and out["ram"].source == "description"
    assert out["storage"].value == "256 GB" and out["storage"].source == "properties"
    assert out["storage"].conflict is None
    assert out["screen"].conflict == '6.9" (properties) / 6.99" (description)'
    v = values(REDMI17_EN, "en")
    assert v["resolution"] == "1600 x 720"
    assert v["cpu"] == "MediaTek Helio G91 Ultra"
    assert v["battery"] == "7500 mAh" and v["camera"] == "50 MP"
    assert "os" not in v and "android_version" not in v


def test_redmi17_de_decimal_comma_ghz_and_expandable_ceiling():
    out = specs.extract(REDMI17_5G_DE, "de")
    assert out["screen"].conflict is None          # 6,9 Zoll == 6.90"
    assert out["ram"].value == "4 GB" and not out["ram"].ceiling
    assert out["storage"].value == "128 GB" and out["storage"].conflict is None
    assert out["cpu"].value == "Snapdragon 4 Gen 5"
    assert "refresh" not in out                     # 2,4 GHz is CPU clock
    assert out["network"].value == "5G"


def test_note17pro_de_ceilings_hyperos_and_inference():
    out = specs.extract(NOTE17PRO_DE, "de")
    assert out["refresh"].value == "120 Hz" and out["refresh"].ceiling
    assert out["brightness"].value == "3500 nits" and out["brightness"].ceiling
    assert out["ram"].value == "12 GB" and out["ram"].ceiling
    assert out["storage"].value == "512 GB" and out["storage"].conflict is None
    assert out["os"].value == "HyperOS 3"
    assert (out["android_version"].value, out["android_version"].state) == ("16", "inferred")
    v = values(NOTE17PRO_DE, "de")
    assert v["cpu"] == "Qualcomm Snapdragon 6s Gen 4"
    assert v["battery"] == "8340 mAh" and v["charging"] == "67 W"
    assert v["ip"] == "IP66/IP68" and v["panel"] == "AMOLED"
    assert v["camera"] == "50 MP" and v["resolution"] == "2772 x 1280"


def test_monitor_de_thousands_dots_cd_m2_and_watt_charging():
    v = values(MONITOR_DE, "de")
    assert v["resolution"] == "3840 x 2160"
    assert specs.extract(MONITOR_DE, "de")["resolution"].conflict is None
    assert v["screen"] == '27"'
    assert v["panel"] == "IPS"
    assert v["brightness"] == "400 nits"
    assert v["response"] == "5 ms"
    assert v["charging"] == "90 W"
    assert v["ports"] == "HDMI, DisplayPort, USB-C"
    assert "refresh" not in v


def test_flip8_en_thousands_comma_and_no_os_from_mention():
    out = specs.extract(FLIP8_EN, "en")
    assert out["screen"].conflict == '6.9" (properties) / 6.7" (description)'
    assert out["brightness"].value == "2600 nits" and out["brightness"].ceiling
    v = values(FLIP8_EN, "en")
    assert v["battery"] == "4300 mAh"
    assert v["charging"] == "25 W"
    assert v["cpu"] == "Exynos 2600"
    assert v["ip"] == "IP48"
    assert "os" not in v                           # "between iOS and Android" is not a spec


def test_ram_storage_disambiguation_by_keyword():
    out = specs.extract_description("Comes with 16 GB RAM and a 512 GB SSD.", "en")
    assert out["ram"] == ("16 GB", False)
    assert out["storage"] == ("512 GB", False)


def test_ceiling_only_value_is_marked():
    out = specs.extract_description("Storage is expandable up to 1 TB via microSD.", "en")
    assert out["storage"] == ("1 TB", True)


def test_android_stated_and_name_5g_inferred():
    p = {"name": "Phone X 5G", "productType": "Smartphones", "properties": "",
         "description": "Runs Android 16 out of the box."}
    out = specs.extract(p, "en")
    assert (out["android_version"].value, out["android_version"].state) == ("16", "stated")
    assert (out["network"].value, out["network"].state, out["network"].source) == ("5G", "inferred", "name")


def test_infer_android_table():
    assert specs.infer_android("HyperOS 2") == "15"
    assert specs.infer_android("One UI 8") == "16"
    assert specs.infer_android("HyperOS 9") is None
    assert specs.infer_android("Windows 11 Home") is None


def test_extract_orders_fields():
    assert list(specs.extract(NOTE17PRO_DE, "de")) == [f for f in specs.FIELD_ORDER
                                                        if f in specs.extract(NOTE17PRO_DE, "de")]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `py -m pytest tests/test_specs.py`
Expected: the 15 Task 6 tests pass; the new ones FAIL with `AttributeError: module 'galaxus_lib.specs' has no attribute 'extract'`.

- [ ] **Step 3: Append the implementation**

Append to `skills/galaxus/scripts/galaxus_lib/specs.py`:
```python
# ------------------------------------------------------------ description

# Keyword regexes per field and language; English is always added as well.
_KW = {
    "ram": {"en": [r"\bram\b", r"\bworking memory"], "de": [r"\bram\b", r"\barbeitsspeicher"],
            "fr": [r"\bram\b", r"mémoire vive"], "it": [r"\bram\b"], "nl": [r"\bram\b", r"\bwerkgeheugen"]},
    "storage": {"en": [r"\bstorage", r"\binternal memory", r"\bssd\b", r"\brom\b", r"\bhard drive"],
                "de": [r"\bspeicher", r"\bssd\b", r"\bfestplatte"],
                "fr": [r"\bstockage", r"mémoire interne", r"\bssd\b"],
                "it": [r"\bmemoria interna", r"\barchiviazione", r"\bssd\b"], "nl": [r"\bopslag", r"\bssd\b"]},
    "weight": {"en": [r"\bweigh"], "de": [r"\bgewicht", r"\bwiegt"], "fr": [r"\bpoids", r"\bpèse"],
               "it": [r"\bpeso", r"\bpesa"], "nl": [r"\bgewicht", r"\bweegt"]},
    "charging": {"en": [r"charg"], "de": [r"\blade", r"charg"], "fr": [r"charg"], "it": [r"ricaric"],
                 "nl": [r"\bopla", r"\blaad"]},
    "speaker": {"en": [r"\bspeaker", r"\baudio", r"\bsound"], "de": [r"\blautsprecher", r"\bklang"],
                "fr": [r"haut-parleur", r"\bson\b"], "it": [r"altoparlant"], "nl": [r"\bluidspreker", r"\bgeluid"]},
    "os": {"en": [r"operating system", r"\bruns\b", r"\brunning\b"], "de": [r"betriebssystem", r"läuft (?:mit|auf)"],
           "fr": [r"système d.exploitation"], "it": [r"sistema operativo"], "nl": [r"besturingssysteem"]},
    "diagonal": {"en": [r"diagonal"], "de": [r"diagonale"], "fr": [r"diagonale"], "it": [r"diagonale"],
                 "nl": [r"diagonaal"]},
}

# A value right after one of these is a range/ceiling, not this variant's value.
_CEILING = ("up to", "bis zu", "jusqu'à", "jusqu’à", "fino a", "tot ", "memory extension",
            "speichererweiterung", "configurations", "konfigurationen")
_EXPAND = re.compile(r"\s*(?:\S+\s+)?(?:expandable|erweiterbar|extensible|espandibile|uitbreidbaar)", re.I)
_BOUNDARY = re.compile(r"[.!?](?=\s|$)|\n|•")
_WINDOW = 40


def _kw(group: str, lang: str) -> list[str]:
    table = _KW[group]
    return table.get(lang, []) + ([] if lang == "en" else table["en"])


def _sentence_span(text: str, pos: int) -> tuple[int, int]:
    start, end = 0, len(text)
    for m in _BOUNDARY.finditer(text):
        if m.end() <= pos:
            start = m.end()
        elif m.start() >= pos:
            end = m.start()
            break
    return start, end


def _keyword_distance(text: str, start: int, end: int, patterns: list[str]) -> int | None:
    s0, s1 = _sentence_span(text, start)
    lo, hi = max(s0, start - _WINDOW), min(s1, end + _WINDOW)
    best = None
    for pat in patterns:
        for m in re.finditer(pat, text[lo:hi], re.I):
            a, b = m.start() + lo, m.end() + lo
            d = start - b if b <= start else (a - end if a >= end else 0)
            best = d if best is None else min(best, d)
    return best


def _is_ceiling(text: str, start: int, end: int, unit: str) -> bool:
    s0, _ = _sentence_span(text, start)
    before = text[max(s0, start - 60):start]
    low = before.lower()
    hits = [low.rfind(p) + len(p) for p in _CEILING if p in low]
    if hits:
        gap = before[max(hits):]
        if not re.search(r"\d", gap):
            return True
        # "bis zu 12 GB RAM und 512 GB": the phrase also covers the next value of the same unit.
        m = re.fullmatch(r"\s*[\d.,'’]+\s*(\S+)(?:\s+\S+)?\s+(?:and|und|et|e|en|,)\s+", gap, re.I)
        if m and m.group(1).lower() == unit.lower():
            return True
    return bool(_EXPAND.match(text, end))


def _rx(unit: str, flags=re.I):
    return re.compile(NUM + unit, flags)


_UNIT_FIELDS = {
    "battery": (_rx(r"\s?mAh\b"), "mAh"),
    "camera": (_rx(r"\s?-?\s?(?:MP|mega-?pixels?|mégapixels?)\b"), "MP"),
    "brightness": (_rx(r"\s?(?:nits?\b|cd/m²|cd/m2)"), "nits"),
    "response": (_rx(r"\s?(?:ms|milliseconds?|millisekunden|millisecondes?|millisecondi|milliseconden)\b"), "ms"),
    "refresh": (_rx(r"\s?Hz\b"), "Hz"),  # "2,4 GHz" never matches: G sits between number and Hz
}
_SCREEN = _rx(r'(?:\s?-?\s?(?:inch(?:es)?|zoll|pouces?|pollici|duim)\b|\s?["”″])')
_SCREEN_CM = _rx(r"\s?(?:cm|zentimeter|centimet\w*)\b")
_SIZE = _rx(r"\s?(GB|TB)\b")
_WEIGHT = _rx(r"\s?(kg|g)\b", 0)    # case-sensitive: "5G" is not grams
_WATT = _rx(r"\s?(?:W|Watt)\b", 0)
_RES = re.compile(r"(?<![\d.,'’])(\d[\d.,'’]{2,5})\s?[x×]\s?(\d[\d.,'’]{2,5})(?!\d)")
_OS = re.compile(r"\b(Android|iOS|iPadOS|HarmonyOS|HyperOS|One UI|Windows|macOS|ChromeOS|Wear OS|watchOS)"
                 r"(?:\s?(\d+(?:\.\d+)?))?(?: (Home|Pro))?\b")
_CPU = re.compile(r"\b(?:(?:Qualcomm |MediaTek )?(?:Snapdragon|Dimensity|Helio|Exynos|Tensor|Unisoc|Kirin)"
                  r"|Intel Core|AMD Ryzen)\b[\w\- ]{0,25}?\d[\w\-]*(?: (?:Ultra|Pro|Plus|Max|Gen \d+))?"
                  r"|\bApple [AM]\d+(?: (?:Pro|Max|Ultra))?\b")
_PANEL = re.compile(r"\b(QD-OLED|Mini-?LED|Super AMOLED|AMOLED|OLED|IPS|VA|TN|LCD)\b")
_NET = re.compile(r"\b(5G|4G|LTE)\b")
_IP = re.compile(r"\bIP[X\d]\d\b")
_PORT = re.compile(r"(?:(?<![A-Za-z])|(?<=\dx))(Thunderbolt \d|USB-C|USB Type-C|HDMI(?: \d\.\d)?|DisplayPort|DP)(?![A-Za-z])")

# Android base of vendor skins; maintained by hand, unknown versions stay unknown.
_ANDROID_BASE = {("HyperOS", "2"): "15", ("HyperOS", "3"): "16", ("One UI", "7"): "15", ("One UI", "8"): "16"}


def infer_android(os_value: str) -> str | None:
    m = re.match(r"(HyperOS|One UI)\s?(\d+)", os_value)
    return _ANDROID_BASE.get((m[1], m[2])) if m else None


def extract_description(text: str, lang: str) -> dict[str, tuple[str, bool]]:
    found: dict[str, list[tuple[str, bool]]] = {}

    def add(field: str, value: str, ceiling: bool = False):
        found.setdefault(field, []).append((value, ceiling))

    for field, (rx, unit) in _UNIT_FIELDS.items():
        for m in rx.finditer(text):
            matched_unit = m[0][len(m[1]):].strip(" -")
            add(field, f"{fmt(parse_number(m[1], lang))} {unit}",
                _is_ceiling(text, m.start(), m.end(), matched_unit))
    for m in _SCREEN.finditer(text):
        add("screen", fmt(parse_number(m[1], lang)) + '"', _is_ceiling(text, m.start(), m.end(), '"'))
    if "screen" not in found:
        for m in _SCREEN_CM.finditer(text):
            if _keyword_distance(text, m.start(), m.end(), _kw("diagonal", lang)) is not None:
                add("screen", fmt(round(parse_number(m[1], lang) / 2.54, 1)) + '"')
    for m in _SIZE.finditer(text):
        d_ram = _keyword_distance(text, m.start(), m.end(), _kw("ram", lang))
        d_sto = _keyword_distance(text, m.start(), m.end(), _kw("storage", lang))
        if d_ram is None and d_sto is None:
            continue
        field = "ram" if d_sto is None or (d_ram is not None and d_ram < d_sto) else "storage"
        add(field, f"{fmt(parse_number(m[1], lang))} {m[2].upper()}",
            _is_ceiling(text, m.start(), m.end(), m[2]))
    for m in _WEIGHT.finditer(text):
        if _keyword_distance(text, m.start(), m.end(), _kw("weight", lang)) is not None:
            add("weight", f"{fmt(parse_number(m[1], lang))} {m[2]}")
    for m in _WATT.finditer(text):
        d_charge = _keyword_distance(text, m.start(), m.end(), _kw("charging", lang))
        d_speaker = _keyword_distance(text, m.start(), m.end(), _kw("speaker", lang))
        if d_charge is not None and (d_speaker is None or d_charge <= d_speaker):
            add("charging", f"{fmt(parse_number(m[1], lang))} W", _is_ceiling(text, m.start(), m.end(), "W"))
    for m in _RES.finditer(text):
        w, h = (int(re.sub(r"\D", "", g)) for g in (m[1], m[2]))
        if w >= 240 and h >= 240:
            add("resolution", f"{w} x {h}")
    for m in _OS.finditer(text):
        if m[2] or _keyword_distance(text, m.start(), m.end(), _kw("os", lang)) is not None:
            add("os", " ".join(x for x in (m[1], m[2], m[3]) if x))
            if m[1] == "Android" and m[2]:
                add("android_version", m[2].split(".")[0])
    if m := _CPU.search(text):
        add("cpu", m[0].strip())
    if m := _PANEL.search(text):
        add("panel", m[1])
    nets = set(_NET.findall(text))
    if nets:
        add("network", "5G" if "5G" in nets else "4G")
    ips = list(dict.fromkeys(_IP.findall(text)))
    if ips:
        add("ip", "/".join(ips))
    ports = list(dict.fromkeys(m[1] for m in _PORT.finditer(text)))
    if ports:
        add("ports", ", ".join(ports))

    out: dict[str, tuple[str, bool]] = {}
    for field, candidates in found.items():
        plain = [c for c in candidates if not c[1]]
        out[field] = plain[0] if plain else candidates[0]
    return out


# ------------------------------------------------------------------ merge

def _same(a: str, b: str) -> bool:
    def nums(s):
        return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]

    def rest(s):
        return re.sub(r"[\d.\s]", "", s).lower()

    na, nb = nums(a), nums(b)
    return rest(a) == rest(b) and len(na) == len(nb) and all(abs(x - y) < 0.005 for x, y in zip(na, nb))


def extract(product: dict, lang: str) -> dict[str, Spec]:
    """properties win over description; disagreement is recorded as a conflict."""
    found = {f: Spec(v, STATED, "properties") for f, v in
             parse_properties(product.get("properties") or "", product.get("productType") or "").items()}
    for field, (value, ceiling) in extract_description(product.get("description") or "", lang).items():
        current = found.get(field)
        if current is None:
            found[field] = Spec(value, STATED, "description", ceiling=ceiling)
        elif not ceiling and not _same(current.value, value):
            current.conflict = f"{current.value} (properties) / {value} (description)"
    if "network" not in found and re.search(r"\b5G\b", product.get("name") or ""):
        found["network"] = Spec("5G", INFERRED, "name")
    if "android_version" not in found and "os" in found:
        base = infer_android(found["os"].value)
        if base:
            found["android_version"] = Spec(base, INFERRED, found["os"].source)
    return {f: found[f] for f in FIELD_ORDER if f in found}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_specs.py`
Expected: `25 passed`. A failing real-description test means a regex or keyword table is wrong; fix the extractor, not the expected value (the expected values were read off the text by hand).

- [ ] **Step 5: Commit**

```bash
git add skills/galaxus/scripts/galaxus_lib/specs.py tests/test_specs.py
git commit -m "Extract specs from descriptions with ceilings and conflicts"
```

---

### Task 8: Variant merge and report

**Files:**
- Create: `skills/galaxus/scripts/galaxus_lib/variants.py`, `skills/galaxus/scripts/galaxus_lib/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `SearchResult`, `Band` (Task 5); `specs.extract`, `specs.schema_for`, `specs.first_number` (Tasks 6–7).
- Produces:
  - `variants.merge_variants(products: list[dict]) -> list[list[dict]]` (key: brand, productType, name, description; order kept).
  - `report.build_document(res, query, lang, version, timestamp, cache=None) -> dict`. Document keys: `version, query, language, range, timestamp, status, maxCalls, calls, estimatedCalls, rootTotal, finalTotal, unfilteredTotal, correctedSearchTerm, error, bands, histogram, products`. Each product is the Galaxus record plus `extras` (Task 4 shape or `None`) and `specs` (`{field: Spec.to_dict()}`), sorted by price, priceless last.
  - `report.coverage_lines(doc) -> list[str]`, `report.format_report(doc, top, out_path=None) -> str`, `report.format_row(group: list[dict]) -> str`, `report.render_spec(spec: dict | None) -> str`, `report.format_price(value) -> str`, `report.FOOTNOTE: str`.

- [ ] **Step 1: Write the failing tests**

`tests/test_report.py`:
```python
from fakes import make_product
from galaxus_lib import report, specs
from galaxus_lib.search import Band, SearchResult
from galaxus_lib.variants import merge_variants


def with_specs(p, lang="en"):
    p = dict(p)
    p["specs"] = {f: s.to_dict() for f, s in specs.extract(p, lang).items()}
    p.setdefault("extras", None)
    return p


def doc(products, status="complete", **kw):
    base = {"version": "0.1.0", "query": "q", "language": "en", "range": [1, 1_000_000], "timestamp": "t",
            "status": status, "maxCalls": 60, "calls": 3, "estimatedCalls": 2, "rootTotal": len(products),
            "finalTotal": None, "unfilteredTotal": None, "correctedSearchTerm": None, "error": None,
            "bands": [], "histogram": [], "products": products}
    base.update(kw)
    return base


DESC = "Smartphone with 4 GB RAM."


def redmi(pid, price, storage, colour):
    return with_specs(make_product(pid, price, name="Redmi 17", brand="Xiaomi", description=DESC,
                                   properties=f'{storage}, {colour}, 6.90", Dual SIM, 4G'))


def test_merge_requires_all_four_fields_equal():
    a, b = redmi(1, 164, "256 GB", "Blue"), redmi(2, 187, "128 GB", "Black")
    c = dict(redmi(3, 150, "128 GB", "Black"), description="Other chip.")
    assert [len(g) for g in merge_variants([a, b, c])] == [2, 1]


def test_build_document_sorts_by_price_and_adds_specs_and_extras():
    res = SearchResult(lo=1, hi=1_000_000, max_calls=60, status="complete", root_total=2, calls=1)
    res.products = {1: make_product(1, 50.0), 2: make_product(2, 20.0), 3: make_product(3, None)}
    res.extras = {1: {"availability": "TICK", "labels": [], "insteadOf": None}}
    res.bands = [Band(1, 1_000_000, 2, "complete")]
    d = report.build_document(res, "phone", "en", "0.1.0", "2026-11-11T00:00:00Z")
    assert [p["id"] for p in d["products"]] == [2, 1, 3]
    assert d["products"][1]["extras"]["availability"] == "TICK"
    assert "specs" in d["products"][0]
    assert d["bands"] == [{"lo": 1, "hi": 1_000_000, "count": 2, "status": "complete"}]
    assert (d["query"], d["language"], d["range"]) == ("phone", "en", [1, 1_000_000])


def test_coverage_complete():
    lines = report.coverage_lines(doc([with_specs(make_product(1, 10.0))]))
    assert lines[0] == "Coverage: complete. 1 unique products found; Galaxus reports 1 for this query and price range (3 calls)."


def test_coverage_partial_lists_band_problems():
    d = doc([], status="partial", rootTotal=400, bands=[
        {"lo": 163, "hi": 164, "count": 165, "status": "capped"},
        {"lo": 500, "hi": 1_000_000, "count": None, "status": "uncovered"}])
    text = "\n".join(report.coverage_lines(d))
    assert text.startswith("Coverage: partial. 0 unique products found of 400 reported")
    assert "capped (more than 50 products within 1 CHF; 50 kept): 163-164 CHF (165)" in text
    assert "uncovered (call budget reached; not searched): 500-1000000 CHF" in text


def test_coverage_infeasible_shows_histogram_and_no_rows():
    d = doc([with_specs(make_product(1, 10.0))], status="infeasible", rootTotal=471_800, estimatedCalls=18_872,
            histogram=[{"lo": 1, "hi": 6, "count": 1200, "status": "histogram"}])
    text = report.format_report(d, top=15)
    assert "Coverage: infeasible. Galaxus reports 471,800 matches" in text
    assert "  1-6: 1,200" in text
    assert "## " not in text


def test_coverage_failed_is_not_zero_results():
    text = "\n".join(report.coverage_lines(doc([], status="failed", error="The request failed")))
    assert "Coverage: failed." in text and "not as zero results" in text


def test_coverage_notes():
    d = doc([], rootTotal=30, finalTotal=31, unfilteredTotal=33, correctedSearchTerm="smartphone")
    text = "\n".join(report.coverage_lines(d))
    assert "moved from 30 to 31" in text
    assert "3 matches have no price of at least 1 CHF" in text
    assert 'spell-corrected the query to "smartphone"' in text


def test_row_shows_variant_sets_unknown_os_discount_and_availability():
    a, b = redmi(1, 164, "256 GB", "Blue"), redmi(2, 187, "128 GB", "Black")
    a["extras"] = {"availability": "TICK", "labels": ["DISCOUNT"],
                   "insteadOf": {"type": "SALES_PRICE_BEFORE", "rebate": 8, "price": 178}}
    row = report.format_row([a, b])
    assert row.startswith("- Xiaomi Redmi 17 | CHF 164-187 | 128/256 GB; 2 colours")
    assert "Android ?" in row
    assert "RAM 4 GB (desc.)" in row
    assert "availability TICK*" in row
    assert "-8 CHF, was 178*" in row
    assert row.endswith("https://www.galaxus.ch/en/s1/product/1")


def test_row_flags_refurbished():
    p = with_specs(make_product(5, 99.5))
    p["pageUrl"] += "?offertype=refurbished"
    assert "refurbished" in report.format_row([p])
    assert "CHF 99.50" in report.format_row([p])


def test_render_spec_states():
    assert report.render_spec(None) == "?"
    assert report.render_spec({"value": "120 Hz", "state": "stated", "source": "description",
                               "ceiling": True, "conflict": None}) == "up to 120 Hz (desc.)"
    assert report.render_spec({"value": "16", "state": "inferred", "source": "description",
                               "ceiling": False, "conflict": None}) == "16 (inferred)"


def test_top_limit_points_to_file():
    products = [with_specs(make_product(i, 10.0 + i)) for i in range(4)]
    text = report.format_report(doc(products), top=3, out_path="out.json")
    assert "## Smartphones: 4 products, 4 rows" in text
    assert "+1 more rows in out.json" in text
    assert text.rstrip().endswith(report.FOOTNOTE)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `py -m pytest tests/test_report.py`
Expected: FAIL, `ImportError: cannot import name 'report'`.

- [ ] **Step 3: Implement**

`skills/galaxus/scripts/galaxus_lib/variants.py`:
```python
"""Conservative variant merge: one row only when brand, productType, name and
description are all equal. Merging different products shows false facts; extra
rows only cost space. Fuzzy de-duplication is deferred."""
from __future__ import annotations


def variant_key(p: dict) -> tuple:
    return (p.get("brand"), p.get("productType"), p.get("name"), p.get("description"))


def merge_variants(products: list[dict]) -> list[list[dict]]:
    groups: dict[tuple, list[dict]] = {}
    for p in products:
        groups.setdefault(variant_key(p), []).append(p)
    return list(groups.values())
```

`skills/galaxus/scripts/galaxus_lib/report.py`:
```python
"""JSON document (the --out file) and the text report printed to stdout."""
from __future__ import annotations

from dataclasses import asdict

from . import specs
from .variants import merge_variants

FOOTNOTE = ("* availability class and discount: per Galaxus data (undocumented field); classes are shown raw, "
            "with no assumed meaning. Spec marks: (desc.) = from the free-text description, weaker than "
            "properties; (inferred) = derived, not stated; up to = a ceiling, not this variant's value; ? = unknown.")

KEY_FIELDS = {"phone": ("android_version", "ram", "network"), "laptop": ("cpu", "ram", "os"),
              "monitor": ("refresh", "panel", "response")}
LABELS = {"android_version": "Android", "ram": "RAM", "cpu": "CPU", "os": "OS"}
_VARIANT_FIELDS = ("storage", "ram", "screen", "network", "colour")


def format_price(value) -> str:
    if value is None:
        return "n/a"
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}"


def _price(p: dict):
    pr = p.get("priceIfAvailable")
    return pr["amountInclusive"] if pr else None


def _price_key(p: dict):
    v = _price(p)
    return (v is None, v or 0)


# --------------------------------------------------------------- document

def build_document(res, query: str, lang: str, version: str, timestamp: str, cache: dict | None = None) -> dict:
    cache = {} if cache is None else cache
    products = []
    for pid, p in res.products.items():
        if pid not in cache:
            cache[pid] = {f: s.to_dict() for f, s in specs.extract(p, lang).items()}
        item = dict(p)
        item["extras"] = res.extras.get(pid)
        item["specs"] = cache[pid]
        products.append(item)
    products.sort(key=_price_key)
    return {
        "version": version, "query": query, "language": lang, "range": [res.lo, res.hi], "timestamp": timestamp,
        "status": res.status, "maxCalls": res.max_calls, "calls": res.calls, "estimatedCalls": res.estimated_calls,
        "rootTotal": res.root_total, "finalTotal": res.final_total, "unfilteredTotal": res.unfiltered_total,
        "correctedSearchTerm": res.corrected, "error": res.error,
        "bands": [asdict(b) for b in res.bands], "histogram": [asdict(b) for b in res.histogram],
        "products": products,
    }


# --------------------------------------------------------------- coverage

def coverage_lines(doc: dict) -> list[str]:
    n, total, status = len(doc["products"]), doc["rootTotal"], doc["status"]
    lines = []
    if status == "infeasible":
        lines.append(f"Coverage: infeasible. Galaxus reports {total:,} matches; a complete search needs about "
                     f"{doc['estimatedCalls']:,} calls, budget is {doc['maxCalls']}. Narrow by brand in the query, "
                     f"by a tighter price range, or ask the user.")
        if doc["histogram"]:
            lines.append("Price histogram (CHF range: matches):")
            lines += [f"  {b['lo']}-{b['hi']}: {b['count']:,}" for b in doc["histogram"]]
    elif status == "complete":
        lines.append(f"Coverage: complete. {n} unique products found; Galaxus reports {total} for this query "
                     f"and price range ({doc['calls']} calls).")
    elif status == "failed":
        lines.append(f"Coverage: failed. Galaxus search error: {doc['error']}. {n} unique products found before "
                     f"the failure; treat this as a failed search, not as zero results.")
    else:
        word = "partial" if status == "partial" else "in progress"
        lines.append(f"Coverage: {word}. {n} unique products found of {total} reported ({doc['calls']} calls).")
    for st, why in (("capped", "more than 50 products within 1 CHF; 50 kept"),
                    ("drifted", "count changed between calls"),
                    ("uncovered", "call budget reached; not searched")):
        bands = [b for b in doc["bands"] if b["status"] == st]
        if bands:
            lines.append(f"  {st} ({why}): " + ", ".join(
                f"{b['lo']}-{b['hi']} CHF" + (f" ({b['count']})" if b["count"] is not None else "") for b in bands))
    final, unfiltered = doc.get("finalTotal"), doc.get("unfilteredTotal")
    if final is not None and final != total:
        lines.append(f"Note: the Galaxus count moved from {total} to {final} during the run; "
                     f"coverage numbers carry that tolerance.")
    if unfiltered is not None and unfiltered > total:
        lines.append(f"Note: {unfiltered - total} matches have no price of at least 1 CHF and cannot be "
                     f"reached by price bands.")
    if doc.get("correctedSearchTerm"):
        lines.append(f'Note: Galaxus spell-corrected the query to "{doc["correctedSearchTerm"]}".')
    return lines


# ------------------------------------------------------------------- rows

def render_spec(spec: dict | None) -> str:
    if not spec:
        return "?"
    value = f"up to {spec['value']}" if spec.get("ceiling") else spec["value"]
    notes = []
    if spec["state"] == "inferred":
        notes.append("inferred")
    elif spec["source"] == "description":
        notes.append("desc.")
    if spec.get("conflict"):
        notes.append(f"conflict: {spec['conflict']}")
    return f"{value} ({'; '.join(notes)})" if notes else value


def _specs_of(p: dict) -> dict:
    return p.get("specs") or {}


def _variant_differences(group: list[dict]) -> str:
    if len(group) < 2:
        return ""
    out = []
    for field in _VARIANT_FIELDS:
        vals = [v for v in dict.fromkeys((_specs_of(p).get(field) or {}).get("value") for p in group) if v]
        if len(vals) < 2:
            continue
        if field == "colour":
            out.append(f"{len(vals)} colours")
            continue
        units = {v.split(" ", 1)[1] if " " in v else "" for v in vals}
        if len(units) == 1 and "" not in units:
            ordered = sorted(vals, key=lambda v: specs.first_number(v) or 0)
            out.append("/".join(v.split(" ", 1)[0] for v in ordered) + " " + units.pop())
        else:
            out.append("/".join(vals))
    return "; ".join(out)


def _key_specs(group: list[dict]) -> str:
    schema = specs.schema_for(group[0].get("productType") or "")
    parts = []
    for field in KEY_FIELDS.get(schema, ()):
        label = LABELS.get(field, field)
        all_values = [_specs_of(p).get(field) for p in group]
        known = [v for v in all_values if v]
        if not known:
            parts.append(f"{label} ?")
            continue
        distinct = list(dict.fromkeys(k["value"] for k in known))
        text = render_spec(known[0]) if len(distinct) == 1 else "/".join(distinct)
        if len(known) < len(all_values):
            text += " (some variants)"
        parts.append(f"{label} {text}")
    return ", ".join(parts)


def _price_range(group: list[dict]) -> str:
    prices = [v for v in map(_price, group) if v is not None]
    if not prices:
        return "price n/a"
    lo, hi = min(prices), max(prices)
    return f"CHF {format_price(lo)}" if lo == hi else f"CHF {format_price(lo)}-{format_price(hi)}"


def _rating(group: list[dict]) -> str:
    rated = [p["ratingSummaryIfAvailable"] for p in group if p.get("ratingSummaryIfAvailable")]
    if not rated:
        return ""
    best = max(rated, key=lambda r: r.get("ratingCount") or 0)
    return f"rating {best.get('averageRating')} ({best.get('ratingCount')})"


def _availability(group: list[dict]) -> str:
    classes = sorted({(p.get("extras") or {}).get("availability") for p in group} - {None})
    return f"availability {'/'.join(classes)}*" if classes else ""


def _discount(group: list[dict]) -> str:
    for p in sorted(group, key=_price_key):
        instead = (p.get("extras") or {}).get("insteadOf")
        if instead and instead.get("rebate") is not None:
            return f"-{format_price(instead['rebate'])} CHF, was {format_price(instead.get('price'))}*"
    return ""


def _refurbished(group: list[dict]) -> str:
    for p in group:
        if "offertype=refurbished" in (p.get("pageUrl") or "") or \
                "USED_AND_CHECKED" in ((p.get("extras") or {}).get("labels") or []):
            return "refurbished/used offer"
    return ""


def format_row(group: list[dict]) -> str:
    first = group[0]
    cheapest = min(group, key=_price_key)
    parts = [f"{first.get('brand') or '?'} {first.get('name')}", _price_range(group)]
    for extra in (_variant_differences(group), _key_specs(group), _rating(group),
                  _availability(group), _discount(group), _refurbished(group)):
        if extra:
            parts.append(extra)
    parts.append(cheapest.get("pageUrl") or "")
    return "- " + " | ".join(parts)


def format_groups(products: list[dict], top: int, out_path: str | None) -> list[str]:
    by_type: dict[str, list[dict]] = {}
    for p in products:
        by_type.setdefault(p.get("productType") or "(no type)", []).append(p)
    lines = []
    for ptype, items in sorted(by_type.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        groups = merge_variants(items)
        lines.append(f"\n## {ptype}: {len(items)} products, {len(groups)} rows")
        lines += [format_row(g) for g in groups[:top]]
        rest = len(groups) - top
        if rest > 0:
            lines.append(f"+{rest} more rows in {out_path}" if out_path
                         else f"+{rest} more rows (rerun with --out FILE to keep them)")
    return lines


def format_report(doc: dict, top: int, out_path: str | None = None) -> str:
    lines = coverage_lines(doc)
    if doc["status"] != "infeasible":
        lines += format_groups(doc["products"], top, out_path)
        lines.append(FOOTNOTE)
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_report.py`
Expected: `11 passed`.

- [ ] **Step 5: Commit**

```bash
git add skills/galaxus/scripts/galaxus_lib/variants.py skills/galaxus/scripts/galaxus_lib/report.py tests/test_report.py
git commit -m "Add variant merge, JSON document and coverage report"
```

---

### Task 9: Filter and compare

**Files:**
- Create: `skills/galaxus/scripts/galaxus_lib/filtering.py`, `skills/galaxus/scripts/galaxus_lib/compare.py`
- Test: `tests/test_filter_compare.py`

**Interfaces:**
- Consumes: document shape (Task 8), `report.coverage_lines/format_row/render_spec/format_price/FOOTNOTE`, `specs.first_number/FIELD_ORDER`, `merge_variants`, `Page` (Task 5).
- Produces:
  - `filtering.Condition(field, op, value)`; `parse_where(expr: str) -> Condition` (ops `>=`, `<=`, `~` contains, `=` equals; raises `ValueError`); `evaluate(cond, spec: dict | None) -> "match" | "fail" | "unknown"`; `run_filter(doc, conditions, types=()) -> Outcome` with `matched: list, unknown: list, excluded: int, unknown_by_field: dict[str, int], type_excluded: dict[str, int], checked: int`; `format_filter_report(doc, outcome, conditions, top) -> str`.
  - `compare.parse_lookup(text: str) -> tuple[int, tuple[str, float | None]]` for `ID=QUERY[@PRICE]`; `compare.lookup(fetch_for_query, pid, query, price) -> dict | None` (≤ 3 calls); `compare.comparison_table(products: list[dict]) -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/test_filter_compare.py`:
```python
import pytest

from fakes import FakeCatalogue, make_product
from galaxus_lib import compare, filtering, specs


def spec(value, state="stated", source="description", ceiling=False, conflict=None):
    return {"value": value, "state": state, "source": source, "ceiling": ceiling, "conflict": conflict}


def prod(pid, ptype="Smartphones", **fields):
    p = make_product(pid, 100.0 + pid, ptype=ptype)
    p["specs"] = fields
    p["extras"] = None
    return p


def doc(products, status="complete"):
    return {"status": status, "rootTotal": len(products), "calls": 1, "maxCalls": 60, "estimatedCalls": 1,
            "finalTotal": None, "unfilteredTotal": None, "correctedSearchTerm": None, "error": None,
            "bands": [], "histogram": [], "products": products, "language": "en"}


def test_parse_where():
    assert filtering.parse_where("android_version>=17") == filtering.Condition("android_version", ">=", "17")
    assert filtering.parse_where("panel = IPS") == filtering.Condition("panel", "=", "IPS")
    assert filtering.parse_where("cpu~snapdragon").op == "~"
    for bad in ("nonsense", "ram>=lots", "=5"):
        with pytest.raises(ValueError):
            filtering.parse_where(bad)


@pytest.mark.parametrize("cond, s, expected", [
    ("refresh>=144", spec("165 Hz"), "match"),
    ("refresh>=144", spec("60 Hz"), "fail"),
    ("refresh>=144", None, "unknown"),
    ("refresh>=144", spec("120 Hz", ceiling=True), "fail"),      # at most 120
    ("refresh>=144", spec("240 Hz", ceiling=True), "unknown"),   # up to 240: maybe
    ("refresh<=60", spec("120 Hz", ceiling=True), "unknown"),
    ("screen>=6.5", spec('6.9"', conflict='6.9" (properties) / 6.4" (description)'), "unknown"),
    ("panel=ips", spec("IPS"), "match"),
    ("cpu~snapdragon", spec("Qualcomm Snapdragon 6s Gen 4"), "match"),
    ("panel=IPS", spec("VA"), "fail"),
])
def test_evaluate(cond, s, expected):
    assert filtering.evaluate(filtering.parse_where(cond), s) == expected


def test_run_filter_counts_and_type_exclusion():
    products = [prod(1, android_version=spec("17")), prod(2, android_version=spec("16")), prod(3),
                prod(4, ptype="Phone cases")]
    d = doc(products)
    out = filtering.run_filter(d, [filtering.parse_where("android_version>=17")], types=["smartphones"])
    assert [p["id"] for p in out.matched] == [1]
    assert [p["id"] for p in out.unknown] == [3]
    assert out.excluded == 1 and out.checked == 3
    assert out.unknown_by_field == {"android_version": 1}
    assert out.type_excluded == {"Phone cases": 1}


def test_verdict_none_confirmed_when_specs_unknown():
    d = doc([prod(1, android_version=spec("16")), prod(2)])
    conds = [filtering.parse_where("android_version>=17")]
    text = filtering.format_filter_report(d, filtering.run_filter(d, conds), conds, top=15)
    assert "Verdict: none confirmed among 2 checked; 1 have unknown specs (android_version: 1 unknown)." in text


def test_verdict_none_qualify_only_when_complete_and_known():
    d = doc([prod(1, android_version=spec("16"))])
    conds = [filtering.parse_where("android_version>=17")]
    assert "Verdict: none qualify" in filtering.format_filter_report(d, filtering.run_filter(d, conds), conds, 15)
    d["status"] = "partial"
    text = filtering.format_filter_report(d, filtering.run_filter(d, conds), conds, 15)
    assert "Verdict: none confirmed among 1 checked; coverage is partial." in text


def test_parse_lookup():
    assert compare.parse_lookup("20=Acme Phone 20@120") == (20, ("Acme Phone 20", 120.0))
    assert compare.parse_lookup("20=Acme Phone 20") == (20, ("Acme Phone 20", None))
    with pytest.raises(ValueError):
        compare.parse_lookup("Acme Phone 20")


def test_lookup_uses_narrow_band_first_and_at_most_three_calls():
    fake = FakeCatalogue([make_product(i, 100.0 + i) for i in range(1, 60)])
    found = compare.lookup(lambda q: fake, 20, "Acme Phone 20", 120.0)
    assert found["id"] == 20
    assert fake.calls[0] == (114, 126, 50)
    missing = FakeCatalogue([make_product(1, 10.0)])
    assert compare.lookup(lambda q: missing, 99, "x y", 50.0) is None
    assert len(missing.calls) == 3


def test_comparison_table_marks_states():
    a = prod(1, refresh=spec("120 Hz", ceiling=True), panel=spec("IPS", source="properties"))
    b = prod(2, panel=spec("VA"))
    table = compare.comparison_table([a, b])
    assert table.splitlines()[0].startswith("| field | Acme Phone 1 (1) | Acme Phone 2 (2) |")
    assert "| refresh | up to 120 Hz (desc.) | ? |" in table
    assert "| panel | IPS | VA (desc.) |" in table
```

- [ ] **Step 2: Run them to verify they fail**

Run: `py -m pytest tests/test_filter_compare.py`
Expected: FAIL, `ImportError: cannot import name 'compare'`.

- [ ] **Step 3: Implement**

`skills/galaxus/scripts/galaxus_lib/filtering.py`:
```python
"""Spec filters over a search document, with honest unknown counts.

A product fails if any condition fails, is unknown if none fail but one is
unknown (missing value, conflict, or a ceiling that cannot decide), else matches.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import report, specs
from .variants import merge_variants

MATCH, FAIL, UNKNOWN = "match", "fail", "unknown"
_OPS = (">=", "<=", "~", "=")


@dataclass(frozen=True)
class Condition:
    field: str
    op: str
    value: str


@dataclass
class Outcome:
    matched: list = field(default_factory=list)
    unknown: list = field(default_factory=list)
    excluded: int = 0
    unknown_by_field: dict = field(default_factory=dict)
    type_excluded: dict = field(default_factory=dict)
    checked: int = 0


def parse_where(expr: str) -> Condition:
    for op in _OPS:
        if op in expr:
            name, value = (part.strip() for part in expr.split(op, 1))
            if name and value:
                if op in (">=", "<="):
                    float(value)  # raises ValueError for non-numbers
                return Condition(name, op, value)
            break
    raise ValueError(f"cannot parse --where {expr!r}; use FIELD=VALUE, FIELD~TEXT, FIELD>=N or FIELD<=N")


def evaluate(cond: Condition, spec: dict | None) -> str:
    if not spec or spec.get("conflict"):
        return UNKNOWN
    value = spec["value"]
    if cond.op in (">=", "<="):
        number = specs.first_number(value)
        if number is None:
            return UNKNOWN
        want = float(cond.value)
        ok = number >= want if cond.op == ">=" else number <= want
        if spec.get("ceiling"):  # the real value is at most `number`
            return FAIL if cond.op == ">=" and not ok else UNKNOWN
        return MATCH if ok else FAIL
    if spec.get("ceiling"):
        return UNKNOWN
    if cond.op == "=":
        return MATCH if value.strip().lower() == cond.value.lower() else FAIL
    return MATCH if cond.value.lower() in value.lower() else FAIL


def run_filter(doc: dict, conditions: list[Condition], types=()) -> Outcome:
    wanted = {t.lower() for t in types}
    out = Outcome()
    for p in doc["products"]:
        ptype = p.get("productType") or "(no type)"
        if wanted and ptype.lower() not in wanted:
            out.type_excluded[ptype] = out.type_excluded.get(ptype, 0) + 1
            continue
        out.checked += 1
        results = [(c, evaluate(c, (p.get("specs") or {}).get(c.field))) for c in conditions]
        verdicts = {r for _, r in results}
        if FAIL in verdicts:
            out.excluded += 1
        elif UNKNOWN in verdicts:
            out.unknown.append(p)
            for c, r in results:
                if r == UNKNOWN:
                    out.unknown_by_field[c.field] = out.unknown_by_field.get(c.field, 0) + 1
        else:
            out.matched.append(p)
    return out


def format_filter_report(doc: dict, outcome: Outcome, conditions: list[Condition], top: int) -> str:
    lines = report.coverage_lines(doc)
    if outcome.type_excluded:
        excluded = ", ".join(f"{t} ({n})" for t, n in sorted(outcome.type_excluded.items(), key=lambda kv: -kv[1]))
        lines.append(f"Excluded by product type: {excluded}. Coverage claims apply to the remaining types only.")
    criteria = ", ".join(f"{c.field}{c.op}{c.value}" for c in conditions) or "(no conditions)"
    unknown = "; ".join(f"{f}: {n} unknown" for f, n in outcome.unknown_by_field.items())
    lines.append(f"Filter {criteria}: {outcome.checked} checked, {len(outcome.matched)} match, "
                 f"{len(outcome.unknown)} unknown{f' ({unknown})' if unknown else ''}, {outcome.excluded} excluded.")
    if not outcome.matched:
        if doc["status"] == "complete" and not outcome.unknown:
            lines.append("Verdict: none qualify (coverage complete and the specs are known for every candidate).")
        else:
            reasons = []
            if doc["status"] != "complete":
                reasons.append(f"coverage is {doc['status']}")
            if outcome.unknown:
                reasons.append(f"{len(outcome.unknown)} have unknown specs ({unknown})")
            lines.append(f"Verdict: none confirmed among {outcome.checked} checked; " + "; ".join(reasons) + ".")
    for title, items in (("Matches", outcome.matched), ("Unknown (could qualify)", outcome.unknown)):
        if not items:
            continue
        groups = merge_variants(items)
        lines.append(f"\n## {title}: {len(items)} products, {len(groups)} rows")
        lines += [report.format_row(g) for g in groups[:top]]
        if len(groups) > top:
            lines.append(f"+{len(groups) - top} more rows")
    lines.append(report.FOOTNOTE)
    return "\n".join(lines)
```

`skills/galaxus/scripts/galaxus_lib/compare.py`:
```python
"""Spec table across chosen products, with best-effort lookup of ids missing from FILE.

Galaxus search does not find products by id (probed 2026-11-11), so a missing
id needs a query (brand + name) and ideally its price: ID=QUERY[@PRICE].
"""
from __future__ import annotations

import math

from . import report, specs


def parse_lookup(text: str) -> tuple[int, tuple[str, float | None]]:
    if "=" not in text:
        raise ValueError(f"--lookup {text!r}: expected ID=BRAND NAME[@PRICE]")
    pid, rest = text.split("=", 1)
    query, _, price = rest.rpartition("@") if "@" in rest else (rest, "", "")
    return int(pid), (query.strip(), float(price) if price else None)


def lookup(fetch_for_query, pid: int, query: str, price: float | None) -> dict | None:
    fetch = fetch_for_query(query)
    bands = [(None, None)]
    if price:
        bands = [(max(1, math.floor(price * 0.95)), math.ceil(price * 1.05)),
                 (max(1, math.floor(price * 0.8)), math.ceil(price * 1.2)),
                 (None, None)]
    for lo, hi in bands:
        page = fetch(lo, hi, 50)
        for p in page.products:
            if p.get("id") == pid:
                item = dict(p)
                item["extras"] = page.extras.get(pid)
                return item
    return None


def comparison_table(products: list[dict]) -> str:
    if not products:
        return "No products to compare."
    head = ["field"] + [f"{p.get('brand', '')} {p.get('name', '')} ({p['id']})".strip() for p in products]
    rows = [["price (CHF)"] + [report.format_price((p.get("priceIfAvailable") or {}).get("amountInclusive"))
                               for p in products]]
    fields = [f for f in specs.FIELD_ORDER if any(f in (p.get("specs") or {}) for p in products)]
    for f in fields:
        rows.append([f] + [report.render_spec((p.get("specs") or {}).get(f)) for p in products])
    rows.append(["availability*"] + [(p.get("extras") or {}).get("availability") or "n/a" for p in products])
    rows.append(["link"] + [p.get("pageUrl", "") for p in products])
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(cell.replace("|", "/") for cell in row) + " |" for row in rows]
    return "\n".join(lines + ["", report.FOOTNOTE])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_filter_compare.py`
Expected: `17 passed`.

- [ ] **Step 5: Commit**

```bash
git add skills/galaxus/scripts/galaxus_lib/filtering.py skills/galaxus/scripts/galaxus_lib/compare.py tests/test_filter_compare.py
git commit -m "Add spec filter with unknown counts and compare table"
```

---

### Task 10: CLI

**Files:**
- Modify: `skills/galaxus/scripts/galaxus.py` (replace the Task 1 stub entirely)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `galaxus.main(argv) -> int`, `galaxus.make_client() -> Client` (tests monkeypatch it), `galaxus.make_fetch(client, query, lang) -> Fetch`, `galaxus.AGENT_INFO`, exit-code constants. Subcommands: `count`, `search`, `filter`, `compare`.

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:
```python
import json

import pytest

import galaxus
from fakes import FakeCatalogue, FakeClient, make_product
from galaxus_lib import transport


def phones(n):
    return [make_product(i, 100.0 + i, description=f"Phone {i} with 8 GB RAM and Android 16.")
            for i in range(1, n + 1)]


@pytest.fixture
def use_catalogue(monkeypatch):
    def install(products, **kw):
        cat = FakeCatalogue(products, **kw)
        monkeypatch.setattr(galaxus, "make_client", lambda: FakeClient(cat))
        return cat
    return install


def test_version(capsys):
    with pytest.raises(SystemExit) as info:
        galaxus.main(["--version"])
    assert info.value.code == 0
    assert capsys.readouterr().out.strip() == f"galaxus-skill {galaxus.__version__}"


def test_count(use_catalogue, capsys):
    use_catalogue(phones(30))
    assert galaxus.main(["count", "phone"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "30"


def test_search_prints_report_and_writes_document(use_catalogue, tmp_path, capsys):
    use_catalogue(phones(30))
    out = tmp_path / "r.json"
    assert galaxus.main(["search", "phone", "--out", str(out), "--top", "5"]) == 0
    text = capsys.readouterr().out
    assert text.startswith("Coverage: complete. 30 unique products")
    assert f"+25 more rows in {out}" in text
    doc = json.loads(out.read_text("utf-8"))
    assert (doc["query"], doc["language"], len(doc["products"])) == ("phone", "en", 30)
    assert doc["products"][0]["specs"]["android_version"]["value"] == "16"
    assert doc["timestamp"].endswith("Z")


def test_unreachable_exits_2(monkeypatch, capsys):
    class Down:
        def search_products(self, *a, **k):
            raise transport.TransportError("network error: down")
    monkeypatch.setattr(galaxus, "make_client", lambda: Down())
    assert galaxus.main(["search", "phone"]) == 2
    assert "unreachable" in capsys.readouterr().err


def test_tool_input_error_exits_3(monkeypatch):
    class Rejects:
        def search_products(self, *a, **k):
            raise transport.ToolInputError("Invalid price range")
    monkeypatch.setattr(galaxus, "make_client", lambda: Rejects())
    assert galaxus.main(["count", "phone"]) == 3


def test_bad_arguments_exit_3():
    for argv in (["search"], ["search", "x", "--min", "0"], ["search", "x", "--min", "9", "--max", "5"]):
        try:
            code = galaxus.main(argv)
        except SystemExit as info:
            code = info.code
        assert code == 3, argv


def test_error_message_mid_run_exits_4_with_checkpoint(use_catalogue, tmp_path, capsys):
    use_catalogue(phones(120), error_on_call=2)
    out = tmp_path / "r.json"
    assert galaxus.main(["search", "phone", "--out", str(out)]) == 4
    assert "Coverage: failed." in capsys.readouterr().out
    doc = json.loads(out.read_text("utf-8"))
    assert doc["status"] == "failed" and len(doc["products"]) == 50


def test_filter_verdicts(use_catalogue, tmp_path, capsys):
    use_catalogue(phones(30))
    out = tmp_path / "r.json"
    galaxus.main(["search", "phone", "--out", str(out)])
    capsys.readouterr()
    assert galaxus.main(["filter", "--from", str(out), "--where", "android_version>=17"]) == 0
    assert "Verdict: none qualify" in capsys.readouterr().out
    assert galaxus.main(["filter", "--from", str(out), "--where", "ram>=8"]) == 0
    assert "30 checked, 30 match" in capsys.readouterr().out
    assert galaxus.main(["filter", "--from", str(out), "--where", "nonsense"]) == 3


def test_compare_table_lookup_and_language_refusal(use_catalogue, tmp_path, capsys):
    use_catalogue(phones(30))
    out = tmp_path / "r.json"
    galaxus.main(["search", "phone", "--max", "115", "--out", str(out)])  # ids 1..15 only
    capsys.readouterr()
    code = galaxus.main(["compare", "--from", str(out), "--ids", "1,20,999",
                         "--lookup", "20=Acme Phone 20@120"])
    text = capsys.readouterr().out
    assert code == 0
    assert "Acme Phone 1 (1)" in text and "Acme Phone 20 (20)" in text
    assert "999: not in FILE" in text
    assert galaxus.main(["compare", "--from", str(out), "--ids", "1", "--lang", "de"]) == 3
```

- [ ] **Step 2: Run them to verify they fail**

Run: `py -m pytest tests/test_cli.py`
Expected: FAIL (`AttributeError: module 'galaxus' has no attribute 'make_client'` and similar).

- [ ] **Step 3: Replace `galaxus.py`**

`skills/galaxus/scripts/galaxus.py`:
```python
#!/usr/bin/env python3
"""Exhaustive product search on Galaxus (galaxus.ch) through its public MCP endpoint.

Stdlib only, Python >= 3.10. See ../SKILL.md, or run `galaxus.py -h`.
Exit codes: 0 ok (also "infeasible"), 2 endpoint unreachable, 3 invalid input,
4 Galaxus search error or failure mid-run (partial report printed).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from galaxus_lib import compare, filtering, meta, report, specs, transport  # noqa: E402
from galaxus_lib import search as searchmod  # noqa: E402

__version__ = "0.1.0"
AGENT_INFO = f"galaxus-skill/{__version__}"
LANGUAGES = ("en", "de", "fr", "it", "nl")
EXIT_OK, EXIT_UNREACHABLE, EXIT_INPUT, EXIT_SEARCH = 0, 2, 3, 4


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # usage errors are invalid input (3), not "unreachable" (2)
        self.print_usage(sys.stderr)
        self.exit(EXIT_INPUT, f"{self.prog}: error: {message}\n")


def make_client() -> transport.Client:
    return transport.Client(AGENT_INFO)


def make_fetch(client, query: str, lang: str):
    def fetch(lo, hi, first):
        result = client.search_products(query, lang, first=first, min_price=lo, max_price=hi)
        payload = result["payload"]
        return searchmod.Page(total=payload.get("totalCount", 0), products=payload.get("products") or [],
                              corrected=payload.get("correctedSearchTerm"), error=payload.get("errorMessage"),
                              extras=meta.product_extras(result.get("meta")))
    return fetch


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: str, doc: dict) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _fail(code: int, message: str) -> int:
    print(message, file=sys.stderr)
    return code


def _price(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("price must be an integer") from None
    if not 1 <= value <= 1_000_000:
        raise argparse.ArgumentTypeError("price must be from 1 to 1000000")
    return value


# ---------------------------------------------------------------- commands

def cmd_count(args) -> int:
    try:
        page = make_fetch(make_client(), args.query, args.lang)(args.min, args.max, 1)
    except transport.TransportError as e:
        return _fail(EXIT_UNREACHABLE, f"Galaxus endpoint unreachable: {e}")
    except transport.ToolInputError as e:
        return _fail(EXIT_INPUT, f"Galaxus rejected the input: {e}")
    if page.error:
        print(f"Galaxus search error: {page.error} (a failed search, not zero results)")
        return EXIT_SEARCH
    print(page.total)
    if page.corrected:
        print(f'Note: Galaxus spell-corrected the query to "{page.corrected}".')
    return EXIT_OK


def cmd_search(args) -> int:
    lo, hi = args.min or 1, args.max or 1_000_000
    if lo > hi:
        return _fail(EXIT_INPUT, "--min must not exceed --max")
    fetch = make_fetch(make_client(), args.query, args.lang)
    cache: dict = {}

    def document(res):
        return report.build_document(res, args.query, args.lang, __version__, _now(), cache)

    def checkpoint(res):
        if args.out:
            _write_json(args.out, document(res))

    try:
        res = searchmod.search(fetch, lo, hi, args.max_calls, on_update=checkpoint)
    except transport.TransportError as e:
        return _fail(EXIT_UNREACHABLE, f"Galaxus endpoint unreachable: {e}")
    except transport.ToolInputError as e:
        return _fail(EXIT_INPUT, f"Galaxus rejected the input: {e}")
    except searchmod.SearchFailed as e:
        doc = document(e.partial)
        if args.out:
            _write_json(args.out, doc)
        print(report.format_report(doc, args.top, args.out))
        return EXIT_SEARCH
    doc = document(res)
    if args.out:
        _write_json(args.out, doc)
    print(report.format_report(doc, args.top, args.out))
    return EXIT_OK


def cmd_filter(args) -> int:
    doc = _read_json(args.source)
    try:
        conditions = [filtering.parse_where(w) for w in args.where]
    except ValueError as e:
        return _fail(EXIT_INPUT, str(e))
    outcome = filtering.run_filter(doc, conditions, args.type)
    print(filtering.format_filter_report(doc, outcome, conditions, args.top))
    return EXIT_OK


def cmd_compare(args) -> int:
    doc = _read_json(args.source)
    lang = doc["language"]
    if args.lang and args.lang != lang:
        return _fail(EXIT_INPUT, f"FILE was searched with --lang {lang}; drop --lang or search again with --lang {args.lang}")
    try:
        ids = [int(x) for x in args.ids.split(",") if x.strip()]
        lookups = dict(compare.parse_lookup(s) for s in args.lookup)
    except ValueError as e:
        return _fail(EXIT_INPUT, str(e))
    by_id = {p["id"]: p for p in doc["products"]}
    found, notes, client = [], [], None
    for pid in ids:
        if pid in by_id:
            found.append(by_id[pid])
            continue
        if pid not in lookups:
            notes.append(f"{pid}: not in FILE (pass --lookup {pid}=BRAND NAME@PRICE to search for it)")
            continue
        client = client or make_client()
        query, price = lookups[pid]
        try:
            product = compare.lookup(lambda q: make_fetch(client, q, lang), pid, query, price)
        except (transport.TransportError, transport.ToolInputError) as e:
            notes.append(f"{pid}: lookup failed ({e})")
            continue
        if product is None:
            notes.append(f"{pid}: not found (best-effort)")
            continue
        product["specs"] = {f: s.to_dict() for f, s in specs.extract(product, lang).items()}
        found.append(product)
    print(compare.comparison_table(found))
    for note in notes:
        print(note)
    return EXIT_OK


# ------------------------------------------------------------------ parser

def _query_options(p) -> None:
    p.add_argument("query")
    p.add_argument("--lang", choices=LANGUAGES, default="en")
    p.add_argument("--min", type=_price, help="minimum price in CHF (integer, inclusive)")
    p.add_argument("--max", type=_price, help="maximum price in CHF (integer, inclusive)")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="galaxus.py", description="Exhaustive Galaxus product search via https://mcp.galaxus.ch/")
    parser.add_argument("--version", action="version", version=f"galaxus-skill {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("count", help="one call; print Galaxus totalCount")
    _query_options(p)
    p.set_defaults(func=cmd_count)

    p = sub.add_parser("search", help="exhaustive search with a coverage report")
    _query_options(p)
    p.add_argument("--max-calls", type=int, default=60)
    p.add_argument("--top", type=int, default=15, help="rows per product type in the printed report")
    p.add_argument("--out", help="write the full JSON document here (checkpointed after every call)")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("filter", help="filter a search document by specs, with unknown counts")
    p.add_argument("--from", dest="source", required=True)
    p.add_argument("--where", action="append", default=[], help="FIELD>=N, FIELD<=N, FIELD=VALUE or FIELD~TEXT")
    p.add_argument("--type", action="append", default=[], help="keep only this productType (repeatable)")
    p.add_argument("--top", type=int, default=15)
    p.set_defaults(func=cmd_filter)

    p = sub.add_parser("compare", help="spec table across product ids")
    p.add_argument("--from", dest="source", required=True)
    p.add_argument("--ids", required=True, help="comma-separated product ids")
    p.add_argument("--lookup", action="append", default=[], help="ID=BRAND NAME[@PRICE] for ids not in FILE")
    p.add_argument("--lang", choices=LANGUAGES)
    p.set_defaults(func=cmd_compare)
    return parser


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the whole suite**

Run: `py -m pytest`
Expected: all tests pass (test_live is added in Task 11).

- [ ] **Step 5: Commit**

```bash
git add skills/galaxus/scripts/galaxus.py tests/test_cli.py
git commit -m "Add galaxus.py CLI: count, search, filter, compare"
```

---

### Task 11: Live contract tests

**Files:**
- Create: `tests/test_live.py`

**Interfaces:**
- Consumes: `transport.Client`, `meta.product_extras`, `search.search`, `galaxus.make_fetch`, `galaxus.AGENT_INFO`.

- [ ] **Step 1: Write the live tests**

`tests/test_live.py`:
```python
"""Opt-in contract checks against the real endpoint: GALAXUS_LIVE=1 py -m pytest tests/test_live.py"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

import galaxus
from galaxus_lib import meta, transport
from galaxus_lib.search import search

pytestmark = pytest.mark.skipif(os.environ.get("GALAXUS_LIVE") != "1",
                                reason="set GALAXUS_LIVE=1 to run live contract tests")


@pytest.fixture(scope="module")
def client():
    return transport.Client(galaxus.AGENT_INFO)


def test_price_shape_and_meta_availability(client):
    result = client.search_products("Redmi 17", "en", first=50)
    priced = [p for p in result["payload"]["products"] if p["priceIfAvailable"]]
    assert priced and all(p["priceIfAvailable"]["currency"] == "CHF" for p in priced)
    assert any(e["availability"] for e in meta.product_extras(result["meta"]).values())


def test_bounds_are_inclusive(client):
    products = client.search_products("Redmi 17", "en", first=50)["payload"]["products"]
    p = next(p for p in products
             if p["priceIfAvailable"] and float(p["priceIfAvailable"]["amountInclusive"]).is_integer())
    price = int(p["priceIfAvailable"]["amountInclusive"])
    band = client.search_products("Redmi 17", "en", first=50, min_price=price, max_price=price)
    assert p["id"] in {x["id"] for x in band["payload"]["products"]}


def test_min_above_max_is_input_error(client):
    with pytest.raises(transport.ToolInputError):
        client.search_products("Redmi 17", "en", min_price=5, max_price=2)


def test_redmi17_search_is_complete():
    res = search(galaxus.make_fetch(transport.Client(galaxus.AGENT_INFO), "Redmi 17", "en"), max_calls=60)
    assert res.status == "complete"
    assert len(res.products) == res.root_total or res.final_total != res.root_total


def test_cli_count_smoke():
    script = Path(galaxus.__file__)
    out = subprocess.run([sys.executable, str(script), "count", "smartphone"],
                         capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0
    assert int(out.stdout.split()[0]) > 1000
```

- [ ] **Step 2: Verify skipped offline, passing live**

Run: `py -m pytest tests/test_live.py`
Expected: `5 skipped`.

Run (Git Bash): `GALAXUS_LIVE=1 py -m pytest tests/test_live.py -v`
Expected: `5 passed`. If `test_redmi17_search_is_complete` reports `partial`, print the bands (`py skills/galaxus/scripts/galaxus.py search "Redmi 17"`) and investigate before changing anything; a capped band at one price would be new server behaviour and belongs in the spec.

- [ ] **Step 3: Commit**

```bash
git add tests/test_live.py
git commit -m "Add opt-in live contract tests"
```

---

### Task 12: SKILL.md and references

**Files:**
- Modify: `skills/galaxus/SKILL.md` (write the body; keep the Task 1 frontmatter)
- Create: `skills/galaxus/references/manual-search.md`, `skills/galaxus/references/spec-fields.md`, `skills/galaxus/references/page-check.md`

Use `superpowers:writing-skills` / `mattpocock-skills:writing-for-agents` for the wording pass. Keep `SKILL.md` under ~150 lines; details go to references.

- [ ] **Step 1: Write `SKILL.md`**

Body after the frontmatter:
````markdown
# Galaxus product search

Galaxus has an official MCP endpoint (`https://mcp.galaxus.ch/`) with one tool,
`search_products`: free-text query, optional integer price range, at most 50
results per call, no pagination. A single call shows a few products out of
thousands. This skill searches **exhaustively** by splitting the price range,
reports how complete the search was, and extracts specs from the free-text
records.

## 1. Choose the path (in this order)

Paths below are relative to this file's directory, never the working directory.

1. Run `scripts/galaxus.py --version` with `python3`, then `py`, then `python`
   (first that works). Then run `scripts/galaxus.py count smartphone`. Exit 0 →
   **script path**. Use it even when the `search_products` MCP tool is also available.
2. Otherwise, if the `search_products` MCP tool is available → **manual path**:
   follow `references/manual-search.md`.
3. Otherwise tell the user the setup is missing and point them to the README
   (https://github.com/daniel-locatelli/galaxus-skill).

## 2. Formulate the query

- Search the **category** ("smartphone", "monitor 27 inch", "laptop") plus the
  user's price range, then filter on extracted specs. Do **not** put spec
  tokens (OS versions, years, model-number fragments like "17") into the query
  unless the user names a model: "Android 17 smartphone" matches "Redmi 17"
  and misses phones whose record never says "17".
- One search uses one language: the conversation language if it is en, de, fr,
  it or nl, else en. Pass it as `--lang`.

## 3. Run (script path)

```bash
python3 scripts/galaxus.py search "smartphone" --max 300 --lang en --out <scratch>/phones.json
python3 scripts/galaxus.py filter --from <scratch>/phones.json --type Smartphones --where "android_version>=17"
python3 scripts/galaxus.py compare --from <scratch>/phones.json --ids 73036751,75040390
```

- `search` prints a coverage line, then rows per product type. `--out` keeps
  everything (write it to a scratch/temp directory).
- **Infeasible** (too many matches for the call budget): the script prints a
  price histogram and exits 0. Narrow by brand in the query, by a tighter price
  range, or ask the user, showing them the histogram. Do not raise
  `--max-calls` above 60 without asking the user.
- `filter --where` takes `FIELD>=N`, `FIELD<=N`, `FIELD=VALUE`, `FIELD~TEXT`,
  repeatable; `--type` keeps only that product type and reports what it
  dropped. Field names: `references/spec-fields.md`.
- `compare` needs ids from FILE; for an id that is not in FILE add
  `--lookup ID=BRAND NAME@PRICE`.
- Exit codes: 2 endpoint unreachable → switch to the manual path;
  3 invalid input → fix the arguments; 4 Galaxus search error or failure
  mid-run → report it as a **failed search, not zero results**, with the
  partial report. Do not fall back to the manual path on 4 (same server).

## 4. Report to the user

- Always quote the coverage line (complete / partial / infeasible / failed,
  with its numbers).
- Never say a product does not exist, or that none qualify, unless coverage is
  complete **and** the spec is known for every candidate. The `filter` verdict
  line already follows this rule; repeat it, e.g. "none confirmed among 412
  checked; 160 have unknown Android version".
- Mention spell correction when the report has a "spell-corrected" note.
- When you drop product types (cases, accessories), say what was excluded;
  coverage claims apply to the remaining types.
- Keep the spec marks: *(desc.)* weaker than properties, *(inferred)*,
  *up to* = ceiling, *?* = unknown, *conflict* = properties and description disagree.
- Availability classes and discounts are "per Galaxus data (undocumented
  field)". Show availability classes raw (`TICK`, `QUARTER`, …); do not
  invent a meaning for them.
- Flag refurbished/used offers.
- Link to the Galaxus `pageUrl`; purchases happen on galaxus.ch.

## 5. Optional: check product pages

Only with a browser tool, only for the final shortlist (max 5): follow
`references/page-check.md`.
````

- [ ] **Step 2: Write `references/manual-search.md`**

```markdown
# Manual search with the `search_products` MCP tool

Use only when `scripts/galaxus.py` cannot run. The same algorithm, by hand,
with a smaller budget.

What the host shows you: the JSON text `{correctedSearchTerm, totalCount,
products[], errorMessage?}`. The undocumented `_meta` block (availability,
discounts) is not shown (checked in Claude Code, 2026-11-11), so on this path
say "availability and discounts: not available on this path".

## Arguments

Always pass `query`, `language` (en/de/fr/it/nl), `agentInfo` (your client
name and model), and `first: 50`. Price bounds `minPrice`/`maxPrice` are
integers 1…1,000,000 and **inclusive**. Do not send `userIntent`.

## Procedure

1. Root call over the user's range. If `errorMessage` is present, the search
   failed: say so; it is not zero results.
2. Gate: if `totalCount` > 500, do not split; ask the user to narrow (brand in
   the query, tighter price range).
3. Keep a list of bands to do and a set of product ids seen.
4. For a band `[a, b]` with `totalCount` > 50: take the median price of the
   returned products, rounded, clamped to `a < m < b`; split into `[a, m]` and
   `[m, b]`. The shared endpoint `m` matters: prices like 193.97 fall between
   integer bounds and are lost with `[a, m]`, `[m+1, b]`.
5. A band with `b − a ≤ 1` and more than 50 products is *capped*: keep its 50,
   note it.
6. Stop after 20 calls; list the bands not searched as *uncovered*.
7. Coverage = number of **unique ids** seen vs the root `totalCount`. Never sum
   band counts (shared endpoints double-count).

Then apply the output rules in SKILL.md section 4, reading specs as described
in `spec-fields.md` (properties first, then description).
```

- [ ] **Step 3: Write `references/spec-fields.md`**

```markdown
# Spec fields

## States

- **stated**: in `properties`, or in `description` next to a field keyword.
- **inferred**: derived, e.g. `network: 5G` from a name ending in "5G", or
  `android_version` from a vendor skin (table below).
- **unknown**: absent. Shown as `?`.

`properties` win over `description`. When both give a value and they differ,
the properties value is kept and the field shows
`conflict: 6.9" (properties) / 6.99" (description)`. Description-only values
are marked *(desc.)* because they are weaker.

## Ceilings

A value right after "up to", "bis zu", "jusqu'à", "fino a", "tot", "memory
extension", "configurations", or followed by "expandable"/"erweiterbar", is a
**ceiling**, not this variant's value ("bis zu 12 GB RAM und 512 GB Speicher"
makes both values ceilings). Filters treat a ceiling as an upper bound:
`refresh>=144` fails on "up to 120 Hz" and is unknown on "up to 240 Hz".

## `properties` schemas (comma-separated, seen 2026-11-11)

| Product type contains | Fields in order |
|---|---|
| smartphone | storage, colour, screen, SIM, network |
| notebook / laptop | screen, storage, RAM, keyboard layout, CPU |
| monitor | resolution, screen |

Order can vary and fields can be missing, so tokens are matched by pattern;
position only separates storage from RAM (laptops: storage first). Other
product types get generic patterns only (screen, resolution, SIM, network,
keyboard, CPU).

## Fields (filter names)

`os`, `android_version`, `cpu`, `ram`, `storage`, `screen` (inches),
`resolution` (`W x H`), `refresh` (Hz; GHz is CPU clock), `panel`,
`brightness` (nits, also from cd/m²), `response` (ms), `battery` (mAh),
`charging` (W, only next to a charging keyword, not speaker watts), `camera`
(MP, main), `weight`, `network` (4G/5G), `sim`, `ip` (e.g. IP66/IP68),
`ports`, `keyboard`, `colour`.

Numbers: `6,99` (decimal comma) and `8,340` / `3.840` / `8'340`
(thousands) are read by language.

## Android base of vendor skins (inferred, maintained by hand)

| OS | Android |
|---|---|
| HyperOS 2 | 15 |
| HyperOS 3 | 16 |
| One UI 7 | 15 |
| One UI 8 | 16 |

Other versions stay unknown until added here and in `specs.py`
(`_ANDROID_BASE`), with a source.
```

- [ ] **Step 4: Write `references/page-check.md`**

```markdown
# Product-page check

Only when a browser tool is available, and only for the final shortlist
(max 5 products). Plain HTTP fetches of galaxus.ch are usually blocked (403),
so expect *blocked* without a real browser.

Per product page (`pageUrl`), read the page **text** (not screenshots) and
extract:

| Field | What to look for |
|---|---|
| availability | the stock/availability text near the price |
| delivery | the delivery estimate ("delivered between …") |
| seller | Galaxus itself or a marketplace seller |
| price | current page price vs the API price; flag any difference |

Label each field *checked*, *not checked* or *blocked*:

- *blocked*: the page needs JavaScript you cannot run, or shows bot
  protection. Never solve captchas.
- *not checked*: the page loaded but the field was not visible.

Expect 5–15 s and a few thousand tokens per page.
```

- [ ] **Step 5: Verify and commit**

Run: `py -m pytest tests/test_version.py`
Expected: `1 passed` (frontmatter version intact).

```bash
git add skills/galaxus/SKILL.md skills/galaxus/references
git commit -m "Write SKILL.md and reference docs"
```

---

### Task 13: README, evals, CI

**Files:**
- Create: `README.md`, `evals/cases.md`, `.github/workflows/test.yml`

- [ ] **Step 1: Write CI**

`.github/workflows/test.yml`:
```yaml
name: test
on:
  push:
  pull_request:
jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        python: ["3.10", "3.13"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: python -m pip install pytest
      - run: python -m pytest
```

- [ ] **Step 2: Write `evals/cases.md`**

```markdown
# Evals

Run each prompt 3 times **with** the skill and 3 times **without** it (fresh
session each). Record the transcript path and pass/fail per criterion.

## Cases

1. "Find me an Android 17 smartphone under 300 CHF on Galaxus."
2. "I want a 27-inch monitor with at least 144 Hz for under 250 CHF from Galaxus."
3. "Show me every smartphone Galaxus sells." (too broad)

## Pass criteria (all must hold)

- The answer quotes a coverage line (complete / partial / infeasible / failed).
- No "does not exist" / "none available" claim under partial coverage or unknown specs.
- No spec tokens in the query ("17", "144", "Android 17" as query text).
- Case 1: an Android 17 phone under 300 CHF is found if one exists. Check by
  hand on galaxus.ch (Chrome; plain HTTP is blocked) and note the result here.
- Case 3: the answer reports infeasibility and offers ways to narrow (brand, price) instead of listing a few products.

## Results

| Date | Case | Skill | Run | Coverage line | No false "none" | No spec tokens | Found | Notes |
|---|---|---|---|---|---|---|---|---|
```

- [ ] **Step 3: Write `README.md`**

Sections and content:

```markdown
# galaxus-skill

An agent skill for **exhaustive** product search on [Galaxus](https://www.galaxus.ch)
through its official MCP endpoint (`https://mcp.galaxus.ch/`, announced
2026-11-11: <https://www.galaxus.ch/en/page/galaxus-introduces-mcp-interface-for-ai-assistants-44216>).

The endpoint returns at most 50 products per call, with no pagination, sort or
spec filters. Asked "is there an Android 17 phone under 300 CHF?", an agent
sees 50 of thousands of matches and often answers "no". This skill:

- splits the price range until every band fits in one call, and reports
  coverage (complete / partial / infeasible) from unique product ids;
- extracts specs from the free-text records with *stated / inferred / unknown*
  states, ceilings ("up to") and conflicts;
- refuses "none exist" unless coverage is complete and the spec is known;
- shows availability and discounts from an undocumented field, labelled as such.

## Install

### Claude Code

    /plugin marketplace add daniel-locatelli/galaxus-skill
    /plugin install galaxus@galaxus-skill

or copy `skills/galaxus/` to `~/.claude/skills/galaxus/`.

Optional, only for the manual fallback (when Python cannot run):

    claude mcp add --transport http galaxus https://mcp.galaxus.ch/

### claude.ai

Zip the `skills/galaxus/` folder and upload it under Settings → Capabilities →
Skills. Add `https://mcp.galaxus.ch/` as a custom connector for the manual
path. Note: the code-execution sandbox may block network access to
`mcp.galaxus.ch`; then the skill uses the connector (manual path).

### Codex and other MCP clients

Point the client at `https://mcp.galaxus.ch/` (HTTP transport, no auth) and
place `skills/galaxus/` where the client loads skills or instructions.

## Requirements

Python ≥ 3.10, standard library only. On Windows the `py` launcher works;
output is UTF-8.

## Use

    python3 skills/galaxus/scripts/galaxus.py search "monitor 27 inch" --max 250 --out monitors.json
    python3 skills/galaxus/scripts/galaxus.py filter --from monitors.json --where "refresh>=144"

## Fair use

Calls are sequential with a short delay and a default budget of 60 calls per
search; `agentInfo` identifies the skill as `galaxus-skill/<version>`. Galaxus
terms of use for automated MCP use were not found at the time of writing.

## Development

    py -m pip install pytest
    py -m pytest                                  # offline
    GALAXUS_LIVE=1 py -m pytest tests/test_live.py  # live contract checks
    py tests/record_fixtures.py                   # re-record fixtures

Design: `docs/superpowers/specs/2026-11-11-galaxus-skill-design.md`.

## Licence

MIT
```

Before committing, open the announcement URL and the claude.ai skills/connector settings path only if you can verify them; if a UI path cannot be checked, write "see the claude.ai help on skills" instead of a guessed menu path.

- [ ] **Step 4: Verify and commit**

Run: `py -m pytest`
Expected: all offline tests pass, live tests skipped.

```bash
git add README.md evals .github
git commit -m "Add README, eval cases and CI workflow"
```

---

### Task 14: End-to-end verification and evals

Use `superpowers:verification-before-completion`.

- [ ] **Step 1: Full suite on 3.12 (local)**

Run: `py -m pytest -v` → all pass, 5 skipped.
Run: `GALAXUS_LIVE=1 py -m pytest tests/test_live.py -v` → 5 passed.

- [ ] **Step 2: Real runs through the CLI**

```bash
SCR="$(mktemp -d)"
py skills/galaxus/scripts/galaxus.py search "smartphone" --max 300 --out "$SCR/phones.json"; echo "exit $?"
py skills/galaxus/scripts/galaxus.py filter --from "$SCR/phones.json" --type Smartphones --where "android_version>=17"
py skills/galaxus/scripts/galaxus.py search "monitor 27 inch" --max 250 --out "$SCR/mon.json"; echo "exit $?"
py skills/galaxus/scripts/galaxus.py filter --from "$SCR/mon.json" --where "refresh>=144"
py skills/galaxus/scripts/galaxus.py search "smartphone"; echo "exit $?"
```
Expected: the first two searches end with a coverage line (probably *infeasible* for "smartphone" ≤ 300 CHF, since ~466k matches; then narrow by brand, e.g. `"Xiaomi smartphone" --max 300`, and record what coverage that gives); the broad search prints the histogram and exits 0. Read the reports by eye: spot-check 5 spec values against the descriptions in the JSON.

- [ ] **Step 3: Evals**

Run the three `evals/cases.md` prompts, 3× with and 3× without the skill (fresh sessions), fill in the results table, and check case 1 by hand on galaxus.ch in Chrome. Commit:

```bash
git add evals/cases.md
git commit -m "Record first eval results"
```

- [ ] **Step 4: Hand over**

Report to Daniel: test counts, live results, eval table, and the open items that remain (Galaxus terms of use, claude.ai sandbox reachability, Digitec coverage). Then `superpowers:finishing-a-development-branch`. Do not create the GitHub repo or push without his go-ahead.
