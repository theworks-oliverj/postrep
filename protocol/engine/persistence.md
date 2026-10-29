# Engine: persistence and session partitioning

*Module `persistence`. Load in S0, and before any search wave (S4-S8).*

## Purpose

Real usage limits cut long runs short. This module ensures that no limit, crash or context reset loses more than one unit of work, and that heavy research is partitioned to fit the person's usage windows.

**Recommended harness:** an AI client that can read and write files on disk and run code, such as the Claude desktop app with Cowork or Claude Code, or any agent harness with a working folder. Chat-only use works (mode P), but it depends on the person saving files.

## Workspace

```
<run_dir>/
  run_state.json              ledger + continuation state vector
  00_orientation/   notes.md                         (S0 reflection)
  01_life_plan/     interview_notes.md  life_plan.md  life_plan.json  life_plan_score.json
  02_map/           interview_notes.md  pathway_map.md  study_pathway_map.json  map_score.json  benchmarks.json
  03_scope/         search_plan.json  AGENT_BRIEF.md
  04_search/        countries/<slug>.json  followups/<slug>_followup[_x].json  crosscuts/<slug>.json
                    overrides.json  orchestrator_notes.md  followup_plan.json
  05_merge/         merged.json  merge_report.json
  06_verify/        verification_sample.json  verification.json
  07_deliverables/  rundown_tables.md  options_rundown.md  due_diligence.md
  logs/             session_log.jsonl
```

## Runtime modes

| Mode | Has | "Save" means | Subagents |
|---|---|---|---|
| **L: local folder** (`local`, recommended) | Files on the person's disk, usually code | Write into `<run_dir>` | If available |
| **C: cloud workspace** (`cloud`) | Files and code in an ephemeral container | Write into `<run_dir>`, then **export at the end of every session** (send files, push to a repo, write to project docs or a drive) | Often |
| **P: project chat** (`project_chat`) | No filesystem | Emit the whole current file as a `FILE:` block for the person to save (format below) | Usually not; use sequential mode |
| **A: API / app** (`api`) | Host-defined | The app persists files and `run_state` | Host-defined |

**Mode P file format.** Emit after every 2-3 interview themes, after every 2-3 research records, and on `save`/`pause`:

````
FILE: 01_life_plan/interview_notes.md
```markdown
...entire current content (not a diff)...
```
````

## Checkpoint rules

| Rule | Protects | Behaviour |
|---|---|---|
| Skeleton first | Proof that work started; a place to resume from | Before any research, write a valid empty file with `status: in_progress` |
| Write per unit | Work in progress | After each interview block, screening list, record or ranked-out batch: read, modify, validate, then replace atomically (temp file + rename), keeping a `.bak` |
| Status honesty | Downstream triage | Use `complete` only when every step is done; `complete_with_gaps` with the gaps listed; `partial_budget_exhausted` when the agent's own budget ran out. Never mark `complete` on instruction while gaps remain |
| Heartbeat | Resume accuracy | After each write, update `run_state.checkpoints[file].updated_at` |
| Short working memory | Context limits | Keep notes in files, not in context |

With scripts available, `scripts/checkpoint.py` implements all of the above, including schema validation (`protocol/engine/scripts.md`). Without them:

```python
# Atomic, validated append of one record (stdlib only).
import json, os, tempfile, shutil
def append_record(path, key, record):
    with open(path) as f: data = json.load(f)
    data.setdefault(key, []).append(record)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))      # same dir => atomic rename
    with os.fdopen(fd, "w") as f: json.dump(data, f, ensure_ascii=False, indent=1); f.flush(); os.fsync(f.fileno())
    json.load(open(tmp))                                       # must parse before it replaces anything
    if os.path.exists(path): shutil.copy(path, path + ".bak")
    os.replace(tmp, path)
```

## Partitioning around usage limits

Usage windows differ by plan, model and time, so Virgil partitions by **work units** and **measures**. It never assumes a fixed session count.

**Units:** deep country = 1.5, standard country = 1, quick country = 0.5, cross-cut or follow-up = 0.75.

| Rule | Protects | Behaviour |
|---|---|---|
| Fresh-window launch | Agents being killed mid-file | Starts a wave only at the start of a usage window |
| Wave cap | Window overrun | Wave 1 is capped at **6 units** |
| Measure, then adapt | Fit to this person's plan | After each wave, records units completed per window in `run_state.agents_per_window_observed` and resizes the next wave to match |
| Explicit budgets | Silent agent exhaustion | Every agent brief states its search/fetch budget (defaults in `sessions/s3_scope_brief.md`) |
| Resume, don't redo | Wasted usage | After a reset, relaunches only files whose status is `in_progress` or `partial_*`, using prompt P2 |
| Light steps grouped | Session count | Interviews S0-S3 fit in short sittings. Merge, verification and deliverables take about one window each with scripts; without scripts, the merge gets its own window |

**Evidence behind these numbers (n = 1 reference run):** 12 parallel country agents launched at once, and 5 finished before the first limit. Search to merge took about 4 windows and about 25 agent runs. Everything unfinished resumed cleanly because each agent had written per record.

A worked example plan (12 countries) is in `protocol/engine/lessons.md`.

## `run_state.json` (ledger)

```json
{
  "protocol_version": "1.0.0", "run_id": "R-2027-01", "applicant_alias": "Applicant", "mode": "local",
  "current_phase": "search",
  "sessions": [{"n": 4, "started_at": "...", "ended_at": "...", "phase": "search", "wave": 1, "outcome": "4/4 complete", "limit_hit": false}],
  "checkpoints": [{"file": "04_search/countries/france.json", "status": "in_progress", "updated_at": "..."}],
  "assumptions": [], "overrides_of_protocol": [],
  "agents_per_window_observed": null,
  "next_action": "Launch wave 2 on a fresh window",
  "state_vector": { "...": "see protocol/state_vector.md" }
}
```
