#!/usr/bin/env python3
"""
init_workspace.py - create an empty, schema-valid run workspace.

PURPOSE
    Every protocol run lives in one folder (RUN_DIR). This script creates the folder layout
    of protocol/engine/persistence.md and an empty-but-valid skeleton of every JSON file, so
    that agents and the other scripts can rely on the files existing from minute one. It also
    writes the first continuation state vector (protocol/state_vector.md) into run_state.json.

INPUTS
    RUN_DIR            folder to create (may already exist; existing files are kept)
    --alias NAME       a pseudonym for the person. NEVER the real name: the alias is
                       printed in outputs and example reports.
    --mode MODE        local | cloud | project_chat | api   (where the agents will run)
    --run-id ID        optional; default "<alias-slug>-<YYYYMMDD>"
    --force            overwrite skeleton files that already exist (DANGEROUS: loses work)

OUTPUTS
    run_state.json (ledger + state_vector), 00_orientation/notes.md, 01_life_plan/*, 02_map/*,
    03_scope/*, 04_search/{countries,followups,crosscuts}/, 04_search/overrides.json,
    04_search/orchestrator_notes.md, 05_merge/, 06_verify/, 07_deliverables/, logs/session_log.jsonl

    The human-readable documents are COPIED from the protocol's own templates (the single
    source of truth, protocol/templates/), never written by this script:
        life_plan.md        -> 01_life_plan/life_plan.md
        pathway_map.md      -> 02_map/pathway_map.md
        AGENT_BRIEF.md      -> 03_scope/AGENT_BRIEF.md
        options_rundown.md  -> 07_deliverables/options_rundown_template.md
        due_diligence.md    -> 07_deliverables/due_diligence_template.md
    The three notes files (00_orientation/notes.md, 01_life_plan/interview_notes.md,
    02_map/interview_notes.md) are created with a header only: they are append-only save
    targets written DURING the sittings, before the finished documents exist.
    If protocol/templates/ cannot be found (script copied elsewhere) a short placeholder is
    written instead and a warning is printed.

USAGE
    python3 scripts/init_workspace.py RUN_DIR --alias "Applicant A" --mode local

EXIT CODES
    0 ok | 1 a generated skeleton failed schema validation (a bug - please report) |
    2 bad arguments / folder not writable
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (AXES, EXIT_OK, EXIT_PROBLEMS, EXIT_USAGE, LAYOUT_DIRS, PROTOCOL_VERSION, REPO_ROOT, RUBRIC_VERSION,  # noqa: E402
                     UsageError, append_jsonl, atomic_write_json, atomic_write_text, now_iso, rp,
                     slugify, today_iso, validate)

TEMPLATES_DIR = REPO_ROOT / "protocol" / "templates"

# Gate / soft criteria and weights. rubric.py holds the authoritative copy for scoring;
# these tables only create the empty score sheets (every gate starts as 'fail', every score 0,
# so an unfilled sheet can never pass).
LP_GATES = ["LP-G1", "LP-G2", "LP-G3", "LP-G4", "LP-G5", "LP-G6", "LP-G7"]
LP_SOFT = {"LP-S1": 1, "LP-S2": 2, "LP-S3": 2, "LP-S4": 2, "LP-S5": 1, "LP-S6": 1, "LP-S7": 2, "LP-S8": 1, "LP-S9": 1, "LP-S10": 1}
PM_GATES = ["PM-G1", "PM-G2", "PM-G3", "PM-G4", "PM-G5"]
PM_SOFT = {"PM-S1": 1, "PM-S2": 2, "PM-S3": 1, "PM-S4": 1, "PM-S5": 1, "PM-S6": 1}

# skeleton key -> (template file in protocol/templates, destination relative to RUN_DIR)
TEMPLATE_COPIES = {
    "life_plan_md": ("life_plan.md", "01_life_plan/life_plan.md"),
    "pathway_map_md": ("pathway_map.md", "02_map/pathway_map.md"),
    "agent_brief": ("AGENT_BRIEF.md", "03_scope/AGENT_BRIEF.md"),
    "options_rundown_template": ("options_rundown.md", "07_deliverables/options_rundown_template.md"),
    "due_diligence_template": ("due_diligence.md", "07_deliverables/due_diligence_template.md"),
}

# Header-only notes files: key -> (relative path, text)
NOTES = {
    "orientation_notes": ("00_orientation/notes.md",
                          "# Orientation notes (S0)\n\n> The person's own reflection, saved verbatim (any language). Virgil reads it before S1 and marks\n"
                          "> which S1/S2 fields it already answers, so they are not asked again.\n"),
    "interview_notes": ("01_life_plan/interview_notes.md",
                        "# Life & Career Plan: interview notes (append-only)\n\n> One section per finished theme; never edit earlier sections. life_plan.md is written from these notes.\n"),
    "map_interview_notes": ("02_map/interview_notes.md",
                            "# Study & Pathway Map: interview notes (append-only)\n\n> One section per finished theme; never edit earlier sections. pathway_map.md is written from these notes.\n"),
    "orchestrator_notes": ("04_search/orchestrator_notes.md",
                           "# Orchestrator notes\n\nAppend dated decisions here (follow-ups chosen, stop-rule decisions, surprises).\n"
                           "Value changes to records belong in overrides.json, NOT here.\n"),
}

DEFAULT_OVERLAY_POLICY = "overlay only: never raise the base funding score; show effect and obligations next to it"


def score_sheet(rubric: str, gates: list[str], soft: dict[str, int]) -> dict:
    return {
        "rubric": rubric, "rubric_version": RUBRIC_VERSION,
        "gates": [{"id": g, "status": "fail", "note": "not yet scored"} for g in gates],
        "soft": [{"id": k, "weight": w, "score": 0, "note": "not yet scored"} for k, w in soft.items()],
        "soft_pct": 0, "passed": False, "scored_at": now_iso(),
    }


def template_text(name: str) -> str | None:
    """Text of protocol/templates/<name>, or None if the folder is not there."""
    try:
        return (TEMPLATES_DIR / name).read_text(encoding="utf-8")
    except OSError:
        return None


def initial_state_vector(run_id: str) -> dict:
    """The vector a brand-new run starts with: session 0, phase init, S0 is next.

    WHY here: the protocol says a fresh session must be able to continue from the vector alone
    (protocol/state_vector.md), so even an untouched workspace has to carry a valid one."""
    return {
        "run": run_id, "session": 0, "date": today_iso(), "phase": "init",
        "session_objective": "Orientation (S0): explain the journey, agree privacy and setup, collect the person's own notes.",
        "context": [], "unknowns": [], "ambiguities": [], "assumptions": [],
        "completed": ["Workspace created"],
        "active": {"user": [], "virgil": []},
        "next": {"user": ["Write down your life plan and study interests in your own words (20-40 minutes)"],
                 "virgil": ["Read 00_orientation/notes.md, then start Session 1 (Life & Career Plan)"]},
        "blockers": [], "artifacts": ["run_state.json"],
    }


def build_skeletons(run_id: str, alias: str, mode: str) -> dict[str, object]:
    """Return {key: content} for every JSON/MD file. Markdown documents come from protocol/templates/."""
    anchor = {"0": "", "1": "", "2": "", "3": ""}
    bench = [{"axis": a, "institution": "", "programme": "", "baseline_vector": {ax: "?" for ax in AXES},
              "evidence_urls": [], "status": "provisional"} for a in AXES]
    sk: dict[str, object] = {
        "run_state": {
            "protocol_version": PROTOCOL_VERSION, "run_id": run_id, "applicant_alias": alias, "mode": mode,
            "created_at": now_iso(), "current_phase": "init", "sessions": [], "checkpoints": [],
            "assumptions": [], "overrides_of_protocol": [],
            "next_action": "Session 0: walk the person through the journey, then collect their own notes (00_orientation/notes.md).",
            "agents_per_window_observed": None, "state_vector": initial_state_vector(run_id)},
        "life_plan": {"schema_version": "1.0", "applicant_alias": alias, "updated_at": now_iso()},
        "life_plan_score": score_sheet("life_plan", LP_GATES, LP_SOFT),
        "study_pathway_map": {
            "schema_version": "1.0", "generated": today_iso(),
            "objective": {"one_line": "", "nearest_frameworks": [], "commitments": [], "non_goals": []},
            "domains": [], "pathway_signals": {"people_topic_signals": [], "organisation_type_signals": [], "known_people_or_orgs": []},
            "false_positive_traps": [],
            "scoring_anchors": {ax: dict(anchor) for ax in AXES},
            "screening_rule": {"description": "", "unsure_policy": "pass"},
            "benchmarks_ref": "02_map/benchmarks.json"},
        "map_score": score_sheet("pathway_map", PM_GATES, PM_SOFT),
        "benchmarks": {"benchmarks": bench},
        "search_plan": {
            "schema_version": "1.0", "rubric_version": RUBRIC_VERSION, "created": today_iso(),
            "countries": [], "crosscuts": [], "benchmarks_ref": "02_map/benchmarks.json",
            # Currency is left empty on purpose: it is a decision of S3 (copied from LP-G3), not a default.
            "funded_definition": {"type": "tuition_only", "max_total_tuition": None, "max_out_of_pocket": None,
                                  "living_support_required_monthly": None, "household_size": None, "currency": ""},
            "overlay_policy": DEFAULT_OVERLAY_POLICY,
            "eligibility_facts_ref": "01_life_plan/life_plan.json#eligibility_facts",
            "exclusions": [], "session_plan": {"waves": [], "agents_per_window_estimate": None}},
        "overrides": [],
    }
    for key, (_path, text) in NOTES.items():
        sk[key] = text
    for key, (tname, _dest) in TEMPLATE_COPIES.items():
        text = template_text(tname)
        if text is None:
            print(f"warning: protocol/templates/{tname} not found; wrote a placeholder for {key}", file=sys.stderr)
            text = f"# {tname} (template missing)\n\nCopy protocol/templates/{tname} from the virgil-protocol repo here.\n"
        sk[key] = text
    return sk


# Which schema validates which skeleton key (markdown files and overrides handled separately).
SCHEMA_OF = {"run_state": "run_state", "life_plan": "life_plan", "life_plan_score": "rubric_score",
             "study_pathway_map": "study_pathway_map", "map_score": "rubric_score", "benchmarks": "benchmarks",
             "search_plan": "search_plan", "overrides": "override"}
# Where a skeleton key is written when it is not a plain PATHS key.
EXTRA_DEST = {**{k: dest for k, (_t, dest) in TEMPLATE_COPIES.items()}, **{k: p for k, (p, _t) in NOTES.items()}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Create a virgil-protocol run workspace with valid empty files.")
    ap.add_argument("run_dir")
    ap.add_argument("--alias", required=True, help="pseudonym for the person (never the real name)")
    ap.add_argument("--mode", required=True, choices=["local", "cloud", "project_chat", "api"])
    ap.add_argument("--run-id")
    ap.add_argument("--force", action="store_true", help="overwrite existing skeleton files")
    a = ap.parse_args(argv)

    run_dir = Path(a.run_dir)
    run_id = a.run_id or f"{slugify(a.alias) or 'run'}-{today_iso().replace('-', '')}"
    try:
        for d in LAYOUT_DIRS:
            (run_dir / d).mkdir(parents=True, exist_ok=True)
        skeletons = build_skeletons(run_id, a.alias, a.mode)
        problems = 0
        for key, content in skeletons.items():
            path = run_dir / EXTRA_DEST[key] if key in EXTRA_DEST else rp(run_dir, key)
            if path.exists() and not a.force:
                print(f"keep   {path.relative_to(run_dir)} (exists)")
                continue
            if key in SCHEMA_OF:
                errs = validate(content, SCHEMA_OF[key])
                if errs:  # would be a bug in this script, never in user data
                    problems += 1
                    print(f"BUG: skeleton {key} invalid: {errs[0]}", file=sys.stderr)
                    continue
                atomic_write_json(path, content, keep_backup=False)
            else:
                atomic_write_text(path, content, keep_backup=False)
            print(f"create {path.relative_to(run_dir)}")
        log = rp(run_dir, "session_log")
        if not log.exists():
            append_jsonl(log, {"ts": now_iso(), "session": None, "event": "note", "phase": "init",
                               "detail": f"workspace created (run_id={run_id}, mode={a.mode})"})
            print(f"create {log.relative_to(run_dir)}")
        return EXIT_PROBLEMS if problems else EXIT_OK
    except (UsageError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
