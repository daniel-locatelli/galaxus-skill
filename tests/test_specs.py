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


# ---- Task 7 fix round 1

def desc(text, lang="en"):
    return specs.extract_description(text, lang)


@pytest.mark.parametrize("text, lang", [
    ("Mit Abmessungen von 162,4 x 75,7 x 8,2 mm liegt es gut in der Hand.", "de"),
    ("The phone measures 160.5 x 75.2 x 8.2 mm.", "en"),
    ("Footprint 300 x 200 mm.", "en"),
])
def test_dimensions_are_not_resolution(text, lang):
    assert "resolution" not in desc(text, lang)


def test_resolution_thousands_and_plain_still_work():
    assert desc("Auflösung von 3.840 x 2.160 Pixeln.", "de")["resolution"] == ("3840 x 2160", False)
    assert desc("A 2560 x 1440 panel.")["resolution"] == ("2560 x 1440", False)


def test_keyword_directly_before_value_wins():
    out = desc("RAM: 8 GB, Storage: 256 GB.")
    assert out["ram"] == ("8 GB", False) and out["storage"] == ("256 GB", False)


def test_graphics_memory_is_not_ram():
    out = desc("NVIDIA RTX 4060 with 8 GB GDDR6 and 16 GB RAM, plus 1 TB SSD.")
    assert out["ram"] == ("16 GB", False) and out["storage"] == ("1 TB", False)


@pytest.mark.parametrize("text, lang, field, value", [
    ("Available with up to 16 GB of RAM and 1 TB of storage.", "en", "storage", "1 TB"),
    ("Erhältlich mit bis zu 12 GB RAM, 512 GB Speicher.", "de", "storage", "512 GB"),
    ("Erhältlich mit bis zu 12 GB RAM und 512 GB Speicher.", "de", "storage", "512 GB"),
])
def test_ceiling_covers_following_values_of_same_kind(text, lang, field, value):
    assert desc(text, lang)[field] == (value, True)


def test_ceiling_does_not_cross_into_other_units():
    out = desc("Taktfrequenz von bis zu 2,4 GHz und 4 GB RAM.", "de")
    assert out["ram"] == ("4 GB", False)


def test_refresh_needs_its_own_keyword_not_touch_sampling():
    assert desc("Touch sampling rate of 240 Hz and a refresh rate of 120 Hz.")["refresh"] == ("120 Hz", False)
    assert "refresh" not in desc("Frequency response 20 Hz - 20 kHz.")
    assert "refresh" not in desc("Frequenzgang 20 Hz bis 20 kHz.", "de")


def test_front_camera_is_not_main_camera():
    assert desc("The 32 MP front camera and the 50 MP main camera.")["camera"] == ("50 MP", False)
    assert "camera" not in desc("Die 32 MP Frontkamera macht scharfe Selfies.", "de")


@pytest.mark.parametrize("text, lang", [
    ("Compatible with smartphones running Android 8.0 or later.", "en"),
    ("Smart Switch: migrate easily from Android 10 devices.", "en"),
    ("Kompatibel mit Smartphones ab Android 9.", "de"),
    ("Funktioniert mit Android 11 oder höher.", "de"),
])
def test_os_compatibility_mentions_are_not_the_os(text, lang):
    out = desc(text, lang)
    assert "os" not in out and "android_version" not in out


@pytest.mark.parametrize("text", ["Connects via 2.4G wireless receiver.", "Uses a 2,4G dongle.",
                                  "Video link on 5.8G."])
def test_network_not_inside_radio_band(text):
    assert "network" not in desc(text)


def test_lte_in_description_is_not_a_conflict_with_lte_properties():
    p = {"name": "X", "productType": "Smartphones", "properties": "128 GB, Black, 6.1\", LTE",
         "description": "Supports LTE for fast mobile data."}
    assert specs.extract(p, "en")["network"].conflict is None


@pytest.mark.parametrize("text, lang", [("Der Akku mit 5,000 mAh hält lange.", "de"),
                                        ("The 5.000 mAh battery lasts.", "en")])
def test_battery_thousands_reparsed(text, lang):
    assert desc(text, lang)["battery"] == ("5000 mAh", False)


def test_battery_implausible_dropped():
    assert "battery" not in desc("A 4.5 mAh coin cell.")


def test_expandable_base_value_is_not_ceiling():
    assert desc("Storage: 128 GB, expandable up to 1 TB via microSD.")["storage"] == ("128 GB", False)


def test_expandable_value_before_keyword_is_ceiling():
    assert desc("Der Speicher ist auf 1 TB erweiterbar.", "de")["storage"] == ("1 TB", True)


def test_plain_value_preferred_over_earlier_ceiling():
    out = desc("Peak brightness up to 2000 nits. Typical brightness 800 nits.")
    assert out["brightness"] == ("800 nits", False)


def test_ceiling_never_creates_conflict():
    p = {"name": "X", "productType": "Smartphones", "properties": '256 GB, Black, 6.1", 5G',
         "description": "Der Speicher ist bis zu 512 GB gross."}
    out = specs.extract(p, "de")
    assert out["storage"].value == "256 GB" and out["storage"].conflict is None


def test_speaker_watts_are_not_charging():
    assert "charging" not in desc("The 30 W speakers deliver rich sound.")
    assert desc("Supports 45 W fast charging and has 2 W speakers.")["charging"] == ("45 W", False)


@pytest.mark.parametrize("text, cpu", [
    ("Powered by an Intel Core Ultra 7 155H processor.", "Intel Core Ultra 7 155H"),
    ("With an AMD Ryzen 7 7840HS and 16 GB RAM.", "AMD Ryzen 7 7840HS"),
    ("The Snapdragon 8 Elite chip is fast.", "Snapdragon 8 Elite"),
])
def test_cpu_keeps_full_model(text, cpu):
    assert desc(text)["cpu"] == (cpu, False)


def test_cpu_truncated_model_is_a_conflict():
    # Round 1 compared by containment; round 2 review: only vendor prefix / "processor"-style
    # filler may differ, so a description missing the model number is a conflict.
    p = {"name": "X", "productType": "Notebooks", "properties": '15.60", 512 GB, 32 GB, CH, Intel Core Ultra 7 155H',
         "description": "Powered by Intel Core Ultra 7 graphics."}
    assert specs.extract(p, "en")["cpu"].conflict is not None


@pytest.mark.parametrize("text", ["Refresh rate bis 144 Hz.", "Refresh rate max. 144 Hz.",
                                  "A maximum refresh rate of 144 Hz."])
def test_more_ceiling_phrases(text):
    assert desc(text, "de")["refresh"] == ("144 Hz", True)


def test_tot_is_ceiling_only_in_dutch():
    assert desc("Opslag tot 512 GB.", "nl")["storage"] == ("512 GB", True)
    assert desc("Storage tot 512 GB.", "en")["storage"] == ("512 GB", False)


def test_flip8_camera_main_value_not_the_one_next_to_keyword():
    # "50 MP / 12 MP dual camera, 10 MP front camera": the first listed value is the main camera.
    assert values(FLIP8_EN, "en")["camera"] == "50 MP"


# ---- Task 7 fix round 2

@pytest.mark.parametrize("text, lang", [("Frequency range 20 Hz - 20 kHz for rich sound.", "en"),
                                        ("Der Frequenzbereich reicht von 20 Hz bis 20 kHz.", "de"),
                                        ("A 60 Hz mains adapter.", "en")])
def test_refresh_requires_refresh_keyword(text, lang):
    assert "refresh" not in desc(text, lang)


def test_selfie_camera_keyword_is_one_unit():
    assert desc("The selfie camera with 32 MP and the main camera with 50 MP shine.")["camera"] == ("50 MP", False)
    assert "camera" not in desc("Die Selfie-Kamera mit 32 MP.", "de")


@pytest.mark.parametrize("text, cpu", [
    ("Powered by the MediaTek Dimensity 7300 Ultra 5G chip.", "MediaTek Dimensity 7300 Ultra"),
    ("Snapdragon 8 Gen 3 8GB RAM 256GB storage.", "Snapdragon 8 Gen 3"),
    ("Snapdragon 8 Gen 3 12 GB RAM.", "Snapdragon 8 Gen 3"),
])
def test_cpu_suffix_stops_at_network_and_sizes(text, cpu):
    assert desc(text)["cpu"] == (cpu, False)


def test_os_after_update_ceiling_is_not_stated():
    out = specs.extract({"name": "X", "productType": "Smartphones", "properties": "",
                         "description": "Samsung guarantees updates up to Android 21 for this phone running One UI 8."},
                        "en")
    assert out["os"].value == "One UI 8"
    assert out["android_version"].value == "16" and out["android_version"].state == "inferred"
    assert "os" not in desc("Mit Updates bis Android 20.", "de")


def test_max_dot_needs_a_following_number():
    assert desc("The iPhone 16 Pro Max. 256 GB storage.")["storage"] == ("256 GB", False)


@pytest.mark.parametrize("text, lang, value", [
    ("128 GB storage expandable via microSD.", "en", "128 GB"),
    ("Der 256 GB Speicher erweiterbar per microSD-Karte.", "de", "256 GB"),
    ("Storage 128 GB expandable up to 1 TB.", "en", "128 GB"),
])
def test_expandable_base_value_is_not_ceiling_round2(text, lang, value):
    assert desc(text, lang)["storage"] == (value, False)


def test_expandable_target_is_ceiling():
    assert desc("Storage expandable up to 1 TB.")["storage"] == ("1 TB", True)
    assert desc("Speicher erweiterbar auf 1 TB.", "de")["storage"] == ("1 TB", True)


@pytest.mark.parametrize("text, lang", [("8 GB RAM 256 GB storage.", "en"), ("8 GB RAM 256 GB Speicher.", "de"),
                                        ("RAM 8 GB Speicher 256 GB.", "de")])
def test_equidistant_keyword_binds_to_the_free_value(text, lang):
    out = desc(text, lang)
    assert out["ram"] == ("8 GB", False) and out["storage"] == ("256 GB", False)


def _cpu_product(props_cpu, description):
    return {"name": "X", "productType": "Notebooks", "properties": f'15.60", 512 GB, 32 GB, CH, {props_cpu}',
            "description": description}


def test_cpu_conflict_rules():
    out = specs.extract(_cpu_product("Apple M3", "Powered by the Apple M3 Pro chip."), "en")
    assert out["cpu"].conflict == "Apple M3 (properties) / Apple M3 Pro (description)"
    out = specs.extract(_cpu_product("Intel Core Ultra 7 155H Processor", "With an Intel Core Ultra 7 155H."), "en")
    assert out["cpu"].conflict is None
    out = specs.extract(_cpu_product("M5", "Powered by the Apple M5 chip."), "en")
    assert out["cpu"].conflict is None


def test_guard_speaker_vs_charging():
    assert desc("45 W charging speaker dock, 20 W speakers.")["charging"] == ("45 W", False)
    assert "charging" not in desc("Loud 20 W speakers and fast charging support.")


@pytest.mark.parametrize("text", ["RAM, 8 GB.", "RAM / 8 GB.", "RAM (8 GB)."])
def test_guard_no_binding_across_comma_slash_bracket(text):
    assert "ram" not in desc(text)


def test_guard_equidistant_keyword_without_free_value_skips():
    assert "ram" not in desc("8 GB RAM 256 GB.")


def test_guard_cross_group_tie_drops_value():
    out = desc("RAM 8 GB SSD.")
    assert "ram" not in out and "storage" not in out


def test_guard_vram_before_ram_keyword():
    assert "ram" not in desc("8 GB GDDR6 RAM.")


def test_guard_os_from_without_migrate():
    assert "os" not in desc("Der Wechsel von Android 10 ist einfach.", "de")


def test_guard_res_not_third_dimension_integers():
    assert "resolution" not in desc("Abmessungen 1230 x 720 x 230.", "de")


def test_guard_res_part_decimal_without_unit():
    assert "resolution" not in desc("Grösse 162,4 x 75,7 laut Hersteller.", "de")


# ---- Task 7 fix round 3

@pytest.mark.parametrize("text, lang", [("The monitor speakers cover a frequency range of 20 Hz.", "en"),
                                        ("Der Monitor-Lautsprecher bietet 20 Hz bis 20 kHz.", "de"),
                                        ("Übertragungsbereich 20 Hz.", "de"),
                                        ("Plage de fréquences de 20 Hz.", "fr"),
                                        ("Gamma di frequenza 20 Hz.", "it")])
def test_audio_frequency_is_not_refresh(text, lang):
    assert "refresh" not in desc(text, lang)


def test_speakers_next_to_display_refresh_keep_refresh():
    assert desc("Stereo speakers and a 120 Hz display.")["refresh"] == ("120 Hz", False)


def test_expand_to_article_only_in_it_fr():
    assert desc("It has a 128 GB expandable storage.")["storage"] == ("128 GB", False)
    assert desc("Memoria interna espandibile a 1 TB.", "it")["storage"] == ("1 TB", True)


def test_nearest_keyword_wins_among_ram_candidates():
    # 8 GB binds "working memory" at distance 9, 16 GB binds "RAM" at distance 1.
    assert desc("With 8 GB of fast working memory and 16 GB RAM.")["ram"] == ("16 GB", False)


def test_uppercase_max_dot_is_ceiling():
    assert desc("Refresh rate MAX. 120 Hz.")["refresh"] == ("120 Hz", True)


def test_german_hz_before_display():
    assert desc("Das 144 Hz Display überzeugt.", "de")["refresh"] == ("144 Hz", False)
