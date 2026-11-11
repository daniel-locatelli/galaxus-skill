"""Spec extraction from Galaxus product records. Spec: "Spec extraction".

A field in the result is *stated* (from `properties`, or from `description`
next to a field keyword) or *inferred* (derived). A missing field is unknown.
Field list, schemas and keyword tables: ../../references/spec-fields.md.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

STATED, INFERRED = "stated", "inferred"

FIELD_ORDER = ("os", "android_version", "cpu", "ram", "storage", "screen", "resolution",
               "refresh", "panel", "brightness", "response", "battery", "charging", "camera",
               "weight", "network", "sim", "ip", "ports", "keyboard", "colour")


@dataclass
class Spec:
    value: str
    state: str          # stated | inferred
    source: str         # properties | description | name
    ceiling: bool = False
    conflict: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- numbers

# A number not glued to a preceding digit/separator: thousands-grouped ("8,340",
# "3.840", "8'340") or plain with optional decimals ("6,99", "6.90", "120").
NUM = r"(?<![\d.,'’])(\d{1,3}(?:[,.'’]\d{3})+(?!\d)|\d+(?:[.,]\d+)?)"


def parse_number(text: str, lang: str) -> float:
    s = text.replace("'", "").replace("’", "")
    if "," in s and "." in s:  # both present: the last one is the decimal mark
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        return float(s.replace("." if dec == "," else ",", "").replace(dec, "."))
    if re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+", s):
        sep = s[-4]
        if s.count(sep) > 1 or (sep == "," and lang == "en") or (sep == "." and lang != "en"):
            return float(s.replace(sep, ""))
    return float(s.replace(",", "."))


def fmt(x: float) -> str:
    x = float(x)
    return str(int(x)) if x.is_integer() else f"{x:.2f}".rstrip("0").rstrip(".")


def first_number(value: str, lang: str = "en") -> float | None:
    m = re.search(NUM, value)
    return parse_number(m.group(1), lang) if m else None


# ------------------------------------------------------------- properties

_PROP = {
    "resolution": re.compile(r"^(\d{3,5}) x (\d{3,5})(?: \w+)?$"),
    "screen": re.compile(r'^(\d+(?:[.,]\d+)?)"$'),
    "size": re.compile(r"^(\d+(?:[.,]\d+)?) (GB|TB)$"),
    "network": re.compile(r"^(?:2G|3G|4G|5G|LTE)$"),
    "sim": re.compile(r"SIM"),
    "keyboard": re.compile(r"^(?:CH|DE|FR|IT|US|UK|NL|ES|INT|Nordic)$"),
    "cpu": re.compile(r"^(?:Intel|AMD|Apple|Snapdragon|Qualcomm|MediaTek|M\d)\b"),
}

# Positional schemas (seen 2026-11-11). Patterns decide; position breaks ties.
SCHEMAS = {
    "phone": ("storage", "colour", "screen", "sim", "network"),
    "laptop": ("screen", "storage", "ram", "keyboard", "cpu"),
    "monitor": ("resolution", "screen"),
}
# Exact allow-list of productType values (probed live 2026-11-11, all languages).
# Anything else, accessories included, is generic: unknown beats wrong.
_TYPES = {
    "laptop": ("notebooks", "notebook", "ordinateur portable", "ordinateurs portables",
               "laptop", "laptops"),
    "monitor": ("monitor", "monitors", "monitore", "moniteur", "moniteurs"),
    "phone": ("smartphones", "smartphone", "téléphone portable", "téléphones portables",
              "handy", "handys"),
}
_TYPE_LOOKUP = {w: schema for schema, words in _TYPES.items() for w in words}
_NON_COLOUR = re.compile(
    r"^(?:wi-?fi.*|wlan.*|lte|nfc|esim|dual sim|single sim|5g|4g|bluetooth.*|usb.*|gps|"
    r"android.*|ios.*)$", re.I)


def schema_for(product_type: str) -> str | None:
    return _TYPE_LOOKUP.get(product_type.replace(" ", " ").strip().lower())


def _size_gb(token: str) -> float:
    number, unit = token.split(" ")
    return float(number) * (1000 if unit == "TB" else 1)


def parse_properties(properties: str, product_type: str) -> dict[str, str]:
    properties = properties.replace(" ", " ")  # real strings contain NBSP
    tokens = [t.strip() for t in properties.split(", ") if t.strip()]
    schema = schema_for(product_type)
    out: dict[str, str] = {}
    sizes: list[str] = []
    leftovers: list[str] = []
    for tok in tokens:
        if m := _PROP["resolution"].match(tok):
            out.setdefault("resolution", f"{m[1]} x {m[2]}")
        elif m := _PROP["screen"].match(tok):
            out.setdefault("screen", fmt(float(m[1].replace(",", "."))) + '"')
        elif m := _PROP["size"].match(tok):
            sizes.append(f"{fmt(float(m[1].replace(',', '.')))} {m[2]}")
        elif _PROP["network"].match(tok):
            out.setdefault("network", tok)
        elif _PROP["sim"].search(tok):
            out.setdefault("sim", tok)
        elif _PROP["keyboard"].match(tok):
            out.setdefault("keyboard", tok)
        elif _PROP["cpu"].match(tok):
            out.setdefault("cpu", tok)
        else:
            leftovers.append(tok)
    if schema is None:
        return out
    fields = SCHEMAS[schema]
    if "storage" in fields and "ram" not in fields and len(sizes) == 1:
        out["storage"] = sizes[0]
    elif "ram" in fields and len(sizes) == 2:
        small, large = sorted(sizes, key=_size_gb)
        lo, hi = _size_gb(small), _size_gb(large)
        if lo <= 64 and hi >= 128 and hi >= 2 * lo:
            out["ram"], out["storage"] = small, large
    colours = [t for t in leftovers if not re.search(r"\d", t) and not _NON_COLOUR.match(t)]
    if "colour" in fields and colours:
        out["colour"] = " / ".join(colours[:2])
    return out


# ------------------------------------------------------------ description

# Keyword regexes per field and language; English is always added as well.
_KW = {
    "ram": {"en": [r"\bram\b", r"\bworking memory"], "de": [r"\bram\b", r"\barbeitsspeicher"],
            "fr": [r"\bram\b", r"mémoire vive"], "it": [r"\bram\b"], "nl": [r"\bram\b", r"\bwerkgeheugen"]},
    "storage": {"en": [r"\bstorage", r"\binternal memory", r"\bssd\b", r"\brom\b", r"\bhard drive"],
                "de": [r"\bspeicher", r"\bssd\b", r"\bfestplatte"],
                "fr": [r"\bstockage", r"mémoire interne", r"\bssd\b"],
                "it": [r"\bmemoria interna", r"\barchiviazione", r"\bssd\b"], "nl": [r"\bopslag", r"\bssd\b"]},
    "weight": {"en": [r"\bweigh"], "de": [r"\bgewicht", r"\bwiegt"], "fr": [r"\bpoids", r"\bpèse"],
               "it": [r"\bpeso", r"\bpesa"], "nl": [r"\bgewicht", r"\bweegt"]},
    "charging": {"en": [r"charg"], "de": [r"\blade", r"charg"], "fr": [r"charg"], "it": [r"ricaric"],
                 "nl": [r"\bopla", r"\blaad"]},
    "speaker": {"en": [r"\bspeaker", r"\baudio", r"\bsound"], "de": [r"\blautsprecher", r"\bklang"],
                "fr": [r"haut-parleur", r"\bson\b"], "it": [r"altoparlant"], "nl": [r"\bluidspreker", r"\bgeluid"]},
    "os": {"en": [r"operating system", r"\bruns\b", r"\brunning\b"], "de": [r"betriebssystem", r"läuft (?:mit|auf)"],
           "fr": [r"système d.exploitation"], "it": [r"sistema operativo"], "nl": [r"besturingssysteem"]},
    "diagonal": {"en": [r"diagonal"], "de": [r"diagonale"], "fr": [r"diagonale"], "it": [r"diagonale"],
                 "nl": [r"diagonaal"]},
}

# A value right after one of these is a range/ceiling, not this variant's value.
_CEILING = ("up to", "bis zu", "jusqu'à", "jusqu’à", "fino a", "tot ", "memory extension",
            "speichererweiterung", "configurations", "konfigurationen")
_EXPAND = re.compile(r"\s*(?:\S+\s+)?(?:expandable|erweiterbar|extensible|espandibile|uitbreidbaar)", re.I)
_BOUNDARY = re.compile(r"[.!?](?=\s|$)|\n|•")
_WINDOW = 40


def _kw(group: str, lang: str) -> list[str]:
    table = _KW[group]
    return table.get(lang, []) + ([] if lang == "en" else table["en"])


def _sentence_span(text: str, pos: int) -> tuple[int, int]:
    start, end = 0, len(text)
    for m in _BOUNDARY.finditer(text):
        if m.end() <= pos:
            start = m.end()
        elif m.start() >= pos:
            end = m.start()
            break
    return start, end


def _keyword_distance(text: str, start: int, end: int, patterns: list[str]) -> int | None:
    s0, s1 = _sentence_span(text, start)
    lo, hi = max(s0, start - _WINDOW), min(s1, end + _WINDOW)
    best = None
    for pat in patterns:
        for m in re.finditer(pat, text[lo:hi], re.I):
            a, b = m.start() + lo, m.end() + lo
            d = start - b if b <= start else (a - end if a >= end else 0)
            best = d if best is None else min(best, d)
    return best


def _is_ceiling(text: str, start: int, end: int, unit: str) -> bool:
    s0, _ = _sentence_span(text, start)
    before = text[max(s0, start - 60):start]
    low = before.lower()
    hits = [low.rfind(p) + len(p) for p in _CEILING if p in low]
    if hits:
        gap = before[max(hits):]
        if not re.search(r"\d", gap):
            return True
        # "bis zu 12 GB RAM und 512 GB": the phrase also covers the next value of the same unit.
        m = re.fullmatch(r"\s*[\d.,'’]+\s*(\S+)(?:\s+\S+)?\s+(?:and|und|et|e|en|,)\s+", gap, re.I)
        if m and m.group(1).lower() == unit.lower():
            return True
    return bool(_EXPAND.match(text, end))


def _rx(unit: str, flags=re.I):
    return re.compile(NUM + unit, flags)


_UNIT_FIELDS = {
    "battery": (_rx(r"\s?mAh\b"), "mAh"),
    "camera": (_rx(r"\s?-?\s?(?:MP|mega-?pixels?|mégapixels?)\b"), "MP"),
    "brightness": (_rx(r"\s?(?:nits?\b|cd/m²|cd/m2)"), "nits"),
    "response": (_rx(r"\s?(?:ms|milliseconds?|millisekunden|millisecondes?|millisecondi|milliseconden)\b"), "ms"),
    "refresh": (_rx(r"\s?Hz\b"), "Hz"),  # "2,4 GHz" never matches: G sits between number and Hz
}
_SCREEN = _rx(r'(?:\s?-?\s?(?:inch(?:es)?|zoll|pouces?|pollici|duim)\b|\s?["”″])')
_SCREEN_CM = _rx(r"\s?(?:cm|zentimeter|centimet\w*)\b")
_SIZE = _rx(r"\s?(GB|TB)\b")
_WEIGHT = _rx(r"\s?(kg|g)\b", 0)    # case-sensitive: "5G" is not grams
_WATT = _rx(r"\s?(?:W|Watt)\b", 0)
_RES = re.compile(r"(?<![\d.,'’])(\d[\d.,'’]{2,5})\s?[x×]\s?(\d[\d.,'’]{2,5})(?!\d)")
_OS = re.compile(r"\b(Android|iOS|iPadOS|HarmonyOS|HyperOS|One UI|Windows|macOS|ChromeOS|Wear OS|watchOS)"
                 r"(?:\s?(\d+(?:\.\d+)?))?(?: (Home|Pro))?\b")
_CPU = re.compile(r"\b(?:(?:Qualcomm |MediaTek )?(?:Snapdragon|Dimensity|Helio|Exynos|Tensor|Unisoc|Kirin)"
                  r"|Intel Core|AMD Ryzen)\b[\w\- ]{0,25}?\d[\w\-]*(?: (?:Ultra|Pro|Plus|Max|Gen \d+))?"
                  r"|\bApple [AM]\d+(?: (?:Pro|Max|Ultra))?\b")
_PANEL = re.compile(r"\b(QD-OLED|Mini-?LED|Super AMOLED|AMOLED|OLED|IPS|VA|TN|LCD)\b")
_NET = re.compile(r"\b(5G|4G|LTE)\b")
_IP = re.compile(r"\bIP[X\d]\d\b")
_PORT = re.compile(r"(?:(?<![A-Za-z])|(?<=\dx))(Thunderbolt \d|USB-C|USB Type-C|HDMI(?: \d\.\d)?|DisplayPort|DP)(?![A-Za-z])")

# Android base of vendor skins; maintained by hand, unknown versions stay unknown.
_ANDROID_BASE = {("HyperOS", "2"): "15", ("HyperOS", "3"): "16", ("One UI", "7"): "15", ("One UI", "8"): "16"}


def infer_android(os_value: str) -> str | None:
    m = re.match(r"(HyperOS|One UI)\s?(\d+)", os_value)
    return _ANDROID_BASE.get((m[1], m[2])) if m else None


def extract_description(text: str, lang: str) -> dict[str, tuple[str, bool]]:
    found: dict[str, list[tuple[str, bool]]] = {}

    def add(field: str, value: str, ceiling: bool = False):
        found.setdefault(field, []).append((value, ceiling))

    for field, (rx, unit) in _UNIT_FIELDS.items():
        for m in rx.finditer(text):
            matched_unit = m[0][len(m[1]):].strip(" -")
            add(field, f"{fmt(parse_number(m[1], lang))} {unit}",
                _is_ceiling(text, m.start(), m.end(), matched_unit))
    for m in _SCREEN.finditer(text):
        add("screen", fmt(parse_number(m[1], lang)) + '"', _is_ceiling(text, m.start(), m.end(), '"'))
    if "screen" not in found:
        for m in _SCREEN_CM.finditer(text):
            if _keyword_distance(text, m.start(), m.end(), _kw("diagonal", lang)) is not None:
                add("screen", fmt(round(parse_number(m[1], lang) / 2.54, 1)) + '"')
    for m in _SIZE.finditer(text):
        d_ram = _keyword_distance(text, m.start(), m.end(), _kw("ram", lang))
        d_sto = _keyword_distance(text, m.start(), m.end(), _kw("storage", lang))
        if d_ram is None and d_sto is None:
            continue
        field = "ram" if d_sto is None or (d_ram is not None and d_ram < d_sto) else "storage"
        add(field, f"{fmt(parse_number(m[1], lang))} {m[2].upper()}",
            _is_ceiling(text, m.start(), m.end(), m[2]))
    for m in _WEIGHT.finditer(text):
        if _keyword_distance(text, m.start(), m.end(), _kw("weight", lang)) is not None:
            add("weight", f"{fmt(parse_number(m[1], lang))} {m[2]}")
    for m in _WATT.finditer(text):
        d_charge = _keyword_distance(text, m.start(), m.end(), _kw("charging", lang))
        d_speaker = _keyword_distance(text, m.start(), m.end(), _kw("speaker", lang))
        if d_charge is not None and (d_speaker is None or d_charge <= d_speaker):
            add("charging", f"{fmt(parse_number(m[1], lang))} W", _is_ceiling(text, m.start(), m.end(), "W"))
    for m in _RES.finditer(text):
        w, h = (int(re.sub(r"\D", "", g)) for g in (m[1], m[2]))
        if w >= 240 and h >= 240:
            add("resolution", f"{w} x {h}")
    for m in _OS.finditer(text):
        if m[2] or _keyword_distance(text, m.start(), m.end(), _kw("os", lang)) is not None:
            add("os", " ".join(x for x in (m[1], m[2], m[3]) if x))
            if m[1] == "Android" and m[2]:
                add("android_version", m[2].split(".")[0])
    if m := _CPU.search(text):
        add("cpu", m[0].strip())
    if m := _PANEL.search(text):
        add("panel", m[1])
    nets = set(_NET.findall(text))
    if nets:
        add("network", "5G" if "5G" in nets else "4G")
    ips = list(dict.fromkeys(_IP.findall(text)))
    if ips:
        add("ip", "/".join(ips))
    ports = list(dict.fromkeys(m[1] for m in _PORT.finditer(text)))
    if ports:
        add("ports", ", ".join(ports))

    out: dict[str, tuple[str, bool]] = {}
    for field, candidates in found.items():
        plain = [c for c in candidates if not c[1]]
        out[field] = plain[0] if plain else candidates[0]
    return out


# ------------------------------------------------------------------ merge

def _same(a: str, b: str) -> bool:
    def nums(s):
        return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]

    def rest(s):
        return re.sub(r"[\d.\s]", "", s).lower()

    na, nb = nums(a), nums(b)
    return rest(a) == rest(b) and len(na) == len(nb) and all(abs(x - y) < 0.005 for x, y in zip(na, nb))


def extract(product: dict, lang: str) -> dict[str, Spec]:
    """properties win over description; disagreement is recorded as a conflict."""
    found = {f: Spec(v, STATED, "properties") for f, v in
             parse_properties(product.get("properties") or "", product.get("productType") or "").items()}
    for field, (value, ceiling) in extract_description(product.get("description") or "", lang).items():
        current = found.get(field)
        if current is None:
            found[field] = Spec(value, STATED, "description", ceiling=ceiling)
        elif not ceiling and not _same(current.value, value):
            current.conflict = f"{current.value} (properties) / {value} (description)"
    if "network" not in found and re.search(r"\b5G\b", product.get("name") or ""):
        found["network"] = Spec("5G", INFERRED, "name")
    if "android_version" not in found and "os" in found:
        base = infer_android(found["os"].value)
        if base:
            found["android_version"] = Spec(base, INFERRED, found["os"].source)
    return {f: found[f] for f in FIELD_ORDER if f in found}
