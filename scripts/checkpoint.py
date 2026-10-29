#!/usr/bin/env python3
"""
checkpoint.py - the ONLY way agents write search results into a run workspace.

PURPOSE
    Agents are cut off by usage limits at unpredictable moments. If an agent keeps its
    findings in memory and writes one big file at the end, a cut loses everything.
    So agents call this script after EVERY record (a screening row, a candidate, a
    ranked-out entry). Each call:
      1. validates the record against its JSON schema (nothing invalid reaches disk;
         rejected records are parked in 04_search/rejected_records.jsonl, not lost),
      2. upserts it into the target file (same key => replaced, so retrying is safe),
      3. validates the whole file again,
      4. writes atomically (temp file + fsync + os.replace) and keeps <file>.bak,
      5. updates run_state.json (checkpoint list + heartbeat) under a lock so parallel
         agents do not overwrite each other.
    A usage-limit cut therefore loses at most the one record being written.

TARGET (choose one)
    --country SLUG                     04_search/countries/SLUG.json
    --country SLUG --followup [X]      04_search/followups/SLUG_followup[_X].json
    --crosscut SLUG                    04_search/crosscuts/SLUG.json

SUBCOMMANDS   (RECORD = --json '{...}' | --file PATH | '-' for stdin | piped stdin)
    init-country   create the target file (status in_progress). --name "Display name"
                   [--agent-model M] [--resume: succeed quietly if the file already exists]
                   For --crosscut, --kind programme_scan|funding_route is REQUIRED (no default:
                   the two kinds are different files) [--route-type T for funding_route].
                   GATE ("no gate, no search", rule R3): refuses unless 01_life_plan/life_plan_score.json
                   AND 02_map/map_score.json both have passed=true (run rubric.py first). --force
                   [--reason T] proceeds anyway and appends the deviation to
                   run_state.overrides_of_protocol.
    add-screening  RECORD = screening_entry   (upsert by institution)
    add-candidate  RECORD = candidate_record  (upsert by id; sources must carry
                   source_type + accessed_date)
    add-ranked-out RECORD = ranked_out_entry  (upsert by institution+programme)
    add-finding    RECORD = one finding of a funding_route cross-cut (upsert by question);
                   incremental writes, so a cut-off verification loses at most one finding
    put-crosscut   RECORD = whole funding_route_crosscut or crosscut_scan file (replace; a
                   funding_route file without `status` is stored as status 'complete')
    set-status     --status S | --path-b-done true|false | --budget-notes T |
                   --country-summary T | --add-gap T (repeatable) | --add-correction RECORD |
                   --add-path-b-person RECORD | --add-urgent-deadline RECORD |
                   --country-context RECORD (merged into country_context; inline JSON or a file path) |
                   --limit-event KIND:DETAIL (repeatable) | --tool-calls N | --note T
                   Works for countries, follow-ups and cross-cuts (--crosscut SLUG). A
                   funding_route cross-cut accepts only --status, --budget-notes and --note.
                   Status 'complete' is refused for a first-pass country while
                   path_b_done is false or any screening row is 'unscreened'
                   (use complete_with_gaps; --force to override).
    clear-rejected [--id ID]  remove parked records from 04_search/rejected_records.jsonl: those
                   whose record id is ID, or all of them. Rejected records are also cleared
                   automatically when a record with the same key (id; institution for screening)
                   is later written successfully to the same file.
    log-session    --start | --end | --event EVENT ; plus --phase P --set-phase P
                   --detail T --country SLUG --agent A --agents-run N --outcome T --wave N
                   --limit-hit --next-action T      (updates run_state + logs/session_log.jsonl;
                   --start also sets state_vector.session and state_vector.date)
    update-vector  RECORD = a whole continuation state vector (protocol/state_vector.md). Validated
                   against schemas/continuation_state_vector.schema.json (and vector.run must equal
                   run_state.run_id), then REPLACES run_state.state_vector. Touches nothing else
                   (no heartbeat, no checkpoint). On a validation error nothing is written.
    add-assumption --id ID --text T [--made-in WHERE] [--revisit]   (run_state.assumptions, upsert by id)
    add-protocol-override --rule R --override O --reason T          (run_state.overrides_of_protocol)

EXAMPLES   (RUN is the run folder; every line is paste-ready)
    python3 scripts/checkpoint.py RUN init-country --country ardenia --name Ardenia --agent-model sonnet
    python3 scripts/checkpoint.py RUN add-candidate --country ardenia --file /tmp/rec.json
    echo '{...}' | python3 scripts/checkpoint.py RUN add-screening --country ardenia
    python3 scripts/checkpoint.py RUN set-status --country ardenia --path-b-done true --status complete
    python3 scripts/checkpoint.py RUN init-country --crosscut home_scheme --kind funding_route --name "Home scheme"
    python3 scripts/checkpoint.py RUN add-finding --crosscut home_scheme --file finding.json
    python3 scripts/checkpoint.py RUN set-status --crosscut home_scheme --status complete
    python3 scripts/checkpoint.py RUN clear-rejected --id IT26-03
    python3 scripts/checkpoint.py RUN log-session --start --phase search --wave 1
    python3 scripts/checkpoint.py RUN update-vector --file vector.json
    python3 scripts/checkpoint.py RUN add-assumption --id A2 --text "Partner works remotely" --revisit
    python3 scripts/checkpoint.py RUN add-protocol-override --rule "no gate, no search" --override "..." --reason "..."

EXIT CODES
    0 written | 1 record/file failed validation (nothing written; see stderr and
    04_search/rejected_records.jsonl) | 2 usage error (missing file, bad JSON, lock timeout)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (EXIT_OK, EXIT_PROBLEMS, EXIT_USAGE, GATES, PHASES, UsageError, VError,  # noqa: E402
                     append_jsonl, atomic_write_json, atomic_write_text, file_lock, gate_state, load_json, norm_text,
                     now_iso, read_json_arg, rp, today_iso, validate, write_time_problems)


# --------------------------------------------------------------------------- helpers

class Rejected(Exception):
    """A record or file failed validation. Carries the error list for reporting."""

    def __init__(self, errors: list[VError], park: bool = True):
        super().__init__("validation failed")
        self.errors = errors
        self.park = park          # False for whole-document commands (update-vector): there is no record to park


def resolve_target(run_dir: Path, a) -> tuple[Path, str]:
    """Map --country/--followup/--crosscut to (file path, kind)."""
    if a.crosscut:
        return rp(run_dir, "crosscuts_dir") / f"{a.crosscut}.json", "crosscut"
    if not a.country:
        raise UsageError("give --country SLUG (optionally with --followup [X]) or --crosscut SLUG")
    if a.followup is not None:
        suffix = f"_{a.followup}" if a.followup else ""
        return rp(run_dir, "followups_dir") / f"{a.country}_followup{suffix}.json", "followup"
    return rp(run_dir, "countries_dir") / f"{a.country}.json", "country"


def schema_for_file(doc: dict, kind: str) -> str:
    if kind == "crosscut":
        return "funding_route_crosscut" if doc.get("crosscut_kind") == "funding_route" else "crosscut_scan_file"
    return "country_run_file"


def check(errors: list[VError]) -> None:
    if errors:
        raise Rejected(errors)


def relpath(run_dir: Path, p: Path) -> str:
    return p.relative_to(run_dir).as_posix()


def update_run_state(run_dir: Path, mutate) -> dict | None:
    """Read-modify-write run_state.json under a lock. Returns the new state (or None if absent)."""
    path = rp(run_dir, "run_state")
    if not path.exists():
        print("warning: run_state.json missing - checkpoint not recorded (run init_workspace.py)", file=sys.stderr)
        return None
    with file_lock(path):
        state = load_json(path)
        mutate(state)
        errs = validate(state, "run_state")
        if errs:
            raise UsageError(f"run_state.json would become invalid: {errs[0].path}: {errs[0].message}")
        atomic_write_json(path, state)
    return state


def current_session(state: dict | None) -> int | None:
    if not state or not state.get("sessions"):
        return None
    open_ones = [s for s in state["sessions"] if not s.get("ended_at")]
    return (open_ones[-1] if open_ones else state["sessions"][-1])["n"]


def record_checkpoint(run_dir: Path, path: Path, doc: dict) -> None:
    rel = relpath(run_dir, path)
    status = doc.get("status", "in_progress")

    def mutate(state):
        now = now_iso()
        entry = next((c for c in state["checkpoints"] if c["file"] == rel), None)
        if entry is None:
            entry = {"file": rel}
            state["checkpoints"].append(entry)
        entry.update(status=status, updated_at=now)
        if "candidates" in doc:
            entry["records"] = len(doc["candidates"])
        state["heartbeat"] = {"at": now, "file": rel}
    update_run_state(run_dir, mutate)


def json_or_path(raw: str):
    """A JSON object given inline ('{...}'), a path to a JSON file (what protocol/templates/AGENT_BRIEF.md
    passes: `--country-context ctx.json`), or '-' for stdin. WHY: agents follow the brief literally."""
    if raw.strip().startswith(("{", "[")):
        return read_json_arg(raw, None)
    return read_json_arg(None, raw)


def upsert(items: list, rec: dict, key) -> str:
    k = key(rec)
    for i, old in enumerate(items):
        if key(old) == k:
            items[i] = rec
            return "replaced"
    items.append(rec)
    return "added"


def write_doc(run_dir: Path, path: Path, kind: str, doc: dict) -> None:
    check(validate(doc, schema_for_file(doc, kind)))
    atomic_write_json(path, doc)  # keeps path.bak of the previous version
    record_checkpoint(run_dir, path, doc)


def reject(run_dir: Path, path: Path, cmd: str, record, errors: list[VError]) -> None:
    """Park an invalid record so the orchestrator can repair it instead of losing it."""
    rej = rp(run_dir, "rejected")
    with file_lock(rej):                                   # clear_rejected() rewrites the file, so appends are locked too
        append_jsonl(rej, {
            "ts": now_iso(), "file": relpath(run_dir, path) if path else None, "command": cmd, "record": record,
            "errors": [{"path": e.path, "kind": e.kind, "message": e.message} for e in errors[:30]]})


def clear_rejected(run_dir: Path, match) -> int:
    """Remove parked entries for which match(entry) is true. Returns how many were removed."""
    rej = rp(run_dir, "rejected")
    if not rej.exists():
        return 0
    with file_lock(rej):
        keep, removed = [], 0
        for line in rej.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                keep.append(line)                          # never destroy a line we cannot read
                continue
            if match(entry):
                removed += 1
            else:
                keep.append(line)
        if removed:
            atomic_write_text(rej, "".join(k + "\n" for k in keep), keep_backup=False)
    return removed


# --------------------------------------------------------------------------- commands

def check_gates(run_dir: Path, a, target_rel: str) -> None:
    """'No gate, no search': refuse unless both score sheets passed. --force records the deviation."""
    state = {k: gate_state(run_dir, k) for k in GATES}
    if all(v == "pass" for v in state.values()):
        return
    pending = ", ".join(f"{k}={v}" for k, v in state.items() if v != "pass")
    if not a.force:
        raise UsageError(f"refusing to start {target_rel}: gate(s) not passed ({pending}). Score them with "
                         "`rubric.py RUN life_plan|pathway_map`, or use --force [--reason T] (recorded in run_state.overrides_of_protocol)")

    def mutate(st):
        st.setdefault("overrides_of_protocol", []).append({
            "date": today_iso(), "rule": "no gate, no search (life_plan and pathway_map must pass before the search starts)",
            "override": f"init-country forced for {target_rel} while gates were: " + ", ".join(f"{k}={v}" for k, v in state.items()),
            "reason": a.reason or "forced with --force (no reason given)"})
    update_run_state(run_dir, mutate)


def cmd_init(run_dir: Path, a) -> dict:
    path, kind = resolve_target(run_dir, a)
    if kind == "crosscut" and not a.kind:
        raise UsageError("init-country --crosscut SLUG needs --kind programme_scan|funding_route (there is no default: "
                         "the kinds are different files)")
    if kind != "crosscut" and a.kind:
        raise UsageError("--kind only applies to --crosscut targets")
    if path.exists():
        if a.resume:
            return {"ok": True, "file": relpath(run_dir, path), "note": "exists, resuming"}
        raise UsageError(f"{relpath(run_dir, path)} already exists (use --resume to continue it)")
    if not a.name:
        raise UsageError("init-country needs --name")
    check_gates(run_dir, a, relpath(run_dir, path))
    slug = a.crosscut or a.country
    meta = {"agent_model": a.agent_model, "started_at": now_iso(), "limit_events": []}
    if kind == "crosscut" and a.kind == "funding_route":
        doc = {"crosscut_kind": "funding_route", "route": a.name, "route_type": a.route_type, "status": "in_progress",
               "findings": [], "verdict": "", "open_questions": []}
    else:
        doc = {"country": a.name, "slug": slug, "run_date": today_iso(), "status": "in_progress",
               "path_b_done": False, "screening": [], "candidates": [], "ranked_out": [],
               "corrections_to_prior": [], "searched_not_surfaced": [], "run_meta": meta}
        if kind == "crosscut":
            doc["crosscut_kind"] = "programme_scan"
        if kind == "followup":
            doc["followup_of"] = a.country
    with file_lock(path):
        write_doc(run_dir, path, kind, doc)
    return {"ok": True, "file": relpath(run_dir, path), "status": "in_progress"}


def load_target(path: Path) -> dict:
    if not path.exists():
        raise UsageError(f"{path.name} does not exist - run init-country first")
    return load_json(path)


def cmd_add(run_dir: Path, a, schema: str | None, field: str, keyfn) -> dict:
    """Upsert one record into list `field` of the target file. schema=None (add-finding): the
    record is validated as part of the whole file instead of on its own."""
    path, kind = resolve_target(run_dir, a)
    rec = read_json_arg(a.json, a.file)
    try:
        if not isinstance(rec, dict):
            raise Rejected([VError("", "type", "record must be a JSON object")])
        errs = validate(rec, schema) if schema else []
        if schema == "candidate_record":
            errs += write_time_problems(rec)
        check(errs)
        with file_lock(path):
            doc = load_target(path)
            is_fr = doc.get("crosscut_kind") == "funding_route"
            if field == "findings" and not is_fr:
                raise UsageError("add-finding is for funding_route cross-cuts (--crosscut SLUG created with --kind funding_route)")
            if field != "findings" and is_fr:
                raise UsageError("a funding_route cross-cut holds findings, not screening/candidates: use add-finding")
            if schema == "candidate_record":
                prov = rec.setdefault("provenance", {})
                prov.setdefault("pass", {"country": "first_pass", "followup": "followup", "crosscut": "crosscut"}[kind])
                prov.setdefault("recorded_at", now_iso())
                state = load_json(rp(run_dir, "run_state")) if rp(run_dir, "run_state").exists() else None
                sess = current_session(state)
                if sess is not None:
                    prov.setdefault("session", sess)
            action = upsert(doc.setdefault(field, []), rec, keyfn)
            write_doc(run_dir, path, kind, doc)
        rel = relpath(run_dir, path)
        cleared = clear_rejected(run_dir, lambda e: e.get("command") == f"add-{field}" and e.get("file") == rel
                                 and isinstance(e.get("record"), dict) and keyfn(e["record"]) == keyfn(rec))
        out = {"ok": True, "file": rel, "action": action, "count": len(doc[field])}
        if cleared:
            out["cleared_rejected"] = cleared
        return out
    except Rejected as r:
        reject(run_dir, path, f"add-{field}", rec, r.errors)
        raise


def cmd_clear_rejected(run_dir: Path, a) -> dict:
    if a.id:
        n = clear_rejected(run_dir, lambda e: isinstance(e.get("record"), dict) and e["record"].get("id") == a.id)
    else:
        n = clear_rejected(run_dir, lambda e: True)
    return {"ok": True, "cleared": n, "id": a.id}


def cmd_put_crosscut(run_dir: Path, a) -> dict:
    path, kind = resolve_target(run_dir, a)
    if kind != "crosscut":
        raise UsageError("put-crosscut needs --crosscut SLUG")
    doc = read_json_arg(a.json, a.file)
    if isinstance(doc, dict) and doc.get("crosscut_kind") == "funding_route":
        doc.setdefault("status", "complete")        # a whole-file write is a finished verification
    try:
        with file_lock(path):
            write_doc(run_dir, path, kind, doc)
    except Rejected as r:
        reject(run_dir, path, "put-crosscut", doc, r.errors)
        raise
    return {"ok": True, "file": relpath(run_dir, path), "status": doc.get("status")}


def cmd_set_status(run_dir: Path, a) -> dict:
    path, kind = resolve_target(run_dir, a)
    changed = []
    with file_lock(path):
        doc = load_target(path)
        if doc.get("crosscut_kind") == "funding_route":
            used = [f for f in ("path_b_done", "country_summary", "add_gap", "add_correction", "add_path_b_person", "add_urgent_deadline",
                                "country_context", "limit_event", "tool_calls") if getattr(a, f)]
            if used:
                raise UsageError("a funding_route cross-cut accepts only --status, --budget-notes and --note (not " +
                                 ", ".join("--" + u.replace("_", "-") for u in used) + ")")
        if a.status:
            if a.status == "complete" and kind == "country" and not a.force:
                unscreened = [s["institution"] for s in doc.get("screening", []) if s.get("decision") == "unscreened"]
                path_b = a.path_b_done == "true" or (a.path_b_done is None and doc.get("path_b_done"))
                if unscreened or not path_b:
                    raise UsageError("refusing status 'complete': " + (
                        "path_b_done is false; " if not path_b else "") + (
                        f"{len(unscreened)} unscreened institution(s); " if unscreened else "") +
                        "use 'complete_with_gaps' (or --force)")
            doc["status"] = a.status
            changed.append("status")
        if a.path_b_done is not None:
            doc["path_b_done"] = a.path_b_done == "true"
            changed.append("path_b_done")
        if a.budget_notes is not None:
            doc["budget_notes"] = a.budget_notes
            changed.append("budget_notes")
        if a.country_summary is not None:
            doc["country_summary"] = a.country_summary
            changed.append("country_summary")
        if a.note is not None:
            doc["notes"] = (doc.get("notes", "") + "\n" + a.note).strip()
            changed.append("notes")
        for gap in a.add_gap or []:
            if gap not in doc.setdefault("searched_not_surfaced", []):
                doc["searched_not_surfaced"].append(gap)
            changed.append("searched_not_surfaced")
        for flag, field, key in (("add_correction", "corrections_to_prior", lambda r: (r.get("prior_id"), r.get("correction"))),
                                 ("add_path_b_person", "path_b_people", lambda r: norm_text(r.get("name"))),
                                 ("add_urgent_deadline", "urgent_deadlines", lambda r: (r.get("name"), r.get("date")))):
            raw = getattr(a, flag)
            if raw:
                rec = json_or_path(raw)
                upsert(doc.setdefault(field, []), rec, key)
                changed.append(field)
        if a.country_context:
            ctx = doc.setdefault("country_context", {})
            ctx.update(json_or_path(a.country_context))
            changed.append("country_context")
        meta = doc.get("run_meta")
        for ev in a.limit_event or []:
            kind_, _, detail = ev.partition(":")
            if meta is None:
                raise UsageError("this file has no run_meta (limit events are for country/crosscut files)")
            meta.setdefault("limit_events", []).append({"at": now_iso(), "kind": kind_, "detail": detail})
            changed.append("limit_events")
        if a.tool_calls is not None and meta is not None:
            meta["tool_calls"] = a.tool_calls
        if meta is not None and (a.status in ("complete", "complete_with_gaps", "partial_budget_exhausted")):
            meta["ended_at"] = now_iso()
        try:
            write_doc(run_dir, path, kind, doc)
        except Rejected as r:
            reject(run_dir, path, "set-status", vars_safe(a), r.errors)
            raise
    return {"ok": True, "file": relpath(run_dir, path), "changed": sorted(set(changed)), "status": doc["status"]}


def cmd_add_assumption(run_dir: Path, a) -> dict:
    rec = {"id": a.id, "text": a.text, "revisit": bool(a.revisit)}
    if a.made_in:
        rec["made_in"] = a.made_in
    state = update_run_state(run_dir, lambda st: upsert(st.setdefault("assumptions", []), rec, lambda r: r["id"]))
    if state is None:
        raise UsageError("run_state.json missing; run init_workspace.py first")
    return {"ok": True, "assumptions": len(state["assumptions"])}


def cmd_add_protocol_override(run_dir: Path, a) -> dict:
    rec = {"date": a.date or today_iso(), "rule": a.rule, "override": a.override, "reason": a.reason}
    state = update_run_state(run_dir, lambda st: st.setdefault("overrides_of_protocol", []).append(rec))
    if state is None:
        raise UsageError("run_state.json missing; run init_workspace.py first")
    return {"ok": True, "overrides_of_protocol": len(state["overrides_of_protocol"])}


def cmd_update_vector(run_dir: Path, a) -> dict:
    """Validate and replace run_state.state_vector (the end-of-session 'update state vector')."""
    vec = read_json_arg(a.json, a.file)
    errs = validate(vec, "continuation_state_vector")
    state_path = rp(run_dir, "run_state")
    if not errs and state_path.exists():
        rid = load_json(state_path).get("run_id")
        if vec["run"] != rid:
            errs = [VError("run", "const", f"vector.run {vec['run']!r} does not match run_state.run_id {rid!r}", vec["run"])]
    check_vec = errs
    if check_vec:
        raise Rejected(check_vec, park=False)

    def mutate(st):
        st["state_vector"] = vec                 # replace wholesale: the vector is rewritten, not patched
    if update_run_state(run_dir, mutate) is None:
        raise UsageError("run_state.json missing; run init_workspace.py first")
    return {"ok": True, "state_vector": {"session": vec["session"], "phase": vec["phase"], "next_virgil_0": (vec["next"]["virgil"] or [None])[0]}}


def vars_safe(a) -> dict:
    return {k: v for k, v in vars(a).items() if v not in (None, False, []) and k not in ("func",)}


def recompute_agents_per_window(state: dict) -> None:
    """Mean agents_run over windows that ended in a limit hit (those show real capacity);
    if none hit a limit yet, mean over all windows that recorded agents_run."""
    with_agents = [s for s in state["sessions"] if s.get("agents_run") is not None]
    hit = [s["agents_run"] for s in with_agents if s.get("limit_hit")]
    pool = hit or [s["agents_run"] for s in with_agents]
    state["agents_per_window_observed"] = round(sum(pool) / len(pool), 1) if pool else None


def cmd_log_session(run_dir: Path, a) -> dict:
    def mutate(state):
        now = now_iso()
        if a.set_phase:
            state["current_phase"] = a.set_phase
        if a.next_action:
            state["next_action"] = a.next_action
        phase = a.phase or state["current_phase"]
        if a.start:
            n = max([s["n"] for s in state["sessions"]], default=0) + 1
            state["sessions"].append({"n": n, "started_at": now, "ended_at": None, "phase": phase, "outcome": "open", "limit_hit": False})
            if a.wave:
                state["sessions"][-1]["wave"] = a.wave
            # The vector's `session` counts sittings (protocol/state_vector.md: "increments session once per sitting").
            if isinstance(state.get("state_vector"), dict):
                state["state_vector"]["session"] = n
                state["state_vector"]["date"] = today_iso()
            event = "session_start"
        elif a.end or a.event == "session_end":
            opened = [s for s in state["sessions"] if not s.get("ended_at")]
            if not opened:
                raise UsageError("no open session to end (use --start first)")
            s = opened[-1]
            s["ended_at"] = now
            s["limit_hit"] = bool(a.limit_hit) or s["limit_hit"]
            s["outcome"] = a.outcome or ("limit_hit" if s["limit_hit"] else "ok")
            if a.agents_run is not None:
                s["agents_run"] = a.agents_run
            event = "session_end"
        else:
            event = a.event or "note"
            if a.limit_hit and state["sessions"]:
                cur = [s for s in state["sessions"] if not s.get("ended_at")]
                if cur:
                    cur[-1]["limit_hit"] = True
                event = "limit_hit"
            if a.agents_run is not None and state["sessions"]:
                state["sessions"][-1]["agents_run"] = a.agents_run
        if a.wave and not a.start and state["sessions"]:
            (next((x for x in reversed(state["sessions"]) if not x.get("ended_at")), state["sessions"][-1]))["wave"] = a.wave
        recompute_agents_per_window(state)
        state["heartbeat"] = {"at": now, "file": "logs/session_log.jsonl"}
        mutate.entry = {"ts": now, "session": current_session(state), "event": event, "phase": phase,
                        "detail": a.detail or a.outcome or event}
        for k, v in (("country", a.country), ("agent", a.agent)):
            if v:
                mutate.entry[k] = v

    state = update_run_state(run_dir, mutate)
    if state is None:
        raise UsageError("run_state.json missing; run init_workspace.py first")
    errs = validate(mutate.entry, "session_log_entry")
    check(errs)
    append_jsonl(rp(run_dir, "session_log"), mutate.entry)
    return {"ok": True, "session": mutate.entry["session"], "event": mutate.entry["event"],
            "agents_per_window_observed": state["agents_per_window_observed"]}


# --------------------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Atomically write one record into a run workspace (see module docstring).")
    ap.add_argument("run_dir")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def target(p):
        p.add_argument("--country", help="country slug (file stem)")
        p.add_argument("--followup", nargs="?", const="", default=None, metavar="X", help="target the follow-up file (optional suffix X)")
        p.add_argument("--crosscut", help="cross-cut slug")

    def record(p):
        p.add_argument("--json", help="record as a JSON string")
        p.add_argument("--file", help="record file path ('-' = stdin)")

    p = sub.add_parser("init-country", help="create the target file"); target(p)
    p.add_argument("--name"); p.add_argument("--agent-model", default="unknown")
    p.add_argument("--kind", choices=["programme_scan", "funding_route"], help="REQUIRED with --crosscut (no default)")
    p.add_argument("--route-type", choices=["regional_programme", "home_country_scheme", "loan", "other"], default="other")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--force", action="store_true", help="start even though a gate has not passed (recorded in run_state.overrides_of_protocol)")
    p.add_argument("--reason", help="why --force was needed (stored in the override record)")
    for name in ("add-screening", "add-candidate", "add-ranked-out", "add-finding", "put-crosscut"):
        p = sub.add_parser(name); target(p); record(p)
    p = sub.add_parser("update-vector", help="validate and replace run_state.state_vector"); record(p)
    p = sub.add_parser("clear-rejected", help="remove parked records from rejected_records.jsonl")
    p.add_argument("--id", help="only entries whose record id is ID (default: all)")
    p = sub.add_parser("add-assumption", help="record an assumption in run_state.assumptions")
    p.add_argument("--id", required=True); p.add_argument("--text", required=True); p.add_argument("--made-in"); p.add_argument("--revisit", action="store_true")
    p = sub.add_parser("add-protocol-override", help="record a deviation from a protocol rule in run_state.overrides_of_protocol")
    p.add_argument("--rule", required=True); p.add_argument("--override", required=True); p.add_argument("--reason", required=True); p.add_argument("--date")
    p = sub.add_parser("set-status"); target(p)
    p.add_argument("--status", choices=["in_progress", "complete", "complete_with_gaps", "partial_budget_exhausted"])
    p.add_argument("--path-b-done", choices=["true", "false"]); p.add_argument("--budget-notes")
    p.add_argument("--country-summary"); p.add_argument("--note"); p.add_argument("--add-gap", action="append")
    p.add_argument("--add-correction"); p.add_argument("--add-path-b-person"); p.add_argument("--add-urgent-deadline")
    p.add_argument("--country-context", help="JSON object merged into country_context")
    p.add_argument("--limit-event", action="append", metavar="KIND:DETAIL"); p.add_argument("--tool-calls", type=int)
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("log-session")
    p.add_argument("--start", action="store_true"); p.add_argument("--end", action="store_true")
    p.add_argument("--event", choices=["limit_hit", "agent_start", "agent_end", "checkpoint", "note", "error", "session_end"])
    p.add_argument("--phase", choices=PHASES); p.add_argument("--set-phase", choices=PHASES)
    p.add_argument("--detail"); p.add_argument("--country"); p.add_argument("--agent"); p.add_argument("--agents-run", type=int)
    p.add_argument("--outcome"); p.add_argument("--limit-hit", action="store_true"); p.add_argument("--next-action")
    p.add_argument("--wave", type=int, help="search wave this session works on")
    return ap


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    run_dir = Path(a.run_dir)
    try:
        if not run_dir.is_dir():
            raise UsageError(f"RUN_DIR not found: {run_dir}")
        if a.cmd == "init-country":
            out = cmd_init(run_dir, a)
        elif a.cmd == "add-screening":
            out = cmd_add(run_dir, a, "screening_entry", "screening", lambda r: norm_text(r.get("institution")))
        elif a.cmd == "add-candidate":
            out = cmd_add(run_dir, a, "candidate_record", "candidates", lambda r: r.get("id"))
        elif a.cmd == "add-ranked-out":
            out = cmd_add(run_dir, a, "ranked_out_entry", "ranked_out",
                          lambda r: (norm_text(r.get("institution")), norm_text(r.get("programme"))))
        elif a.cmd == "add-finding":
            out = cmd_add(run_dir, a, None, "findings", lambda r: norm_text(r.get("question")))
        elif a.cmd == "clear-rejected":
            out = cmd_clear_rejected(run_dir, a)
        elif a.cmd == "add-assumption":
            out = cmd_add_assumption(run_dir, a)
        elif a.cmd == "add-protocol-override":
            out = cmd_add_protocol_override(run_dir, a)
        elif a.cmd == "put-crosscut":
            out = cmd_put_crosscut(run_dir, a)
        elif a.cmd == "update-vector":
            out = cmd_update_vector(run_dir, a)
        elif a.cmd == "set-status":
            out = cmd_set_status(run_dir, a)
        else:
            out = cmd_log_session(run_dir, a)
        print(json.dumps(out, ensure_ascii=False))
        return EXIT_OK
    except Rejected as r:
        print("REJECTED - nothing was written. Fix these and retry" + (" (record parked in 04_search/rejected_records.jsonl):" if r.park else ":"), file=sys.stderr)
        for e in r.errors[:20]:
            print(f"  {e.path or '<root>'}: [{e.kind}] {e.message}", file=sys.stderr)
        return EXIT_PROBLEMS
    except (UsageError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
