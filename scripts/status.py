#!/usr/bin/env python3
"""
status.py - "Where we are": the human brief, then a summary of the run ledger.

PURPOSE
    Any agent or person resuming a run in a fresh session starts here: which phase are we
    in, did both gates pass, what is done, what is the person's move, what is Virgil's next
    step, what are we waiting on, and which files are finished or pending. It implements the
    `where are we` command (protocol/preamble.md) with the template
    protocol/templates/where_we_are.md.

INPUTS   RUN_DIR/run_state.json (the ledger AND the continuation state vector) and the two gate
         score files (01_life_plan/life_plan_score.json, 02_map/map_score.json); optionally
         03_scope/search_plan.json to list countries not yet started.

OUTPUT   Default: the six-line brief, a blank line, the checkpoint table and counters.
         --brief: the six lines only (this is what Virgil prints at session start and end):

           VIRGIL | Run <run_id> | Session <n> | Phase: <phase> | Gates: Life Plan <✓|pending|✗> · Map <✓|pending|✗>
           Done since last time: <last two entries of state_vector.completed>
           Your move: <next.user[0]>
           My next step: <next.virgil[0]>
           Waiting on: <blockers, each with owner; or "nothing">
           Saved: <latest artifact>

         Gate words come from the two score files: ✓ = passed; ✗ = rubric.py evaluated it and it
         did not pass; pending = never evaluated.
         --json: the same facts as JSON (the brief is under "brief").

DEFINITIONS
    done     checkpoint status complete | complete_with_gaps | validated
    pending  in_progress | partial_budget_exhausted | pending | error  (needs work or a follow-up)
    not started  a country/cross-cut in search_plan.json with no checkpoint yet

USAGE
    python3 scripts/status.py RUN_DIR [--brief] [--json]

EXIT CODES
    0 ok | 2 run_state.json missing or invalid
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import EXIT_OK, EXIT_USAGE, GATES, UsageError, gate_state, load_json, rp, validate  # noqa: E402

DONE = {"complete", "complete_with_gaps", "validated"}
GATE_SYMBOL = {"pass": "✓", "pending": "pending", "fail": "✗"}


def sentence(items: list[str]) -> str:
    """Join list items into one line that ends with a full stop (the template's style)."""
    text = "; ".join(i.strip().rstrip(".") for i in items if i and i.strip())
    return (text + ".") if text else ""


def brief_lines(st: dict, gates: dict[str, str], saved: str) -> list[str]:
    """The six-line 'Where we are' brief, exactly in the format of protocol/templates/where_we_are.md.

    WHY computed here and not typed by Virgil: the person reads this after days away, so every
    field must come from the saved vector and score files, never from a model's memory."""
    sv = st["state_vector"]
    done = sentence(sv["completed"][-2:]) or "nothing yet."
    user = sv["next"]["user"][0] if sv["next"]["user"] else "nothing needed from you right now"
    virgil = sv["next"]["virgil"][0] if sv["next"]["virgil"] else "nothing queued"
    waiting = "; ".join(f"{b['item']} ({b['owner']})" for b in sv["blockers"]) or "nothing"
    saved_path = sv["artifacts"][-1] if sv["artifacts"] else saved
    g = " · ".join(f"{GATES[r][1]} {GATE_SYMBOL[gates[r]]}" for r in GATES)
    return [f"VIRGIL | Run {sv['run']} | Session {sv['session']} | Phase: {sv['phase']} | Gates: {g}",
            f"Done since last time: {done}",
            f"Your move: {user}",
            f"My next step: {virgil}",
            f"Waiting on: {waiting}",
            f"Saved: {saved_path}"]


def summarise(run_dir: Path) -> dict:
    p = rp(run_dir, "run_state")
    if not p.exists():
        raise UsageError(f"{p} not found - is this a run directory? (init_workspace.py creates one)")
    st = load_json(p)
    errs = validate(st, "run_state")
    if errs:
        raise UsageError(f"run_state.json invalid: {errs[0].path}: {errs[0].message}")
    done = [c for c in st["checkpoints"] if c["status"] in DONE]
    pending = [c for c in st["checkpoints"] if c["status"] not in DONE]
    started = {Path(c["file"]).stem.split("_followup")[0] for c in st["checkpoints"]}
    not_started: list[str] = []
    sp = rp(run_dir, "search_plan")
    if sp.exists():
        plan = load_json(sp)
        not_started = [c["slug"] for c in plan.get("countries", []) if c["slug"] not in started] + \
                      [c["slug"] for c in plan.get("crosscuts", []) if c["slug"] not in started]
    sessions = st["sessions"]
    open_n = next((s["n"] for s in sessions if not s.get("ended_at")), None)
    session_n = open_n if open_n is not None else (sessions[-1]["n"] if sessions else 0)
    gates = {r: gate_state(run_dir, r) for r in GATES}
    hb = st.get("heartbeat") or {}
    last_cp = max(st["checkpoints"], key=lambda c: c["updated_at"], default=None)
    saved = last_cp["file"] if last_cp else (hb.get("file") or "-")
    brief = brief_lines(st, gates, saved)
    return {"brief": brief, "gates": gates, "saved": saved, "session": session_n, "checkpoints": st["checkpoints"],
            "assumptions": st.get("assumptions", []), "overrides_of_protocol": st.get("overrides_of_protocol", []),
            "run_id": st["run_id"], "state_vector": st["state_vector"], "applicant_alias": st["applicant_alias"], "mode": st["mode"], "phase": st["current_phase"],
            "done": [c["file"] for c in done], "pending": [{"file": c["file"], "status": c["status"]} for c in pending],
            "not_started": not_started, "next_action": st["next_action"], "sessions_used": len(sessions),
            "limit_hits": sum(1 for s in sessions if s["limit_hit"]), "open_session": next((s["n"] for s in sessions if not s.get("ended_at")), None),
            "agents_per_window_observed": st["agents_per_window_observed"], "heartbeat": st.get("heartbeat")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Summarise run_state.json.")
    ap.add_argument("run_dir")
    ap.add_argument("--brief", action="store_true", help="print only the six-line 'Where we are' brief")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        s = summarise(Path(a.run_dir))
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    if a.json:
        print(json.dumps(s, indent=2))
        return EXIT_OK
    print("\n".join(s["brief"]))
    if a.brief:
        return EXIT_OK
    print()
    cps = s["checkpoints"]
    if cps:
        w = max(len(c["file"]) for c in cps)
        print(f"{'File'.ljust(w)}  {'Status'.ljust(24)}  {'Records':>7}  Updated")
        for c in sorted(cps, key=lambda c: c["file"]):
            print(f"{c['file'].ljust(w)}  {c['status'].ljust(24)}  {str(c.get('records', '-')):>7}  {c['updated_at']}")
    else:
        print("(no checkpoints yet)")
    print()
    print(f"Not started ({len(s['not_started'])}): " + (", ".join(s["not_started"]) or "-"))
    print(f"Sessions used: {s['sessions_used']}  | limit hits: {s['limit_hits']}  | open session: {s['open_session'] or 'none'}"
          f"  | agents per window observed: {s['agents_per_window_observed'] if s['agents_per_window_observed'] is not None else 'n/a'}")
    if s["assumptions"]:
        print(f"Assumptions to revisit: {sum(1 for a in s['assumptions'] if a.get('revisit'))} of {len(s['assumptions'])}")
    if s["overrides_of_protocol"]:
        print(f"Protocol overrides recorded: {len(s['overrides_of_protocol'])} (see run_state.json)")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
