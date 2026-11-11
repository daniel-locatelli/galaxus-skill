# Galaxus skill — design

Date: 2026-11-11 (rev. 2, after adversarial review)
Status: approved (2026-11-11)

## Context

On 2026-11-11 Galaxus announced an official MCP server for its Swiss catalogue
(~13 M items): <https://www.galaxus.ch/en/page/galaxus-introduces-mcp-interface-for-ai-assistants-44216>.
It exposes **one tool**, `search_products`: free-text query, optional integer
price range, max 50 results per call. No pagination offset, no sort, no brand
filter, no lookup by id, no prompts.

### Limitations raised in the article's comments, checked by probing (2026-11-11)

| Comment claim | Probe result |
|---|---|
| Agent lists a few known products instead of searching systematically | Confirmed: no pagination; "smartphone" `totalCount` ≈ 471,800, max 50 returned; 29 of 50 "Android 17 smartphone" results were variants |
| Agent says an Android 17 phone under 300 CHF does not exist | Confirmed cause: no structured specs (OS appears in 7 of 50 records, in free-text `description` only); the query token "17" matched model names |
| `minPrice`/`maxPrice`/brand applied client-side on one page | Partly wrong: price filter is server-side; there is no brand parameter |
| No availability, seller or discounts | Partly wrong: undocumented `_meta` carries availability and discount data (see below); seller is absent |
| No price history | Confirmed; Galaxus staff: only product search for now |
| Catalogue data is messy | Not fixable; out of scope for v1 |
| Only ChatGPT/Claude promoted | Endpoint works with any MCP client |

## Server contract (as probed, 2026-11-11)

Transport:

- Endpoint `https://mcp.galaxus.ch/`, **POST only** on the root path
  (GET → 405, DELETE → 501, `/mcp` → 404). No auth.
- Headers: `Content-Type: application/json`,
  `Accept: application/json, text/event-stream` (otherwise 406),
  `MCP-Protocol-Version: 2025-06-18` after initialize.
- Handshake: `initialize` (protocolVersion `2025-06-18`) → response header
  `Mcp-Session-Id` → `notifications/initialized` (202). Every later request
  must carry `Mcp-Session-Id` (missing → 400 "Session ID required"), but the
  id is **not validated** (a made-up id works), so sessions never expire in
  practice.
- Responses are **always SSE** (`event: message` / `data: <json>`, possibly
  several `data:` lines); the client parses by `Content-Type`.
- Tool result: JSON text in `result.content[0].text`; no `structuredContent`.
  Validation errors arrive as `isError: true` result text, not JSON-RPC
  errors.

Inputs (`search_products`):

- **Required**: `query`, `agentInfo`, `language` (en/de/fr/it/nl).
- `first`: 1–50 (51 rejected), default 10.
- `minPrice` / `maxPrice`: integers 1…1,000,000; both bounds **inclusive**;
  `min == max` allowed; `min > max` → `isError`.
- `userIntent`: optional, analytics only. The skill does not send it.

Outputs:

- `{correctedSearchTerm, totalCount, products[], errorMessage?}`; product
  fields `id, name, properties, description, productType, brand,
  priceIfAvailable ({amountInclusive, currency} or null), pageUrl,
  previewImage, ratingSummaryIfAvailable, productReviewsSummaryIfAvailable`.
- `errorMessage` can appear with `totalCount: 0` and no `isError` (seen for
  query "x"): it means a failed search, not zero results.
- `result._meta` repeats the raw GraphQL payload (undocumented). Per product
  it adds, among others: `availability.availabilityClassification` (seen:
  `TICK`, `FULL`, `THREE_QUARTER`, `QUARTER`; meaning undocumented),
  `labels` (seen: `DISCOUNT`, `SHOWROOM`, `USED_AND_CHECKED`),
  `insteadOfPrice` (`{type: SALES_PRICE_BEFORE | LAST_NEW, rebate, price}`).
  Some strings are mis-encoded (`Â `).

Behaviour that shapes the algorithm:

- **Cent prices fall between integer bands**: "Redmi 17" `[1,193]` = 417 and
  `[194,∞]` = 40, total 459; products at 193.97 and 193.88 appear only in a
  band containing both 193 and 194. The server compares the real price.
- **A single price can hold > 50 products**: "smartphone" `[163,163]` = 165.
- Broad queries are huge: "smartphone" ≈ 471,800 → ≥ 9,400 bands of ≤ 50.
- Matching is loose: a nonsense query returns ~1,000 products; spell
  correction is weak ("smartfone" not corrected).
- Result order within a call varies between identical calls (same id set).
- `totalCount` is stable over minutes, drifts over hours.
- `totalCount` and `productType` names depend on `language`
  ("Smartphones" en / "Smartphone" de).
- Products with `priceIfAvailable: null` can still pass a price filter.
  Unfiltered total equalled `[1, 1000000]` total for all queries tried.
- `pageUrl` can carry `offertype=refurbished`.
- A call takes 0.26–0.43 s; a 50-product response is ~220 KB HTTP body
  (~88 KB of it the text content, the rest `_meta`).

## Scope

**v1 public core** (this repo):

1. Exhaustive search, with a feasibility gate.
2. Spec extraction, with stated / inferred / unknown states.
3. Availability and discounts from `_meta`, labelled undocumented.
4. Product-page check when the client has a browser tool.

**Personal, not in this repo:** devil's-advocate mode, as a separate skill in
Daniel's own skills repo.

**Deferred:** price log / history and any scheduler; catalogue-quality report
(including fuzzy duplicate detection); bundle / bill-of-materials builder.

## Approach

`SKILL.md` + a stdlib-only Python CLI (`galaxus.py`, Python ≥ 3.10) that
talks to the endpoint directly. The script path does not need the MCP
connector; the manual fallback does. Rejected: instructions only (context
blow-up, agent sloppiness); own MCP wrapper server (hosting, not needed).

Unverified: whether claude.ai's code-execution sandbox can reach
`mcp.galaxus.ch` (it may block it by default); whether the `ui://mcp-app`
resource changes what a host shows the model for tool results.

## Repository layout

```
galaxus-skill/
├── .claude-plugin/plugin.json
├── skills/galaxus/
│   ├── SKILL.md
│   ├── scripts/galaxus.py
│   └── references/
│       ├── manual-search.md
│       ├── spec-fields.md
│       └── page-check.md
├── tests/
│   ├── fixtures/            # recorded real SSE responses
│   ├── test_transport.py
│   ├── test_search.py
│   ├── test_specs.py
│   └── test_live.py         # opt-in
├── evals/cases.md
├── .github/workflows/test.yml
├── pyproject.toml           # pytest config only; script stays stdlib
├── LICENSE                  # MIT
└── README.md
```

Remote (when pushed): `gh-daniel-locatelli:daniel-locatelli/galaxus-skill`.
Version: `__version__` in `galaxus.py`, mirrored in `plugin.json` and the
`SKILL.md` frontmatter; a test asserts they match.

## SKILL.md

### Trigger description

> Use when the user wants to search, filter, compare or price products sold
> on Galaxus (galaxus.ch), or asks for a thorough product search in CHF on
> the Swiss Galaxus shop. Not for general buying advice without Galaxus,
> other shops, or non-Swiss markets.

Digitec is not mentioned: whether the MCP covers the Digitec range is
unverified.

### Path choice (deterministic)

1. Run `<skill-dir>/scripts/galaxus.py --version` with `python3`, then `py`,
   then `python`. Then `galaxus.py count smartphone`. Exit 0 → **script
   path**. Use it even when the MCP tool is also available.
2. Else, if the `search_products` MCP tool is available → **manual path**
   (`references/manual-search.md`).
3. Else tell the user the setup is missing and point to the README.

All paths are relative to the skill directory, never the cwd.

### Query formulation

- Search the **category** (e.g. "smartphone", "monitor 27 inch") plus the
  user's price range, then filter on extracted specs. Never put spec tokens
  (OS versions, years, model-number fragments like "17") into the query
  unless the user names a model.
- One search uses one `language`: the user's conversation language if it is
  en/de/fr/it/nl, else en. Pass it as `--lang`.
- If the feasibility gate (below) says the search is too broad, narrow by
  brand in the query, by a tighter price range, or ask the user. Show the
  price histogram the script returns so the user can choose.

### Output rules

- Always print the coverage line from the script (complete / partial /
  infeasible, with numbers).
- Never say a product does not exist or that none qualify unless coverage is
  complete **and** the relevant spec is known for every candidate. Otherwise:
  "none confirmed among X checked; Y have unknown OS".
- Report spell correction when `correctedSearchTerm` is non-null.
- Report what was excluded when dropping product types ("excluded 120
  cases/accessories"); coverage claims apply to the remaining groups.
- Spec values carry their state: stated / inferred / unknown.
- Availability and discount values are marked "per Galaxus data
  (undocumented field)". Raw availability classes are shown as-is with no
  invented meaning.
- Refurbished offers are flagged.
- Links point to Galaxus `pageUrl`; purchases happen there.

### Product-page check (`references/page-check.md`)

Only when a browser tool is available, and only for the final shortlist
(max 5 products). Per page, read text (not screenshots) and extract:
availability text, delivery estimate, seller (Galaxus vs marketplace), current
price vs API price (flag differences). Each field is labelled *checked*,
*not checked* or *blocked*. Pages that need JS or show bot protection →
*blocked*; never solve captchas. A plain web-fetch that does not show a field
→ *not checked*. Expect 5–15 s and a few thousand tokens per page.

## `scripts/galaxus.py`

Subcommands (all take `--lang`, default `en`):

- `--version`
- `count QUERY [--min N] [--max N]`: one call, prints `totalCount`.
- `search QUERY [--min N] [--max N] [--max-calls 60] [--top 15] [--out FILE]`
- `compare --from FILE --ids ID,ID,…`

`agentInfo` is sent as `galaxus-skill/<version>`.

### Transport

Implements the server contract above with `urllib`: handshake once per run,
SSE parsing, `_meta` read only through one accessor module so its removal
degrades to "not available". Per-request timeout 30 s. Strictly sequential
calls with a 0.2 s delay. On 429 honour `Retry-After` (else back off
1 s / 4 s). On 5xx / network errors two retries with backoff. On 400/404
re-initialise once. stdout is forced to UTF-8.

### Search algorithm

Every call uses `first: 50`, so one call returns a band's count and, if it
holds ≤ 50, all of its products.

1. **Root call** over the requested range (default `[1, 1000000]`).
2. **Feasibility gate**: estimated calls ≈ 2 × `totalCount` / 50. If that
   exceeds `--max-calls`, do not split. Instead spend up to 8 calls on a
   coarse price histogram (log-spaced bands, counts only), print it with a
   "too broad, narrow by brand or price" verdict, and exit 0.
3. **Split**: a band `[a, b]` with count > 50 splits at `m` into `[a, m]` and
   `[m, b]` (shared endpoint, so cent prices between integers are covered).
   `m` = median of the ≤ 50 non-null prices returned for the band, rounded to
   an integer and clamped to `a < m < b`; if that fails, the geometric mean
   of `a` and `b`, clamped likewise. Process bands in ascending price order
   within the requested range; no band is prioritised over another.
4. **Termination**: a band with `b − a ≤ 1` and count > 50 cannot be split
   without losing cent prices; it is marked *capped* (we keep its 50
   products). Every split strictly shrinks both children, so the loop ends.
5. **Leaves**: a band with count ≤ 50 is complete only if
   `len(products) == totalCount`; otherwise (drift between calls) it is
   split again or, at the budget, marked *drifted*.
6. **Budget**: stop at `--max-calls`. Remaining bands are listed as
   *uncovered* with their price ranges.
7. **Coverage** is computed only from unique product ids, never from summed
   band counts (shared endpoints double-count). Report: unique ids found,
   root `totalCount`, capped / drifted / uncovered bands, and a tolerance note
   when the root count moved during the run. If the unfiltered total exceeds
   the `[1, 1000000]` total, the difference is reported as unreachable by
   price bands (priceless or < 1 CHF).
8. **Checkpointing**: with `--out`, results are written after every call, so
   a failure mid-run keeps everything found so far. On failure the script
   prints the partial report, then exits non-zero.

### Variant merge (conservative)

Products are merged into one row only when `brand`, `productType`, `name`
**and** `description` are all equal. Anything else stays a separate row:
showing extra rows costs space; merging different products shows false
facts (two "Redmi 17" records are a Helio 4G and a Snapdragon 5G phone).
Fuzzy de-duplication is deferred with the catalogue-quality report.

### Report format

- Coverage line (+ spell correction, partial / capped / uncovered notes).
- Per `productType` (largest first): up to `--top` rows; each row shows name,
  brand, price or price range, differing variant values as sets
  ("128/256 GB; 5 colours"), one rating (not averaged across variants),
  availability class, discount (`-6 CHF, was 155`), refurbished flag, link.
  Beyond `--top`: "+N more in FILE".
- `--out FILE` holds full data plus `language`, query, range and timestamp.

### `compare`

Reads FILE (refuses if `--lang` differs from the file's language). Ids not in
FILE are looked up by `brand + name` within a narrow price band around the
stored price, at most 3 calls per id; still missing → "not found
(best-effort)". Output: spec table across the ids with state per cell.

### Errors

| Situation | Behaviour |
|---|---|
| Endpoint unreachable at start | exit 2; SKILL.md switches to manual path |
| `isError` (invalid input) | exit 3 with message; agent fixes input |
| `errorMessage` in payload | treated as a failed search, not zero results; exit 4 with partial report; no manual fallback (same server) |
| Failure mid-run | partial report + checkpoint, exit 4 |
| Zero results, no `errorMessage` | normal output: "0 matches" |

## Spec extraction

### States

- **stated**: in `properties`, or in `description` next to a field keyword.
- **inferred**: derived (e.g. 5G from the name, Android base of HyperOS).
- **unknown**: absent.

Ceiling phrases ("up to", "bis zu", "jusqu'à", "fino a", "tot", "expandable",
"memory extension", "multiple configurations") yield a *range/ceiling*, not
this variant's value. In a merged row a value present for only some variants
shows "some variants".

### Sources and precedence

`properties` wins over `description`. On disagreement both are shown:
"conflict: 6.90" (properties) / 6.99" (description)". Description-only values
are marked as weaker.

### `properties` parsing

Split on `", "`, keep the raw string. Per `productType` a positional schema in
`spec-fields.md` (e.g. phone: storage, colour, screen, SIM, network; laptop:
screen, storage, RAM, keyboard layout, CPU; monitor: resolution, screen),
matched by pattern with position as tiebreak, because order varies and fields
can be missing. Unknown product types: generic pattern matching only.

### Description extractors

Per **field**, not per unit, with keyword adjacency and a per-language synonym
table (en/de/fr/it/nl): RAM, storage, screen size (inch, Zoll, cm diagonal),
resolution (`1920 x 1080`, `1920x1080@144Hz`), refresh rate (Hz; GHz is CPU
clock, never refresh), brightness (nits, cd/m²), response time (ms), battery
(mAh), charging power (W, distinguished from speaker W by keyword), camera
(MP), weight, OS + version, CPU model, panel type, network (4G/5G),
IP rating, ports (USB-C PD, HDMI, DP). Number parsing handles decimal commas
(`6,99`) and thousands separators (`8,340`) by language.

## Testing

- `test_transport.py`: replays **recorded real** SSE responses (success,
  `isError`, `errorMessage`, 400 missing session, 406 bad Accept).
- `test_search.py`: fake server over simulated catalogues (cent prices at
  band edges; 165 products at one price → capped; budget hit → uncovered;
  drift between calls; feasibility gate on 471,800). Asserts coverage from
  unique ids, termination, checkpoint content.
- `test_specs.py`: extractors on real recorded descriptions in en and de,
  including RAM/storage disambiguation, ceilings, conflicts, decimal commas.
- `test_live.py` (opt-in, `GALAXUS_LIVE=1`): contract check — bounds
  inclusive, price shape, `_meta` availability fields present; "Redmi 17"
  search complete (unique ids == `totalCount`, no exact total asserted).
- Version consistency test.
- CI: GitHub Actions, Python 3.10 and 3.13, Ubuntu and Windows, offline tests
  only.
- `evals/cases.md`: fixed prompts (Android 17 phone under 300 CHF; 27" monitor
  ≥ 144 Hz under 250 CHF; one too-broad query), 3 runs each with and without
  the skill. Pass = coverage line present; no "does not exist" under partial
  coverage or unknown specs; no spec tokens in the query; Android 17 phone
  under 300 found if one exists (checked by hand on galaxus.ch).

## Distribution

README covers:

- Claude Code: `claude mcp add --transport http galaxus https://mcp.galaxus.ch/`
  (only for the manual path) and install as a plugin from this repo, or copy
  `skills/galaxus/` into `~/.claude/skills/`.
- claude.ai: ZIP upload of `skills/galaxus/`; custom connector for the
  manual path; note the sandbox network limitation.
- Codex and other MCP clients: endpoint + where to place the skill.
- Windows: `py` launcher; UTF-8 output.
- Use is limited to normal search volume (sequential calls, budget 60);
  `agentInfo` identifies the skill honestly.

Open: Galaxus terms of use for automated MCP use were not found; check before
publishing.
