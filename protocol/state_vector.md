# Continuation state vector

*Module `state_vector`. Load every session. Agents read and write the vector; the person reads only the "Where we are" brief.*

## Purpose

The state vector is the compact, authoritative record of **where a run stands**. (Not to be confused with a programme's scoring vector, `candidate.state_vector` = {funding, programme, pathway}. This module always means `run_state.state_vector`.) It lives in `run_state.json → state_vector` and is rewritten at the end of every session (the command **update state vector**), and whenever a limit looks close. A fresh session, possibly a different model or a different person's chat, must be able to continue from the vector, the run's Preamble and the workspace files alone. The previous conversation is not needed.

## Fields

The JSON keys are lowercase versions of the template names: CONTEXT = `context`, UNKNOWNS = `unknowns`, AMBIGUITIES = `ambiguities`, ASSUMPTIONS = `assumptions`, PHASE = `phase`, SESSION_OBJECTIVE = `session_objective`, COMPLETED = `completed`, ACTIVE = `active`, NEXT = `next`, BLOCKERS = `blockers`, ARTIFACTS = `artifacts`.

Each field: what it tracks → how Virgil treats it.

| Field | Tracks | Virgil's behaviour |
|---|---|---|
| `run`, `session`, `date` | Identity and sequence | Increments `session` once per sitting |
| `phase` | Stage of the run (`init, life_plan, map, scope, search, followups, merge, verify, deliverables, done`) | Writes transitions as `A → B` in the session they happen |
| `session_objective` | What this sitting set out to do | Sets it at session start; judges completion against it at close |
| `context` | Session-determined decisions that shape later work (e.g. "funded = tuition-only", "wave 1 = 4 deep countries") | Never restates the Preamble. Keeps only decisions not recorded elsewhere |
| `unknowns` | Missing data, unverified facts, measurement gaps | Routes each one either to `active`/`next` or to `assumptions`. An item that stays here across two sessions is a failure, so Virgil raises it with the person |
| `ambiguities` | Inputs from the person that need clarifying | Treats them as blocking: Virgil resolves them first in the next session, before other work |
| `assumptions` | Positions taken despite unknowns, each with its basis | Keeps the basis explicit so a later answer can overturn the assumption cleanly |
| `completed` | Results, decisions and milestones | Appends facts, not effort ("FR file complete: 11 records") |
| `active.user` / `active.virgil` | Work in progress, split by owner | Lists substantive actions only, never protocol mechanics |
| `next.user` / `next.virgil` | The next concrete actions, split by owner | Makes `next.virgil[0]` the first thing the next session does |
| `blockers` | Dependencies, each tagged `USER`, `VIRGIL` or `EXTERNAL` | Names an owner for every blocker |
| `artifacts` | Files and links produced | Uses paths relative to the run directory |

**Target size:** about 200-400 tokens. If the vector grows past that, move detail into files and reference them in `artifacts`.

```json
"state_vector": {
  "run": "R-2027-01", "session": 5, "date": "2027-01-14",
  "phase": "search → followups",
  "session_objective": "Finish wave 2 and triage waves 1-2",
  "context": ["funded = tuition_only, max out-of-pocket <amount>", "wave plan: 3 waves, 5 units each"],
  "unknowns": ["Graduation-year rule for scheme X (routed: next.virgil)"],
  "ambiguities": [],
  "assumptions": [{"text": "Partner does not need work rights in year 1", "basis": "S1 answer, 'decide for me'"}],
  "completed": ["Wave 2 done: 5/5 files complete", "followup_plan.json written: 6 triggers"],
  "active": {"user": ["Booking language test"], "virgil": []},
  "next": {"user": ["Confirm whether a thesis-only research master's is acceptable"], "virgil": ["Launch follow-ups FR, SE, CH on a fresh window"]},
  "blockers": [{"item": "Official fee page blocked by robots", "owner": "EXTERNAL"}],
  "artifacts": ["04_search/followup_plan.json", "04_search/orchestrator_notes.md"]
}
```

## The "Where we are" brief (what the person sees)

This is generated from the vector at the start and end of each session, and on `where are we`. It is written for a busy human returning after days away: 6 lines, and no field names.

<!-- template: protocol/templates/where_we_are.md -->
```
VIRGIL | Run R-2027-01 | Session 5 | Phase: search → follow-ups | Gates: Life Plan ✓ · Map ✓
Done since last time: wave 2 finished (5 countries, 41 programmes on file); 6 gaps flagged for follow-up.
Your move: tell me whether a thesis-only research master's is acceptable (it changes 4 options).
My next step: follow-ups for France, Sweden and Switzerland (about 1 usage window).
Waiting on: an official fee page that blocks automated access (I'll ask you to check it by hand).
Saved: 04_search/followup_plan.json
```

## Lifecycle

| Moment | Virgil's action |
|---|---|
| Session start | Read the vector. Resolve `ambiguities`. Set `session_objective`. Print the brief |
| During work | Update `completed` and `artifacts` as files are written (R1) |
| Limit looks close | Write the vector immediately, then continue |
| Session end (**update state vector**) | Rewrite every field. Route every unknown. Print the brief and the resume prompt (`protocol/prompts/agent_prompts.md`, P1) |

With scripts, write the vector with `python3 scripts/checkpoint.py RUN_DIR update-vector --file vector.json`, which validates it before replacing, and print the brief with `python3 scripts/status.py RUN_DIR --brief`.

**Single questions don't need the vector.** A quick question that changes nothing (e.g. "what's a research master's?") doesn't trigger an update.
