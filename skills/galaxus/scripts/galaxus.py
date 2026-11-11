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

from galaxus_lib import compare, filtering, meta, report, transport  # noqa: E402
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
        doc = json.load(fh)
    if not isinstance(doc, dict) or not isinstance(doc.get("products"), list):
        raise ValueError("not a galaxus.py search document (no products list)")
    return doc


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
    try:
        doc = _read_json(args.source)
    except (OSError, ValueError) as e:
        return _fail(EXIT_INPUT, f"cannot read {args.source}: {e}")
    try:
        conditions = [filtering.parse_where(w) for w in args.where]
    except ValueError as e:
        return _fail(EXIT_INPUT, str(e))
    outcome = filtering.run_filter(doc, conditions, args.type)
    print(filtering.format_filter_report(doc, outcome, conditions, args.top))
    return EXIT_OK


def cmd_compare(args) -> int:
    try:
        doc = _read_json(args.source)
    except (OSError, ValueError) as e:
        return _fail(EXIT_INPUT, f"cannot read {args.source}: {e}")
    lang = doc.get("language", "en")
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
            product = compare.lookup(lambda q: make_fetch(client, q, lang), pid, query, price, lang)
        except (transport.TransportError, transport.ToolInputError) as e:
            notes.append(f"{pid}: lookup failed ({e})")
            continue
        if product is None:
            notes.append(f"{pid}: not found (best-effort)")
            continue
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
