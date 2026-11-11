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


REDMI17_EN = {
    "id": 73036751, "name": "Redmi 17", "brand": "Xiaomi", "productType": "Smartphones",
    "properties": '256 GB, Dark Blue, 6.90", Hybrid Dual SIM, 4G',
    "description": """The Xiaomi Redmi 17 is a powerful smartphone equipped with a 6.99-inch display and a resolution of 1600 x 720 pixels. Powered by a MediaTek Helio G91 Ultra processor and 4 GB of RAM, it offers smooth performance for everyday applications and multitasking. With an impressive internal storage capacity of 256 GB, users have plenty of space for photos, videos, and apps. The 50 MP rear camera allows for high-resolution image capture, while the 7500 mAh battery ensures long usage time. The device also supports modern features such as NFC and a fingerprint sensor, making it a practical choice for tech-savvy users.

- Powerful MediaTek Helio G91 Ultra processor
- 50 MP rear camera for high-quality photos
- 7500 mAh battery for long-lasting performance
- 256 GB internal storage for extensive use.""",
}

REDMI17_5G_DE = {
    "id": 74647549, "name": "Redmi 17", "brand": "Xiaomi", "productType": "Smartphone",
    "properties": '128 GB, Vivid Orange, 6.90", Hybrid Dual SIM, 5G',
    "description": """Das Xiaomi Redmi 17 5G ist ein leistungsstarkes Smartphone, das mit einem 6,9 Zoll grossen Display und einer Auflösung von 1600 x 720 Pixeln ausgestattet ist. Angetrieben von einem Snapdragon 4 Gen 5 Prozessor mit einer Taktfrequenz von bis zu 2,4 GHz und 4 GB RAM bietet es eine flüssige Benutzererfahrung. Die Dual-Kamera mit 50 MP auf der Rückseite ermöglicht beeindruckende Fotos, während die 7500 mAh Batterie eine lange Nutzungsdauer gewährleistet. Mit 128 GB internem Speicher, der auf bis zu 2048 GB erweiterbar ist, bietet das Gerät ausreichend Platz für Apps und Medien. Das Smartphone unterstützt 5G-Konnektivität und ist mit Dual-SIM-Funktionalität ausgestattet, was es zu einer flexiblen Wahl für moderne Nutzer macht.

- Leistungsstarker Snapdragon 4 Gen 5 Prozessor
- Dual-Kamera mit 50 MP für hochwertige Fotos
- 7500 mAh Akku für lange Laufzeit
- Erweiterbarer Speicher bis zu 2048 GB.""",
}

NOTE17PRO_DE = {
    "id": 76154192, "name": "Redmi Note 17 Pro", "brand": "Xiaomi", "productType": "Smartphone",
    "properties": '512 GB, Black, 6.83", Dual SIM, 5G',
    "description": """Das Redmi Note 17 Pro 5G vereint ein brillantes 1,5K CrystalRes AMOLED-Display, ein fortschrittliches Kamerasystem und einen aussergewöhnlich langlebigen Akku in einem robusten, zertifizierten Design. Sein 6,83-Zoll-AMOLED-Display bietet eine Auflösung von 2772 x 1280 mit einer Bildwiederholfrequenz von bis zu 120 Hz, einer maximalen Helligkeit von bis zu 3500 Nits und TUV-zertifiziertem, augenschonendem, flimmerfreiem Licht, geschützt durch Corning Gorilla Glass Victus 2 mit SGS-zertifizierter Fallfestigkeit von 3 Metern. Die 50-Megapixel-OIS-Hauptkamera mit einem 8-Megapixel-Ultraweitwinkelobjektiv und einer 16-Megapixel-Frontkamera, unterstützt von einem KI-gestützten Ultra-Klar-Bildsystem, ermöglicht detaillierte Fotos und lebensechte Porträts. Angetrieben vom Qualcomm Snapdragon 6s Gen 4, der im 4-nm-Prozess gefertigt ist, ist das Gerät in mehreren Speicherkonfigurationen mit bis zu 12 GB RAM und 512 GB Speicher erhältlich und läuft mit Xiaomi HyperOS 3, das KI-Tools wie Google Gemini und ein 60-monatiges, neuwertiges Softwareerlebnis umfasst. Ein 8340 mAh Siliziumkarbon-Akku mit 67W HyperCharge unterstützt mehr als zwei Tage Nutzung, während die IP66- und IP68-Zertifizierung für Wasser- und Staubschutz bis zu 2 Meter und 72 Stunden gewährleistet. Ein im Display integrierter Fingerabdrucksensor, KI-gestütztes Gesichtserkennung, ein 300 Prozent lauterer Klang mit Dolby Atmos und Hi-Res Audio sowie Dual-Band-WiFi mit NFC runden dieses leistungsstarke 5G-Smartphone ab, das für anspruchsvolle Alltagsnutzung konzipiert ist.""",
}

MONITOR_DE = {
    "id": 53920915, "name": "27UP850K-W", "brand": "LG Electronics", "productType": "Monitor",
    "properties": '3840 x 2160 Pixel, 27"',
    "description": """Ob Produktivität oder Unterhaltung – der 27UP850K-W von LG Electronics ist der ideale Monitor für alle Lebenslagen. Der IPS-Bildschirm mit einer Bilddiagonalen von 27 Zoll (68,4 Zentimeter) stellt sämtliche Inhalte in nativer 4K-Auflösung von 3.840 x 2.160 Pixeln absolut brillant dar. Seine 95-prozentige Abdeckung des DCI-P3-Farbraums garantiert eine präzise Farbwiedergabe. Die Spitzenhelligkeit von 400 cd/m² sorgt im Zusammenspiel mit DisplayHDR 400 für die Sichtbarkeit sämtlicher Details mit beeindruckender Detailschärfe. Die 5 Millisekunden Reaktionsgeschwindigkeit mit Unterstützung für AMD FreeSync machen ihn auch für Gaming-Fans interessant. Abgerundet wird das Profil des 27UP850K-W als echter Allrounder durch seine Anschlussvielfalt – neben Anschlüssen für HDMI und DisplayPort bietet der 4K-Monitor auch USB-C-Konnektivität, inklusive 90 Watt Ladeleistung für Notebooks. Mehr Monitor geht nicht. Mit dem ergonomischen Edge-ArcLine Standfuss ist er das Glanzstück auf jedem Schreibtisch.""",
}

FLIP8_EN = {
    "id": 72284580, "name": "Galaxy Z Flip8", "brand": "Samsung", "productType": "Smartphones",
    "properties": '256 GB, Graphite, 6.90", Dual SIM, 5G',
    "description": """The Galaxy Z Flip8 impresses with its compact and elegant flip design. With a depth of just 6.1 mm and a slim profile, it fits perfectly in the hand and is easy to carry around. The flexible display ensures a seamless experience when opening and closing the device. With a robust build featuring Corning Gorilla Glass Victus 2 and Advanced Armour Aluminium, as well as IP48 water resistance, the Galaxy Z Flip8 is not only stylish but also durable and ready for everyday use.

Available in the elegant colours Pink, Graphite and Cream, the Galaxy Z Flip8 combines innovative design with powerful technology for an unrivalled user experience.

Galaxy Z Flip8 highlights
• 6.7" Dynamic Display with up to 2,600 nits brightness and a 4.1" HD Super Cover Screen
• Compact and elegant flip design, just 6.1 mm thick.
• 50 MP / 12 MP dual camera, 10 MP front camera
• Smart Switch: Seamless switching between iOS and Android
• Samsung Exynos 2600 processor
• 4,300 mAh battery life and 25W fast charging""",
}


def values(product, lang):
    return {f: s.value for f, s in specs.extract(product, lang).items()}


def test_redmi17_en_ram_storage_and_screen_conflict():
    out = specs.extract(REDMI17_EN, "en")
    assert out["ram"].value == "4 GB" and out["ram"].source == "description"
    assert out["storage"].value == "256 GB" and out["storage"].source == "properties"
    assert out["storage"].conflict is None
    assert out["screen"].conflict == '6.9" (properties) / 6.99" (description)'
    v = values(REDMI17_EN, "en")
    assert v["resolution"] == "1600 x 720"
    assert v["cpu"] == "MediaTek Helio G91 Ultra"
    assert v["battery"] == "7500 mAh" and v["camera"] == "50 MP"
    assert "os" not in v and "android_version" not in v


def test_redmi17_de_decimal_comma_ghz_and_expandable_ceiling():
    out = specs.extract(REDMI17_5G_DE, "de")
    assert out["screen"].conflict is None          # 6,9 Zoll == 6.90"
    assert out["ram"].value == "4 GB" and not out["ram"].ceiling
    assert out["storage"].value == "128 GB" and out["storage"].conflict is None
    assert out["cpu"].value == "Snapdragon 4 Gen 5"
    assert "refresh" not in out                     # 2,4 GHz is CPU clock
    assert out["network"].value == "5G"


def test_note17pro_de_ceilings_hyperos_and_inference():
    out = specs.extract(NOTE17PRO_DE, "de")
    assert out["refresh"].value == "120 Hz" and out["refresh"].ceiling
    assert out["brightness"].value == "3500 nits" and out["brightness"].ceiling
    assert out["ram"].value == "12 GB" and out["ram"].ceiling
    assert out["storage"].value == "512 GB" and out["storage"].conflict is None
    assert out["os"].value == "HyperOS 3"
    assert (out["android_version"].value, out["android_version"].state) == ("16", "inferred")
    v = values(NOTE17PRO_DE, "de")
    assert v["cpu"] == "Qualcomm Snapdragon 6s Gen 4"
    assert v["battery"] == "8340 mAh" and v["charging"] == "67 W"
    assert v["ip"] == "IP66/IP68" and v["panel"] == "AMOLED"
    assert v["camera"] == "50 MP" and v["resolution"] == "2772 x 1280"


def test_monitor_de_thousands_dots_cd_m2_and_watt_charging():
    v = values(MONITOR_DE, "de")
    assert v["resolution"] == "3840 x 2160"
    assert specs.extract(MONITOR_DE, "de")["resolution"].conflict is None
    assert v["screen"] == '27"'
    assert v["panel"] == "IPS"
    assert v["brightness"] == "400 nits"
    assert v["response"] == "5 ms"
    assert v["charging"] == "90 W"
    assert v["ports"] == "HDMI, DisplayPort, USB-C"
    assert "refresh" not in v


def test_flip8_en_thousands_comma_and_no_os_from_mention():
    out = specs.extract(FLIP8_EN, "en")
    assert out["screen"].conflict == '6.9" (properties) / 6.7" (description)'
    assert out["brightness"].value == "2600 nits" and out["brightness"].ceiling
    v = values(FLIP8_EN, "en")
    assert v["battery"] == "4300 mAh"
    assert v["charging"] == "25 W"
    assert v["cpu"] == "Exynos 2600"
    assert v["ip"] == "IP48"
    assert "os" not in v                           # "between iOS and Android" is not a spec


def test_ram_storage_disambiguation_by_keyword():
    out = specs.extract_description("Comes with 16 GB RAM and a 512 GB SSD.", "en")
    assert out["ram"] == ("16 GB", False)
    assert out["storage"] == ("512 GB", False)


def test_ceiling_only_value_is_marked():
    out = specs.extract_description("Storage is expandable up to 1 TB via microSD.", "en")
    assert out["storage"] == ("1 TB", True)


def test_android_stated_and_name_5g_inferred():
    p = {"name": "Phone X 5G", "productType": "Smartphones", "properties": "",
         "description": "Runs Android 16 out of the box."}
    out = specs.extract(p, "en")
    assert (out["android_version"].value, out["android_version"].state) == ("16", "stated")
    assert (out["network"].value, out["network"].state, out["network"].source) == ("5G", "inferred", "name")


def test_infer_android_table():
    assert specs.infer_android("HyperOS 2") == "15"
    assert specs.infer_android("One UI 8") == "16"
    assert specs.infer_android("HyperOS 9") is None
    assert specs.infer_android("Windows 11 Home") is None


def test_extract_orders_fields():
    assert list(specs.extract(NOTE17PRO_DE, "de")) == [f for f in specs.FIELD_ORDER
                                                        if f in specs.extract(NOTE17PRO_DE, "de")]
