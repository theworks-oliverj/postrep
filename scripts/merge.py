#!/usr/bin/env python3
"""
merge.py - fold country files, follow-ups and cross-cuts into one merged, ranked file.

PURPOSE
    Turns the raw per-agent files in 04_search/ into 05_merge/merged.json (+ a machine-
    readable merge_report.json). It replaces the reference run's ad-hoc merge script and
    fixes its known flaws:
      * no hard-coded paths, country lists or overrides   -> everything is discovered/read from RUN_DIR
      * follow-up extras silently dropped                  -> kept (urgent_deadlines, path_b_people,
                                                              still_open, notes, extras, context additions)
      * country_context/country_summary changed type       -> they keep ONE type (see schema)
      * no schema validation                               -> every input is validated; invalid files are
                                                              reported and skipped, never half-merged
      * score overrides lived in code                      -> read from 04_search/overrides.json, original
                                                              value stored in candidate._overrides_applied
      * duplicated screening rows / stale ranked_out       -> deduplicated; promoted programmes purged

INPUTS (all under RUN_DIR)
    04_search/countries/<slug>.json            first-pass files (country_run_file)
    04_search/followups/<slug>_followup[_x].json  gap-filling passes; folded into <slug>
    04_search/crosscuts/<slug>.json            programme_scan (candidates join the ranking) or
                                               funding_route (kept as its own section)
    04_search/overrides.json                   optional
    02_map/benchmarks.json                     optional (copied into merged.json)
    --baseline PATH                            optional baseline_ledger.json for deltas

OUTPUTS
    05_merge/merged.json, 05_merge/merge_report.json     (stdout: short summary)

FOLD RULES (the "why" behind the code)
    * Files are folded in name order: base first, then follow-ups; later passes win.
    * A follow-up candidate with `replaces: ID` supersedes that first-pass record IN PLACE:
      it keeps the ORIGINAL id (so references stay valid), remembers its own id in
      `_followup_id` and the old vector in `_replaced_first_pass_vector`.
    * Screening rows are keyed by normalised institution name (later pass wins).
    * ranked_out entries that became full records are removed from ranked_out.
    * Exact duplicates (same normalised institution|programme|track) are dropped, keeping the
      record with more sources (country origin before cross-cut on ties). Near-duplicates
      (difflib ratio >= threshold on institution+programme) are only FLAGGED for a human.
    * `_total` is the unweighted sum of scored axes; '?' axes are skipped (see _common.vector_total
      for the bias this causes - `_unscored_axes` is stored so readers can see it).
    * Rank = total desc, then pathway desc, then funding desc (then id, for stability); this is
      the order of protocol/sessions/s8_merge_verify.md.

PLANNED vs PRESENT
    Every country and cross-cut listed in 03_scope/search_plan.json must have a file in
    04_search/. A missing one is the error `planned_country_missing` (the protocol exists to
    stop countries silently going missing); with --allow-partial it is a warning. A cross-cut
    (programme_scan OR funding_route) still `in_progress` is reported like an in-progress country.

EXIT CODES
    0 merged, no error-level issues | 1 merged but error-level issues exist (invalid input file,
    in-progress file, planned country missing, missing replace target, unmatched override ...) |
    2 usage error
    The outputs are written in both 0 and 1 so the report can be read.

USAGE
    python3 scripts/merge.py RUN_DIR [--baseline PATH] [--allow-partial] [--near-dup 0.75]
"""
from __future__ import annotations

import argparse
import copy
import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (AXES, EXIT_OK, EXIT_PROBLEMS, EXIT_USAGE, PROTOCOL_VERSION, UsageError,  # noqa: E402
                     atomic_write_json, followups_for, get_path, list_json, load_json, norm_text,
                     now_iso, rank_sort_key, record_key, rp, score_int, set_path, unscored_axes,
                     validate, vector_total)


class Ctx:
    """Collects issues and counters while merging."""

    def __init__(self):
        self.issues: list[dict] = []
        self.counts: dict[str, int] = {"files_read": 0, "candidates_in": 0, "replaced": 0, "screening_rows_in": 0,
                                       "screening_rows_out": 0, "ranked_out_purged": 0}

    def issue(self, level: str, code: str, message: str, ref: str = "") -> None:
        d = {"level": level, "code": code, "message": message}
        if ref:
            d["ref"] = ref
        self.issues.append(d)


def load_validated(path: Path, schema: str, ctx: Ctx) -> dict | list | None:
    """Load + validate one input file. Invalid/unreadable files are reported and skipped."""
    try:
        doc = load_json(path)
    except UsageError as e:
        ctx.issue("error", "unreadable_file", str(e), path.name)
        return None
    errs = validate(doc, schema)
    if errs:
        shown = "; ".join(f"{e.path or '<root>'}: {e.message}" for e in errs[:3])
        ctx.issue("error", "invalid_file", f"{path.name} fails {schema} ({len(errs)} error(s)): {shown}", path.name)
        return None
    ctx.counts["files_read"] += 1
    return doc


def check_status(doc: dict, name: str, ctx: Ctx, allow_partial: bool) -> None:
    st = doc.get("status")
    if st == "in_progress":
        ctx.issue("warning" if allow_partial else "error", "in_progress_file",
                  f"{name} is still in_progress (agent cut off or running); merging it would hide gaps. Resume the agent or use --allow-partial.", name)
    elif st in ("partial_budget_exhausted", "complete_with_gaps"):
        ctx.issue("warning", "incomplete_status", f"{name} status={st}: see followups.py", name)


def upsert_by(items: list, new: dict, key) -> None:
    k = key(new)
    for i, old in enumerate(items):
        if key(old) == k:
            items[i] = new
            return
    items.append(new)


def fold_country(run_dir: Path, base_path: Path, ctx: Ctx, allow_partial: bool, kind: str = "country"):
    """Fold one base file and its follow-ups. Returns (country_block, candidates) or None."""
    base = load_validated(base_path, "crosscut_scan_file" if kind == "crosscut" else "country_run_file", ctx)
    if base is None:
        return None
    slug = base_path.stem
    check_status(base, base_path.name, ctx, allow_partial)
    ctx_base = {k: v for k, v in (base.get("country_context") or {}).items() if k != "additions"}
    blk = {
        "country": base["country"], "slug": slug, "kind": kind, "status": base["status"], "status_effective": base["status"],
        "path_b_done": bool(base.get("path_b_done")), "screening": [], "ranked_out": [], "corrections_to_prior": [],
        "country_context": dict(ctx_base, additions=list((base.get("country_context") or {}).get("additions", []))),
        "searched_not_surfaced": list(base.get("searched_not_surfaced", [])),
        "country_summary": base.get("country_summary", ""), "budget_notes": base.get("budget_notes", ""),
        "run_meta": [], "urgent_deadlines": list(base.get("urgent_deadlines", [])), "path_b_people": list(base.get("path_b_people", [])),
        "still_open": list(base.get("still_open", [])), "followup_files": [], "followups": {}, "candidate_ids": []}
    if base.get("run_meta"):
        blk["run_meta"].append(dict(base["run_meta"], file=base_path.name))
    if base.get("notes") or base.get("extras"):
        blk["followups"][base_path.name] = {k: base[k] for k in ("notes", "extras") if base.get(k)}
    skey = lambda r: norm_text(r["institution"])
    ctx.counts["screening_rows_in"] += len(base.get("screening", []))
    for row in base.get("screening", []):
        upsert_by(blk["screening"], row, skey)
    blk["ranked_out"] = list(base.get("ranked_out", []))
    blk["corrections_to_prior"] = list(base.get("corrections_to_prior", []))
    cands = [copy.deepcopy(c) for c in base.get("candidates", [])]
    ctx.counts["candidates_in"] += len(cands)

    fu_paths = followups_for(run_dir, slug) if kind == "country" else []
    for fp in fu_paths:
        fu = load_validated(fp, "country_run_file", ctx)
        if fu is None:
            continue
        check_status(fu, fp.name, ctx, allow_partial)
        blk["followup_files"].append(fp.name)
        blk["status_effective"] = fu["status"]            # the latest pass describes the current state
        blk["path_b_done"] = blk["path_b_done"] or bool(fu.get("path_b_done"))
        extras = {k: fu[k] for k in ("notes", "extras", "budget_notes", "status", "run_date", "followup_of") if k in fu}
        blk["followups"][fp.name] = extras
        if fu.get("budget_notes"):
            blk["budget_notes"] = (blk["budget_notes"] + f"\n[{fp.name}] " + fu["budget_notes"]).strip()
        if fu.get("run_meta"):
            blk["run_meta"].append(dict(fu["run_meta"], file=fp.name))
        ctx.counts["screening_rows_in"] += len(fu.get("screening", []))
        for row in fu.get("screening", []):
            upsert_by(blk["screening"], row, skey)
        blk["ranked_out"] += fu.get("ranked_out", [])
        blk["corrections_to_prior"] += [c for c in fu.get("corrections_to_prior", []) if c not in blk["corrections_to_prior"]]
        blk["searched_not_surfaced"] += [g for g in fu.get("searched_not_surfaced", []) if g not in blk["searched_not_surfaced"]]
        if fu.get("country_context"):
            blk["country_context"]["additions"].append({"source": fp.name, "context": fu["country_context"]})
        if fu.get("country_summary"):
            blk["country_summary"] = (blk["country_summary"] + f"\n\n[Follow-up {fp.name}] " + fu["country_summary"]).strip()
        for d in fu.get("urgent_deadlines", []):
            if d not in blk["urgent_deadlines"]:
                blk["urgent_deadlines"].append(d)
        for p in fu.get("path_b_people", []):
            upsert_by(blk["path_b_people"], p, lambda r: norm_text(r["name"]))
        blk["still_open"] += [s for s in fu.get("still_open", []) if s not in blk["still_open"]]
        ctx.counts["candidates_in"] += len(fu.get("candidates", []))
        for rec in fu.get("candidates", []):
            rec = copy.deepcopy(rec)
            target = rec.get("replaces")
            if target:
                idx = next((i for i, c in enumerate(cands) if c["id"] == target), None)
                if idx is None:
                    ctx.issue("error", "replace_target_missing", f"{rec['id']} in {fp.name} replaces {target}, which does not exist; appended as a NEW record", rec["id"])
                    cands.append(rec)
                    continue
                old = cands[idx]
                rec["_followup_id"] = rec["id"]
                rec["_replaces"] = target
                rec["_replaced_first_pass_vector"] = old.get("state_vector")
                rec["id"] = target                     # keep the ORIGINAL id so references stay valid
                if not rec.get("prior_id") and old.get("prior_id"):
                    rec["prior_id"] = old["prior_id"]
                    rec["status"] = old["status"]
                cands[idx] = rec
                ctx.counts["replaced"] += 1
            else:
                idx = next((i for i, c in enumerate(cands) if c["id"] == rec["id"]), None)
                if idx is not None:
                    ctx.issue("error", "duplicate_id", f"{rec['id']} in {fp.name} reuses an existing id without `replaces`; the later record wins", rec["id"])
                    cands[idx] = rec
                else:
                    cands.append(rec)

    # ranked_out: later entry wins, then purge anything that became a full record (promotion)
    ro_key = lambda r: (norm_text(r["institution"]), norm_text(r["programme"]))
    deduped: list[dict] = []
    for r in blk["ranked_out"]:
        upsert_by(deduped, r, ro_key)
    full = {(norm_text(c["institution"]), norm_text(c["programme"])) for c in cands}
    kept = [r for r in deduped if ro_key(r) not in full]
    ctx.counts["ranked_out_purged"] += len(deduped) - len(kept)
    # Promotions are often renamed ("MSc X" -> "MSc X, track Y"), so exact matching misses some.
    # Flag (never purge) ranked-out entries that look almost identical to a full record.
    for r in kept:
        k = norm_text(r["institution"]) + " " + norm_text(r["programme"])
        for c in cands:
            if difflib.SequenceMatcher(None, k, norm_text(c["institution"]) + " " + norm_text(c["programme"])).ratio() >= 0.9:
                ctx.issue("info", "stale_ranked_out_suspect", f"ranked_out '{r['institution']} | {r['programme']}' resembles full record {c['id']} - promoted? remove by hand if so", slug)
                break
    blk["ranked_out"] = kept
    ctx.counts["screening_rows_out"] += len(blk["screening"])
    for c in cands:
        c["_country_slug"] = slug
        c["_origin"] = {"kind": kind, "slug": slug}
    blk["candidate_ids"] = [c["id"] for c in cands]
    return blk, cands


def apply_overrides(cands: list[dict], run_dir: Path, ctx: Ctx) -> tuple[list[dict], list[dict]]:
    path = rp(run_dir, "overrides")
    if not path.exists():
        return [], []
    ovs = load_validated(path, "override", ctx)
    if ovs is None:
        return [], []
    by_id = {c["id"]: c for c in cands}
    applied, unmatched = [], []
    for ov in ovs:
        c = by_id.get(ov["target_id"])
        if c is None:
            ctx.issue("error", "override_target_missing", f"override for {ov['target_id']} ({ov['field']}) matches no record - decision NOT applied", ov["target_id"])
            unmatched.append(ov)
            continue
        try:
            found = get_path(c, ov["field"])
        except (KeyError, IndexError, ValueError, TypeError):
            found = None
        if found != ov["original_value"]:
            ctx.issue("warning", "override_original_mismatch",
                      f"{ov['target_id']}.{ov['field']}: override expected {ov['original_value']!r} but found {found!r}; applied anyway (may be stale)", ov["target_id"])
        try:
            set_path(c, ov["field"], ov["new_value"])
        except (KeyError, IndexError, ValueError, TypeError, AttributeError) as e:
            ctx.issue("error", "override_bad_path", f"{ov['target_id']}.{ov['field']}: cannot set ({e})", ov["target_id"])
            unmatched.append(ov)
            continue
        rec = {"field": ov["field"], "original_value": found, "declared_original_value": ov["original_value"], "new_value": ov["new_value"],
               "reason": ov["reason"], "decided_by": ov["decided_by"], "date": ov["date"]}
        c.setdefault("_overrides_applied", []).append(rec)
        applied.append(dict(rec, target_id=ov["target_id"]))
        errs = validate({k: v for k, v in c.items()}, "candidate_record")
        if errs:
            ctx.issue("error", "override_invalid_result", f"{ov['target_id']} invalid after override: {errs[0].path}: {errs[0].message}", ov["target_id"])
    return applied, unmatched


def dedupe_exact(cands: list[dict], ctx: Ctx) -> tuple[list[dict], list[dict]]:
    groups: dict[str, list[dict]] = {}
    for c in cands:
        groups.setdefault(record_key(c), []).append(c)
    dropped, report = set(), []
    for key, grp in groups.items():
        if len(grp) < 2:
            continue
        # Keep the record with the most sources; on ties prefer country origin over cross-cut, then lowest id.
        grp.sort(key=lambda c: (-len(c.get("sources", [])), c["_origin"]["kind"] == "crosscut", c["id"]))
        keeper = grp[0]
        keeper["_also_listed_as"] = [g["id"] for g in grp[1:]]
        for g in grp[1:]:
            dropped.add(id(g))
            report.append({"kept": keeper["id"], "dropped": g["id"], "key": key})
            ctx.issue("warning", "exact_duplicate", f"{g['id']} duplicates {keeper['id']} ({key}); dropped", g["id"])
    return [c for c in cands if id(c) not in dropped], report


def near_duplicates(cands: list[dict], baseline: list[dict], thr: float) -> list[dict]:
    """Flag-only similarity report. quick_ratio()/real_quick_ratio() are cheap upper bounds that
    let us skip most pairs before the expensive ratio() call (matters for hundreds of records)."""
    keys = [(c["id"], norm_text(c["institution"]) + " " + norm_text(c["programme"]), norm_text(c.get("track"))) for c in cands]
    out = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            sm = difflib.SequenceMatcher(None, keys[i][1], keys[j][1])
            if sm.real_quick_ratio() < thr or sm.quick_ratio() < thr:
                continue
            r = sm.ratio()
            if r >= thr:
                out.append({"a": keys[i][0], "b": keys[j][0], "ratio": round(r, 3), "same_track": keys[i][2] == keys[j][2]})
    by_id = {c["id"]: c for c in cands}
    for c in cands:
        if c.get("status") != "net_new":
            continue
        k = norm_text(c["institution"]) + " " + norm_text(c["programme"])
        for b in baseline:
            if difflib.SequenceMatcher(None, k, norm_text(b.get("label"))).ratio() >= thr:
                out.append({"a": c["id"], "b": "baseline:" + b["id"], "ratio": round(difflib.SequenceMatcher(None, k, norm_text(b.get("label"))).ratio(), 3), "same_track": False})
                by_id[c["id"]]["_possible_duplicate_of"] = b["id"]
    return out


def baseline_delta(cands: list[dict], rows: list[dict]) -> tuple[dict, list[str]]:
    by_id = {r["id"]: r for r in rows}
    stats = {ax: {"same": 0, "up": 0, "down": 0, "filled_from_unknown": 0, "lost_to_unknown": 0} for ax in AXES}
    revisited = set()
    n = 0
    for c in cands:
        pid = c.get("prior_id")
        if not pid or pid not in by_id:
            continue
        revisited.add(pid)
        n += 1
        delta = {}
        for ax in AXES:
            old, new = score_int(by_id[pid].get(ax)), score_int(c["state_vector"].get(ax))
            if old is None and new is None:
                continue
            if old is None:
                stats[ax]["filled_from_unknown"] += 1
            elif new is None:
                stats[ax]["lost_to_unknown"] += 1
            elif new > old:
                stats[ax]["up"] += 1
            elif new < old:
                stats[ax]["down"] += 1
            else:
                stats[ax]["same"] += 1
            if by_id[pid].get(ax) != c["state_vector"].get(ax):
                delta[ax] = [by_id[pid].get(ax), c["state_vector"].get(ax)]
        if delta:
            c["_delta_vs_baseline"] = delta
    not_revisited = [r["id"] for r in rows if r.get("in_scope", not r.get("benchmark", False)) and r["id"] not in revisited]
    return {"revisited_records": n, "axes": stats}, not_revisited


def check_planned(run_dir: Path, countries: dict, crosscuts: dict, ctx: Ctx, allow_partial: bool) -> None:
    """Every country / cross-cut in search_plan.json needs a file (see module docstring)."""
    plan_path = rp(run_dir, "search_plan")
    if not plan_path.exists():
        return
    try:
        plan = load_json(plan_path)
    except UsageError:
        return                                   # validate.py reports an unreadable plan
    have_files = {p.stem for p in list_json(rp(run_dir, "countries_dir"))} | {p.stem for p in list_json(rp(run_dir, "crosscuts_dir"))}
    missing = 0
    for kind, entries in (("country", plan.get("countries", [])), ("cross-cut", plan.get("crosscuts", []))):
        for e in entries if isinstance(entries, list) else []:
            slug = e.get("slug") if isinstance(e, dict) else None
            if slug and slug not in have_files:
                missing += 1
                ctx.issue("warning" if allow_partial else "error", "planned_country_missing",
                          f"search_plan lists {kind} '{slug}' but 04_search has no file for it; it is NOT in the merge", slug)
    ctx.counts["planned_missing"] = missing


def merge(run_dir: Path, baseline_path: Path | None, allow_partial: bool, near_thr: float, now: str | None = None) -> tuple[dict, dict]:
    ctx = Ctx()
    countries: dict[str, dict] = {}
    crosscuts: dict[str, dict] = {}
    cands: list[dict] = []

    for p in list_json(rp(run_dir, "countries_dir")):
        res = fold_country(run_dir, p, ctx, allow_partial)
        if res:
            countries[p.stem], c = res[0], res[1]
            cands += c
    # follow-ups whose base file is missing would otherwise vanish silently
    claimed = {fp for q in list_json(rp(run_dir, "countries_dir")) for fp in followups_for(run_dir, q.stem)}
    for p in list_json(rp(run_dir, "followups_dir")):
        if p not in claimed:
            ctx.issue("error", "orphan_followup", f"{p.name} has no base country file", p.name)

    for p in list_json(rp(run_dir, "crosscuts_dir")):
        try:
            raw = load_json(p)
        except UsageError as e:
            ctx.issue("error", "unreadable_file", str(e), p.name)
            continue
        if isinstance(raw, dict) and raw.get("crosscut_kind") == "funding_route":
            doc = load_validated(p, "funding_route_crosscut", ctx)
            if doc is not None:
                check_status(doc, p.name, ctx, allow_partial)
                crosscuts[p.stem] = dict(doc, kind="funding_route")
        else:
            res = fold_country(run_dir, p, ctx, allow_partial, kind="crosscut")
            if res:
                blk, c = res
                cands += c
                raw_doc = {k: v for k, v in raw.items() if k not in ("candidates",)}
                crosscuts[p.stem] = dict(raw_doc, kind="programme_scan", candidate_ids=blk["candidate_ids"], status_effective=blk["status_effective"])

    check_planned(run_dir, countries, crosscuts, ctx, allow_partial)
    applied, unmatched = apply_overrides(cands, run_dir, ctx)
    cands, exact = dedupe_exact(cands, ctx)

    baseline_rows: list[dict] = []
    if baseline_path:
        bl = load_validated(baseline_path, "baseline_ledger", ctx)
        baseline_rows = bl["rows"] if bl else []
    near = near_duplicates(cands, baseline_rows, near_thr)
    for n in near:
        ctx.issue("info", "near_duplicate", f"{n['a']} ~ {n['b']} (ratio {n['ratio']}{', same track' if n.get('same_track') else ''}) - human check", n["a"])
    delta, not_revisited = baseline_delta(cands, baseline_rows) if baseline_rows else (None, [])

    for c in cands:
        sv = c["state_vector"]
        c["_total"] = vector_total(sv)
        c["_unscored_axes"] = unscored_axes(sv)
    cands.sort(key=rank_sort_key)
    for i, c in enumerate(cands, 1):
        c["_rank"] = i
    unscored = sum(1 for c in cands if c["_unscored_axes"])
    if unscored:
        ctx.issue("info", "unscored_axes", f"{unscored} record(s) have at least one '?' axis; their _total is understated", "")

    bm_path = rp(run_dir, "benchmarks")
    benchmarks = load_validated(bm_path, "benchmarks", ctx) if bm_path.exists() else None
    state_path = rp(run_dir, "run_state")
    run_id = load_json(state_path).get("run_id") if state_path.exists() else None
    stamp = now or now_iso()
    merged = {
        "generated": stamp, **({"run_id": run_id} if run_id else {}), "protocol_version": PROTOCOL_VERSION,
        "countries": countries, "crosscuts": crosscuts, "candidates": cands, "prior_not_revisited": not_revisited,
        "benchmarks": benchmarks, "overrides_applied": applied, "baseline_used": str(baseline_path) if baseline_path else None}
    report = {
        "generated": stamp, "ok": not any(i["level"] == "error" for i in ctx.issues),
        "counts": dict(ctx.counts, candidates_out=len(cands), exact_duplicates_dropped=len(exact), near_duplicates=len(near),
                       overrides_applied=len(applied), unscored_records=unscored),
        "issues": ctx.issues, "exact_duplicates_dropped": exact, "near_duplicates": near, "overrides_applied": applied,
        "overrides_unmatched": unmatched, "delta_vs_baseline": delta,
        "countries": {s: {"status": b["status"], "status_effective": b["status_effective"], "followup_files": b["followup_files"], "records": len(b["candidate_ids"])}
                      for s, b in countries.items()}}
    return merged, report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Merge country files, follow-ups and cross-cuts (see module docstring).")
    ap.add_argument("run_dir")
    ap.add_argument("--baseline", help="baseline_ledger.json for deltas (optional)")
    ap.add_argument("--allow-partial", action="store_true", help="merge files whose status is in_progress (warning instead of error)")
    ap.add_argument("--near-dup", type=float, default=0.75, help="difflib ratio for the flag-only near-duplicate report")
    ap.add_argument("--now", help="timestamp to stamp into outputs (tests)")
    a = ap.parse_args(argv)
    run_dir = Path(a.run_dir)
    try:
        if not run_dir.is_dir():
            raise UsageError(f"RUN_DIR not found: {run_dir}")
        merged, report = merge(run_dir, Path(a.baseline) if a.baseline else None, a.allow_partial, a.near_dup, a.now)
        for doc, schema in ((merged, "merged_file"), (report, "merge_report")):
            errs = validate(doc, schema)
            if errs:
                print(f"INTERNAL: {schema} output invalid: {errs[0].path}: {errs[0].message}", file=sys.stderr)
                return EXIT_PROBLEMS
        atomic_write_json(rp(run_dir, "merged"), merged)
        atomic_write_json(rp(run_dir, "merge_report"), report)
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    c = report["counts"]
    print(f"merged {c['candidates_out']} records from {c['files_read']} file(s): replaced={c['replaced']} exact_dupes={c['exact_duplicates_dropped']} "
          f"near_dupes={c['near_duplicates']} overrides={c['overrides_applied']} ranked_out_purged={c['ranked_out_purged']}")
    for i in report["issues"]:
        if i["level"] != "info":
            print(f"  [{i['level']}] {i['code']}: {i['message']}")
    return EXIT_OK if report["ok"] else EXIT_PROBLEMS


if __name__ == "__main__":
    sys.exit(main())
