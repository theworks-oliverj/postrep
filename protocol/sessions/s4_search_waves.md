# Sessions 4-6: Search waves

*Module `s4_search_waves`. Load in phase `search`, together with `engine/persistence.md`. Reads `03_scope/`. Writes `04_search/countries/`.*

## Purpose

Run one research agent per country, in waves sized to the person's usage windows. The result is a complete, evidence-backed country file for every in-scope country, with no work lost to limits.

## Orchestrator behaviour (Virgil)

| Moment | Behaviour |
|---|---|
| Before a wave | Confirm the window is fresh and get "go" (R8). Create a skeleton file per country and log the checkpoints |
| Launch | One background agent per country, with: the brief path, the slug, `cap_n`, the budget, the output path, and the run directory. Use a mid-tier model at high effort for country agents; keep the strongest model for orchestration |
| During | Keep `04_search/orchestrator_notes.md` as replies arrive: deadlines, material corrections, follow-up ideas. These notes are the only memory shared between agents. Tell the person at once about anything due within 30 days |
| After | Read each file's `status`. A file still `in_progress` after its agent stopped was interrupted: relaunch it with prompt P2. Record `agents_per_window_observed` and resize the next wave |
| Limit mid-wave | Nothing clever. After the reset, read `run_state.json` and the files, and relaunch only the unfinished work |

## Deadline horizons (used throughout the protocol)

- **30 days:** tell the person now.
- **60 days:** re-verify on the official page now.
- **90 days:** list in the deliverables.

## Sequential mode (no subagents)

Run one country per sitting. Load the preamble, `engine/persistence.md`, the brief and `run_state.json`, then say "Virgil: run country <slug>". In mode P, emit the country file as a `FILE:` block after screening and after every 2-3 records. Do a short orchestrator sitting afterwards to update the notes and the state vector.

## Exit

Every country in the wave plan is `complete`, `complete_with_gaps` or `partial_budget_exhausted`. Update the state vector with `phase: search → followups`.
