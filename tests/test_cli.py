import json

import pytest

import galaxus
from fakes import FakeCatalogue, FakeClient, make_product
from galaxus_lib import transport


def phones(n):
    return [make_product(i, 100.0 + i, description=f"Phone {i} with 8 GB RAM and Android 16.")
            for i in range(1, n + 1)]


@pytest.fixture
def use_catalogue(monkeypatch):
    def install(products, **kw):
        cat = FakeCatalogue(products, **kw)
        monkeypatch.setattr(galaxus, "make_client", lambda: FakeClient(cat))
        return cat
    return install


def test_version(capsys):
    with pytest.raises(SystemExit) as info:
        galaxus.main(["--version"])
    assert info.value.code == 0
    assert capsys.readouterr().out.strip() == f"galaxus-skill {galaxus.__version__}"


def test_count(use_catalogue, capsys):
    use_catalogue(phones(30))
    assert galaxus.main(["count", "phone"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "30"


def test_search_prints_report_and_writes_document(use_catalogue, tmp_path, capsys):
    use_catalogue(phones(30))
    out = tmp_path / "r.json"
    assert galaxus.main(["search", "phone", "--out", str(out), "--top", "5"]) == 0
    text = capsys.readouterr().out
    assert text.startswith("Coverage: complete. 30 unique products")
    assert f"+25 more rows in {out}" in text
    doc = json.loads(out.read_text("utf-8"))
    assert (doc["query"], doc["language"], len(doc["products"])) == ("phone", "en", 30)
    assert doc["products"][0]["specs"]["android_version"]["value"] == "16"
    assert doc["timestamp"].endswith("Z")


def test_unreachable_exits_2(monkeypatch, capsys):
    class Down:
        def search_products(self, *a, **k):
            raise transport.TransportError("network error: down")
    monkeypatch.setattr(galaxus, "make_client", lambda: Down())
    assert galaxus.main(["search", "phone"]) == 2
    assert "unreachable" in capsys.readouterr().err


def test_tool_input_error_exits_3(monkeypatch):
    class Rejects:
        def search_products(self, *a, **k):
            raise transport.ToolInputError("Invalid price range")
    monkeypatch.setattr(galaxus, "make_client", lambda: Rejects())
    assert galaxus.main(["count", "phone"]) == 3


def test_bad_arguments_exit_3():
    for argv in (["search"], ["search", "x", "--min", "0"], ["search", "x", "--min", "9", "--max", "5"]):
        try:
            code = galaxus.main(argv)
        except SystemExit as info:
            code = info.code
        assert code == 3, argv


def test_error_message_mid_run_exits_4_with_checkpoint(use_catalogue, tmp_path, capsys):
    use_catalogue(phones(120), error_on_call=2)
    out = tmp_path / "r.json"
    assert galaxus.main(["search", "phone", "--out", str(out)]) == 4
    assert "Coverage: failed." in capsys.readouterr().out
    doc = json.loads(out.read_text("utf-8"))
    assert doc["status"] == "failed" and len(doc["products"]) == 50


def test_filter_verdicts(use_catalogue, tmp_path, capsys):
    use_catalogue(phones(30))
    out = tmp_path / "r.json"
    galaxus.main(["search", "phone", "--out", str(out)])
    capsys.readouterr()
    assert galaxus.main(["filter", "--from", str(out), "--where", "android_version>=17"]) == 0
    assert "Verdict: none qualify" in capsys.readouterr().out
    assert galaxus.main(["filter", "--from", str(out), "--where", "ram>=8"]) == 0
    assert "30 checked, 30 match" in capsys.readouterr().out
    assert galaxus.main(["filter", "--from", str(out), "--where", "nonsense"]) == 3


def test_compare_table_lookup_and_language_refusal(use_catalogue, tmp_path, capsys):
    use_catalogue(phones(30))
    out = tmp_path / "r.json"
    galaxus.main(["search", "phone", "--max", "115", "--out", str(out)])  # ids 1..15 only
    capsys.readouterr()
    code = galaxus.main(["compare", "--from", str(out), "--ids", "1,20,999",
                         "--lookup", "20=Acme Phone 20@120"])
    text = capsys.readouterr().out
    assert code == 0
    assert "Acme Phone 1 (1)" in text and "Acme Phone 20 (20)" in text
    assert "999: not in FILE" in text
    assert galaxus.main(["compare", "--from", str(out), "--ids", "1", "--lang", "de"]) == 3


# ---- fix round 1

def _code(argv):
    try:
        return galaxus.main(argv)
    except SystemExit as info:
        return info.code


def test_out_in_missing_directory_exits_3_before_any_call(use_catalogue, tmp_path, capsys):
    cat = use_catalogue(phones(30))
    assert galaxus.main(["search", "phone", "--out", str(tmp_path / "nodir" / "x.json")]) == 3
    assert cat.calls == []
    assert "nodir" in capsys.readouterr().err
    assert not (tmp_path / "nodir").exists()


def test_checkpoint_write_failure_warns_once_and_continues(use_catalogue, tmp_path, monkeypatch, capsys):
    use_catalogue(phones(120))
    real, state = galaxus._write_json, {"n": 0}

    def flaky(path, doc):
        state["n"] += 1
        if state["n"] <= 2:
            raise OSError("disk full")
        real(path, doc)
    monkeypatch.setattr(galaxus, "_write_json", flaky)
    out = tmp_path / "r.json"
    assert galaxus.main(["search", "phone", "--out", str(out)]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("Coverage: complete.")
    assert captured.err.count("warning") == 1 and "disk full" in captured.err


def test_final_write_failure_exits_4_with_report(use_catalogue, tmp_path, monkeypatch, capsys):
    use_catalogue(phones(30))

    def broken(path, doc):
        raise OSError("read-only")
    monkeypatch.setattr(galaxus, "_write_json", broken)
    assert galaxus.main(["search", "phone", "--out", str(tmp_path / "r.json")]) == 4
    captured = capsys.readouterr()
    assert captured.out.startswith("Coverage: complete.")
    assert "read-only" in captured.err


def test_write_json_removes_tmp_on_failure(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise OSError("nope")
    monkeypatch.setattr(galaxus.os, "replace", boom)
    target = tmp_path / "r.json"
    with pytest.raises(OSError):
        galaxus._write_json(str(target), {"a": 1})
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("argv", [
    ["search", "x", "--max-calls", "0"], ["search", "x", "--max-calls", "-3"], ["search", "x", "--max-calls", "a"],
    ["search", "x", "--top", "0"], ["search", "x", "--top", "-1"],
    ["filter", "--from", "f.json", "--top", "0"],
    ["search", "x", "--min", "1.5"], ["search", "x", "--max", "1000001"],
    ["count", "x", "--min", "9", "--max", "5"],
])
def test_invalid_numbers_exit_3(argv, use_catalogue):
    cat = use_catalogue(phones(3))
    assert _code(argv) == 3
    assert cat.calls == []


def test_min_equals_max_accepted(use_catalogue):
    use_catalogue(phones(30))
    assert galaxus.main(["search", "phone", "--min", "100", "--max", "100"]) == 0


def test_root_error_message_exits_4(use_catalogue, capsys):
    use_catalogue(phones(30), error_on_call=1)
    assert galaxus.main(["search", "phone"]) == 4
    capsys.readouterr()
    use_catalogue(phones(30), error_on_call=1)
    assert galaxus.main(["count", "phone"]) == 4
    captured = capsys.readouterr()
    assert "Galaxus search error" in captured.err and captured.out == ""


def test_count_unreachable_exits_2(monkeypatch, capsys):
    class Down:
        def search_products(self, *a, **k):
            raise transport.TransportError("network error: down")
    monkeypatch.setattr(galaxus, "make_client", lambda: Down())
    assert galaxus.main(["count", "phone"]) == 2
    assert "unreachable" in capsys.readouterr().err


def test_bad_files_exit_3(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", "utf-8")
    other = tmp_path / "other.json"
    other.write_text("[1]", "utf-8")
    for path in (tmp_path / "missing.json", bad, other):
        assert galaxus.main(["filter", "--from", str(path), "--where", "ram>=8"]) == 3
        assert galaxus.main(["compare", "--from", str(path), "--ids", "1"]) == 3


def test_compare_lookup_transport_failure_exits_4(use_catalogue, tmp_path, monkeypatch, capsys):
    use_catalogue(phones(30))
    out = tmp_path / "r.json"
    galaxus.main(["search", "phone", "--max", "115", "--out", str(out)])
    capsys.readouterr()

    class Down:
        def search_products(self, *a, **k):
            raise transport.TransportError("network error: down")
    monkeypatch.setattr(galaxus, "make_client", lambda: Down())
    code = galaxus.main(["compare", "--from", str(out), "--ids", "1,20", "--lookup", "20=Acme Phone 20@120"])
    text = capsys.readouterr().out
    assert code == 4
    assert "Acme Phone 1 (1)" in text and "20: lookup failed" in text


def test_compare_lookup_not_found_stays_exit_0(use_catalogue, tmp_path, capsys):
    use_catalogue(phones(30))
    out = tmp_path / "r.json"
    galaxus.main(["search", "phone", "--max", "115", "--out", str(out)])
    assert galaxus.main(["compare", "--from", str(out), "--ids", "1,555", "--lookup", "555=Nothing@120"]) == 0
