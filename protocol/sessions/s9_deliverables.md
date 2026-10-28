# Session 9: Deliverables

*Module `s9_deliverables`. Load in phase `deliverables`. Reads the Preamble, `05_merge/` and `06_verify/`. Writes `07_deliverables/`.*

## Purpose

Turn the merged dataset into two documents:
- **D6 Options Rundown:** a decision document the person can act on this week.
- **D7 Due-Diligence One-Pager:** shows how wide and deep the search was, and how much of it was verified.

## Build order

1. `python3 scripts/shortlist.py RUN_DIR` writes `07_deliverables/rundown_tables.md`: benchmark line, shortlist, overlays, deadlines, ruled-out list and stop-rule notes, all computed from data.
2. `python3 scripts/due_diligence.py RUN_DIR` writes `07_deliverables/due_diligence.md`.
3. Virgil writes the Options Rundown prose around the computed tables (`protocol/templates/options_rundown.md`).
4. Publish in the richest shareable format the runtime offers. In order of preference: a document artifact (editable, shareable), a self-contained HTML page, Markdown.

In degraded mode (no scripts), steps 1-2 are done by hand from `merged.json`. Cap the shortlist at 15 and mark the hand-counted numbers.

## Writing rules for D6

| Rule | Protects | Behaviour |
|---|---|---|
| Decision support, not a league table | The person's own weighting | Rank by the vector. Use a weighted "overall score" only if the person gave weights (LP-S4), and show them |
| One screen first | Busy readers | Section 1 alone must name the live options and this week's actions |
| The person's own terms | Relevance | Explain fit through their domains, pathway signals and life-plan constraints |
| Every fact links, every option ends in an action | Trust and momentum | Inline confidence; a `contact_actions` question for each unverified route |
| Decisions that reorder the list come early | Wasted deliberation | Surface the open choices from the Preamble that change rankings, e.g. "affordable vs zero tuition" or "accept a return obligation?" |

**Optional:** an interactive explorer built from `merged.json` (sortable shortlist, vector-swap view, filters by country, funding route and practical component). The reference applicant found it the most useful way to digest 128 records.

## D7 contents

Generated, never hand-typed.
- Scope.
- Coverage funnel, with a per-country table.
- Novelty versus any prior run.
- Benchmark position.
- Evidence quality: confirmed people/partner routes, confirmed funding eligibility, source mix, null sources.
- Independent verification: sample, method, verdicts, weakest claim type.
- Known gaps.
- Time sensitivity.
- Method caveats.
- Effort: agent runs, windows, sessions.

Template: `protocol/templates/due_diligence.md`.

**Reference scale (n = 1, anonymised):**
- 353 institutions screened, of which 194 passed.
- 128 full records and 186 ranked-out.
- Verification: 78% confirmed, 8% wrong, 14% not found.
- About 25 agent runs across about 4 windows.

Treat these as orders of magnitude, not targets. Details are in `examples/reference_run/`.

## Hand-over

Deliver both documents. Give a three-line summary and one recommended next step. Update the state vector with `phase: deliverables → done`. Export everything in modes C and P.
