#!/usr/bin/env python3
"""
followups.py - decide which countries need another agent pass, and which do NOT.

PURPOSE
    Agent budgets, not search difficulty, decided coverage in the reference run. The
    orchestrator therefore needs a repeatable answer to "where is the evidence still
    thin?" and an equally explicit answer to "where would more work change nothing?"
    (protocol/sessions/s7_triage.md). This script computes both from the files in RUN_DIR
    (it folds first-pass + follow-up files in memory using merge.py, so you can run it
    BEFORE the final merge).

TRIGGERS (one entry per country and type)
    budget_exhausted          effective status is in_progress or partial_budget_exhausted
    complete_with_gaps        effective status is complete_with_gaps
    path_b_missing            path_b_done is false (the people/partner-first path, Path B, never ran)
    unscored_axis             a top-N record has a '?' axis      (N = --top-n, else the plan's cap_n, else 8)
    promote_flag              a ranked_out entry has promote=true
    deadline_soon             a record deadline falls within --deadline-days (default 60) of --today
    suspected_false_negative  a screening row says fail with a reason that reads like missing
                              EVIDENCE rather than a judgement on merit (or is 'unscreened'):
                              "no ... found|identified|located|listed|information|evidence|data" (up to
                              30 characters between), could not / cannot / unable, inaccessible, not
                              accessible, 401/403/404, paywall, login, captcha, robots, timeout,
                              blocked, not found, failed to load, no response, unverified
                              (case-insensitive; see FALSE_NEG_RE)
    "Effective status" is the status of the LATEST file for the country, so a follow-up that
    finished the job removes the trigger.

STOP RULE ("the decision cannot flip")
    For every country with at least one trigger, suggest decision=no_followup when
      max achievable funding score (full records + ranked_out) < the plan's minimum funding score
      AND no record (full or ranked_out) has pathway >= 2.
    Then even a perfect follow-up could not produce a record the person would pick.
    '?' is treated conservatively by default: an unknown funding score COULD be 3 and an unknown
    pathway score COULD be >= 2, so the rule will not fire while such unknowns exist. Use
    --unknowns ignore for the literal reading (unknown = absent).
    The minimum comes from --min-funding, else search_plan.funded_definition.min_funding_score,
    else a DEFAULT PER FUNDED TYPE (DEFAULT_MIN below):
        stipend_and_tuition -> 3   (tuition-free AND a stipend: only a 3 is "funded")
        tuition_only        -> 2   (tuition covered; living costs paid by the person)
        affordable          -> 1   (the person pays, below a ceiling)
    The value used and where it came from are printed on stderr ("min funding score: 2 (source:
    ...)") and stored in the output as params.min_funding_score / params.min_funding_source. The
    output is a SUGGESTION: the orchestrator confirms it (write it in orchestrator_notes.md).

OUTPUT
    JSON on stdout (schema: followup_trigger). With --write also 04_search/followup_plan.json.

USAGE
    python3 scripts/followups.py RUN_DIR [--today YYYY-MM-DD] [--deadline-days 60] [--top-n N]
                                         [--min-funding 0-3] [--unknowns conservative|ignore] [--write]

EXIT CODES
    0 ok (triggers are information, not failure) | 2 usage error
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import merge as merge_mod  # noqa: E402
from _common import (EXIT_OK, EXIT_USAGE, UsageError, atomic_write_json, cap_n_of, load_json, now_iso,  # noqa: E402
                     parse_date, rank_sort_key, rp, score_int, today_iso, validate)

# Wording that signals missing EVIDENCE (the agent could not look) rather than a judgement on MERIT.
# WHY broad: a false alarm costs one extra check, a missed false negative can hide the best option.
# Bare phrases that are often a merit judgement ("not available to ...") are deliberately NOT included.
FALSE_NEG_RE = re.compile(
    r"\bno\b.{0,30}(?:found|identified|located|listed|information|evidence|data|public)"
    r"|could ?n[o']t|\bcannot\b|\bcan't\b|unable|inaccessible|not (?:publicly )?accessible|not (?:publicly )?(?:available|published) online"
    r"|\b40[134]\b|paywall|log-?in|sign-?in required|captcha|robots|time[sd]? ?out|blocked|not found|failed to (?:load|fetch|open)|no response|unverified",
    re.I)
DEFAULT_MIN = {"stipend_and_tuition": 3, "tuition_only": 2, "affordable": 1}


def plan_info(run_dir: Path) -> tuple[dict, int | None, str]:
    """Return ({slug: cap_n}, min_funding_score or None, source text) from search_plan.json."""
    p = rp(run_dir, "search_plan")
    if not p.exists():
        return {}, None, "no search plan"
    plan = load_json(p)
    caps = {c["slug"]: cap_n_of(c) for c in plan.get("countries", [])}
    fd = plan.get("funded_definition") or {}
    if fd.get("min_funding_score") is not None:
        return caps, fd["min_funding_score"], "search_plan.funded_definition.min_funding_score"
    if fd.get("type") in DEFAULT_MIN:
        return caps, DEFAULT_MIN[fd["type"]], f"default for funded type {fd['type']}"
    return caps, None, "not set"


def max_funding(records: list[dict], vec_of, unknowns: str) -> int:
    vals = []
    for r in records:
        v = vec_of(r).get("funding")
        if score_int(v) is not None:
            vals.append(v)
        elif unknowns == "conservative":
            vals.append(3)
    return max(vals, default=0)


def has_pathway_ge2(records: list[dict], vec_of, unknowns: str) -> bool:
    for r in records:
        v = vec_of(r).get("pathway")
        if score_int(v) is not None and v >= 2:
            return True
        if score_int(v) is None and unknowns == "conservative":
            return True
    return False


def compute(run_dir: Path, today: dt.date, deadline_days: int, top_n: int | None, min_funding: int | None, unknowns: str) -> dict:
    merged, _ = merge_mod.merge(run_dir, None, allow_partial=True, near_thr=1.01)  # 1.01 disables the O(n^2) near-dup scan
    caps, plan_min, min_source = plan_info(run_dir)
    if min_funding is None:
        min_funding = plan_min
    else:
        min_source = "--min-funding"
    by_country: dict[str, list[dict]] = {}
    for c in merged["candidates"]:
        by_country.setdefault(c["_country_slug"], []).append(c)

    triggers: list[dict] = []
    add = lambda slug, typ, detail, ids=(): triggers.append({"country": slug, "trigger_type": typ, "detail": detail, "record_ids": list(ids)})

    units = dict(merged["countries"])
    for slug, cc in merged["crosscuts"].items():                    # programme-scan cross-cuts behave like countries
        if cc.get("kind") == "programme_scan":
            units[slug] = {"slug": slug, "status_effective": cc.get("status_effective", cc.get("status")), "path_b_done": True,
                           "screening": cc.get("screening", []), "ranked_out": cc.get("ranked_out", []), "budget_notes": "", "kind": "crosscut",
                           "urgent_deadlines": []}
    for slug, blk in sorted(units.items()):
        recs = sorted(by_country.get(slug, []), key=rank_sort_key)
        st = blk["status_effective"]
        if st in ("in_progress", "partial_budget_exhausted"):
            add(slug, "budget_exhausted", f"status={st}. {blk.get('budget_notes', '')[:160]}".strip())
        elif st == "complete_with_gaps":
            add(slug, "complete_with_gaps", "finished with gaps listed in searched_not_surfaced")
        if not blk["path_b_done"]:
            add(slug, "path_b_missing", "people/partner-first path (Path B) has not run for this country")
        n = top_n or caps.get(slug) or 8
        unscored = [r["id"] for r in recs[:n] if r["_unscored_axes"]]
        if unscored:
            add(slug, "unscored_axis", f"{len(unscored)} of the top {n} records have a '?' axis", unscored)
        promote = [f"ranked_out:{r['institution']} | {r['programme']}" for r in blk["ranked_out"] if r.get("promote")]
        if promote:
            add(slug, "promote_flag", f"{len(promote)} ranked-out entr(y/ies) flagged promote=true", promote)
        soon, unconfirmed = [], 0
        for r in recs:
            for d in r.get("deadlines", []):
                dd = parse_date(d["date"])
                if dd and 0 <= (dd - today).days <= deadline_days:
                    soon.append(r["id"])
                    unconfirmed += d["date_type"] != "confirmed"
        for d in blk.get("urgent_deadlines", []):
            dd = parse_date(d["date"])
            if dd and 0 <= (dd - today).days <= deadline_days and d.get("record_id") and d["record_id"] not in soon:
                soon.append(d["record_id"])
                unconfirmed += d["date_type"] != "confirmed"
        if soon:
            add(slug, "deadline_soon", f"{len(soon)} deadline(s) within {deadline_days} days of {today}; {unconfirmed} not 'confirmed' (reconfirm before relying)", sorted(set(soon)))
        sus = [s["institution"] for s in blk["screening"]
               if (s["decision"] == "fail" and FALSE_NEG_RE.search(s.get("reason", ""))) or s["decision"] == "unscreened"]
        if sus:
            add(slug, "suspected_false_negative", f"{len(sus)} institution(s) failed/unscreened for lack of evidence rather than on merit", sus)

    stops = []
    if min_funding is not None:
        for slug in sorted({t["country"] for t in triggers}):
            recs = by_country.get(slug, [])
            ro = units[slug]["ranked_out"]
            vec_c = lambda r: r["state_vector"]
            vec_r = lambda r: r["prelim_state_vector"]
            mf = max(max_funding(recs, vec_c, unknowns), max_funding(ro, vec_r, unknowns))
            p2 = has_pathway_ge2(recs, vec_c, unknowns) or has_pathway_ge2(ro, vec_r, unknowns)
            if mf < min_funding and not p2:
                stops.append({"country": slug, "decision": "no_followup",
                              "reason": f"max achievable funding {mf} < plan minimum {min_funding} and no record has pathway >= 2 (unknowns: {unknowns}); a follow-up cannot change the decision",
                              "confirmed_by": ""})
    stopped = {s["country"] for s in stops}
    need = sorted({t["country"] for t in triggers} - stopped)
    return {"generated": now_iso(), "today": today.isoformat(),
            "params": {"top_n": top_n, "deadline_days": deadline_days, "min_funding_score": min_funding, "min_funding_source": min_source, "unknowns": unknowns},
            "triggers": triggers, "stop_rule_decisions": stops, "countries_needing_followup": need}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Emit follow-up triggers and stop-rule suggestions (see module docstring).")
    ap.add_argument("run_dir")
    ap.add_argument("--today", default=today_iso(), help="reference date YYYY-MM-DD (default: today)")
    ap.add_argument("--deadline-days", type=int, default=60)
    ap.add_argument("--top-n", type=int, help="override per-country cap_n for the unscored_axis check")
    ap.add_argument("--min-funding", type=int, choices=range(0, 4), help="override the plan's minimum funding score")
    ap.add_argument("--unknowns", choices=["conservative", "ignore"], default="conservative")
    ap.add_argument("--write", action="store_true", help="also write 04_search/followup_plan.json")
    a = ap.parse_args(argv)
    try:
        run_dir = Path(a.run_dir)
        if not run_dir.is_dir():
            raise UsageError(f"RUN_DIR not found: {run_dir}")
        today = parse_date(a.today)
        if today is None:
            raise UsageError("--today must be YYYY-MM-DD")
        out = compute(run_dir, today, a.deadline_days, a.top_n, a.min_funding, a.unknowns)
        errs = validate(out, "followup_trigger")
        if errs:
            raise UsageError(f"internal: output invalid: {errs[0].path}: {errs[0].message}")
        p = out["params"]
        print(f"min funding score: {p['min_funding_score'] if p['min_funding_score'] is not None else 'none (stop rule off)'} (source: {p['min_funding_source']})", file=sys.stderr)
        if a.write:
            atomic_write_json(rp(run_dir, "followup_plan"), out)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return EXIT_OK
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
