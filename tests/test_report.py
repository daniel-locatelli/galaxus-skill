from fakes import make_product
from galaxus_lib import report, specs
from galaxus_lib.search import Band, SearchResult
from galaxus_lib.variants import merge_variants


def with_specs(p, lang="en"):
    p = dict(p)
    p["specs"] = {f: s.to_dict() for f, s in specs.extract(p, lang).items()}
    p.setdefault("extras", None)
    return p


def doc(products, status="complete", **kw):
    base = {"version": "0.1.0", "query": "q", "language": "en", "range": [1, 1_000_000], "timestamp": "t",
            "status": status, "maxCalls": 60, "calls": 3, "estimatedCalls": 2, "rootTotal": len(products),
            "finalTotal": None, "unfilteredTotal": None, "correctedSearchTerm": None, "error": None,
            "bands": [], "histogram": [], "products": products}
    base.update(kw)
    return base


DESC = "Smartphone with 4 GB RAM."


def redmi(pid, price, storage, colour):
    return with_specs(make_product(pid, price, name="Redmi 17", brand="Xiaomi", description=DESC,
                                   properties=f'{storage}, {colour}, 6.90", Dual SIM, 4G'))


def test_merge_requires_all_four_fields_equal():
    a, b = redmi(1, 164, "256 GB", "Blue"), redmi(2, 187, "128 GB", "Black")
    c = dict(redmi(3, 150, "128 GB", "Black"), description="Other chip.")
    assert [len(g) for g in merge_variants([a, b, c])] == [2, 1]


def test_build_document_sorts_by_price_and_adds_specs_and_extras():
    res = SearchResult(lo=1, hi=1_000_000, max_calls=60, status="complete", root_total=2, calls=1)
    res.products = {1: make_product(1, 50.0), 2: make_product(2, 20.0), 3: make_product(3, None)}
    res.extras = {1: {"availability": "TICK", "labels": [], "insteadOf": None}}
    res.bands = [Band(1, 1_000_000, 2, "complete")]
    d = report.build_document(res, "phone", "en", "0.1.0", "2026-11-11T00:00:00Z")
    assert [p["id"] for p in d["products"]] == [2, 1, 3]
    assert d["products"][1]["extras"]["availability"] == "TICK"
    assert "specs" in d["products"][0]
    assert d["bands"] == [{"lo": 1, "hi": 1_000_000, "count": 2, "status": "complete"}]
    assert (d["query"], d["language"], d["range"]) == ("phone", "en", [1, 1_000_000])


def test_coverage_complete():
    lines = report.coverage_lines(doc([with_specs(make_product(1, 10.0))]))
    assert lines[0] == "Coverage: complete. 1 unique products found; Galaxus reports 1 for this query and price range (3 calls)."


def test_coverage_partial_lists_band_problems():
    d = doc([], status="partial", rootTotal=400, bands=[
        {"lo": 163, "hi": 164, "count": 165, "status": "capped"},
        {"lo": 500, "hi": 1_000_000, "count": None, "status": "uncovered"}])
    text = "\n".join(report.coverage_lines(d))
    assert text.startswith("Coverage: partial. 0 unique products found of 400 reported")
    assert "capped (more than 50 products within 1 CHF; 50 kept): 163-164 CHF (165)" in text
    assert "uncovered (call budget reached; not searched): 500-1000000 CHF" in text


def test_coverage_infeasible_shows_histogram_and_no_rows():
    d = doc([with_specs(make_product(1, 10.0))], status="infeasible", rootTotal=471_800, estimatedCalls=18_872,
            histogram=[{"lo": 1, "hi": 6, "count": 1200, "status": "histogram"}])
    text = report.format_report(d, top=15)
    assert "Coverage: infeasible. Galaxus reports 471,800 matches" in text
    assert "  1-6: 1,200" in text
    assert "## " not in text


def test_coverage_failed_is_not_zero_results():
    text = "\n".join(report.coverage_lines(doc([], status="failed", error="The request failed")))
    assert "Coverage: failed." in text and "not as zero results" in text


def test_coverage_notes():
    d = doc([], rootTotal=30, finalTotal=31, unfilteredTotal=33, correctedSearchTerm="smartphone")
    text = "\n".join(report.coverage_lines(d))
    assert "moved from 30 to 31" in text
    assert "3 matches have no price of at least 1 CHF" in text
    assert 'spell-corrected the query to "smartphone"' in text


def test_row_shows_variant_sets_unknown_os_discount_and_availability():
    a, b = redmi(1, 164, "256 GB", "Blue"), redmi(2, 187, "128 GB", "Black")
    a["extras"] = {"availability": "TICK", "labels": ["DISCOUNT"],
                   "insteadOf": {"type": "SALES_PRICE_BEFORE", "rebate": 8, "price": 178}}
    row = report.format_row([a, b])
    assert row.startswith("- Xiaomi Redmi 17 | CHF 164-187 | 128/256 GB; 2 colours")
    assert "Android ?" in row
    assert "RAM 4 GB (desc.)" in row
    assert "availability TICK*" in row
    assert "-8 CHF, was 178*" in row
    assert row.endswith("https://www.galaxus.ch/en/s1/product/1")


def test_row_flags_refurbished():
    p = with_specs(make_product(5, 99.5))
    p["pageUrl"] += "?offertype=refurbished"
    assert "refurbished" in report.format_row([p])
    assert "CHF 99.50" in report.format_row([p])


def test_render_spec_states():
    assert report.render_spec(None) == "?"
    assert report.render_spec({"value": "120 Hz", "state": "stated", "source": "description",
                               "ceiling": True, "conflict": None}) == "up to 120 Hz (desc.)"
    assert report.render_spec({"value": "16", "state": "inferred", "source": "description",
                               "ceiling": False, "conflict": None}) == "16 (inferred)"


def test_top_limit_points_to_file():
    products = [with_specs(make_product(i, 10.0 + i)) for i in range(4)]
    text = report.format_report(doc(products), top=3, out_path="out.json")
    assert "## Smartphones: 4 products, 4 rows" in text
    assert "+1 more rows in out.json" in text
    assert text.rstrip().endswith(report.FOOTNOTE)


def test_unknown_counts_never_print_none_or_zero():
    d = doc([], status="partial", rootTotal=None, calls=None, bands=[
        {"lo": 1, "hi": 5, "count": None, "status": "drifted"}])
    text = "\n".join(report.coverage_lines(d))
    assert "None" not in text and "unknown" in text
    inf = doc([], status="infeasible", rootTotal=None, estimatedCalls=None,
              histogram=[{"lo": 1, "hi": 6, "count": None, "status": "histogram"}])
    t = "\n".join(report.coverage_lines(inf))
    assert "None" not in t and "unknown" in t


def test_row_tolerates_unvalidated_extras():
    p = with_specs(make_product(7, 10.0))
    p["extras"] = {"availability": 3, "labels": "DISCOUNT",
                   "insteadOf": {"type": 1, "rebate": "8", "price": None}}
    row = report.format_row([p])
    assert "availability 3*" in row
