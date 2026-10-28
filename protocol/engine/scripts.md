# Engine: scripts reference

*Module `scripts`. Load when running the tooling. The scripts are standard-library Python 3.10+. They use `jsonschema` if it's installed, and a built-in validator otherwise. Every script takes the run directory first and never hard-codes countries or paths.*

| Step | Session | Command |
|---|---|---|
| Create workspace | S0 | `python3 scripts/init_workspace.py RUN_DIR --alias "Applicant A" --mode local\|cloud\|project_chat\|api [--run-id ID]` |
| Score a rubric | S1, S2 | `python3 scripts/rubric.py RUN_DIR life_plan\|pathway_map [--check]` |
| Status / "Where we are" | every | `python3 scripts/status.py RUN_DIR [--brief] [--json]` |
| Replace the state vector | session close | `python3 scripts/checkpoint.py RUN_DIR update-vector --file vector.json` |
| Log an assumption / protocol override | any | `python3 scripts/checkpoint.py RUN_DIR add-assumption ...`<br>`python3 scripts/checkpoint.py RUN_DIR add-protocol-override ...` |
| Log a session event | any | `python3 scripts/checkpoint.py RUN_DIR log-session --start\|--end\|--event E [--phase P] [--set-phase P] [--agents-run N] [--limit-hit] [--next-action T]` |
| Start a country file | S4-S7 | `python3 scripts/checkpoint.py RUN_DIR init-country --country SLUG --name NAME [--followup [X]] [--resume]`. Refuses unless both rubrics passed; `--force --reason T` logs a protocol override |
| Start a cross-cut file | S7 | `python3 scripts/checkpoint.py RUN_DIR init-country --crosscut SLUG --kind programme_scan\|funding_route --name NAME` |
| Append one unit (after **each** record) | S4-S7 | `python3 scripts/checkpoint.py RUN_DIR add-screening\|add-candidate\|add-ranked-out --country SLUG [--followup [X]] (--json STR \| --file PATH \| -)` |
| Append a funding finding | S7 | `python3 scripts/checkpoint.py RUN_DIR add-finding --crosscut SLUG --file finding.json` |
| Close a file | S4-S7 | `python3 scripts/checkpoint.py RUN_DIR set-status --country SLUG [--status S] [--path-b-done true\|false] [--country-context FILE\|JSON] [--budget-notes T] [--add-gap T] [--limit-event KIND:DETAIL]` (use `--crosscut SLUG` for cross-cuts) |
| Clear parked invalid records | any | `python3 scripts/checkpoint.py RUN_DIR clear-rejected [--id ID]` |
| Validate everything | any | `python3 scripts/validate.py RUN_DIR [--strict] [--json]` |
| Follow-up triggers + stop rule | S7 | `python3 scripts/followups.py RUN_DIR [--today D] [--deadline-days 60] [--top-n N] [--min-funding 0-3] [--unknowns conservative\|ignore] [--write]` |
| Merge | S8 | `python3 scripts/merge.py RUN_DIR [--baseline PATH] [--allow-partial] [--near-dup 0.75]` |
| Verification sample | S8 | `python3 scripts/sample_verification.py RUN_DIR --top 10 --random 10 --seed 42 [--claims fee,deadline,people_partner,language,funding]` |
| Rundown tables | S9 | `python3 scripts/shortlist.py RUN_DIR [--top 15] [--today D] [--deadline-days 90]` |
| Due-diligence one-pager | S9 | `python3 scripts/due_diligence.py RUN_DIR [--today D] [--deadline-days 90] [--no-examples]` |
| Self-test | - | `python3 tests/run_tests.py` |

**Behaviour notes**
- `followups.py` treats `"?"` conservatively by default, so the stop rule rarely fires on sparse data. Use `--unknowns ignore` to relax it.
- `merge.py` reports `planned_country_missing` as an error unless `--allow-partial` is given. It flags near-duplicates but never merges them automatically.
- `checkpoint.py` parks records that fail validation in `04_search/rejected_records.jsonl` instead of losing them. Fix the record and write it again; the parked copy clears automatically.
- `due_diligence.py --no-examples` produces the aggregate-only version that is safe to share publicly.
