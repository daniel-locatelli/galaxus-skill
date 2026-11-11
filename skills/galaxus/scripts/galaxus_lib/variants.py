"""Conservative variant merge: one row only when brand, productType, name,
description and refurbished flag are all equal. Merging different products
shows false facts; extra rows only cost space. Fuzzy de-duplication is deferred."""
from __future__ import annotations


def is_refurbished(p: dict) -> bool:
    extras = p.get("extras")
    labels = extras.get("labels") if isinstance(extras, dict) else None
    if "offertype=refurbished" in (p.get("pageUrl") or ""):
        return True
    return isinstance(labels, (list, tuple)) and "USED_AND_CHECKED" in labels


def variant_key(p: dict) -> tuple:
    return (p.get("brand"), p.get("productType"), p.get("name"), p.get("description"), is_refurbished(p))


def merge_variants(products: list[dict]) -> list[list[dict]]:
    groups: dict[tuple, list[dict]] = {}
    for p in products:
        groups.setdefault(variant_key(p), []).append(p)
    return list(groups.values())
