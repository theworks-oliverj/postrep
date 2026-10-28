# Session 8: Merge and independent verification

*Module `s8_merge_verify`. Load in phases `merge` and `verify`. Writes `05_merge/` and `06_verify/`.*

## Purpose

Turn many agent files into one clean, scored dataset, and measure how far it can be trusted.

## Merge rules

`scripts/merge.py RUN_DIR` implements these rules. In degraded mode, Virgil follows them by hand.

| Rule | Protects | Behaviour |
|---|---|---|
| Validate first | Aggregation | Validate every file against its schema and report enum drift (`scripts/validate.py`) |
| Coverage check | Countries going missing silently | Every country and cross-cut in `search_plan` must have a file. A missing one is an error unless the person accepts a partial merge |
| Overrides as data | Traceable corrections | Apply `04_search/overrides.json` (target, field, original, new, reason, who, date). Never hard-code corrections in scripts or prose |
| Dedupe | Double counting | Exact match on normalised institution + programme. Near-duplicates (fuzzy match ≥ 0.75) are flagged for a human, never auto-merged |
| Keep extras | Decision-relevant detail | Keep follow-up deadlines, scheme terms, Path B people and promoted records |
| Compute, don't type | Miscounts | Totals (ignoring "?"), the list of unscored axes, rank (total, then pathway, then funding) and the delta vs a previous run under the same rubric version all come from data |

After a clean merge, update the state vector with `phase: merge → verify`.

## Verification rules

| Rule | Protects | Behaviour |
|---|---|---|
| Mixed sample | Extrapolation | Take the top N (≈10-12) plus a random M (≈8-10) from the rest (`scripts/sample_verification.py`) |
| Independence | Self-grading | A fresh agent that hasn't seen the research checks the claims (fee, deadline, people/partners, language, funding) on official pages (prompt P4) |
| Adjudication | Verifier error | The verifier flags; Virgil adjudicates disputes on the primary source |
| Perishables | Stale facts | Re-verify every deadline within 60 days, whether or not it was sampled |

**What to expect (n = 1):** in the reference run, 78% of sampled claims were confirmed, 8% wrong and 14% not found. People claims held 12/12. Fees and future deadlines failed about one time in three. The deliverables should treat them accordingly.

## Exit

`merged.json` is written and the verification is adjudicated. Update the state vector with `phase: verify → deliverables`.
