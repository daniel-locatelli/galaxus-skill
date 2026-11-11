# Spec fields

How `galaxus.py` reads specs from a product record, and how to read them by
hand on the manual path. Extraction is conservative: a value that is not
clearly this product's is left unknown rather than guessed.

## States and marks

- **stated**: in `properties`, or in `description` bound to a field keyword
  (rules below). Description values show *(desc.)*: weaker than properties.
- **inferred**: derived, shown *(inferred)*: `network: 5G` from a product
  name containing "5G"; `android_version` from a vendor skin (table below).
- **unknown**: absent, shown `?`.

`properties` win over `description`. When both give a value and they differ,
the properties value is kept and the field shows
`conflict: 6.9" (properties) / 6.99" (description)`. `filter` treats a
conflict as unknown.

## Which product types get a schema

`properties` is split on ", " and tokens are matched by pattern. The
product-type-specific rules (storage, RAM, colour) apply only to these exact
`productType` values (any language, case-insensitive); everything else,
accessories included, gets the generic patterns only (screen, resolution,
SIM, network, keyboard, CPU):

| Schema | productType values |
|---|---|
| phone | Smartphones, Smartphone, Téléphone portable, Téléphones portables, Handy, Handys |
| laptop | Notebooks, Notebook, Ordinateur portable, Ordinateurs portables, Laptop, Laptops |
| monitor | Monitor, Monitors, Monitore, Moniteur, Moniteurs |

- phone: a single GB/TB token is storage; leftover words are the colour (max 2).
- laptop: two GB/TB tokens are RAM (smaller) and storage (larger) only when
  RAM ≤ 64 GB, storage ≥ 128 GB and at least twice the RAM; otherwise neither.
- The description is read for every product type.

## Description: keyword binding

- RAM, storage and refresh rate need an **adjacent keyword** ("8 GB RAM",
  "RAM: 8 GB", "120 Hz display"): same sentence, within ~40 characters, not
  across a comma, slash or bracket. A keyword equally close to two values
  binds to neither. GB next to graphics/VRAM words is ignored.
- Battery (mAh), camera (MP), brightness (nits, cd/m²) and response (ms) are
  kept on their unit alone; the camera is the first MP value not bound to a
  front/selfie keyword.
- Charging (W) only next to a charging keyword and not closer to a speaker
  keyword. Weight (g/kg) and cm screen sizes only next to a weight/diagonal
  keyword.
- OS mentions about compatibility, requirements, migration or future updates
  ("updates up to Android 16", "iOS 15 or later") are ignored.

## Ceilings

A value right after "up to", "bis zu", "bis", "jusqu'à", "fino a", "max." /
"maximum", "memory extension", "Speichererweiterung", "configurations" /
"Konfigurationen" (nl: "tot") is a **ceiling**, shown *up to*. One phrase
covers the following values of the same unit ("bis zu 12 GB RAM und 512 GB
Speicher" makes both ceilings). With "expandable" / "erweiterbar" only the
expansion target is a ceiling: in "128 GB storage expandable to 1 TB" the
storage is 128 GB, stated. A plain value always beats a ceiling for the same
field.

`filter` and ceilings (the real value is at most the ceiling):
`refresh>=144` is excluded on "up to 120 Hz" and unknown on "up to 240 Hz";
`refresh<=144` matches "up to 120 Hz" and is unknown on "up to 240 Hz";
`=` and `~` on a ceiling are unknown.

## Fields (filter names)

`os`, `android_version`, `cpu`, `ram`, `storage`, `screen` (inches),
`resolution` (`W x H`), `refresh` (Hz; GHz is CPU clock), `panel`,
`brightness` (nits), `response` (ms), `battery` (mAh), `charging` (W),
`camera` (MP, main), `weight`, `network` (4G/5G), `sim`, `ip` (e.g.
IP66/IP68), `ports`, `keyboard`, `colour`.

Per-field filter rules:

- `weight`: `>=`, `<=` and `=` need a unit, g or kg, and compare in grams
  (`weight<=1.5kg` = `weight<=1500g`). A bare number (`weight<=1500`) is
  invalid input, exit 3.
- `network=4G` also matches `LTE`.
- `=` with text is an exact match: `os=Android` fails on "Android 15"; use
  `os~Android` (substring), or `android_version>=15`.
- `resolution>=N` / `<=N` compare the first number only, the width
  (`resolution>=2560` on "2560 x 1440").
- `ram`, `storage`: numbers in GB, 1 TB = 1000 GB.

Numbers: `6,99` is a decimal comma; `8'340`, `3.840` (de/fr/it/nl) and
`8,340` (en) are thousands.

## Android base of vendor skins (inferred, maintained by hand)

| OS | Android |
|---|---|
| HyperOS 2 | 15 |
| HyperOS 3 | 16 |
| One UI 7 | 15 |
| One UI 8 | 16 |

Other versions stay unknown until added here and in `specs.py`
(`_ANDROID_BASE`), with a source.
