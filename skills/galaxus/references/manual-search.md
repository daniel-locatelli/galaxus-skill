# Manual search with the `search_products` MCP tool

Use only when `scripts/galaxus.py` cannot run. The same algorithm as the
script, by hand, with a smaller budget (20 calls).

What the host shows you: the JSON text `{correctedSearchTerm, totalCount,
products[], errorMessage?}`. The undocumented `_meta` block (availability,
discounts) is not shown (checked in Claude Code, 2026-11-11), so on this path
say "availability and discounts: not available on this path".

## Arguments

Pass on every call:

- `query`: the category query (SKILL.md section 2).
- `language`: en, de, fr, it or nl (required).
- `agentInfo` (required): name the skill and yourself honestly, e.g.
  `galaxus-skill/0.1.0 manual path, <host>, <model id>`.
- `first: 50` (the default is 10).
- `minPrice` / `maxPrice`: integers 1…1,000,000, **inclusive**. Without a
  user range, search 1–1,000,000.

Leave `userIntent` out; it is optional and this skill never sends it.

## Procedure

1. Root call over the user's range.
   **On any call**, root or band: if the payload has `errorMessage` or the
   tool returns an error result, the search has *failed*. Stop, and report a
   failed search (not zero results) with the unique ids seen so far and the
   bands not searched. A band whose call failed is never done or empty.
2. Gate: if `totalCount` > 500, do not split; ask the user to narrow (brand in
   the query, tighter price range).
3. Keep a list of bands to do and a set of product ids seen.
4. A band `[a, b]` is done when `totalCount` ≤ 50 and all its products came
   back. Otherwise take the median of the returned
   `priceIfAvailable.amountInclusive` values (skip null prices), rounded,
   clamped to `a < m < b` (no prices: the geometric mean of `a` and `b`).
   Split into `[a, m]` and `[m, b]` and do them in ascending order. The shared endpoint `m` matters: prices like 193.97 fall
   between integer bounds and are lost with `[a, m]`, `[m+1, b]`.
5. A band with `b − a ≤ 1` and more than 50 products is *capped*: keep its 50,
   note it. Capped bands are usually cheap accessories; a narrower query or a
   `minPrice` above them avoids them.
6. Stop after 20 calls; list the bands not searched as *uncovered*.
7. Coverage = number of **unique ids** seen vs the root `totalCount`. Never sum
   band counts (shared endpoints double-count). Status: *complete* when every
   band is done, else *partial* with the capped and uncovered bands listed.

## Reading and filtering

Read specs as described in `spec-fields.md`: properties first, then the
description next to a field keyword; mark description values *(desc.)*,
derived values *(inferred)*, ceilings *up to*, missing values *?*. For each
condition the user asked for, count matched, unknown and excluded products
yourself and report them the way the script's `filter` does. Then apply the
output rules in SKILL.md section 4.
