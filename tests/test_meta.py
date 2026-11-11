import json
from pathlib import Path

from galaxus_lib import meta, transport

FIX = Path(__file__).parent / "fixtures"

SAMPLE = {"response": {"data": {"serverToolShopSearch": {"products": {"edges": [
    {"node": {"trackingId": 73036751, "labels": ["DISCOUNT"],
              "insteadOfPrice": {"type": "SALES_PRICE_BEFORE", "rebate": 8, "price": {"amountInclusive": 178}},
              "availability": {"availabilityClassification": "TICK", "id": "x"}}},
    {"node": {"trackingId": 2, "labels": None, "insteadOfPrice": None, "availability": None}},
]}}}}}


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


def test_real_fixture_covers_every_product():
    body = json.loads((FIX / "success.json").read_text("utf-8"))["body"]
    result = transport.parse_sse(body)[-1]["result"]
    payload = json.loads(result["content"][0]["text"])
    extras = meta.product_extras(result["_meta"])
    assert {p["id"] for p in payload["products"]} <= set(extras)
