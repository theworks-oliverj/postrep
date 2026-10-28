#!/usr/bin/env python3
"""
validate.py - check every file of a run workspace against its schema.

PURPOSE
    One command that answers "is this workspace consistent?" Reports, grouped so a
    non-expert can act on them:
      * ERRORS          schema violations per file (wrong type, bad id pattern, ...)
      * MISSING REQUIRED  required fields that agents forgot, counted per field
      * ENUM DRIFT      values outside an allowed list ("pass (weak)", "path A" ...),
                        counted per field - the reference run lost much of its
                        aggregation power to free-text enums, so drift is surfaced loudly
      * WARNINGS        things the schema cannot express (see list below)
    Missing OPTIONAL files (e.g. merged.json before the merge phase) are only listed.

SEMANTIC CHECKS (beyond JSON Schema)
    errors:   file slug != file name; ranked_out promote=true without promote_reason;
              benchmarks with duplicate axes; rubric sheet whose `rubric` contradicts its file
    warnings: candidate id used twice; candidate domain ids not defined in the Study & Pathway Map;
              canonical source claim_fields missing; sources without source_type/accessed_date;
              url null without a note; state vectors without rubric_version; status 'complete'
              with path_b_done=false; checkpoints pointing at missing files; overrides naming
              unknown ids; unparked rejected records in rejected_records.jsonl (clear them with
              `checkpoint.py clear-rejected`); countries in the search plan that have no file yet;
              deep/standard countries without cap_n; records without household_fit, and finished
              country files without country_context.dependant_pathway, when the life plan has
              dependants or a partner who moves; state_vector.phase not ending in current_phase.
    errors:   also state_vector.run different from run_state.run_id.
    --strict turns warnings into errors.

USAGE
    python3 scripts/validate.py RUN_DIR [--strict] [--json]

EXIT CODES
    0 no errors | 1 errors found (or warnings with --strict) | 2 RUN_DIR missing
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (EXIT_OK, EXIT_PROBLEMS, EXIT_USAGE, UsageError, list_json, load_json, rp, validate,  # noqa: E402
                     validator_name)

CANONICAL_SOURCES = ["programme", "study_plan", "pathway", "admissions_language", "tuition", "scholarship"]
DRIFT_KINDS = {"enum", "const", "anyOf", "oneOf"}


def norm_path(p: str) -> str:
    return re.sub(r"\[\d+\]", "[]", p)


class Report:
    def __init__(self):
        self.files: list[dict] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.missing_optional: list[str] = []
        self.required: collections.Counter = collections.Counter()
        self.drift: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)

    def schema_errors(self, rel: str, schema: str, errs) -> None:
        self.files.append({"file": rel, "schema": schema, "errors": len(errs)})
        for e in errs:
            where = f"{rel}: {e.path or '<root>'}"
            if e.kind == "required":
                self.required[f"{schema}.{norm_path(e.path)}.{e.value}".replace("..", ".")] += 1
            elif e.kind in DRIFT_KINDS and e.value is not None:
                self.drift[f"{schema}.{norm_path(e.path)}"][repr(e.value)] += 1
            self.errors.append(f"{where}: [{e.kind}] {e.message}")


def check_json(run_dir: Path, rep: Report, rel_key_or_path, schema: str, optional: bool = True):
    path = rel_key_or_path
    rel = path.relative_to(run_dir).as_posix()
    if not path.exists():
        if optional:
            rep.missing_optional.append(rel)
        else:
            rep.errors.append(f"{rel}: required file missing")
        return None
    try:
        doc = load_json(path)
    except UsageError as e:
        rep.errors.append(str(e))
        rep.files.append({"file": rel, "schema": schema, "errors": 1})
        return None
    rep.schema_errors(rel, schema, validate(doc, schema))
    return doc


def semantic_candidates(rep: Report, rel: str, doc: dict, domain_ids: set[str], seen_ids: dict, kind: str, household: bool = False) -> None:
    missing_types = missing_dates = null_no_note = no_rubric = no_household = 0
    for c in doc.get("candidates", []):
        cid = c.get("id", "?")
        if cid in seen_ids and not c.get("replaces") and seen_ids[cid] != rel:
            rep.warnings.append(f"{rel}: candidate id {cid} also appears in {seen_ids[cid]}")
        seen_ids.setdefault(cid, rel)
        have = {s.get("claim_field") for s in c.get("sources", [])}
        for f in CANONICAL_SOURCES:
            if f not in have:
                rep.warnings.append(f"{rel}: {cid}: no source entry for claim_field '{f}'")
        for s in c.get("sources", []):
            missing_types += "source_type" not in s
            missing_dates += "accessed_date" not in s
            null_no_note += (s.get("url") is None and not s.get("note"))
        no_rubric += "rubric_version" not in (c.get("state_vector") or {})
        no_household += household and "household_fit" not in c
        if domain_ids:
            extra = set(c.get("axis_1_curriculum", {})) - domain_ids
            if extra:
                rep.warnings.append(f"{rel}: {cid}: domain id(s) {sorted(extra)} not defined in study_pathway_map")
    for n, msg in ((missing_types, "source entries without source_type"), (missing_dates, "source entries without accessed_date"),
                   (null_no_note, "null source urls without an explanatory note"), (no_rubric, "records whose state_vector lacks rubric_version"),
                   (no_household, "records without household_fit although the life plan has dependants or a partner who moves")):
        if n:
            rep.warnings.append(f"{rel}: {n} {msg}")
    for r in doc.get("ranked_out", []):
        if r.get("promote") and not r.get("promote_reason"):
            rep.errors.append(f"{rel}: ranked_out '{r.get('institution')} | {r.get('programme')}' has promote=true without promote_reason")


def run(run_dir: Path, strict: bool) -> Report:
    rep = Report()
    dm_path = rp(run_dir, "study_pathway_map")
    domain_ids: set[str] = set()
    if dm_path.exists():
        try:
            domain_ids = {d.get("id") for d in load_json(dm_path).get("domains", []) if isinstance(d, dict)}
        except UsageError:
            pass

    state = check_json(run_dir, rep, rp(run_dir, "run_state"), "run_state", optional=False)
    lp = check_json(run_dir, rep, rp(run_dir, "life_plan"), "life_plan")
    hh = (lp or {}).get("household") if isinstance(lp, dict) else None
    household = isinstance(hh, dict) and bool((hh.get("dependants") or 0) > 0 or hh.get("partner_moves"))
    for key, rubric in (("life_plan_score", "life_plan"), ("map_score", "pathway_map")):
        d = check_json(run_dir, rep, rp(run_dir, key), "rubric_score")
        if isinstance(d, dict) and d.get("rubric") != rubric:
            rep.errors.append(f"{rp(run_dir, key).relative_to(run_dir).as_posix()}: rubric is {d.get('rubric')!r}, expected {rubric!r}")
    check_json(run_dir, rep, dm_path, "study_pathway_map")
    bm = check_json(run_dir, rep, rp(run_dir, "benchmarks"), "benchmarks")
    if isinstance(bm, dict):
        axes = [b.get("axis") for b in bm.get("benchmarks", []) if isinstance(b, dict)]
        if len(set(axes)) != len(axes):
            rep.errors.append(f"02_map/benchmarks.json: duplicate axes {axes}")
    plan = check_json(run_dir, rep, rp(run_dir, "search_plan"), "search_plan")

    seen_ids: dict[str, str] = {}
    all_ids: set[str] = set()
    file_slugs: set[str] = set()
    for sub, key in (("countries_dir", "country"), ("followups_dir", "followup"), ("crosscuts_dir", "crosscut")):
        for p in list_json(rp(run_dir, sub)):
            rel = p.relative_to(run_dir).as_posix()
            try:
                doc = load_json(p)
            except UsageError as e:
                rep.errors.append(str(e))
                continue
            if key == "crosscut":
                schema = "funding_route_crosscut" if isinstance(doc, dict) and doc.get("crosscut_kind") == "funding_route" else "crosscut_scan_file"
            else:
                schema = "country_run_file"
            rep.schema_errors(rel, schema, validate(doc, schema))
            if not isinstance(doc, dict):
                continue
            file_slugs.add(p.stem.split("_followup")[0])
            if key != "crosscut" or schema == "crosscut_scan_file":
                slug = doc.get("slug")
                expect = p.stem if key != "followup" else p.stem.split("_followup")[0]
                if slug and slug != expect:
                    rep.errors.append(f"{rel}: slug '{slug}' does not match file name '{expect}'")
                if doc.get("status") == "complete" and key == "country" and not doc.get("path_b_done"):
                    rep.warnings.append(f"{rel}: status complete but path_b_done=false")
                if household and key == "country" and doc.get("status") in ("complete", "complete_with_gaps") and not (doc.get("country_context") or {}).get("dependant_pathway"):
                    rep.warnings.append(f"{rel}: the life plan has dependants or a partner who moves, but country_context.dependant_pathway is empty")
                semantic_candidates(rep, rel, doc, domain_ids, seen_ids, key, household)
                all_ids |= {c.get("id") for c in doc.get("candidates", []) if isinstance(c, dict)}
    ov = check_json(run_dir, rep, rp(run_dir, "overrides"), "override")
    if isinstance(ov, list) and all_ids:
        for o in ov:
            if isinstance(o, dict) and o.get("target_id") not in all_ids:
                rep.warnings.append(f"04_search/overrides.json: target_id {o.get('target_id')} not found in any country/cross-cut file")
    check_json(run_dir, rep, rp(run_dir, "followup_plan"), "followup_trigger")
    check_json(run_dir, rep, rp(run_dir, "merged"), "merged_file")
    check_json(run_dir, rep, rp(run_dir, "merge_report"), "merge_report")
    check_json(run_dir, rep, rp(run_dir, "verification_sample"), "verification_sample")
    check_json(run_dir, rep, rp(run_dir, "verification"), "verification_record")

    log = rp(run_dir, "session_log")
    if log.exists():
        n = bad = 0
        for i, line in enumerate(log.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            n += 1
            try:
                errs = validate(json.loads(line), "session_log_entry")
            except json.JSONDecodeError as e:
                rep.errors.append(f"logs/session_log.jsonl line {i}: invalid JSON ({e})")
                bad += 1
                continue
            for e in errs:
                bad += 1
                rep.errors.append(f"logs/session_log.jsonl line {i}: {e.path or '<root>'}: [{e.kind}] {e.message}")
        rep.files.append({"file": "logs/session_log.jsonl", "schema": f"session_log_entry x{n}", "errors": bad})
    else:
        rep.missing_optional.append("logs/session_log.jsonl")

    rej = rp(run_dir, "rejected")
    if rej.exists() and rej.read_text(encoding="utf-8").strip():
        rep.warnings.append(f"04_search/rejected_records.jsonl has {len(rej.read_text().splitlines())} parked record(s) awaiting triage")
    if isinstance(state, dict):
        sv = state.get("state_vector")
        if isinstance(sv, dict):
            # The vector is what a fresh session continues from, so it must agree with the ledger.
            if sv.get("run") != state.get("run_id"):
                rep.errors.append(f"run_state.json: state_vector.run {sv.get('run')!r} != run_id {state.get('run_id')!r}")
            if str(sv.get("phase", "")).replace("->", "→").split("→")[-1].strip() != state.get("current_phase"):
                rep.warnings.append(f"run_state.json: state_vector.phase {sv.get('phase')!r} does not end in current_phase {state.get('current_phase')!r}")
        for c in state.get("checkpoints", []):
            if not (run_dir / c["file"]).exists():
                rep.warnings.append(f"run_state checkpoint points at missing file {c['file']}")
    if isinstance(plan, dict):
        for c in plan.get("countries", []):
            if isinstance(c, dict) and not c.get("cap_n") and c.get("depth") != "quick":
                rep.warnings.append(f"search_plan: country '{c.get('slug')}' (depth {c.get('depth')}) has no cap_n (only depth quick defaults to 4)")
        for c in plan.get("countries", []) + plan.get("crosscuts", []):
            if c["slug"] not in file_slugs:
                rep.warnings.append(f"search_plan lists '{c['slug']}' but no file exists yet")
    if strict:
        rep.errors += [f"(strict) {w}" for w in rep.warnings]
        rep.warnings = []
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validate every file of a run workspace.")
    ap.add_argument("run_dir")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args(argv)
    run_dir = Path(a.run_dir)
    if not run_dir.is_dir():
        print(f"error: RUN_DIR not found: {run_dir}", file=sys.stderr)
        return EXIT_USAGE
    rep = run(run_dir, a.strict)
    if a.json:
        print(json.dumps({"validator": validator_name(), "files": rep.files, "errors": rep.errors, "warnings": rep.warnings,
                          "missing_optional": rep.missing_optional, "missing_required": dict(rep.required),
                          "enum_drift": {k: dict(v) for k, v in rep.drift.items()}}, indent=2))
    else:
        bad = [f for f in rep.files if f["errors"]]
        print(f"validator: {validator_name()} | files checked: {len(rep.files)} | with errors: {len(bad)} | optional files absent: {len(rep.missing_optional)}")
        if rep.required:
            print("\nMISSING REQUIRED FIELDS (count)")
            for k, n in rep.required.most_common():
                print(f"  {n:4d}  {k}")
        if rep.drift:
            print("\nENUM DRIFT (field: value x count)")
            for k, c in rep.drift.items():
                print(f"  {k}: " + ", ".join(f"{v} x{n}" for v, n in c.most_common(8)))
        if rep.errors:
            print(f"\nERRORS ({len(rep.errors)})")
            for e in rep.errors[:60]:
                print("  " + e)
            if len(rep.errors) > 60:
                print(f"  ... {len(rep.errors) - 60} more (use --json)")
        if rep.warnings:
            print(f"\nWARNINGS ({len(rep.warnings)})")
            for w in rep.warnings[:40]:
                print("  " + w)
            if len(rep.warnings) > 40:
                print(f"  ... {len(rep.warnings) - 40} more (use --json)")
        if rep.missing_optional:
            print("\nNot yet created (ok): " + ", ".join(rep.missing_optional))
        print("\nRESULT: " + ("FAIL" if rep.errors else "OK"))
    return EXIT_PROBLEMS if rep.errors else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
