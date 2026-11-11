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
# Groups starting with "_" disqualify: a value bound to one of them is dropped.
_KW = {
    "ram": {"en": [r"\bram\b", r"\bworking memory"], "de": [r"\bram\b", r"\barbeitsspeicher"],
            "fr": [r"\bram\b", r"mémoire vive"], "it": [r"\bram\b"], "nl": [r"\bram\b", r"\bwerkgeheugen"]},
    "storage": {"en": [r"\bstorage", r"\binternal memory", r"\bssd\b", r"\brom\b", r"\bhard drive"],
                "de": [r"\bspeicher", r"\bssd\b", r"\bfestplatte"],
                "fr": [r"\bstockage", r"mémoire interne", r"\bssd\b"],
                "it": [r"\bmemoria interna", r"\barchiviazione", r"\bssd\b"], "nl": [r"\bopslag", r"\bssd\b"]},
    "_vram": {"en": [r"\bgddr\w*", r"\bvram\b", r"\bgraphics", r"\bvideo memory"],
              "de": [r"\bgrafik\w*"], "fr": [r"\bgraphique"], "it": [r"\bgrafic\w*"], "nl": [r"\bgrafisch\w*"]},
    "refresh": {"en": [r"\brefresh", r"\w*display", r"\bscreen", r"\bpanel", r"\bmonitor"],
                "de": [r"\bbildwiederhol\w*", r"\bwiederholrate", r"\bbildschirm"],
                "fr": [r"rafra[iî]chissement", r"\bécran"], "it": [r"\baggiornamento", r"\bschermo"],
                "nl": [r"\bverversing\w*", r"\bscherm"]},
    "_not_refresh": {"en": [r"\btouch[- ]?sampling", r"\bsampling", r"\bfrequency response", r"\bfrequency range",
                            r"\bpwm\b", r"\bdimming", r"\bspeakers?"],
                     "de": [r"\babtast\w*", r"\bfrequenzgang", r"\bfrequenzbereich", r"\bübertragungsbereich",
                            r"\w*lautsprecher\w*"],
                     "fr": [r"réponse en fréquence", r"échantillonnage", r"plage de fréquences?", r"haut-parleurs?"],
                     "it": [r"risposta in frequenza", r"\bcampionamento", r"gamma di frequenz\w*", r"altoparlant\w*"],
                     "nl": [r"\bfrequentiebereik", r"\bluidspreker\w*"]},
    "camera": {"en": [r"\w*camera"], "de": [r"\w*kamera"], "fr": [r"caméra"], "it": [r"\w*camera"],
               "nl": [r"\w*camera"]},
    # Whole phrases, so plain "camera"/"Kamera" cannot bind the selfie value on its own.
    "_not_camera": {"en": [r"\bfront[- ]?(?:facing[- ])?(?:camera|kamera)", r"\w*selfie(?:[- ]?(?:camera|kamera)|\w*)"],
                    "de": [r"\bfront-?kamera"], "fr": [r"caméra frontale"], "it": [r"fotocamera frontale"],
                    "nl": [r"\bvoorcamera", r"\bfrontcamera"]},
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
_CEILING = (r"up to", r"bis zu", r"\bbis\b", r"jusqu.à", r"fino a", r"(?-i:\b(?:max|Max|MAX)\.)\s*$", r"\bmaxim(?:um|al)\w*",
            r"memory extension", r"speichererweiterung", r"configurations", r"konfigurationen")
_CEILING_LANG = {"nl": (r"\btot\b",)}
# Only the expansion target is a ceiling: "erweiterbar auf 1 TB", "auf 1 TB erweiterbar". The base
# value in "128 GB storage expandable via microSD" / "128 GB expandable up to 1 TB" is not.
_EXPAND_WORD = r"(?:expandable|erweiterbar|extensible|espandibile|uitbreidbaar)"
_EXPAND_BEFORE = re.compile(_EXPAND_WORD + r"(?:\s+(?:up to|to|auf|bis|jusqu.à|à|fino a|a|tot))?\s+$", re.I)
_EXPAND_AFTER = re.compile(r"\s*" + _EXPAND_WORD, re.I)
# Word before an expansion target; English "to" always applies, the articles-looking "a"/"à" only in it/fr.
_EXPAND_TO = {"de": r"auf", "fr": r"à|jusqu.à", "it": r"a|fino a", "nl": r"tot"}
_BOUNDARY = re.compile(r"(?<!\bca)[.!?](?=\s|$)|\n|•|;")
# "max. 120 Hz" / "Max. 144 Hz" / "MAX. 120 Hz": an abbreviation before a number, so no sentence end
# (and a ceiling via _CEILING). "Pro Max. 256 GB" is a model name ending a sentence.
_MAX_ABBREV = re.compile(r"(?<!\w)(?:max|Max|MAX)\.(?=\s*\d)")
_MAX_MODEL = re.compile(r"\b(?:Pro|Ultra|Plus|Note|Mini|Fold|Edge)\s+$")
_WINDOW = 40
# Connector words a keyword absorbs on its right: "RAM: 8 GB", "refresh rate of 120 Hz".
_CONNECT = re.compile(r"(?:\s*(?:[:=]|\b(?:rate|of|von|de|du|di|van)\b))*", re.I)
_NO_BIND = re.compile(r",\s|[/()]")


def _kw(group: str, lang: str) -> list[str]:
    table = _KW[group]
    return table.get(lang, []) + ([] if lang == "en" else table["en"])


def _sentence_span(text: str, pos: int) -> tuple[int, int]:
    start, end = 0, len(text)
    for m in _BOUNDARY.finditer(text):
        a = m.start() - 3
        if a >= 0 and _MAX_ABBREV.match(text, a) and not _MAX_MODEL.search(text, 0, a):
            continue
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


def _bind(text: str, spans: list[tuple[int, int]], groups: list[str], lang: str) -> list[tuple[str, int] | None]:
    """Keyword adjacency for one field family.

    Each keyword binds to its nearest value span in the same sentence, within _WINDOW and not across
    a comma, slash or bracket; a keyword equidistant from two values binds to neither. Each value then
    takes the group of its nearest bound keyword: (group, distance), ("?", d) on a tie between groups,
    None if no keyword is bound to it. Overlapping keywords: the longer wins, then the group listed first.
    """
    found = [(m.start(), _CONNECT.match(text, m.end()).end(), g)
             for g in groups for pat in _kw(g, lang) for m in re.finditer(pat, text, re.I)]
    found.sort(key=lambda k: k[0] - k[1])  # longest first; the sort is stable, so group order breaks ties
    keywords: list[tuple[int, int, str]] = []
    for a, b, g in found:
        if all(b <= ka or a >= kb for ka, kb, _ in keywords):
            keywords.append((a, b, g))
    bound: list[list[tuple[int, str]]] = [[] for _ in spans]
    ties: list[tuple[str, list[int], int]] = []
    for a, b, g in keywords:
        s0, s1 = _sentence_span(text, a)
        near = []
        for i, (vs, ve) in enumerate(spans):
            if vs < s0 or ve > s1 or (vs < b and ve > a):
                continue
            gap = text[b:vs] if b <= vs else text[ve:a]
            if len(gap) <= _WINDOW and not _NO_BIND.search(gap):
                near.append((len(gap), i))
        near.sort()
        if near and (len(near) == 1 or near[0][0] < near[1][0]):
            bound[near[0][1]].append((near[0][0], g))
        elif near:
            ties.append((g, [i for d, i in near if d == near[0][0]], near[0][0]))
    # "8 GB RAM 256 GB storage": RAM is equidistant, but 256 GB is already held as closely by
    # storage, so RAM takes the value that is still free; with no single free value it binds to none.
    for g, idx, d in ties:
        free = [i for i in idx if not any(hd <= d and hg != g for hd, hg in bound[i])]
        if len(free) == 1:
            bound[free[0]].append((d, g))
    out: list[tuple[str, int] | None] = []
    for hits in bound:
        hits.sort()
        if not hits:
            out.append(None)
        elif len(hits) > 1 and hits[0][0] == hits[1][0] and hits[0][1] != hits[1][1]:
            out.append(("?", hits[0][0]))
        else:
            out.append((hits[0][1], hits[0][0]))
    return out


def _family(unit: str) -> str:
    u = unit.lower()
    if u in ("gb", "tb"):
        return "size"
    if u == "mp" or u.startswith(("mega", "méga")):
        return "mp"
    if u.startswith(("nit", "cd")):
        return "nits"
    return u


def _is_ceiling(text: str, start: int, end: int, unit: str, lang: str) -> bool:
    s0, _ = _sentence_span(text, start)
    before = text[max(s0, start - 60):start]
    hits = [m.end() for p in _CEILING + _CEILING_LANG.get(lang, ()) for m in re.finditer(p, before, re.I)]
    if hits:
        gap = before[max(hits):]
        nums = re.findall(NUM, gap)
        if not nums:
            return True
        # "up to 16 GB RAM and 1 TB storage": the phrase covers later values of the same kind only;
        # "bis zu 2,4 GHz und 4 GB RAM" does not make the RAM a ceiling.
        units = [u for _, u in re.findall(NUM + r"\s?-?\s?([^\W\d_]+|[\"”″])", gap)]
        if len(units) == len(nums) and all(_family(u) == _family(unit) for u in units):
            return True
    return bool(_EXPAND_BEFORE.search(before)
                or (_EXPAND_AFTER.match(text, end)
                    and re.search(r"\b(?:to|" + _EXPAND_TO.get(lang, "to") + r")\s+$", before, re.I)))


def _rx(unit: str, flags=re.I):
    return re.compile(NUM + unit, flags)


# field -> (regex, unit, keyword group, disqualifying group); the unit itself is the evidence, so
# unbound values are kept (except for _BIND_REQUIRED fields, where Hz alone is too weak: audio
# frequency ranges, mains adapters), and values bound to the disqualifying group are dropped.
_BIND_REQUIRED = {"refresh"}
_UNIT_FIELDS = {
    "battery": (_rx(r"\s?mAh\b"), "mAh", None, None),
    "camera": (_rx(r"\s?-?\s?(?:MP|mega-?pixels?|mégapixels?)\b"), "MP", "camera", "_not_camera"),
    "brightness": (_rx(r"\s?(?:nits?\b|cd/m²|cd/m2)"), "nits", None, None),
    "response": (_rx(r"\s?(?:ms|milliseconds?|millisekunden|millisecondes?|millisecondi|milliseconden)\b"), "ms",
                 None, None),
    "refresh": (_rx(r"\s?Hz\b"), "Hz", "refresh", "_not_refresh"),  # "2,4 GHz" never matches
}
_SCREEN = _rx(r'(?:\s?-?\s?(?:inch(?:es)?|zoll|pouces?|pollici|duim)\b|\s?["”″])')
_SCREEN_CM = _rx(r"\s?(?:cm|zentimeter|centimet\w*)\b")
_SIZE = _rx(r"\s?(GB|TB)\b")
_WEIGHT = _rx(r"\s?(kg|g)\b", 0)    # case-sensitive: "5G" is not grams
_WATT = _rx(r"\s?(?:W|Watt)\b", 0)
_RES = re.compile(r"(?<![\d.,'’])(\d[\d.,'’]{2,5})\s?[x×]\s?(\d[\d.,'’]{2,5})(?!\d)")
_RES_PART = re.compile(r"\d{1,3}(?:[.,'’]\d{3})+|\d+")  # integer or thousands groups, never a decimal
_RES_NOT = re.compile(r"\s?(?:[x×]\s?\d|mm\b|cm\b)")    # a third dimension or a length unit follows
_OS = re.compile(r"\b(Android|iOS|iPadOS|HarmonyOS|HyperOS|One UI|Windows|macOS|ChromeOS|Wear OS|watchOS)"
                 r"(?:\s?(\d+(?:\.\d+)?))?(?: (Home|Pro))?\b")
# Compatibility / migration mentions name another device's OS, not this one's.
_OS_NOT = re.compile(r"or (?:later|higher|newer|above)|oder (?:höher|neuer)|ou (?:supérieur|plus récent)"
                     r"|o superiore|of hoger|compatib|kompatib|requires|erfordert|nécessite|richiede|vereist"
                     r"|migrat|\bab (?=Android|iOS)", re.I)
_OS_FROM = re.compile(r"\b(?:from|von|de|da|van|ab)\s+$", re.I)
# "updates up to Android 21" promises a future OS, not the shipped one.
_OS_CEILING = re.compile(r"up to|bis zu|\bbis\b|jusqu.à|fino a|\btot\b|update|upgrade|mises? à jour|aggiornament",
                         re.I)
_CPU = re.compile(r"\b(?:(?:Qualcomm |MediaTek )?(?:Snapdragon|Dimensity|Helio|Exynos|Tensor|Unisoc|Kirin)"
                  r"|Intel Core|AMD Ryzen)\b[\w\- ]{0,25}?\d[\w\-]*"
                  r"(?: (?:(?!\d+(?:G|[GT]B)\b)\d+[A-Za-z][\w\-]*|Ultra|Pro|Plus|Max|Elite|Gen \d+)\b)*"
                  r"|\bApple [AM]\d+(?: (?:Pro|Max|Ultra))?\b")
_PANEL = re.compile(r"\b(QD-OLED|Mini-?LED|Super AMOLED|AMOLED|OLED|IPS|VA|TN|LCD)\b")
_NET = re.compile(r"(?<!\d[.,])\b(5G|4G|LTE)\b")   # "2.4G" / "5.8G" are radio bands
_IP = re.compile(r"\bIP[X\d]\d\b")
_PORT = re.compile(r"(?:(?<![A-Za-z])|(?<=\dx))(Thunderbolt \d|USB-C|USB Type-C|HDMI(?: \d\.\d)?|DisplayPort|DP)(?![A-Za-z])")

# Android base of vendor skins; maintained by hand, unknown versions stay unknown.
_ANDROID_BASE = {("HyperOS", "2"): "15", ("HyperOS", "3"): "16", ("One UI", "7"): "15", ("One UI", "8"): "16"}


def infer_android(os_value: str) -> str | None:
    m = re.match(r"(HyperOS|One UI)\s?(\d+)", os_value)
    return _ANDROID_BASE.get((m[1], m[2])) if m else None


def _battery(token: str, lang: str) -> float | None:
    mah = parse_number(token, lang)
    if mah < 100 and re.fullmatch(r"\d{1,3}[.,]\d{3}", token):  # "5,000" in de, "5.000" in en
        mah = float(re.sub(r"\D", "", token))
    return mah if mah >= 100 else None


def extract_description(text: str, lang: str) -> dict[str, tuple[str, bool]]:
    found: dict[str, list[tuple[str, bool, int]]] = {}

    def add(field: str, value: str, ceiling: bool = False, rank: int = 0):
        found.setdefault(field, []).append((value, ceiling, rank))

    def ceiling(m, unit: str) -> bool:
        return _is_ceiling(text, m.start(), m.end(), unit, lang)

    for field, (rx, unit, kw, not_kw) in _UNIT_FIELDS.items():
        matches = list(rx.finditer(text))
        binds = (_bind(text, [m.span() for m in matches], [not_kw, kw], lang) if kw
                 else [None] * len(matches))
        for m, b in zip(matches, binds):
            if (b and (b[0] == "?" or b[0].startswith("_"))) or (b is None and field in _BIND_REQUIRED):
                continue
            number = _battery(m[1], lang) if field == "battery" else parse_number(m[1], lang)
            if number is None:
                continue
            # Text order, not keyword distance: in "50 MP / 12 MP dual camera" the first is the main one.
            add(field, f"{fmt(number)} {unit}", ceiling(m, m[0][len(m[1]):].strip(" -")))
    for m in _SCREEN.finditer(text):
        add("screen", fmt(parse_number(m[1], lang)) + '"', ceiling(m, '"'))
    if "screen" not in found:
        for m in _SCREEN_CM.finditer(text):
            if _keyword_distance(text, m.start(), m.end(), _kw("diagonal", lang)) is not None:
                add("screen", fmt(round(parse_number(m[1], lang) / 2.54, 1)) + '"')
    sizes = list(_SIZE.finditer(text))
    for m, b in zip(sizes, _bind(text, [m.span() for m in sizes], ["_vram", "ram", "storage"], lang)):
        if b and b[0] in ("ram", "storage"):
            add(b[0], f"{fmt(parse_number(m[1], lang))} {m[2].upper()}", ceiling(m, m[2]), b[1])
    for m in _WEIGHT.finditer(text):
        if _keyword_distance(text, m.start(), m.end(), _kw("weight", lang)) is not None:
            add("weight", f"{fmt(parse_number(m[1], lang))} {m[2]}")
    for m in _WATT.finditer(text):
        d_charge = _keyword_distance(text, m.start(), m.end(), _kw("charging", lang))
        d_speaker = _keyword_distance(text, m.start(), m.end(), _kw("speaker", lang))
        if d_charge is not None and (d_speaker is None or d_charge <= d_speaker):
            add("charging", f"{fmt(parse_number(m[1], lang))} W", ceiling(m, "W"))
    for m in _RES.finditer(text):
        if (not all(_RES_PART.fullmatch(g) for g in (m[1], m[2])) or _RES_NOT.match(text, m.end())
                or re.search(r"[x×]\s?$", text[:m.start()])):
            continue
        w, h = (int(re.sub(r"\D", "", g)) for g in (m[1], m[2]))
        if w >= 240 and h >= 240:
            add("resolution", f"{w} x {h}")
    for m in _OS.finditer(text):
        s0, s1 = _sentence_span(text, m.start())
        near = text[max(s0, m.start() - _WINDOW):min(s1, m.end() + _WINDOW)]
        if (_OS_NOT.search(near) or _OS_FROM.search(text[max(s0, m.start() - 10):m.start()])
                or _OS_CEILING.search(text[max(s0, m.start() - 30):m.start()])):
            continue
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
        value, is_ceiling, _ = min(plain or candidates, key=lambda c: c[2])  # nearest keyword, then first
        out[field] = (value, is_ceiling)
    return out


# ------------------------------------------------------------------ merge

_CPU_VENDOR = re.compile(r"^(?:(?:apple|qualcomm|mediatek|intel|amd|samsung|google)\s+)+")
_CPU_FILLER = re.compile(r"(?:\s+(?:processor|prozessor|processeur|processore|chip|chipset|cpu|soc))+$")


def _cpu_key(s: str) -> str:
    s = " ".join(s.lower().split())
    return _CPU_FILLER.sub("", _CPU_VENDOR.sub("", s))


def _same(field: str, a: str, b: str) -> bool:
    if field == "network":
        return a.replace("LTE", "4G") == b.replace("LTE", "4G")
    if field == "cpu":  # "M5" == "Apple M5"; "… 155H Processor" == "… 155H"; "Apple M3 Pro" != "Apple M3"
        return _cpu_key(a) == _cpu_key(b)

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
        elif not ceiling and not _same(field, current.value, value):
            current.conflict = f"{current.value} (properties) / {value} (description)"
    if "network" not in found and re.search(r"\b5G\b", product.get("name") or ""):
        found["network"] = Spec("5G", INFERRED, "name")
    if "android_version" not in found and "os" in found:
        base = infer_android(found["os"].value)
        if base:
            found["android_version"] = Spec(base, INFERRED, found["os"].source)
    return {f: found[f] for f in FIELD_ORDER if f in found}
