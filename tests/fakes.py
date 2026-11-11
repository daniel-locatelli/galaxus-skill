"""Simulated Galaxus catalogue for offline tests."""
import random

from galaxus_lib.search import Page

ERROR_TEXT = "The request failed unexpectedly. No products are returned. Please try again later."


def make_product(pid, price, name=None, ptype="Smartphones", brand="Acme", description=None, properties=""):
    return {
        "id": pid,
        "name": name or f"Phone {pid}",
        "brand": brand,
        "productType": ptype,
        "description": description if description is not None else f"Phone {pid}.",
        "properties": properties,
        "priceIfAvailable": None if price is None else {"amountInclusive": price, "currency": "CHF"},
        "pageUrl": f"https://www.galaxus.ch/en/s1/product/{pid}",
        "ratingSummaryIfAvailable": None,
    }


class FakeCatalogue:
    """Callable like search.Fetch. Bounds are inclusive and compare the real (cent) price."""

    def __init__(self, products, seed=0, order="shuffle", error_on_call=None, raise_on_call=None,
                 drift=None, priceless=()):
        self.products = list(products)
        self.priceless = list(priceless)
        self.rng = random.Random(seed)
        self.order = order
        self.error_on_call = error_on_call
        self.raise_on_call = raise_on_call
        self.drift = dict(drift or {})
        self.calls = []

    def __call__(self, lo, hi, first):
        self.calls.append((lo, hi, first))
        n = len(self.calls)
        if n == self.raise_on_call:
            raise RuntimeError("connection reset")
        if n == self.error_on_call:
            return Page(total=0, products=[], error=ERROR_TEXT)
        if lo is None and hi is None:
            hits = self.products + self.priceless
        else:
            a = 1 if lo is None else lo
            b = 1_000_000 if hi is None else hi
            hits = [p for p in self.products
                    if p["priceIfAvailable"] and a <= p["priceIfAvailable"]["amountInclusive"] <= b]
        if self.order == "asc":
            hits = sorted(hits, key=lambda p: (p["priceIfAvailable"] or {}).get("amountInclusive", 0))
        else:
            hits = self.rng.sample(hits, len(hits))
        total = len(hits) + self.drift.pop((lo, hi), 0)
        return Page(total=total, products=hits[:first])


class FakeClient:
    """Stands in for transport.Client in CLI tests."""

    def __init__(self, catalogue):
        self.catalogue = catalogue

    def search_products(self, query, language, first=50, min_price=None, max_price=None):
        page = self.catalogue(min_price, max_price, first)
        payload = {"correctedSearchTerm": None, "totalCount": page.total, "products": page.products}
        if page.error:
            payload["errorMessage"] = page.error
        return {"payload": payload, "meta": None}
