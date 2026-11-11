import pytest

from fakes import FakeCatalogue, make_product
from galaxus_lib import compare, filtering, specs


def spec(value, state="stated", source="description", ceiling=False, conflict=None):
    return {"value": value, "state": state, "source": source, "ceiling": ceiling, "conflict": conflict}


def prod(pid, ptype="Smartphones", **fields):
    p = make_product(pid, 100.0 + pid, ptype=ptype)
    p["specs"] = fields
    p["extras"] = None
    return p


def doc(products, status="complete"):
    return {"status": status, "rootTotal": len(products), "calls": 1, "maxCalls": 60, "estimatedCalls": 1,
            "finalTotal": None, "unfilteredTotal": None, "correctedSearchTerm": None, "error": None,
            "bands": [], "histogram": [], "products": products, "language": "en"}


def test_parse_where():
    assert filtering.parse_where("android_version>=17") == filtering.Condition("android_version", ">=", "17")
    assert filtering.parse_where("panel = IPS") == filtering.Condition("panel", "=", "IPS")
    assert filtering.parse_where("cpu~snapdragon").op == "~"
    for bad in ("nonsense", "ram>=lots", "=5"):
        with pytest.raises(ValueError):
            filtering.parse_where(bad)


@pytest.mark.parametrize("cond, s, expected", [
    ("refresh>=144", spec("165 Hz"), "match"),
    ("refresh>=144", spec("60 Hz"), "fail"),
    ("refresh>=144", None, "unknown"),
    ("refresh>=144", spec("120 Hz", ceiling=True), "fail"),      # at most 120
    ("refresh>=144", spec("240 Hz", ceiling=True), "unknown"),   # up to 240: maybe
    ("refresh<=60", spec("120 Hz", ceiling=True), "unknown"),
    ("screen>=6.5", spec('6.9"', conflict='6.9" (properties) / 6.4" (description)'), "unknown"),
    ("panel=ips", spec("IPS"), "match"),
    ("cpu~snapdragon", spec("Qualcomm Snapdragon 6s Gen 4"), "match"),
    ("panel=IPS", spec("VA"), "fail"),
    ("storage>=512", spec("1 TB"), "match"),
    ("storage<=512", spec("1 TB"), "fail"),
    ("ram>=8", spec("8 GB"), "match"),
])
def test_evaluate(cond, s, expected):
    assert filtering.evaluate(filtering.parse_where(cond), s) == expected


def test_run_filter_counts_and_type_exclusion():
    products = [prod(1, android_version=spec("17")), prod(2, android_version=spec("16")), prod(3),
                prod(4, ptype="Phone cases")]
    d = doc(products)
    out = filtering.run_filter(d, [filtering.parse_where("android_version>=17")], types=["smartphones"])
    assert [p["id"] for p in out.matched] == [1]
    assert [p["id"] for p in out.unknown] == [3]
    assert out.excluded == 1 and out.checked == 3
    assert out.unknown_by_field == {"android_version": 1}
    assert out.type_excluded == {"Phone cases": 1}


def test_verdict_none_confirmed_when_specs_unknown():
    d = doc([prod(1, android_version=spec("16")), prod(2)])
    conds = [filtering.parse_where("android_version>=17")]
    text = filtering.format_filter_report(d, filtering.run_filter(d, conds), conds, top=15)
    assert "Verdict: none confirmed among 2 checked; 1 have unknown specs (android_version: 1 unknown)." in text


def test_verdict_none_qualify_only_when_complete_and_known():
    d = doc([prod(1, android_version=spec("16"))])
    conds = [filtering.parse_where("android_version>=17")]
    assert "Verdict: none qualify" in filtering.format_filter_report(d, filtering.run_filter(d, conds), conds, 15)
    d["status"] = "partial"
    text = filtering.format_filter_report(d, filtering.run_filter(d, conds), conds, 15)
    assert "Verdict: none confirmed among 1 checked; coverage is partial." in text


def test_parse_lookup():
    assert compare.parse_lookup("20=Acme Phone 20@120") == (20, ("Acme Phone 20", 120.0))
    assert compare.parse_lookup("20=Acme Phone 20") == (20, ("Acme Phone 20", None))
    with pytest.raises(ValueError):
        compare.parse_lookup("Acme Phone 20")


def test_lookup_uses_narrow_band_first_and_at_most_three_calls():
    fake = FakeCatalogue([make_product(i, 100.0 + i) for i in range(1, 60)])
    found = compare.lookup(lambda q: fake, 20, "Acme Phone 20", 120.0)
    assert found["id"] == 20
    assert fake.calls[0] == (114, 126, 50)
    missing = FakeCatalogue([make_product(1, 10.0)])
    assert compare.lookup(lambda q: missing, 99, "x y", 50.0) is None
    assert len(missing.calls) == 3


def test_comparison_table_marks_states():
    a = prod(1, refresh=spec("120 Hz", ceiling=True), panel=spec("IPS", source="properties"))
    b = prod(2, panel=spec("VA"))
    table = compare.comparison_table([a, b])
    assert table.splitlines()[0].startswith("| field | Acme Phone 1 (1) | Acme Phone 2 (2) |")
    assert "| refresh | up to 120 Hz (desc.) | ? |" in table
    assert "| panel | IPS | VA (desc.) |" in table
