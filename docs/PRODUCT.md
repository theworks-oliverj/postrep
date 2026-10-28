# From protocol to product

*Companion to the Virgil Protocol (`START_HERE.md`). Not needed to run the protocol.*

*Half a joke, half a spec.* This file is the engine and the seats. Bolt it to a chassis and you have an AI start-up:

| Protocol piece | Product piece |
|---|---|
| Virgil persona + wizard rules (`protocol/preamble.md`) | System prompt + a chat UI with progress bar, buttons for multiple choice, commands as UI actions |
| Workspace + `run_state.json` (`protocol/engine/persistence.md`) | One database row per run + an object store per run; `run_state` is the state machine |
| `checkpoint.py` (checkpoint rules) | A write API with schema validation; agents call it as a tool |
| Waves + usage windows (partitioning) | A job queue with a rate-limit-aware scheduler (concurrency cap, retry from checkpoint) |
| One agent per country (`s4_search_waves`) | Parallel workers (e.g. a serverless function per country) running the brief with web search/fetch tools |
| Rubrics (S1, S2 rubrics) | Evals/gates: the UI won't unlock the search until both pass |
| Follow-up triggers + stop rules (`s7_triage`) | Deterministic rules engine over the JSON |
| Merge, verification, due diligence (`s8`, `s9`) | Batch jobs + an independent-verifier worker + a rendered report |
| Options Rundown + explorer (`s9_deliverables`) | The product's main screen |

**Things a real product must add:**
- Data freshness: re-check deadlines on a schedule.
- Clear "not advice" framing for eligibility and immigration claims.
- Privacy: life plans are sensitive. Encrypt them and make deletion easy.
- Cost controls per run.
- A human-review step before anything is sent to universities.
