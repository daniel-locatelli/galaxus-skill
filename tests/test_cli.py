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
