"""JSON document (the --out file) and the text report printed to stdout."""
from __future__ import annotations

from dataclasses import asdict

from . import specs
from .variants import is_refurbished, merge_variants

FOOTNOTE = ("* availability class and discount: per Galaxus data (undocumented field); classes are shown raw, "
            "with no assumed meaning. Spec marks: (desc.) = from the free-text description, weaker than "
            "properties; (inferred) = derived, not stated; up to = a ceiling, not this variant's value; ? = unknown.")

KEY_FIELDS = {"phone": ("android_version", "ram", "network"), "laptop": ("cpu", "ram", "os"),
              "monitor": ("refresh", "panel", "response")}
LABELS = {"android_version": "Android", "ram": "RAM", "cpu": "CPU", "os": "OS"}
_VARIANT_FIELDS = ("storage", "ram", "screen", "network", "colour")


def _num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def format_price(value) -> str:
    if value is None:
        return "n/a"
    n = _num(value)
    if n is None:
        return str(value)
    return str(int(n)) if float(n).is_integer() else f"{n:.2f}"


def _count(value) -> str:
    """Thousands-separated count; unknown (None) is never shown as 0."""
    n = _num(value)
    return "unknown" if n is None else f"{n:,}"


def _price(p: dict):
    pr = p.get("priceIfAvailable")
    v = pr.get("amountInclusive") if isinstance(pr, dict) else None
    return _num(v)


def _price_key(p: dict):
    v = _price(p)
    return (v is None, v or 0)


# --------------------------------------------------------------- document

def enrich_product(p: dict, extras, lang: str, cache: dict | None = None) -> dict:
    """Document form of a raw product: a copy with `extras` and extracted `specs` (cached by id)."""
    pid = p.get("id")
    if cache is not None and pid in cache:
        extracted = cache[pid]
    else:
        extracted = {f: s.to_dict() for f, s in specs.extract(p, lang).items()}
        if cache is not None:
            cache[pid] = extracted
    item = dict(p)
    item["extras"] = extras
    item["specs"] = extracted
    return item


def build_document(res, query: str, lang: str, version: str, timestamp: str, cache: dict | None = None) -> dict:
    cache = {} if cache is None else cache
    products = [enrich_product(p, res.extras.get(pid), lang, cache) for pid, p in res.products.items()]
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
    n, total, status = len(doc["products"]), doc.get("rootTotal"), doc["status"]
    calls = _count(doc.get("calls"))
    lines = []
    if status == "infeasible":
        lines.append(f"Coverage: infeasible. Galaxus reports {_count(total)} matches; a complete search needs about "
                     f"{_count(doc.get('estimatedCalls'))} calls, budget is {_count(doc.get('maxCalls'))}. "
                     f"Narrow by brand in the query, by a tighter price range, or ask the user.")
        if doc["histogram"]:
            lines.append("Price histogram (CHF range: matches):")
            lines += [f"  {b['lo']}-{b['hi']}: {_count(b['count'])}" for b in doc["histogram"]]
    elif status == "complete":
        if _num(total) is None:
            lines.append(f"Coverage: complete. {n} unique products found; Galaxus did not report a total for "
                         f"this query and price range ({calls} calls).")
        else:
            lines.append(f"Coverage: complete. {n} unique products found; Galaxus reports {_count(total)} for "
                         f"this query and price range ({calls} calls).")
    elif status == "failed":
        lines.append(f"Coverage: failed. Galaxus search error: {doc.get('error') or 'the server gave no message'}. {n} unique products found before "
                     f"the failure; treat this as a failed search, not as zero results.")
    else:
        word = "partial" if status == "partial" else "in progress"
        lines.append(f"Coverage: {word}. {n} unique products found of {_count(total)} reported ({calls} calls).")
    for st, why in (("capped", "more than 50 products within 1 CHF; 50 kept"),
                    ("drifted", "count changed between calls"),
                    ("uncovered", "call budget reached; not searched")):
        bands = [b for b in doc["bands"] if b["status"] == st]
        if bands:
            lines.append(f"  {st} ({why}): " + ", ".join(
                f"{b['lo']}-{b['hi']} CHF" + (f" ({b['count']})" if b["count"] is not None
                                              else " (count unknown)" if st == "drifted" else "")
                for b in bands))
    final, unfiltered = _num(doc.get("finalTotal")), _num(doc.get("unfilteredTotal"))
    total_n = _num(total)
    if final is not None and total_n is not None and final != total_n:
        lines.append(f"Note: the Galaxus count moved from {_count(total)} to {_count(final)} during the run; "
                     f"coverage numbers carry that tolerance.")
    if unfiltered is not None and total_n is not None and unfiltered > total_n:
        lines.append(f"Note: {unfiltered - total_n} matches have no price of at least 1 CHF and cannot be "
                     f"reached by price bands.")
    if status == "complete":
        if _num(total) is not None and n != total:
            lines.append(f"Note: {n} unique products found but Galaxus reports {_count(total)}; "
                         f"the difference is not explained by the bands.")
        if final is None:
            lines.append("Note: drift check not run (the final re-count did not complete), so the count may "
                         "have changed during the run.")
        if unfiltered is None and list(doc.get("range") or []) == [1, 1_000_000]:
            lines.append("Note: products without a price not counted (the unfiltered total was not available).")
    if doc.get("correctedSearchTerm"):
        lines.append(f'Note: Galaxus spell-corrected the query to "{doc["correctedSearchTerm"]}".')
    return lines


# ------------------------------------------------------------------- rows

def render_spec(spec: dict | None) -> str:
    if not spec:
        return "?"
    value = f"up to {spec['value']}" if spec.get("ceiling") else str(spec["value"])
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


def _mark_key(spec: dict) -> tuple:
    return (str(spec.get("value")), spec.get("state"), spec.get("source"), bool(spec.get("ceiling")),
            spec.get("conflict"))


def _distinct_specs(group: list[dict], field: str) -> list[dict]:
    """Distinct non-empty specs of one field; equal only if value and marks match."""
    seen: dict[tuple, dict] = {}
    for p in group:
        s = _specs_of(p).get(field)
        if s and s.get("value") not in (None, ""):
            seen.setdefault(_mark_key(s), s)
    return list(seen.values())


def _variant_differences(group: list[dict]) -> str:
    if len(group) < 2:
        return ""
    out = []
    for field in _VARIANT_FIELDS:
        found = _distinct_specs(group, field)
        if field == "colour":
            n = len({str(s["value"]) for s in found})
            if n >= 2:
                out.append(f"{n} colours")
            continue
        if len(found) < 2:
            continue
        rendered = [render_spec(s) for s in found]
        vals = [str(s["value"]) for s in found]
        units = {v.split(" ", 1)[1] if " " in v else "" for v in vals}
        if rendered == vals and len(set(vals)) == len(vals) and len(units) == 1 and "" not in units:
            ordered = sorted(vals, key=lambda v: specs.first_number(v) or 0)
            out.append("/".join(v.split(" ", 1)[0] for v in ordered) + " " + units.pop())
        else:
            out.append("/".join(rendered))
    return "; ".join(out)


def _key_specs(group: list[dict]) -> str:
    schema = specs.schema_for(group[0].get("productType") or "")
    parts = []
    for field in KEY_FIELDS.get(schema, ()):
        label = LABELS.get(field, field)
        found = _distinct_specs(group, field)
        if not found:
            parts.append(f"{label} ?")
            continue
        text = "/".join(render_spec(s) for s in found)
        if sum(1 for p in group if _specs_of(p).get(field)) < len(group):
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
    rated = [p["ratingSummaryIfAvailable"] for p in group if isinstance(p.get("ratingSummaryIfAvailable"), dict)]
    if not rated:
        return ""
    best = max(rated, key=lambda r: _num(r.get("ratingCount")) or 0)
    return f"rating {best.get('averageRating')} ({best.get('ratingCount')})"


def _extras(p: dict) -> dict:
    e = p.get("extras")
    return e if isinstance(e, dict) else {}


def _availability(group: list[dict]) -> str:
    classes = sorted({str(_extras(p)["availability"]) for p in group if _extras(p).get("availability") is not None})
    return f"availability {'/'.join(classes)}*" if classes else ""


def _discount(group: list[dict]) -> str:
    def rebate(p):
        instead = _extras(p).get("insteadOf")
        return instead if isinstance(instead, dict) and instead.get("rebate") is not None else None
    having = [p for p in sorted(group, key=_price_key) if rebate(p)]
    if not having:
        return ""
    instead = rebate(having[0])
    text = f"-{format_price(instead['rebate'])} CHF, was {format_price(instead.get('price'))}*"
    return text + " (some variants)" if len(having) < len(group) else text


def _refurbished(group: list[dict]) -> str:
    return "refurbished/used offer" if any(is_refurbished(p) for p in group) else ""


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
