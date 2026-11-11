"""The only reader of the undocumented `result._meta` payload.

`_meta` repeats the raw GraphQL response. It is undocumented and may vanish
or change shape; every accessor degrades to "not available" and never raises,
so a malformed `_meta` cannot kill a search. Malformed edges are skipped;
malformed sub-fields become None or []. Only enum-like fields are read, so
the mis-encoded strings seen in `_meta` (e.g. "Â ") do not matter here.
"""
from __future__ import annotations


def _tracking_id(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    return None


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def product_extras(meta: dict | None) -> dict[int, dict]:
    try:
        edges = meta["response"]["data"]["serverToolShopSearch"]["products"]["edges"]
    except (KeyError, TypeError):
        return {}
    if not isinstance(edges, list):
        return {}
    out: dict[int, dict] = {}
    for edge in edges:
        node = _as_dict(_as_dict(edge).get("node"))
        pid = _tracking_id(node.get("trackingId"))
        if pid is None:
            continue
        availability = _as_dict(node.get("availability")).get("availabilityClassification")
        instead = node.get("insteadOfPrice")
        instead_of = None
        if isinstance(instead, dict) and instead:
            instead_of = {"type": instead.get("type"), "rebate": instead.get("rebate"),
                          "price": _as_dict(instead.get("price")).get("amountInclusive")}
        labels = node.get("labels")
        out[pid] = {"availability": availability,
                    "labels": [s for s in labels if isinstance(s, str)] if isinstance(labels, list) else [],
                    "insteadOf": instead_of}
    return out
