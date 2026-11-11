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
_TYPE_WORDS = (
    ("phone", r"smartphones?|handys?|handies|téléphones?|telefono|telefoni|telefoon|telefoons"),
    ("laptop", r"notebooks?|laptops?|portatil[ei]|ordinateurs? portables?"),
    ("monitor", r"monitor[es]?|monitors|moniteurs?|écrans?"),
)
# Accessory words: a type containing one of these is never a device type.
_ACCESSORY = re.compile(
    r"(?<!\w)(?:hülle|huelle|case|cover|tasche|bag|sleeve|halter|halterung|mount|stand|"
    r"schutz|protection|protector|folie|glass|kabel|cable|adapter|charger|ladegerät)"
    r"(?:s|n|en|e)?(?!\w)")
_NON_COLOUR = re.compile(r"^(?:wi-?fi|wlan|lte|nfc|esim|dual sim|single sim|5g|4g)$", re.I)


def schema_for(product_type: str) -> str | None:
    t = product_type.lower().replace(" ", " ")
    if _ACCESSORY.search(t):
        return None
    for schema, words in _TYPE_WORDS:
        if re.search(rf"(?<!\w)(?:{words})(?!\w)", t):
            return schema
    return None


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
        if _size_gb(small) <= 128 and _size_gb(large) >= 128 and _size_gb(large) > _size_gb(small):
            out["ram"], out["storage"] = small, large
    colours = [t for t in leftovers if not re.search(r"\d", t) and not _NON_COLOUR.match(t)]
    if "colour" in fields and colours:
        out["colour"] = " / ".join(colours)
    return out
