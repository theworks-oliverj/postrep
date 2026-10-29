# Session 7: Triage, follow-ups and cross-cuts

*Module `s7_triage`. Load in phase `followups`. Reads `04_search/`. Writes `followup_plan.json`, `followups/` and `crosscuts/`.*

## Purpose

Spend follow-up effort only where it can change the person's decision, and cover the schemes that don't fit a per-country split.

## Triggers

Each trigger names a condition and the response. `scripts/followups.py RUN_DIR --write` emits them.

| Trigger | Condition | Response |
|---|---|---|
| `complete_with_gaps` / `budget_exhausted` | The agent stopped with listed gaps | Follow-up on the listed gaps only |
| `path_b_missing` | `path_b_done` is false, or Path B is thin | A Path B-only follow-up |
| `promote_flag` | A ranked-out entry has `promote: true` | Full records for promoted entries; swap them in if they win |
| `unscored_axis` | A top-N record has "?" | Targeted evidence search for that axis |
| `deadline_soon` | A deadline within 60 days | Verify on the official page now; tell the person |
| `suspected_false_negative` | A fail or unscreened reason signals an evidence gap ("no … found", "blocked", "could not access") rather than merit | Re-check with different queries, or ask the person to check a blocked page by hand |

## Stop rule: "the decision can't flip"

Skip follow-ups for a country when **its best achievable funding score (ranked-out entries included) is below `search_plan.funded_definition.min_funding_score` AND no record has pathway ≥ 2**. Record the reason in the notes; it appears in the deliverables.

## Cross-cut agents

| Kind | Tracks | Behaviour |
|---|---|---|
| programme_scan (regional or joint-degree catalogues) | Programmes that span countries | Scan the catalogue against the domains, and record the funding mechanics. Competitive consortium awards rarely justify funding 3; cap them with an override if agents over-score them |
| funding_route (home-country, donor, government schemes) | Money that follows the person, not the programme | Read the **current call text** (the PDF, not summaries). Quote each clause with its page for amount, eligibility, timing (when an acceptance letter is needed) and obligations. Agent summaries of PDFs are not primary evidence |

Use prompt P3 for follow-ups and P4-style independence for cross-cuts. Write cross-cut files incrementally (`checkpoint.py add-finding`).

## Exit

Every trigger is resolved or stopped by the rule. Update the state vector with `phase: followups → merge`.
