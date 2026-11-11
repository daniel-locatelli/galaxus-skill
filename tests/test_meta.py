import json
from pathlib import Path

import pytest

from galaxus_lib import meta, transport

FIX = Path(__file__).parent / "fixtures"

SAMPLE = {"response": {"data": {"serverToolShopSearch": {"products": {"edges": [
    {"node": {"trackingId": 73036751, "labels": ["DISCOUNT"],
              "insteadOfPrice": {"type": "SALES_PRICE_BEFORE", "rebate": 8, "price": {"amountInclusive": 178}},
              "availability": {"availabilityClassification": "TICK", "id": "x"}}},
    {"node": {"trackingId": 2, "labels": None, "insteadOfPrice": None, "availability": None}},
]}}}}}


def _meta_with(edges):
    return {"response": {"data": {"serverToolShopSearch": {"products": {"edges": edges}}}}}


SIBLING = {"node": {"trackingId": 2, "labels": ["DISCOUNT"], "insteadOfPrice": None,
                    "availability": {"availabilityClassification": "TICK"}}}
SIBLING_OUT = {2: {"availability": "TICK", "labels": ["DISCOUNT"], "insteadOf": None}}
BLANK = {"availability": None, "labels": [], "insteadOf": None}


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


@pytest.mark.parametrize("edges, expected", [
    pytest.param(None, {}, id="edges-none"),
    pytest.param({"node": SIBLING["node"]}, {}, id="edges-not-a-list"),
    pytest.param([None, "x", 5, ["list"]] + [SIBLING], SIBLING_OUT, id="edge-not-a-dict"),
    pytest.param([{"node": None}, {"node": "str"}, {"node": ["l"]}, SIBLING], SIBLING_OUT, id="node-not-a-dict"),
    pytest.param([{"node": {}}, {"node": {"trackingId": None}}, SIBLING], SIBLING_OUT, id="trackingid-missing"),
    pytest.param([{"node": {"trackingId": ["x"]}}, {"node": {"trackingId": {"a": 1}}}, SIBLING],
                 SIBLING_OUT, id="trackingid-unhashable"),
    pytest.param([{"node": {"trackingId": "abc"}}, {"node": {"trackingId": "7x"}}, SIBLING],
                 SIBLING_OUT, id="trackingid-non-digit-str"),
    pytest.param([{"node": {"trackingId": True}}, SIBLING], SIBLING_OUT, id="trackingid-bool"),
    pytest.param([{"node": {"trackingId": "7"}}, SIBLING],
                 {**SIBLING_OUT, 7: BLANK}, id="trackingid-digit-str-coerced"),
    pytest.param([{"node": {"trackingId": 9, "labels": "DISCOUNT", "insteadOfPrice": "oops",
                            "availability": 3}}, SIBLING],
                 {**SIBLING_OUT, 9: BLANK}, id="non-dict-subfields-to-none"),
    pytest.param([{"node": {"trackingId": 9, "labels": ["DISCOUNT", None, 3, "NEW"]}}, SIBLING],
                 {**SIBLING_OUT, 9: {"availability": None, "labels": ["DISCOUNT", "NEW"], "insteadOf": None}},
                 id="labels-keep-str-only"),
    pytest.param([{"node": {"trackingId": 9, "insteadOfPrice": {"type": "T", "rebate": 1, "price": "bad"}}},
                  SIBLING],
                 {**SIBLING_OUT, 9: {"availability": None, "labels": [],
                                     "insteadOf": {"type": "T", "rebate": 1, "price": None}}},
                 id="price-not-a-dict"),
])
def test_malformed_meta_never_raises_and_siblings_survive(edges, expected):
    assert meta.product_extras(_meta_with(edges)) == expected


def test_real_fixture_covers_every_product():
    body = json.loads((FIX / "success.json").read_text("utf-8"))["body"]
    result = transport.parse_sse(body)[-1]["result"]
    payload = json.loads(result["content"][0]["text"])
    assert payload["products"]
    extras = meta.product_extras(result["_meta"])
    assert {p["id"] for p in payload["products"]} <= set(extras)
