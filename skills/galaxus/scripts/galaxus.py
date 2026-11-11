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
MAX_LOOKUPS = 20
DOCUMENT_KEYS = ("status", "bands", "histogram", "products", "version", "language")


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # usage errors are invalid input (3), not "unreachable" (2)
        self.print_usage(sys.stderr)
        self.exit(EXIT_INPUT, f"{self.prog}: error: {message}\n")


def make_client() -> transport.Client:
    return transport.Client(AGENT_INFO)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_payload(payload) -> None:
    """A missing totalCount must never read as "0 found": raise TransportError on any odd shape."""
    def bad(why):
        raise transport.TransportError(f"unexpected response shape: {why}")
    if not isinstance(payload, dict):
        bad(f"payload is {type(payload).__name__}, not an object")
    if payload.get("errorMessage"):
        return  # a failed search; its other fields carry no information
    total, products = payload.get("totalCount"), payload.get("products")
    if not _is_int(total) or total < 0:
        bad(f"totalCount is {total!r}")
    if products is None and total == 0:
        return
    if not isinstance(products, list):
        bad(f"products is {type(products).__name__}, not a list")
    for p in products:
        if not isinstance(p, dict) or not _is_int(p.get("id")):
            bad("a product has no numeric id")


def make_fetch(client, query: str, lang: str):
    def fetch(lo, hi, first):
        result = client.search_products(query, lang, first=first, min_price=lo, max_price=hi)
        payload = result.get("payload") if isinstance(result, dict) else None
        _check_payload(payload)
        error = payload.get("errorMessage") or None
        products = payload.get("products")
        return searchmod.Page(total=payload.get("totalCount") if _is_int(payload.get("totalCount")) else 0,
                              products=products if isinstance(products, list) and not error else [],
                              corrected=payload.get("correctedSearchTerm"), error=error,
                              extras=meta.product_extras(result.get("meta")))
    return fetch


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: str, doc: dict) -> None:
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if not isinstance(doc, dict):
        raise ValueError("not a galaxus.py search document (not a JSON object)")
    missing = [k for k in DOCUMENT_KEYS if k not in doc]
    if missing:
        raise ValueError(f"not a galaxus.py search document (missing: {', '.join(missing)})")
    for key in ("products", "bands", "histogram"):
        if not isinstance(doc[key], list):
            raise ValueError(f"not a galaxus.py search document ({key} is not a list)")
    if doc["version"] != __version__:
        print(f"warning: {path} was written by galaxus-skill {doc['version']}, this is {__version__}; "
              f"search again if the output looks wrong", file=sys.stderr)
    return doc


def _fail(code: int, message: str) -> int:
    print(message, file=sys.stderr)
    return code


def _positive(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a positive integer") from None
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def _max_calls(text: str) -> int:
    value = _positive(text)
    if value > searchmod.MAX_CALLS_CAP:
        raise argparse.ArgumentTypeError(f"must be at most {searchmod.MAX_CALLS_CAP} (fair use)")
    return value


def _check_out(path: str | None) -> str | None:
    """Error message if the --out parent directory is missing or not writable (never creates it)."""
    if not path:
        return None
    if os.path.isdir(path):
        return f"--out is a directory, not a file: {path}"
    parent = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(parent):
        return f"--out directory does not exist: {parent}"
    if not os.access(parent, os.W_OK):
        return f"--out directory is not writable: {parent}"
    return None


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
    lo, hi = args.min or searchmod.FULL_RANGE[0], args.max or searchmod.FULL_RANGE[1]  # same default as search
    if lo > hi:
        return _fail(EXIT_INPUT, "--min must not exceed --max")
    try:
        page = make_fetch(make_client(), args.query, args.lang)(lo, hi, 1)
    except transport.TransportError as e:
        return _fail(EXIT_UNREACHABLE, f"Galaxus endpoint unreachable: {e}")
    except transport.ToolInputError as e:
        return _fail(EXIT_INPUT, f"Galaxus rejected the input: {e}")
    if page.error:
        return _fail(EXIT_SEARCH, f"Galaxus search error: {page.error} (a failed search, not zero results)")
    print(page.total)
    if page.corrected:
        print(f'Note: Galaxus spell-corrected the query to "{page.corrected}".')
    return EXIT_OK


def cmd_search(args) -> int:
    lo, hi = args.min or 1, args.max or 1_000_000
    if lo > hi:
        return _fail(EXIT_INPUT, "--min must not exceed --max")
    problem = _check_out(args.out)
    if problem:
        return _fail(EXIT_INPUT, problem)
    fetch = make_fetch(make_client(), args.query, args.lang)
    cache: dict = {}
    warned = []

    def document(res):
        return report.build_document(res, args.query, args.lang, __version__, _now(), cache)

    def checkpoint(res):
        if args.out:
            try:
                _write_json(args.out, document(res))
            except OSError as e:
                if not warned:
                    warned.append(True)
                    print(f"warning: cannot write checkpoint to {args.out}: {e}; continuing without checkpoints",
                          file=sys.stderr)

    def finish(doc, code):
        print(report.format_report(doc, args.top, args.out))
        if args.out:
            try:
                _write_json(args.out, doc)
            except OSError as e:
                print(f"cannot write {args.out}: {e}", file=sys.stderr)
                return EXIT_SEARCH
        return code

    try:
        res = searchmod.search(fetch, lo, hi, args.max_calls, on_update=checkpoint)
    except transport.TransportError as e:
        return _fail(EXIT_UNREACHABLE, f"Galaxus endpoint unreachable: {e}")
    except transport.ToolInputError as e:
        return _fail(EXIT_INPUT, f"Galaxus rejected the input: {e}")
    except searchmod.SearchFailed as e:
        return finish(document(e.partial), EXIT_SEARCH)
    return finish(document(res), EXIT_OK)


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
    if len(lookups) > MAX_LOOKUPS:
        return _fail(EXIT_INPUT, f"--lookup: at most {MAX_LOOKUPS} ids per run (each costs up to 3 calls)")
    by_id = {p["id"]: p for p in doc["products"]}
    found, notes, client, failed = [], [], None, False
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
        except (transport.TransportError, transport.ToolInputError, compare.LookupFailed) as e:
            notes.append(f"{pid}: lookup failed ({e})")
            failed = failed or not isinstance(e, transport.ToolInputError)
            continue
        if product is None:
            notes.append(f"{pid}: not found (best-effort)")
            continue
        found.append(product)
    print(compare.comparison_table(found))
    for note in notes:
        print(note)
    return EXIT_SEARCH if failed else EXIT_OK


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
    p.add_argument("--max-calls", type=_max_calls, default=60,
                   help=f"call budget (default 60, at most {searchmod.MAX_CALLS_CAP})")
    p.add_argument("--top", type=_positive, default=15, help="rows per product type in the printed report")
    p.add_argument("--out", help="write the full JSON document here (checkpointed after every call)")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("filter", help="filter a search document by specs, with unknown counts")
    p.add_argument("--from", dest="source", required=True)
    p.add_argument("--where", action="append", default=[], help="FIELD>=N, FIELD<=N, FIELD=VALUE or FIELD~TEXT")
    p.add_argument("--type", action="append", default=[], help="keep only this productType (repeatable)")
    p.add_argument("--top", type=_positive, default=15)
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
