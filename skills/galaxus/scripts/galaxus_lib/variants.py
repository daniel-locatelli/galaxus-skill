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
