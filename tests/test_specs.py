import pytest

from galaxus_lib import specs


@pytest.mark.parametrize("text, lang, value", [
    ("6,99", "de", 6.99),
    ("6.90", "en", 6.9),
    ("8,340", "en", 8340),
    ("2,600", "en", 2600),
    ("3.840", "de", 3840),
    ("8'340", "de", 8340),
    ("1.500", "en", 1.5),
    ("6,830", "de", 6.83),
])
def test_parse_number_by_language(text, lang, value):
    assert specs.parse_number(text, lang) == value


def test_fmt_drops_trailing_zeros():
    assert specs.fmt(6.90) == "6.9"
    assert specs.fmt(256.0) == "256"
    assert specs.fmt(15.6) == "15.6"


def test_phone_properties():
    out = specs.parse_properties('256 GB, Dark Blue, 6.90", Hybrid Dual SIM, 4G', "Smartphones")
    assert out == {"storage": "256 GB", "colour": "Dark Blue", "screen": '6.9"',
                   "sim": "Hybrid Dual SIM", "network": "4G"}


def test_phone_properties_with_two_colour_tokens_and_no_sim():
    out = specs.parse_properties('256 GB, Black, Schwarz, 6.90", 5G', "Smartphone")
    assert out["colour"] == "Black / Schwarz"
    assert "sim" not in out


def test_laptop_properties_storage_before_ram():
    out = specs.parse_properties('15.60", 512 GB, 32 GB, CH, Intel Core Ultra 7 255U', "Notebooks")
    assert out == {"screen": '15.6"', "storage": "512 GB", "ram": "32 GB",
                   "keyboard": "CH", "cpu": "Intel Core Ultra 7 255U"}


def test_laptop_apple_cpu():
    assert specs.parse_properties('13.60", 512 GB, 16 GB, CH, M5', "Notebooks")["cpu"] == "M5"


def test_monitor_properties_en_and_de():
    assert specs.parse_properties('2560 x 1440 pixels, 27"', "Monitor") == {
        "resolution": "2560 x 1440", "screen": '27"'}
    assert specs.parse_properties('3840 x 2160 Pixel, 27"', "Monitor")["resolution"] == "3840 x 2160"


def test_unknown_type_uses_generic_patterns_only():
    assert specs.parse_properties("Black, 128 GB", "Phone cases") == {}
    assert specs.parse_properties("", "Smartphones") == {}


# ---- fix round 1

@pytest.mark.parametrize("ptype, schema", [
    ("Smartphone-Hüllen", None), ("Notebook bags", None), ("Monitor mounts", None),
    ("Protection d'écran", None), ("Ordinateurs portables", "laptop"),
    ("Portatili", None), ("Notebooks", "laptop"), ("Laptops", "laptop"),
    ("Smartphones", "phone"), ("Handys", "phone"), ("Monitore", "monitor"),
    ("Moniteurs", "monitor"), ("Smartphone", "phone"), ("Monitor", "monitor"),
])
def test_schema_for_whole_words_and_accessories(ptype, schema):
    assert specs.schema_for(ptype) == schema


def test_laptop_lone_size_token_is_not_guessed():
    out = specs.parse_properties('64 GB, Silver, 11.60"', "Notebooks")
    assert "ram" not in out and "storage" not in out


@pytest.mark.parametrize("props", ['16 GB, 512 GB', '512 GB, 16 GB'])
def test_laptop_two_sizes_by_plausibility(props):
    out = specs.parse_properties(props, "Notebooks")
    assert out["ram"] == "16 GB" and out["storage"] == "512 GB"


def test_laptop_two_equal_sizes_assign_neither():
    out = specs.parse_properties("256 GB, 256 GB", "Notebooks")
    assert "ram" not in out and "storage" not in out


def test_phone_colour_ignores_non_colour_tokens():
    out = specs.parse_properties('Black, 5G NR, 6.1"', "Smartphones")
    assert out["colour"] == "Black"
    out = specs.parse_properties('128 GB, Blue, Wi-Fi, NFC, eSIM, 6.1"', "Smartphones")
    assert out["colour"] == "Blue"


def test_first_number_uses_language_aware_parsing():
    assert specs.first_number("8,340 mAh") == 8340.0
    assert specs.first_number("1,5 kg", "de") == 1.5
    assert specs.first_number("6.9 inch") == 6.9
    assert specs.first_number("none") is None


def test_parse_number_mixed_separators():
    assert specs.parse_number("1,234.56", "en") == 1234.56
    assert specs.parse_number("1.234,56", "de") == 1234.56


# ---- fix round 2

@pytest.mark.parametrize("ptype, schema", [
    ("Notebooks", "laptop"), ("Notebook", "laptop"), ("Ordinateur portable", "laptop"),
    ("Monitor", "monitor"), ("Moniteur", "monitor"),
    ("Smartphones", "phone"), ("Smartphone", "phone"), ("Téléphone portable", "phone"),
    ("  notebooks ", "laptop"), ("Laptop", "laptop"), ("Laptops", "laptop"),
    ("Monitors", "monitor"), ("Monitore", "monitor"), ("Moniteurs", "monitor"),
    ("Ordinateurs portables", "laptop"), ("Téléphones portables", "phone"),
    ("Handy", "phone"), ("Handys", "phone"),
    ("Smartphone-Schutzfolien", None), ("Zubehör für Notebooks", None),
    ("Housses pour ordinateurs portables", None), ("Smartphone-Hüllen", None),
    ("Notebook bags", None), ("Monitor mounts", None), ("", None),
])
def test_schema_for_exact_allow_list(ptype, schema):
    assert specs.schema_for(ptype) == schema


def test_laptop_two_sizes_ram_must_be_clearly_smaller():
    out = specs.parse_properties("128 GB, 256 GB", "Notebooks")
    assert "ram" not in out and "storage" not in out
    out = specs.parse_properties("64 GB, 128 GB", "Notebooks")
    assert out["ram"] == "64 GB" and out["storage"] == "128 GB"
    out = specs.parse_properties("16 GB, 512 GB", "Notebooks")
    assert out["ram"] == "16 GB" and out["storage"] == "512 GB"


def test_phone_colour_skips_feature_tokens_and_caps_at_two():
    out = specs.parse_properties('256 GB, Black, Bluetooth, USB-C, 6.1"', "Smartphones")
    assert out["colour"] == "Black"
    out = specs.parse_properties('256 GB, Black, GPS, Android, iOS, Wi-Fi 6', "Smartphones")
    assert out["colour"] == "Black"
    out = specs.parse_properties('256 GB, Black, Schwarz, Noir', "Smartphones")
    assert out["colour"] == "Black / Schwarz"
