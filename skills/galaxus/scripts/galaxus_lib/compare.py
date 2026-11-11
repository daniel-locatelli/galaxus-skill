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
    if not pid.strip().isdigit():
        raise ValueError(f"--lookup {text!r}: the id must be numeric, got {pid.strip()!r}")
    query, _, price = rest.rpartition("@") if "@" in rest else (rest, "", "")
    try:
        amount = float(price) if price else None
    except ValueError:
        raise ValueError(f"--lookup {text!r}: the price after @ must be a number") from None
    return int(pid), (query.strip(), amount)


def lookup(fetch_for_query, pid: int, query: str, price: float | None, lang: str = "en") -> dict | None:
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
                return report.enrich_product(p, page.extras.get(pid), lang)
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
    rows.append(["availability*"] + [str((p.get("extras") or {}).get("availability") or "n/a") for p in products])
    rows.append(["link"] + [p.get("pageUrl", "") for p in products])
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(cell.replace("|", "/") for cell in row) + " |" for row in rows]
    return "\n".join(lines + ["", report.FOOTNOTE])
