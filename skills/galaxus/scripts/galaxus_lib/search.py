"""Exhaustive search over price bands. Spec: "Search algorithm".

A band [a, b] holding more than 50 products splits at m into [a, m] and
[m, b]. The shared endpoint keeps products priced between two integers
(193.97) reachable. Coverage counts unique product ids, never band sums.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Callable, Optional

PAGE_SIZE = 50
HISTOGRAM_CALLS = 8
# Calls per page-full of matches, calibrated 2026-11-11 against FakeCatalogue runs
# (shuffled = relevance order as seen live; uniform and 35 % clustered at x49/x99/x00
# prices; 200-1500 matches): worst case 3.5 x N / 50 calls (400 -> 28, 611 -> 40,
# 1500 -> 106). Live: 611 matches took 40 calls; 959 ran out at 60. The + 2 covers the
# unfiltered-total and final re-count calls. Price-sorted pages (not seen live) need ~4.
CALLS_PER_PAGE = 3.5
EXTRA_CALLS = 2
MAX_CALLS_CAP = 300  # --max-calls upper bound (fair use)


FULL_RANGE = (1, 1_000_000)


def estimate_calls(total: int) -> int:
    return math.ceil(CALLS_PER_PAGE * total / PAGE_SIZE) + EXTRA_CALLS


@dataclass
class Page:
    total: int
    products: list
    corrected: Optional[str] = None
    error: Optional[str] = None
    extras: dict = field(default_factory=dict)


Fetch = Callable[[Optional[int], Optional[int], int], Page]


@dataclass
class Band:
    lo: int
    hi: int
    count: Optional[int]
    status: str  # complete | capped | drifted | uncovered | histogram


@dataclass
class SearchResult:
    lo: int
    hi: int
    max_calls: int
    status: str = "running"  # running | complete | partial | infeasible | failed
    root_total: int = 0
    final_total: Optional[int] = None
    unfiltered_total: Optional[int] = None
    corrected: Optional[str] = None
    calls: int = 0
    estimated_calls: int = 0
    error: Optional[str] = None
    bands: list = field(default_factory=list)
    histogram: list = field(default_factory=list)
    products: dict = field(default_factory=dict)
    extras: dict = field(default_factory=dict)


class SearchFailed(Exception):
    def __init__(self, message: str, partial: SearchResult):
        super().__init__(message)
        self.partial = partial


def split_point(lo: int, hi: int, products: list) -> int:
    """Median of the returned prices, else the geometric mean; clamped to lo < m < hi."""
    prices = []
    for p in products:
        price = p.get("priceIfAvailable") if isinstance(p, dict) else None
        amount = price.get("amountInclusive") if isinstance(price, dict) else None
        if isinstance(amount, (int, float)) and not isinstance(amount, bool) and math.isfinite(amount):
            prices.append(amount)
    m = round(statistics.median(prices)) if prices else round(math.sqrt(lo * hi))
    return min(max(m, lo + 1), hi - 1)


def search(fetch: Fetch, lo: int = 1, hi: int = 1_000_000, max_calls: int = 60,
           on_update: Optional[Callable[[SearchResult], None]] = None) -> SearchResult:
    res = SearchResult(lo=lo, hi=hi, max_calls=max_calls)

    def notify():
        if on_update:
            on_update(res)

    def call(a, b, first=PAGE_SIZE) -> Page:
        page = fetch(a, b, first)
        res.calls += 1
        return page

    def collect(page: Page):
        for p in page.products:
            res.products[p["id"]] = p
        res.extras.update(page.extras)
        notify()

    def fail(message: str, cause: Optional[BaseException] = None):
        res.status = "failed"
        res.error = message
        notify()
        raise SearchFailed(message, res) from cause

    root = call(lo, hi)  # errors here propagate unchanged: nothing found yet
    res.root_total = root.total
    res.corrected = root.corrected
    if root.error:
        fail(root.error)
    collect(root)

    res.estimated_calls = estimate_calls(root.total)
    holds_all = root.total <= PAGE_SIZE and len(root.products) == root.total
    # the optional extra count calls are budget-guarded, so they do not make a run infeasible
    if not holds_all and res.estimated_calls - EXTRA_CALLS > max_calls:
        res.status = "infeasible"
        _histogram(call, res)
        notify()
        return res

    try:
        _split(call, collect, fail, notify, res, root)
        # optional extras: an error or exception leaves the field None, status unchanged
        if (lo, hi) == FULL_RANGE and res.calls < max_calls:
            res.unfiltered_total = _count(call, None, None)
        if res.calls < max_calls:
            res.final_total = _count(call, lo, hi)
    except SearchFailed:
        raise
    except Exception as exc:  # any mid-run failure keeps the partial result
        fail(f"{type(exc).__name__}: {exc}", exc)
    notify()
    return res


def _count(call, a, b) -> Optional[int]:
    try:
        page = call(a, b, 1)
    except Exception:
        return None
    return None if page.error else page.total


def _split(call, collect, fail, notify, res: SearchResult, root: Page) -> None:
    pending = [(res.lo, res.hi, root)]
    try:
        _split_loop(call, collect, fail, res, pending)
    except Exception:
        # mid-run failure: the in-flight band and everything pending is unsearched
        # a band fetched but not split keeps its count (up to 50 of it were collected)
        res.bands.extend(Band(a, b, page.total if page else None, "uncovered") for a, b, page in pending)
        res.bands.sort(key=lambda band: (band.lo, band.hi))
        notify()  # checkpoint again so it carries the uncovered bands
        raise
    res.bands.sort(key=lambda band: (band.lo, band.hi))
    res.status = "complete" if all(band.status == "complete" for band in res.bands) else "partial"


def _split_loop(call, collect, fail, res: SearchResult, pending: list) -> None:
    while pending:
        a, b, page = pending[0]  # stays in `pending` until handled, so a failure can report it
        if page is None:
            if res.calls >= res.max_calls:
                res.bands.append(Band(a, b, None, "uncovered"))
                pending.pop(0)
                continue
            page = call(a, b)
            if page.error:
                fail(page.error)
            collect(page)
            pending[0] = (a, b, page)
        can_split = b - a > 1 and res.calls < res.max_calls
        if page.total <= PAGE_SIZE and len(page.products) == page.total:
            outcome = Band(a, b, page.total, "complete")
        elif can_split:
            m = split_point(a, b, page.products)  # may raise: the band is still pending
            pending[0:1] = [(a, m, None), (m, b, None)]  # ascending order, left first
            continue
        elif page.total <= PAGE_SIZE:
            outcome = Band(a, b, page.total, "drifted")
        elif b - a <= 1:
            outcome = Band(a, b, page.total, "capped")
        else:
            outcome = Band(a, b, page.total, "uncovered")
        pending.pop(0)
        res.bands.append(outcome)


def _histogram(call, res: SearchResult) -> None:
    n = min(HISTOGRAM_CALLS, res.max_calls - res.calls)
    if n < 1:
        return
    ratio = res.hi / res.lo
    edges = sorted({round(res.lo * ratio ** (i / n)) for i in range(n + 1)})
    for a, b in zip(edges, edges[1:]):
        try:
            page = call(a, b, 1)
        except Exception as exc:  # a histogram is a hint; stop on the first failure
            res.error = f"{type(exc).__name__}: {exc}"
            break
        if page.error:
            res.error = page.error
            break
        res.histogram.append(Band(a, b, page.total, "histogram"))
