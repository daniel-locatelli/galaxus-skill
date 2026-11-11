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
