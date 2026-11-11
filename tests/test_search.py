import random

import pytest

from fakes import FakeCatalogue, make_product
from galaxus_lib.search import Page, SearchFailed, search, split_point


def catalogue(prices, **kw):
    return FakeCatalogue([make_product(i, p) for i, p in enumerate(prices, 1)], **kw)


def test_small_band_is_complete_in_one_band_call():
    fake = catalogue([10.0 + i for i in range(30)])
    res = search(fake, lo=1, hi=1000)
    assert res.status == "complete"
    assert len(res.products) == 30
    assert [b.status for b in res.bands] == ["complete"]


def test_cent_prices_between_integers_are_not_lost():
    fake = catalogue([round(100 + i * 0.37, 2) for i in range(300)], seed=3)
    res = search(fake)
    assert res.status == "complete"
    assert len(res.products) == 300


def test_children_share_the_split_endpoint():
    fake = catalogue([float(p) for p in range(1, 121)], order="asc")
    search(fake, lo=1, hi=1000)
    (_, _, _), (a1, b1, _), (a2, b2, _) = fake.calls[:3]
    assert a1 == 1 and b1 == a2 and b2 == 1000


def test_coverage_counts_unique_ids_not_band_sums():
    fake = catalogue([float(p) for p in range(1, 101)], order="asc")
    res = search(fake, lo=1, hi=1000)
    assert res.status == "complete"
    assert len(res.products) == 100
    assert sum(b.count for b in res.bands) > 100  # shared endpoints double-count


def test_more_than_50_at_one_price_is_capped():
    prices = [163.0] * 165 + [100.0 + i for i in range(40)]
    res = search(catalogue(prices))
    assert res.status == "partial"
    capped = [b for b in res.bands if b.status == "capped"]
    assert capped and all(b.hi - b.lo <= 1 and b.lo <= 163 <= b.hi for b in capped)
    others = {i for i, p in enumerate(prices, 1) if p != 163.0}
    assert others <= set(res.products)


def test_budget_leaves_uncovered_bands():
    fake = catalogue([float(p) for p in range(1, 401)], order="asc")  # price-sorted pages: worst case
    res = search(fake, max_calls=30)
    assert res.estimated_calls <= 30  # the gate did not fire
    assert res.status == "partial"
    assert res.calls == 30
    assert any(b.status == "uncovered" for b in res.bands)


def test_drift_in_wide_band_is_split_again():
    fake = catalogue([10.0 + i for i in range(30)], drift={(1, 1000): 1})
    res = search(fake, lo=1, hi=1000)
    assert res.status == "complete"
    assert len(res.products) == 30
    assert res.calls >= 3


def test_drift_in_narrow_band_is_marked_drifted():
    fake = catalogue([5.0] * 30, drift={(5, 6): 1})
    res = search(fake, lo=5, hi=6)
    assert res.status == "partial"
    assert [b.status for b in res.bands] == ["drifted"]


def test_feasibility_gate_returns_histogram():
    calls = []

    def huge(lo, hi, first):
        calls.append((lo, hi, first))
        return Page(total=471_800, products=[make_product(i, 100.0 + i) for i in range(50)])

    res = search(huge)
    assert res.status == "infeasible"
    assert res.estimated_calls == 33_028  # ceil(3.5 * 471_800 / 50) + 2
    assert len(res.histogram) == 8
    assert res.histogram[0].lo == 1 and res.histogram[-1].hi == 1_000_000
    assert res.calls == 9
    assert all(first == 1 for _, _, first in calls[1:])


def test_unfiltered_total_reveals_priceless_products():
    fake = FakeCatalogue([make_product(i, 10.0 + i) for i in range(30)],
                         priceless=[make_product(900 + i, None) for i in range(3)])
    res = search(fake)
    assert res.root_total == 30
    assert res.unfiltered_total == 33


def test_final_recount_records_drift():
    class Growing(FakeCatalogue):
        def __call__(self, lo, hi, first):
            if len(self.calls) == 1:
                self.products.append(make_product(999, 50.0))
            return super().__call__(lo, hi, first)

    res = search(Growing([make_product(i, 10.0 + i) for i in range(30)]), lo=1, hi=1000)
    assert res.root_total == 30
    assert res.final_total == 31


def test_checkpoint_after_every_band_call():
    snapshots = []
    fake = catalogue([float(p) for p in range(1, 121)], order="asc")
    res = search(fake, lo=1, hi=1000, on_update=lambda r: snapshots.append(len(r.products)))
    assert snapshots == sorted(snapshots)
    assert snapshots[-1] == len(res.products) == 120
    # one snapshot per band call (root included), one for the count-only recount
    # (which does not collect), plus the final notify: calls == band calls + 1 recount
    assert len(snapshots) == len(fake.calls)


def test_error_message_mid_run_raises_with_partial():
    fake = catalogue([float(p) for p in range(1, 121)], error_on_call=2)
    with pytest.raises(SearchFailed) as info:
        search(fake, lo=1, hi=1000)
    assert info.value.partial.status == "failed"
    assert len(info.value.partial.products) == 50
    assert "request failed" in info.value.partial.error


def test_exception_mid_run_raises_with_partial():
    fake = catalogue([float(p) for p in range(1, 121)], raise_on_call=2)
    with pytest.raises(SearchFailed) as info:
        search(fake, lo=1, hi=1000)
    assert "connection reset" in info.value.partial.error


def test_error_message_at_root_is_a_failed_search():
    fake = catalogue([10.0], error_on_call=1)
    with pytest.raises(SearchFailed) as info:
        search(fake)
    assert info.value.partial.products == {}


def test_split_point_median_then_geometric_mean():
    prices = [make_product(i, p) for i, p in enumerate([10.0, 20.0, 30.0], 1)]
    assert split_point(1, 1000, prices) == 20
    assert split_point(1, 100, [make_product(1, None)]) == 10
    assert split_point(163, 1000, [make_product(1, 163.0)]) == 164
    assert split_point(1, 163, [make_product(1, 163.0)]) == 162


@pytest.mark.parametrize("seed", range(20))
def test_terminates_on_messy_catalogues(seed):
    rng = random.Random(seed)
    prices = [rng.choice([5.0, 5.5, 99.99, 100.0, 250.0, 999.0]) for _ in range(rng.randint(50, 400))]
    res = search(catalogue(prices, seed=seed), max_calls=500)
    assert res.calls <= 500
    assert res.status in ("complete", "partial")
    gaps = [b for b in res.bands if b.status != "complete"]
    for pid, price in enumerate(prices, 1):
        if not any(b.lo <= price <= b.hi for b in gaps):
            assert pid in res.products


def test_final_recount_error_leaves_final_total_none():
    res = search(catalogue([10.0 + i for i in range(30)], error_on_call=2), lo=1, hi=1000)
    assert res.status == "complete"
    assert res.final_total is None


def test_final_recount_exception_leaves_final_total_none():
    res = search(catalogue([10.0 + i for i in range(30)], raise_on_call=2), lo=1, hi=1000)
    assert res.status == "complete"
    assert res.final_total is None


def test_unfiltered_total_error_leaves_none():
    res = search(catalogue([10.0 + i for i in range(30)], error_on_call=2))
    assert res.status == "complete"
    assert res.unfiltered_total is None


def test_failure_partial_lists_unsearched_ranges():
    fake = catalogue([float(p) for p in range(1, 281)], order="asc", error_on_call=5)
    with pytest.raises(SearchFailed) as info:
        search(fake, lo=1, hi=1000)
    bands = info.value.partial.bands
    assert [b.lo for b in bands] == sorted(b.lo for b in bands)
    assert any(b.status == "uncovered" and b.count is None for b in bands)
    covered = 1
    for b in bands:
        assert b.lo <= covered
        covered = max(covered, b.hi)
    assert covered == 1000


def test_histogram_error_is_recorded_but_status_stays_infeasible():
    n = []

    def huge(lo, hi, first):
        n.append(1)
        if len(n) == 3:
            return Page(total=0, products=[], error="boom")
        return Page(total=471_800, products=[make_product(i, 100.0 + i) for i in range(50)])

    res = search(huge)
    assert res.status == "infeasible"
    assert res.error == "boom"


def test_last_checkpoint_after_failure_matches_partial_bands():
    snaps = []
    fake = catalogue([float(p) for p in range(1, 281)], order="asc", error_on_call=5)
    with pytest.raises(SearchFailed) as info:
        search(fake, lo=1, hi=1000, on_update=lambda r: snaps.append(list(r.bands)))
    assert snaps[-1] == info.value.partial.bands


def test_estimate_marks_959_infeasible_and_611_feasible_at_60():
    def fixed(total):
        def fetch(lo, hi, first):
            return Page(total=total, products=[make_product(i, 200.0 + i) for i in range(min(first, 50))])
        return fetch
    assert search(fixed(959)).status == "infeasible"
    assert search(fixed(959)).estimated_calls == 70
    res = search(fixed(611), max_calls=60)
    assert res.estimated_calls == 45 and res.status != "infeasible"


def clustered_prices(n, lo, hi, rng, share=0.35):
    points = [p for p in range(lo, hi + 1) if p % 50 in (0, 49) or p % 100 == 99]
    out = []
    for _ in range(n):
        if rng.random() < share:
            p = rng.choice(points) + rng.choice([0, 0, 0.9, 0.95, -0.1])
        else:
            p = rng.uniform(lo, hi)
        out.append(round(min(max(p, lo), hi), 2))
    return out


@pytest.mark.parametrize("n,lo,hi", [(200, 200, 500), (611, 200, 500), (959, 100, 250)])
@pytest.mark.parametrize("seed", range(3))
def test_estimate_covers_simulated_runs_with_clustered_prices(n, lo, hi, seed):
    """Calibration guard for estimated_calls (relevance order = shuffled prices, as live)."""
    prices = clustered_prices(n, lo, hi, random.Random(seed))
    res = search(catalogue(prices, seed=seed), lo, hi, max_calls=10_000)
    assert res.calls <= res.estimated_calls


def test_split_point_skips_malformed_prices():
    bad = [make_product(1, 10.0), make_product(2, 30.0), make_product(3, 20.0)]
    bad[1]["priceIfAvailable"] = {"currency": "CHF"}
    bad[2]["priceIfAvailable"] = {"amountInclusive": "n/a"}
    assert split_point(1, 1000, bad) == 10
    assert split_point(1, 100, [dict(make_product(4, None), priceIfAvailable="?")]) == 10


def test_band_is_kept_in_partial_when_split_fails(monkeypatch):
    from galaxus_lib import search as searchmod

    def boom(lo, hi, products):
        raise RuntimeError("split failed")
    monkeypatch.setattr(searchmod, "split_point", boom)
    fake = catalogue([float(p) for p in range(1, 121)])
    with pytest.raises(SearchFailed) as info:
        search(fake, lo=1, hi=1000)
    bands = info.value.partial.bands
    assert [(b.lo, b.hi, b.status) for b in bands] == [(1, 1000, "uncovered")]
    assert bands[0].count == 120  # fetched, not split: count known, up to 50 kept
