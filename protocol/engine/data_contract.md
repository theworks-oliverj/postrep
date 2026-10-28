# Engine: data contract

*Module `data_contract`. Load when writing JSON without the scripts, or when unsure of a field.*

## Purpose

Every file a run writes has a JSON Schema in `schemas/` (draft 2020-12). The schemas are the contract between Virgil, the research agents and the scripts. Field names and enums are fixed: an agent never invents a value. Minimal, schema-valid examples of every core file are in [`docs/appendix_a_examples.md`](../../docs/appendix_a_examples.md). They are tested, so they can't drift from the schemas.

## Files and their schemas

| File | Schema | Tracks |
|---|---|---|
| `run_state.json` | `run_state` | Ledger: mode, sessions, checkpoints, assumptions, protocol overrides, the continuation `state_vector` |
| `01_life_plan/life_plan.json` | `life_plan` | The Life & Career Plan. Gate fields live under `purpose_horizon`, `post_degree_intent`, `money` (LP-G3), `eligibility_facts` (LP-G4), `geography` (LP-G5), `timeline` (LP-G6), `household` (LP-G7) |
| `01_life_plan/life_plan_score.json`, `02_map/map_score.json` | `rubric_score` | Gate statuses, soft scores, `soft_pct`, `passed` |
| `02_map/study_pathway_map.json` | `study_pathway_map` | Objective, knowledge domains, pathway signals, practical component needed, anchors |
| `02_map/benchmarks.json` | `benchmarks` | Exactly three benchmarks (axes funding, programme, pathway) with baseline vectors |
| `03_scope/search_plan.json` | `search_plan` | Countries, depth, caps, waves, cross-cuts, funded definition, overlay policy, exclusions |
| `04_search/countries/<slug>.json` (and follow-ups) | `country_run_file` | Screening, candidates, ranked-out, country context, status, `path_b_done`, run metadata |
| a candidate inside it | `candidate_record` | One programme: sources, `axis_1_curriculum`, `axis_2_pathway`, `practical_component`, language, tuition, funding, overlays, `household_fit`, deadlines, `state_vector`, `contact_actions` |
| `04_search/crosscuts/<slug>.json` | `crosscut_scan_file` / `funding_route_crosscut` | Cross-country programme scans, or funding schemes (findings quoted with clause and page) |
| `04_search/overrides.json` | `override` | Dated corrections: target, field, original, new, reason, who |
| `04_search/followup_plan.json` | `followup_trigger` | Triggers and stop-rule decisions |
| `05_merge/merged.json`, `merge_report.json` | `merged_file`, `merge_report` | The merged dataset and the merge issues |
| `06_verify/verification_sample.json`, `verification.json` | `verification_sample`, `verification_record` | The sample, plus verdicts with evidence |
| `logs/session_log.jsonl` | `session_log_entry` | One event per line |

## Field rules that matter most

| Field | Rule |
|---|---|
| `candidate.state_vector.{funding, programme, pathway}` | An integer 0-3, or `"?"`. Never a guess. This is the scoring vector, not `run_state.state_vector`, which is the continuation vector |
| `*.confidence`, `takes_students`, `applicant_eligible` | Fixed enums (`confirmed`, `inferred`, `verification_needed`, `unknown`). Absence of evidence is not `confirmed` |
| `deadlines[].date_type` | `confirmed` (this cycle, official), `pattern` (last cycle's date) or `inferred` |
| `sources[]` | Each entry has a `url` (or null with a note), `source_type` and `accessed_date` |
| `overlays[].effect` | The funding score the programme would have *if* the scheme were awarded. Never part of the base score |
| `status` (files) | `in_progress`, `complete`, `complete_with_gaps` or `partial_budget_exhausted`, reported honestly |
