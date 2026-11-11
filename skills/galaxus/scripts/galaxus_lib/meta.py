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
