# Galaxus skill — design

Date: 2026-11-11
Status: approved in brainstorming, awaiting spec review

## Context

On 2026-11-11 Galaxus announced an official MCP server for its Swiss catalogue
(~13 M items): <https://www.galaxus.ch/en/page/galaxus-introduces-mcp-interface-for-ai-assistants-44216>.
Endpoint: `https://mcp.galaxus.ch/` (streamable HTTP, root path, no auth,
session via `Mcp-Session-Id` header).

The server exposes **one tool**, `search_products`:

- inputs: `query` (free text), `first` (1–50, default 10), `minPrice` /
  `maxPrice` (integer CHF), `language` (en/de/fr/it/nl), `agentInfo` and
  `userIntent` (analytics only)
- output: `{correctedSearchTerm, totalCount, products[]}`; each product has
  `id, name, properties, description, productType, brand, priceIfAvailable,
  pageUrl, previewImage, ratingSummaryIfAvailable,
  productReviewsSummaryIfAvailable`
- no prompts, no lookup by id, no pagination offset, no sort, no brand filter,
  no stock / delivery / seller, no discounts, no cart

### Limitations raised in the article's comments, checked by probing (2026-11-11)

| Comment claim | Probe result |
|---|---|
| Agent lists a few known products instead of searching systematically | Confirmed: no pagination; "smartphone" has `totalCount` 471,659 but max 50 returned; 29 of 50 "Android 17 smartphone" results were colour/storage variants |
| Agent says an Android 17 phone under 300 CHF does not exist | Confirmed cause: no structured specs; OS named in only 7 of 50 records, inside free-text `description`; query matched model names containing "17" |
| `minPrice`/`maxPrice`/brand are applied client-side on one page | Partly wrong: price filter is server-side (`minPrice:1500` → `totalCount` 410); there is no brand parameter |
| No availability or seller | Confirmed (tool description states it) |
| No price history | Confirmed; Galaxus staff reply: only product search with some filters for now |
| Catalogue data is messy (wrong specs, duplicates) | Not fixable by us; out of scope for v1 |
| Only ChatGPT/Claude promoted | Endpoint works with any MCP client |

Further probe facts the design relies on:

- `minPrice` and `maxPrice` are **inclusive**: for "Redmi 17", `[1,163]` = 405
  and `[164,∞]` = 54, sum 459 = unfiltered total.
- Unfiltered total equals `[1, 1000000]` total in the samples tried, so no
  priceless products were lost to the filter there.
- Prices can carry cents (e.g. 809.99) while bounds are integers.
- A `first:1` call takes ~0.4 s and still returns `totalCount`.
- A 50-product response is ~100 KB of JSON.
- Search matching is loose: "Redmi 17" returns 459 products.

## Scope

**v1 public core** (this repo):

1. Exhaustive search — price-band slicing, variant merge, coverage report.
2. Spec extraction — specs from `properties` and `description`, with source;
   missing means *unknown*, never *no*.
3. Product-page check — when the client has a browser tool, verify stock,
   delivery and seller on `pageUrl`; otherwise say they were not checked.

**Personal, not in this repo:** devil's-advocate mode (argue against buying
before recommending), as a separate skill in Daniel's own skills repo.

**Deferred:** price log / history and any scheduler, catalogue-quality report,
bundle / bill-of-materials builder.

## Approach

`SKILL.md` + a stdlib-only Python CLI that talks to the MCP endpoint over HTTP
(approach B). When the client cannot run Python with network access, the skill
falls back to the same procedure done by hand through the MCP tool
(`references/manual-search.md`). Rejected: instructions only (context blow-up
and agent sloppiness on large searches); own MCP wrapper server (hosting cost,
not needed for v1).

Unverified: whether claude.ai's code-execution sandbox can reach
`mcp.galaxus.ch`. The fallback covers the case where it cannot.

## Repository layout

```
galaxus-skill/
├── skills/galaxus/
│   ├── SKILL.md
│   ├── scripts/galaxus.py
│   └── references/
│       ├── manual-search.md
│       └── spec-fields.md
├── tests/
│   ├── fixtures/
│   └── test_galaxus.py
├── docs/superpowers/specs/
└── README.md
```

Remote (when pushed): `gh-daniel-locatelli:daniel-locatelli/galaxus-skill`.

## Components

### `SKILL.md`

- Triggers on product search, comparison or price questions about Galaxus /
  the Swiss market.
- Chooses path: script if Python + network is available, else manual fallback.
- Output rules, always:
  - state coverage ("checked 410 of 410 matches"); say "partial" with the
    reason when not complete
  - merge variants into one row
  - a spec absent from the data is *unknown*; inferred values are labelled
    *inferred*
  - report spell correction when `correctedSearchTerm` is non-null
  - links point to Galaxus `pageUrl`; purchases happen there
- Product-page check: when a browser tool exists, open `pageUrl` for the
  shortlisted products and mark stock / delivery / seller per product as
  *checked* or *not checked*. Never assert stock that was not seen.

### `scripts/galaxus.py` (stdlib only)

Subcommands:

- `count QUERY [--min N] [--max N] [--lang L]` — one `first:1` call, prints
  `totalCount`.
- `search QUERY [--min N] [--max N] [--lang L] [--max-calls 60] [--out FILE]`
  — exhaustive search (below); prints a compact Markdown report; full JSON to
  `FILE` when `--out` is given.
- `compare --from FILE --ids ID,ID,… [--lang L]` — spec table for the given
  ids. Ids missing from `FILE` are re-searched by product name and matched by
  id; still missing → reported as not found.

`agentInfo` is sent as `galaxus-skill/<version>`.

#### Search algorithm

1. Count the whole requested price range with `first:1`.
2. If `totalCount` ≤ 50, fetch it with `first:50`. Otherwise split the range
   and count each half; repeat until every band holds ≤ 50. The split point is
   chosen from the prices seen so far (median of observed prices inside the
   band), falling back to the midpoint.
3. Adjacent bands overlap by 1 CHF; results are de-duplicated by product id.
   This closes the gap for prices with cents between integer bounds.
4. Budget: stop at `--max-calls` (default 60). The report then says
   "partial: X of Y, bands covered: …", cheapest bands first. A 1 CHF band
   with > 50 products cannot be split and is reported as capped.
5. Final check: unique ids found vs root `totalCount`; any difference is
   printed.
6. Merge variants by (`brand`, `name`): one row with variant count, price
   range and the list of variant `properties`.
7. Group rows by `productType`, largest group first, so the agent can drop
   irrelevant types from loose matches. "Complete" means complete for what
   Galaxus returned, and the report says so.

#### Report format

- Coverage line (+ spell correction, + partial / capped notes).
- Per `productType`: table of name, brand, price or range, variants, rating
  (avg / count), key specs, link.

#### Errors

- Expired or missing session → re-initialise once and retry.
- Transport errors / 5xx → two retries with backoff, then exit non-zero with a
  clear message.
- `errorMessage` in the payload or an MCP error result → exit non-zero with
  the message; `SKILL.md` then switches to the manual fallback.

### Spec extraction

- Sources: `properties` (comma list, field order varies by type) and
  `description` (free text).
- Unit-tagged extractors: GB / TB, inches, Hz, mAh, W, MP, g / kg, mm, and OS
  name + version (Android, iOS, HyperOS, One UI, Windows, macOS, ChromeOS).
- Each value carries `source` (`properties` | `description`) and a short
  surrounding snippet, so ambiguous phrases ("up to 12GB RAM") can be judged.
- Not found → `unknown`.

### `references/spec-fields.md`

Per common product type (smartphones, monitors, laptops, TVs, headphones,
tablets) the fields worth showing as columns, and a reminder to tell the user
which of them Galaxus does not supply.

### `references/manual-search.md`

The search algorithm restated as steps for an agent using the MCP tool
directly, including the `first:1` count trick and the coverage-reporting
rules.

## Testing

- Offline unit tests (default run):
  - fake MCP server over a simulated catalogue: all ids found; prices with
    cents at band edges; a dense 1 CHF band reported as capped; budget hit
    reported as partial; session expiry handled
  - variant merge and spec extractors on real recorded descriptions in
    `tests/fixtures/`
- Live smoke test, opt-in via `GALAXUS_LIVE=1`: "Redmi 17" unique ids equal
  `totalCount`; response shape unchanged.
- Skill check: the two comment failures (Android 17 phone under 300 CHF;
  systematic monitor search) run with and without the skill, comparing
  coverage and "does not exist" errors.

## Distribution

`README.md` covers setup for Claude Code (`claude mcp add --transport http
galaxus https://mcp.galaxus.ch/` + skill install), claude.ai (custom connector
+ ZIP upload of `skills/galaxus/`), Codex, and generic MCP clients.
