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
_SIZE_FIELDS = ("storage", "ram")  # numeric conditions on these are in GB


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


def _number(cond: Condition, value: str) -> float | None:
    number = specs.first_number(value)
    if number is not None and cond.field in _SIZE_FIELDS and "tb" in value.lower():
        number *= 1024  # compare storage/RAM in GB
    return number


def evaluate(cond: Condition, spec: dict | None) -> str:
    if not spec or spec.get("conflict") or spec.get("value") in (None, ""):
        return UNKNOWN
    value = str(spec["value"])
    if cond.op in (">=", "<="):
        number = _number(cond, value)
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
    detail = f" ({unknown})" if unknown else ""
    lines.append(f"Filter {criteria}: {outcome.checked} checked, {len(outcome.matched)} match, "
                 f"{len(outcome.unknown)} unknown{detail}, {outcome.excluded} excluded.")
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
