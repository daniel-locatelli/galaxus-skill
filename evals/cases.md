# Evals

Run each prompt 3 times **with** the skill and 3 times **without** it (fresh
session each). Record the transcript path and pass/fail per criterion.

Counts below were measured with `galaxus.py count` on 2026-11-11 and drift
over time; re-run `count` before judging a run. The script estimates a
complete search at ceil(3.5 x count / 50) + 2 calls against a budget of 60, so
it fits up to about 800 matches (live: 611 matches took 40 calls; 959 ran out
at 60).

## Cases

1. "Find me a Samsung smartphone with at least 8 GB RAM and Android 15 or
   newer, between 200 and 500 CHF on Galaxus."
   Feasible: `count "Samsung smartphone" --min 200 --max 500` = 611
   (estimate 45 calls; 40 used live).
2. "I want a 27-inch monitor with at least 144 Hz for under 250 CHF from Galaxus."
   Over budget at the default 60: `count "monitor 27 inch" --min 100 --max
   250` = 959 (estimate 70 calls, `infeasible`). Narrowed: `--min 150 --max
   250` = 541 (estimate 40, feasible). A good run counts first, then narrows
   (a stated lower bound such as CHF 150, or a brand) or asks the user before
   using `--max-calls 70`. The user gave no lower bound; any lower bound the
   agent chooses must be stated.
3. "Find me an Android 17 smartphone under 300 CHF on Galaxus."
   Deliberately infeasible as a bare category: `count smartphone --min 100
   --max 300` = 43014. A good run counts first, then narrows (brand, price) or
   asks. A run that puts "Android 17" into the query is also acceptable only
   if it reports the result as partial ("Android 17 smartphone" matches
   "Redmi 17" and its cases, not phones whose record never says "17").
4. "Show me every smartphone Galaxus sells." (too broad)
5. "Is there a Redmi 17 on Galaxus for under 30 CHF?" Honest-partial path:
   "Redmi 17" matches about 290 phone covers at CHF 19-23, more than 50 in a
   1-CHF band, which integer price bounds cannot split. Expect `partial` with
   capped bands.
6. Manual path: run in a session where Python cannot run (or the script
   exits 2) and only the `search_products` MCP tool is available. Prompt:
   "Find a Samsung smartphone between 250 and 300 CHF on Galaxus."
7. Failure path: "Search Galaxus for x." A single-character query is answered
   by the server with `errorMessage` (seen 2026-11-11 for "x"; may change).

The failed / `errorMessage` path cannot be triggered reliably live. It is
covered offline by `tests/test_cli.py`:
`test_root_error_message_exits_4`,
`test_error_message_mid_run_exits_4_with_checkpoint`,
`test_tool_input_error_exits_3`. Case 7 is an optional live spot check.

## Pass criteria (all must hold unless a case says otherwise)

- The answer quotes a coverage line (complete / partial / infeasible / failed)
  with its numbers.
- No "does not exist" / "none available" claim under partial coverage or
  unknown specs. A "none qualify" claim needs complete coverage and known
  specs for every candidate.
- No spec tokens in the query ("17", "144", "Android 17" as query text),
  except where the user names a model (cases 3 and 5, see their notes).
- Case 1: matches use the script's `filter`; products with unknown OS or RAM
  are listed as candidates, not dropped (n/a if none are unknown).
- Case 2: the run does not search 100-250 at the default budget without
  narrowing or the user's agreement; the answer states the price range
  actually searched and reports how many products had unknown refresh rate.
- Case 3: the answer reports infeasibility (or partial coverage) and offers
  ways to narrow (brand, price range) instead of listing a few products.
  If it finds an Android 17 phone under 300 CHF, check by hand on galaxus.ch
  (Chrome; plain HTTP is blocked) and note the result here.
- Case 4: the answer reports infeasibility, shows or mentions the price
  histogram, and does not list a handful of products as "every smartphone".
- Case 5: the answer reports capped bands and that coverage is partial; it
  tells the user which range was not fully searched.
- Case 6: every call passes `agentInfo` naming the skill and host; the
  answer says "availability and discounts: not available on this path"; any
  call whose payload has `errorMessage` is treated as a failed search; the
  coverage line (unique ids vs root `totalCount`, status) is reported; the
  budget is 20 calls.
- Case 7: reported as a failed search, not zero results.
- Availability classes, if shown, are raw and labelled as an undocumented
  field; discounts and availability are not claimed on the manual path.
- Without the skill, note what the baseline did (typically 1 call, no
  coverage statement) for comparison; baseline failures are expected.

## Check by hand

For any "found" or "none" claim, check galaxus.ch by hand and record it here
(date, case, what the site shows, agrees with the answer yes/no).

| Date | Case | Site shows | Agrees |
|---|---|---|---|

## Results

| Date | Case | Skill | Run | Coverage line | No false "none" | No spec tokens | Found | Checked by hand | Notes |
|---|---|---|---|---|---|---|---|---|---|
