# galaxus-skill

An agent skill for **exhaustive** product search on [Galaxus](https://www.galaxus.ch)
through its official MCP endpoint (`https://mcp.galaxus.ch/`; Galaxus announcement:
<https://www.galaxus.ch/en/page/galaxus-introduces-mcp-interface-for-ai-assistants-44216>).

Status: version 0.1.0, early release. See "Open items" below.

The endpoint has one tool, `search_products`. It returns at most 50 products
per call, with no pagination, sort or spec filters. Asked "is there an Android
17 phone under 300 CHF?", an agent sees 50 of thousands of matches and often
answers "no". This skill:

- splits the price range until every band fits in one call, and reports
  coverage (complete / partial / infeasible / failed) from unique product ids;
- extracts specs from the free-text records with stated / inferred / unknown
  states, ceilings ("up to") and conflicts;
- refuses "none exist" unless coverage is complete and the spec is known;
- shows availability and discounts from an undocumented field, labelled as
  such (script path only).

It cannot find specs the endpoint does not send. The site's "Android 17"
filter lists a Samsung Galaxy A18 at CHF 189, but its MCP record never
mentions the OS, so the skill reports it as "unknown, could qualify" rather
than as a match. See [docs/findings-2026-11-11.md](docs/findings-2026-11-11.md).

## Install

### Claude Code

    /plugin marketplace add daniel-locatelli/galaxus-skill
    /plugin install galaxus@galaxus-skill

or, from a shell:

    claude plugin marketplace add daniel-locatelli/galaxus-skill
    claude plugin install galaxus@galaxus-skill

To try a local checkout instead:

    /plugin marketplace add <path to checkout>
    /plugin install galaxus@galaxus-skill

Alternatively copy `skills/galaxus/` to `~/.claude/skills/galaxus/`; it is then
a standalone skill invoked as `/galaxus`.

Optional, only for the manual fallback (when Python cannot run):

    claude mcp add --transport http galaxus https://mcp.galaxus.ch/

### claude.ai

Zip the `skills/galaxus/` folder and upload it as a skill (see the claude.ai
help on skills for the current menu path). Build the zip from git, so no
`__pycache__/` or other untracked files end up in it:

    git archive --format=zip --prefix=galaxus/ -o galaxus.zip HEAD:skills/galaxus

Add `https://mcp.galaxus.ch/` as a custom connector for the manual path.
Unverified: whether the code-execution sandbox can reach `mcp.galaxus.ch`. If
it cannot, the script exits 2 and the skill falls back to the connector
(manual path).

### Codex and other MCP clients

Point the client at `https://mcp.galaxus.ch/` (HTTP transport, no auth) and
place `skills/galaxus/` where the client loads skills or instructions. Not
tested with other clients.

## Requirements

Python 3.10 or newer, standard library only. The skill tries `python3`, then
`py`, then `python`. Output is UTF-8. `count`, `search` and `compare --lookup`
need network access to `mcp.galaxus.ch`; `filter` and `compare --ids` read a
saved file.

## Use

Subcommands: `count`, `search`, `filter`, `compare` (`<sub> --help` lists
flags). Prices are integer CHF, inclusive; languages `en de fr it nl`.

    # one call: how many matches? (a complete search needs about 3.5 x count / 50 + 2 calls; budget 60, so up to ~800)
    python3 skills/galaxus/scripts/galaxus.py count "Samsung smartphone" --min 200 --max 500

    # exhaustive search, full result kept in a file
    python3 skills/galaxus/scripts/galaxus.py search "Samsung smartphone" --min 200 --max 500 --out phones.json

    # filter offline, with counts of matching / unknown / excluded products
    python3 skills/galaxus/scripts/galaxus.py filter --from phones.json --type Smartphones --where "android_version>=15" --where "ram>=8"

    # spec table for chosen product ids
    python3 skills/galaxus/scripts/galaxus.py compare --from phones.json --ids <id>,<id>

On Windows use `py` instead of `python3`. Search over the default budget is
refused as `infeasible` with a price histogram (a bare "smartphone" at
CHF 100-300 has 43014 matches) rather than listing a few products.

Exit codes: 0 ok (including partial and infeasible), 2 endpoint unreachable,
3 invalid input, 4 Galaxus error or failure mid-run (a failed search, not zero
results).

### Limits to know

- Price filters are integers. More than 50 products inside one 1-CHF band end
  as an honest `partial` with the capped bands listed (for example "Redmi 17"
  matches about 290 phone covers at CHF 19-23).
- The manual path (MCP tool only, no Python) uses a 20-call budget and has no
  availability or discount data: the host does not show the `_meta` block.
- Weight filters need a unit (`weight<=1.5kg`).
- Product pages answer plain HTTP with 403; the optional page check needs a
  real browser tool.

## Fair use

Calls are sequential with a 0.2 s delay and a default budget of 60 calls per
search (`--max-calls` at most 300; `compare` at most 20 lookups); a server
`Retry-After` is honoured up to 30 s. `agentInfo` identifies the skill as
`galaxus-skill/<version>`.

## Open items

Endpoint findings and suggestions for Galaxus: [docs/findings-2026-11-11.md](docs/findings-2026-11-11.md).

Not resolved at the time of writing:

- Galaxus terms of use for automated MCP use were not found or checked.
- Reachability of `mcp.galaxus.ch` from the claude.ai code sandbox is unverified.
- Whether the catalogue also covers Digitec is unverified.
- The `_meta` availability classes (`TICK`, `FULL`, `THREE_QUARTER`,
  `QUARTER`) are undocumented; the skill shows them raw and gives them no
  meaning. Availability and discounts come from this undocumented field.

## Development

    py -m pip install pytest
    py -m pytest                                    # offline
    GALAXUS_LIVE=1 py -m pytest tests/test_live.py  # live contract checks (needs network)
    py tests/record_fixtures.py                     # re-record fixtures (needs network)

CI runs the offline tests on Python 3.10 and 3.13, Ubuntu and Windows.
Eval prompts and pass criteria: `evals/cases.md`. Design:
`docs/superpowers/specs/2026-11-11-galaxus-skill-design.md`.

## Licence

MIT
