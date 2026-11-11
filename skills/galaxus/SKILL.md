---
name: galaxus
description: Use when the user wants to search, filter, compare or price products sold on Galaxus (galaxus.ch), or asks for a thorough product search in CHF on the Swiss Galaxus shop. Not for general buying advice without Galaxus, other shops, or non-Swiss markets.
license: MIT
metadata:
  version: "0.1.0"
---

# Galaxus product search

Galaxus has an official MCP endpoint (`https://mcp.galaxus.ch/`) with one tool,
`search_products`: free-text query, optional integer price range, at most 50
results per call, no pagination. One call shows a few products out of
thousands. This skill searches **exhaustively** by splitting the price range,
reports how complete the search was, and extracts specs from the free-text
records. Every answer you give carries its **coverage**.

## 1. Choose the path (in this order)

Paths below are relative to this file's directory, never the working directory.

1. Run `scripts/galaxus.py --version` with `python3`, then `py`, then `python`;
   the first that works is `<python>` from here on. Then run
   `<python> scripts/galaxus.py count smartphone`: it prints one number.
   - Exit 0 → **script path**. Use it even when the `search_products` MCP
     tool is also available.
   - Exit 2 (endpoint unreachable), or no Python → step 2.
   - Exit 3 or 4 → report the error message to the user and stop; the
     manual path hits the same server.
2. If the `search_products` MCP tool is available → **manual path**:
   follow `references/manual-search.md`.
3. Otherwise tell the user the setup is missing and point them to the README
   (https://github.com/daniel-locatelli/galaxus-skill).

## 2. Formulate the query and check the budget

- Search the **category** ("smartphone", "monitor 27 inch", "laptop") plus the
  user's price range, then filter on extracted specs. Spec tokens (OS
  versions, years, model-number fragments like "17") go into the query only
  when the user names a model: "Android 17 smartphone" matches "Redmi 17" and
  its cases, and misses phones whose record never says "17".
- One search uses one language: the conversation language if it is en, de, fr,
  it or nl, else en. Pass it as `--lang`. Product types come back in that
  language ("Smartphones" / "Smartphone" / "Téléphone portable").
- **Count first**: `<python> scripts/galaxus.py count "<query>" --min A --max B
  --lang L`. A complete search needs about ceil(2 × count / 50) calls; the
  budget is 60 (`--max-calls`), so count ≤ 1500. A bare category is usually far
  over: `count smartphone --min 100 --max 300` = 43014, `"Android smartphone"`
  in the same range = 1864 (2026-11-11). When the count is over budget, narrow
  the query (brand, model or type words), narrow the price range, or ask the
  user; raise `--max-calls` only when the user agrees.

## 3. Run (script path)

Write `--out` files to a scratch/temp directory.

```bash
# count "Samsung smartphone" --min 200 --max 500 = 611 (2026-11-11): about 25 calls, fits
<python> scripts/galaxus.py search "Samsung smartphone" --min 200 --max 500 --lang en --out <scratch>/phones.json
<python> scripts/galaxus.py filter --from <scratch>/phones.json --type Smartphones --where "android_version>=15" --where "ram>=8"
<python> scripts/galaxus.py compare --from <scratch>/phones.json --ids <id>,<id>   # ids from the --out file
```

**search** prints a `Coverage:` line, notes, then rows grouped by product type
(`## <productType>: N products, M rows`; `--top` rows each, default 15). The
`--out` file keeps every product with its extracted specs. Prices (`--min`,
`--max`) are integer CHF, inclusive. Act on the coverage status:

| Status | What it means | What you do |
|---|---|---|
| `complete` | every match collected | report normally |
| `partial` + `capped` bands | more than 50 products share a 1-CHF band (often cheap accessories: "Redmi 17" hits ~290 phone covers at CHF 19–23); integer prices cannot split it | search again with more specific terms, or with `--min` above the capped bands and tell the user the range is now CHF X+; or report the partial coverage as such |
| `partial` + `uncovered` bands | call budget ran out | search again over a tighter range, or ask the user |
| `partial` + `drifted` bands | the Galaxus count changed between calls | relay them; those bands may be incomplete |
| `infeasible` | too many matches for the budget (about 2 × matches / 50 calls > `--max-calls`); prints a price histogram, no product rows, exit 0 | narrow by brand in the query or a tighter price range, or ask the user, showing them the histogram |
| `failed` | Galaxus error or failure mid-run (exit 4) | report a **failed search, not zero results**, with the partial numbers |

Relay every `Note:` line and every capped / drifted / uncovered band list to
the user.

**filter** reads an `--out` file (no network) and prints the coverage lines
again, then `Filter …: N checked, N match, N unknown (field: N unknown), N
excluded.` and a `Verdict:` line when nothing matches.
- `--where` (repeatable, all must hold): `FIELD>=N`, `FIELD<=N`, `FIELD=VALUE`
  (numeric when VALUE is a number, else case-insensitive exact text),
  `FIELD~TEXT` (case-insensitive substring). `ram`/`storage` compare in GB
  (1 TB = 1000); `weight` needs a unit (`weight<=1.5kg`, `weight<=1500g`).
  Field names and per-field rules: `references/spec-fields.md`.
- `--type` (repeatable) keeps only products whose `productType` equals it
  (case-insensitive); copy the type name from a `##` heading. The report lists
  what the type filter excluded.
- A product is **unknown**, not excluded, when a field is missing, in
  conflict, or a ceiling that cannot decide the condition. Unknown products
  are listed under `Unknown (could qualify)`.

**compare** builds a spec table for `--ids` from the file. For an id that is
not in the file add `--lookup ID=BRAND NAME@PRICE` (price optional): it
searches for that product near the price, best-effort, and prints a note when
not found. Galaxus search does not find products by id.

**Exit codes**

| Code | Meaning | What you do |
|---|---|---|
| 0 | ok, including `partial` and `infeasible` | read the coverage line |
| 2 | endpoint unreachable on the first call | switch to the manual path |
| 3 | invalid input (bad option, unknown field, `--min` > `--max`, input rejected by Galaxus, unreadable file) | fix the arguments |
| 4 | Galaxus search error, failure mid-run, `--out` not writable at the end, or a `compare --lookup` transport failure | report a failed search with the partial report; stay on the script path (the manual path hits the same server) |

## 4. Report to the user

- Quote the `Coverage:` line with its numbers, every `Note:` line, and any
  capped / drifted / uncovered bands.
- Say a product does not exist, or that none qualify, only when coverage is
  complete **and** the spec is known for every candidate. The `filter`
  verdict follows this rule; repeat it as printed, e.g. "Verdict: none
  confirmed among 56 checked; coverage is partial; 37 have unknown specs
  (android_version: 37 unknown)." List the unknown products as candidates
  the user can check.
- When matches rely on inferred values ("N of them rely on inferred values"),
  say so.
- Mention spell correction when the report has a "spell-corrected" note.
- When you drop product types (cases, accessories), say what was excluded;
  coverage claims apply to the remaining types.
- Keep the spec marks: *(desc.)* = from the description, weaker than
  properties; *(inferred)* = derived, not stated; *up to* = a ceiling, not
  this variant's value; *?* = unknown; *conflict* = properties and
  description disagree (properties value shown).
- Availability classes and discounts (marked `*`) are "per Galaxus data
  (undocumented field)". Show availability classes raw (`TICK`, `QUARTER`,
  `FULL`, …) without giving them a meaning.
- Flag rows marked `refurbished/used offer`.
- Link to the Galaxus `pageUrl`; purchases happen on galaxus.ch.

## 5. Optional: check product pages

Only with a real browser tool (e.g. Claude in Chrome), only for the final
shortlist (max 5): follow `references/page-check.md`.
