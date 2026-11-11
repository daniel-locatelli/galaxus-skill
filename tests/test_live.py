"""Opt-in contract checks against the real endpoint: GALAXUS_LIVE=1 py -m pytest tests/test_live.py"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

import galaxus
from galaxus_lib import meta, transport
from galaxus_lib.search import search

pytestmark = pytest.mark.skipif(os.environ.get("GALAXUS_LIVE") != "1",
                                reason="set GALAXUS_LIVE=1 to run live contract tests")


@pytest.fixture(scope="module")
def client():
    return transport.Client(galaxus.AGENT_INFO)


def test_price_shape_and_meta_availability(client):
    result = client.search_products("Redmi 17", "en", first=50)
    priced = [p for p in result["payload"]["products"] if p["priceIfAvailable"]]
    assert priced and all(p["priceIfAvailable"]["currency"] == "CHF" for p in priced)
    assert any(e["availability"] for e in meta.product_extras(result["meta"]).values())


def test_bounds_are_inclusive(client):
    products = client.search_products("Redmi 17", "en", first=50)["payload"]["products"]
    p = next(p for p in products
             if p["priceIfAvailable"] and float(p["priceIfAvailable"]["amountInclusive"]).is_integer())
    price = int(p["priceIfAvailable"]["amountInclusive"])
    band = client.search_products("Redmi 17", "en", first=50, min_price=price, max_price=price)
    assert p["id"] in {x["id"] for x in band["payload"]["products"]}


def test_min_above_max_is_input_error(client):
    with pytest.raises(transport.ToolInputError):
        client.search_products("Redmi 17", "en", min_price=5, max_price=2)


def test_redmi17_search_is_complete():
    res = search(galaxus.make_fetch(transport.Client(galaxus.AGENT_INFO), "Redmi 17", "en"), max_calls=60)
    assert res.status == "complete"
    assert len(res.products) == res.root_total or res.final_total != res.root_total


def test_cli_count_smoke():
    script = Path(galaxus.__file__)
    out = subprocess.run([sys.executable, str(script), "count", "smartphone"],
                         capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0
    assert int(out.stdout.split()[0]) > 1000
