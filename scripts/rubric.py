#!/usr/bin/env python3
"""
rubric.py - compute soft_pct and `passed` for a gate/soft score sheet.

PURPOSE
    The Life & Career Plan (S1, rubric LP-1.0) and the Study & Pathway Map (S2, rubric PM-1.0)
    are each scored against a rubric BEFORE the search is allowed to start ("no gate, no search",
    rule R3): a vague plan produces an expensive, useless search. Virgil does the judgement
    (each gate: pass | declared_unknown | fail with a note; each soft criterion: 0/1/2 with a
    note). It must NOT do the arithmetic. This script does:
      * soft_pct and the pass rule,
      * the per-rubric limits on gates the person may leave open, and
      * mechanical cross-checks of every 'pass' gate against the real files, so that "pass"
        cannot be claimed for an empty section.
    Wording of each gate is in protocol/sessions/s1_life_plan.md and s2_pathway_map.md; the
    checks below implement the "Done when" column of those tables.

INPUTS
    life_plan    -> 01_life_plan/life_plan_score.json (+ checks against life_plan.json)
    pathway_map  -> 02_map/map_score.json (+ checks against study_pathway_map.json and benchmarks.json)

OUTPUT
    The same score file, rewritten with soft_pct, passed, auto_checks and problems.
    Exit code 0 only when the rubric passes.

PASS RULE (limits are per rubric; both come from the protocol modules)
    passed = every expected gate present
             AND every gate is pass or declared_unknown (none fail)
             AND at most MAX_UNKNOWN declared_unknown:  life_plan 2, pathway_map 1
             AND life_plan:  LP-G3 / LP-G4 are NOT declared_unknown unless the person accepted the
                             consequence (gate.user_accepted_consequence=true, or note "ACCEPTED: ...")
             AND pathway_map: PM-G2 / PM-G4 are NEVER declared_unknown (no domains or no benchmarks
                             means there is nothing to search with)
             AND every mechanical check of a 'pass' gate succeeds (otherwise the gate is
                 downgraded to fail and the reason is appended to its note)
             AND the source JSON file is valid against its schema
             AND soft_pct >= 70
    soft_pct = 100 * sum(weight*score) / (2 * sum(weight)) over ALL expected soft criteria
    (maximum 28 for the life plan, 14 for the map); a missing criterion counts as 0.
    Weights come from the tables below, not from the file.

GATES (id name)  and what the mechanical check requires ("Done when" in the protocol)
    LP-G1 purpose_horizon        purpose_horizon.purpose and horizon_years (a number)
    LP-G2 post_degree_intent     post_degree_intent.intent; if routes_open lists more than one route,
                                 keep_open_is is 'requirement' or 'hedge'
    LP-G3 money_operationalised  money.funded_type, currency, debt_acceptable (true/false) and the numbers
                                 its type needs: stipend_and_tuition -> living_support_required_monthly +
                                 household_size; tuition_only -> max_total_tuition; affordable ->
                                 max_out_of_pocket + living_support_required_monthly + household_size
    LP-G4 eligibility_facts      citizenships, residence_country, residence_region (key present, '' allowed),
                                 highest_degree.field/graduation_year/grade/grade_scale, and certificate
                                 status (language_certificates non-empty, or language_certificates_note
                                 says 'none')
    LP-G5 geography_language     geography.considered, teaching_languages_accepted (non-empty); excluded and
                                 languages_willing_c1 present as lists (empty = none)
    LP-G6 timeline               earliest_start, latest_start, immovable_dates list (empty allowed),
                                 wait_one_cycle true/false
    LP-G7 household_dealbreakers household.dependants (a number), partner_moves true/false (and
                                 partner_work_needed if the partner moves), return_obligation_stance other
                                 than 'unknown', deal_breakers list (an explicit empty list means none)
    PM-G1 objective              objective.one_line (a research question, if present, has a status)
    PM-G2 knowledge_domains      5 to 12 domains, each with coverage keywords
    PM-G3 pathway_signals        >= 5 people_topic_signals and >= 2 organisation_type_signals
    PM-G4 benchmarks             exactly 3, one per axis (funding, programme, pathway), real names, a baseline
                                 vector (all-'?' only if provisional AND noted), verified ones with evidence URLs
    PM-G5 scoring_anchors        12 anchors (3 axes x scores 0-3) and a screening rule
    Soft (weight): LP-S1 strengths(1) S2 gaps(2) S3 long_term_role(2) S4 tradeoff_ranking(2) S5 risk_tolerance(1)
                   S6 study_format(1) S7 decision_criteria(2) S8 application_assets(1) S9 assumptions_log(1)
                   S10 lifestyle(1);  PM-S1 nearest_frameworks(1) S2 commitments_non_goals(2)
                   S3 false_positive_traps(1) S4 practical_component(1) S5 connectedness_check(1) S6 progression(1)

USAGE
    python3 scripts/rubric.py RUN_DIR life_plan|pathway_map [--check]
      (--check: print the result but do not write the file back)

EXIT CODES
    0 passed | 1 not passed (the file is still updated and the reasons listed) | 2 usage error
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (AXES, EXIT_OK, EXIT_PROBLEMS, EXIT_USAGE, GATES as GATE_FILES, RUBRIC_VERSION, UsageError,  # noqa: E402
                     atomic_write_json, is_url, load_json, now_iso, rp, validate)

GATES = {
    "life_plan": {"LP-G1": "purpose_horizon", "LP-G2": "post_degree_intent", "LP-G3": "money_operationalised", "LP-G4": "eligibility_facts",
                  "LP-G5": "geography_language", "LP-G6": "timeline", "LP-G7": "household_dealbreakers"},
    "pathway_map": {"PM-G1": "objective", "PM-G2": "knowledge_domains", "PM-G3": "pathway_signals", "PM-G4": "benchmarks", "PM-G5": "scoring_anchors"},
}
SOFT = {
    "life_plan": {"LP-S1": 1, "LP-S2": 2, "LP-S3": 2, "LP-S4": 2, "LP-S5": 1, "LP-S6": 1, "LP-S7": 2, "LP-S8": 1, "LP-S9": 1, "LP-S10": 1},
    "pathway_map": {"PM-S1": 1, "PM-S2": 2, "PM-S3": 1, "PM-S4": 1, "PM-S5": 1, "PM-S6": 1},
}
# Per-rubric limits on gates the person may consciously leave open (declared_unknown).
# WHY different limits: a life plan has 7 gates and two of them (money, eligibility) can be open
# if the person accepts the consequence; the map has 5 and only one may be open, because without
# domains or benchmarks the agents have nothing to search with.
MAX_UNKNOWN = {"life_plan": 2, "pathway_map": 1}
NEEDS_ACCEPTANCE = {"life_plan": {"LP-G3", "LP-G4"}, "pathway_map": set()}
NEVER_UNKNOWN = {"life_plan": set(), "pathway_map": {"PM-G2", "PM-G4"}}
PLACEHOLDER_RE = re.compile(
    r"\btbd\b|\btba\b|\btodo\b|placeholder|to be (?:determined|decided|chosen|selected)|not (?:yet )?(?:run|chosen|selected|scouted|verified|known)|"
    r"scout not run|\bunknown\b|\bn/?a\b|^\W*\?*\W*$|<[^>]*>|\bxxx+\b|\blorem\b", re.I)
PASS_PCT = 70.0
SCHEMA_OF_SOURCE = {"life_plan": ("life_plan", "life_plan"), "pathway_map": ("study_pathway_map", "study_pathway_map")}   # rubric -> (PATHS key, schema)
DOMAIN_RANGE = (5, 12)


def nonempty(v) -> bool:
    return bool(v) if not isinstance(v, (int, float)) else True


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def verdict(miss: list[str], ok_text: str, what: str) -> tuple[bool, str]:
    return (not miss, ok_text if not miss else f"{what} lacks: " + "; ".join(miss))


# --------------------------------------------------------------------------- life plan checks

def check_purpose(ph: dict) -> tuple[bool, str]:
    miss = []
    if not nonempty(ph.get("purpose")):
        miss.append("purpose")
    if not is_num(ph.get("horizon_years")):
        miss.append("horizon_years (a number)")
    return verdict(miss, "purpose_horizon has a purpose and a horizon", "purpose_horizon")


def check_intent(pd: dict) -> tuple[bool, str]:
    miss = []
    if not nonempty(pd.get("intent")):
        miss.append("intent")
    if len(pd.get("routes_open") or []) > 1 and pd.get("keep_open_is") not in ("requirement", "hedge"):
        miss.append("keep_open_is ('requirement' or 'hedge', needed because several routes are open)")
    return verdict(miss, "post_degree_intent has an intent (and keep_open_is when several routes are open)", "post_degree_intent")


def check_money(m: dict) -> tuple[bool, str]:
    miss = []
    ftype = m.get("funded_type")
    if not nonempty(ftype):
        miss.append("funded_type")
    need = {"stipend_and_tuition": ["living_support_required_monthly", "household_size"],
            "tuition_only": ["max_total_tuition"],
            "affordable": ["max_out_of_pocket", "living_support_required_monthly", "household_size"]}.get(ftype, [])
    for k in need:
        if not (is_int(m.get(k)) if k == "household_size" else is_num(m.get(k))):
            miss.append(f"{k} (a number; needed for funded_type '{ftype}')")
    if not nonempty(m.get("currency")):
        miss.append("currency")
    if not isinstance(m.get("debt_acceptable"), bool):
        miss.append("debt_acceptable (true/false)")
    return verdict(miss, "money has funded_type, the numbers its type needs, currency and debt_acceptable", "money")


def check_eligibility(e: dict) -> tuple[bool, str]:
    miss = []
    if not nonempty(e.get("citizenships")):
        miss.append("citizenships")
    if not nonempty(e.get("residence_country")):
        miss.append("residence_country")
    if "residence_region" not in e:
        miss.append("residence_region (write '' if no rule depends on it)")
    hd = e.get("highest_degree") or {}
    for k in ("field", "grade", "grade_scale"):
        if not nonempty(hd.get(k)):
            miss.append(f"highest_degree.{k}")
    if not is_int(hd.get("graduation_year")):
        miss.append("highest_degree.graduation_year")
    certs, note = e.get("language_certificates"), str(e.get("language_certificates_note") or "")
    if not (nonempty(certs) or re.search(r"\bnone\b", note, re.I)):
        miss.append("language certificate status (list them, or write 'none' in language_certificates_note)")
    return verdict(miss, "eligibility_facts has citizenship, residence, degree details and certificate status", "eligibility_facts")


def check_geography(g: dict) -> tuple[bool, str]:
    miss = []
    if not nonempty(g.get("considered")):
        miss.append("considered (the exhaustive list)")
    if not nonempty(g.get("teaching_languages_accepted")):
        miss.append("teaching_languages_accepted")
    for k in ("excluded", "languages_willing_c1"):
        if not isinstance(g.get(k), list):
            miss.append(f"{k} (a list; empty = none)")
    return verdict(miss, "geography has considered countries, accepted languages, exclusions and languages willing to learn", "geography")


def check_timeline(t: dict) -> tuple[bool, str]:
    miss = []
    for k in ("earliest_start", "latest_start"):
        if not nonempty(t.get(k)):
            miss.append(k)
    if not isinstance(t.get("immovable_dates"), list):
        miss.append("immovable_dates (a list; empty = none)")
    if not isinstance(t.get("wait_one_cycle"), bool):
        miss.append("wait_one_cycle (true/false)")
    return verdict(miss, "timeline has earliest/latest start, immovable_dates and wait_one_cycle", "timeline")


def check_household(h: dict) -> tuple[bool, str]:
    miss = []
    if not is_int(h.get("dependants")):
        miss.append("dependants (a number; 0 = none)")
    if not isinstance(h.get("partner_moves"), bool):
        miss.append("partner_moves (true/false; false when there is no partner)")
    elif h["partner_moves"] and not isinstance(h.get("partner_work_needed"), bool):
        miss.append("partner_work_needed (true/false, because the partner moves)")
    if h.get("return_obligation_stance") not in ("acceptable", "unacceptable", "depends"):
        miss.append("return_obligation_stance (acceptable | unacceptable | depends)")
    if not isinstance(h.get("deal_breakers"), list):
        miss.append("deal_breakers (a list; an explicit empty list means none)")
    return verdict(miss, "household states dependants, partner, return-obligation stance and deal-breakers", "household")


# --------------------------------------------------------------------------- pathway map checks

def check_objective(o: dict) -> tuple[bool, str]:
    miss = []
    if not nonempty(o.get("one_line")):
        miss.append("one_line")
    rq = o.get("research_question")
    if rq is not None and not (isinstance(rq, dict) and nonempty(rq.get("text")) and rq.get("status") in ("settled", "working", "exploratory")):
        miss.append("research_question.status (settled | working | exploratory)")
    return verdict(miss, "objective has a one-line statement (and a status for any research question)", "objective")


def check_domains(domains: list[dict]) -> tuple[bool, str]:
    lo, hi = DOMAIN_RANGE
    miss = []
    if not (lo <= len(domains) <= hi):
        miss.append(f"{len(domains)} domains (need {lo}-{hi})")
    bare = [d.get("id", "?") for d in domains if not nonempty(d.get("coverage_keywords"))]
    if bare:
        miss.append("coverage_keywords for " + ", ".join(bare))
    return verdict(miss, f"{len(domains)} knowledge domains, all with coverage keywords", "knowledge_domains")


def check_signals(ps: dict) -> tuple[bool, str]:
    a, b = len(ps.get("people_topic_signals") or []), len(ps.get("organisation_type_signals") or [])
    return (a >= 5 and b >= 2, f"{a} people/topic signals (need >= 5), {b} organisation-type signals (need >= 2)")


def check_benchmarks(bm: list[dict]) -> tuple[bool, str]:
    axes = {x.get("axis") for x in bm}
    problems = []
    if len(bm) != 3 or axes != set(AXES):
        problems.append(f"{len(bm)} benchmarks on axes {sorted(a for a in axes if a)} (need exactly one each for {', '.join(AXES)})")
    for x in bm:
        who = f"{x.get('axis') or '?'} benchmark"
        names = [x.get("institution"), x.get("programme")]
        if not all(nonempty(n) for n in names):
            problems.append(f"{who}: name missing")
        elif any(PLACEHOLDER_RE.search(str(n)) for n in names):
            problems.append(f"{who}: placeholder name {names[0]!r} / {names[1]!r}")
        v = x.get("baseline_vector") or {}
        if all(not isinstance(v.get(a), int) for a in AXES):
            if not (x.get("status") == "provisional" and nonempty(x.get("notes"))):
                problems.append(f"{who}: all-'?' vector (allowed only with status provisional AND a note)")
        if x.get("status") == "verified" and not any(is_url(u) for u in x.get("evidence_urls") or []):
            problems.append(f"{who}: status verified but no http(s) evidence URL")
    return (not problems, "3 benchmarks (one per axis) with real names and vectors" if not problems else "; ".join(problems))


def check_anchors(anch: dict, rule) -> tuple[bool, str]:
    cells = [(anch.get(ax) or {}).get(k) for ax in AXES for k in "0123"]
    ok = all(nonempty(c) for c in cells) and nonempty(rule)
    return (ok, f"{sum(nonempty(c) for c in cells)}/12 anchors filled; screening rule present={nonempty(rule)}")


def mechanical_checks(rubric: str, run_dir: Path) -> dict[str, tuple[bool, str]]:
    """gate id -> (ok, detail), computed from the real files. A missing file makes its checks fail."""
    res: dict[str, tuple[bool, str]] = {}
    if rubric == "pathway_map":
        p = rp(run_dir, "study_pathway_map")
        pm = load_json(p) if p.exists() else {}
        res["PM-G1"] = check_objective(pm.get("objective") or {})
        res["PM-G2"] = check_domains(pm.get("domains") or [])
        res["PM-G3"] = check_signals(pm.get("pathway_signals") or {})
        bp = rp(run_dir, "benchmarks")
        res["PM-G4"] = check_benchmarks(load_json(bp).get("benchmarks", []) if bp.exists() else [])
        res["PM-G5"] = check_anchors(pm.get("scoring_anchors") or {}, (pm.get("screening_rule") or {}).get("description"))
    else:
        p = rp(run_dir, "life_plan")
        lp = load_json(p) if p.exists() else {}
        res["LP-G1"] = check_purpose(lp.get("purpose_horizon") or {})
        res["LP-G2"] = check_intent(lp.get("post_degree_intent") or {})
        res["LP-G3"] = check_money(lp.get("money") or {})
        res["LP-G4"] = check_eligibility(lp.get("eligibility_facts") or {})
        res["LP-G5"] = check_geography(lp.get("geography") or {})
        res["LP-G6"] = check_timeline(lp.get("timeline") or {})
        res["LP-G7"] = check_household(lp.get("household") or {})
    return res


def source_problems(rubric: str, run_dir: Path) -> list[str]:
    """A source file that breaks its schema cannot back a pass (its fields may be mis-typed)."""
    key, schema = SCHEMA_OF_SOURCE[rubric]
    p = rp(run_dir, key)
    if not p.exists():
        return [f"{p.relative_to(run_dir).as_posix()} does not exist"]
    errs = validate(load_json(p), schema)
    return [f"{p.relative_to(run_dir).as_posix()} fails its schema: {errs[0].path or '<root>'}: {errs[0].message}"] if errs else []


def evaluate(doc: dict, rubric: str, run_dir: Path) -> dict:
    problems: list[str] = []
    expected_g, expected_s = GATES[rubric], SOFT[rubric]
    gates = {g["id"]: g for g in doc.get("gates", [])}
    for gid in expected_g:
        if gid not in gates:
            problems.append(f"gate {gid} ({expected_g[gid]}) missing")
            gates[gid] = {"id": gid, "status": "fail", "note": "missing from score sheet"}
    for gid in list(gates):
        if gid not in expected_g:
            problems.append(f"unknown gate {gid} for rubric {rubric}")
            del gates[gid]
    checks = mechanical_checks(rubric, run_dir)
    auto = []
    for gid, (ok, detail) in checks.items():
        g = gates[gid]
        auto.append({"id": gid, "ok": bool(ok), "detail": detail})
        if g["status"] == "pass" and not ok:
            g["status"] = "fail"
            g["note"] = (g.get("note", "") + f" [auto-check failed: {detail}]").strip()
    declared = [g for g in gates.values() if g["status"] == "declared_unknown"]
    for g in gates.values():
        if g["status"] == "fail":
            problems.append(f"{g['id']} ({expected_g[g['id']]}) is fail: {g.get('note', '')}".strip())
    if len(declared) > MAX_UNKNOWN[rubric]:
        problems.append(f"{len(declared)} gates declared_unknown (max {MAX_UNKNOWN[rubric]} for {rubric})")
    for g in declared:
        accepted = g.get("user_accepted_consequence") or str(g.get("note", "")).strip().upper().startswith("ACCEPTED:")
        if g["id"] in NEVER_UNKNOWN[rubric]:
            problems.append(f"{g['id']} ({expected_g[g['id']]}) may never be declared_unknown in the {rubric} rubric")
        elif g["id"] in NEEDS_ACCEPTANCE[rubric] and not accepted:
            problems.append(f"{g['id']} declared_unknown without the person accepting the consequence (set user_accepted_consequence=true)")
    problems += source_problems(rubric, run_dir)
    soft_by = {s["id"]: s for s in doc.get("soft", [])}
    soft_out, num, den = [], 0, 0
    for sid, w in expected_s.items():
        s = soft_by.get(sid)
        if s is None:
            problems.append(f"soft {sid} missing (counted as 0)")
            s = {"id": sid, "weight": w, "score": 0, "note": "missing from score sheet"}
        s = dict(s, weight=w)                       # weights are fixed by the rubric, never by the file
        soft_out.append(s)
        num += w * s["score"]
        den += 2 * w
    pct = round(100.0 * num / den, 1)
    if pct < PASS_PCT:
        problems.append(f"soft_pct {pct} < {PASS_PCT}")
    return {"rubric": rubric, "rubric_version": doc.get("rubric_version", RUBRIC_VERSION),
            "gates": [gates[g] for g in expected_g], "soft": soft_out, "soft_pct": pct, "passed": not problems,
            "scored_at": now_iso(), "auto_checks": auto, "problems": problems}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compute soft_pct / passed for a rubric score sheet.")
    ap.add_argument("run_dir")
    ap.add_argument("rubric", choices=sorted(GATES))
    ap.add_argument("--check", action="store_true", help="do not write the file back")
    a = ap.parse_args(argv)
    try:
        run_dir = Path(a.run_dir)
        path = rp(run_dir, GATE_FILES[a.rubric][0])
        doc = load_json(path)
        if doc.get("rubric") != a.rubric:
            raise UsageError(f"{path.name} has rubric={doc.get('rubric')!r}, expected {a.rubric!r}")
        out = evaluate(doc, a.rubric, run_dir)
        errs = validate(out, "rubric_score")
        if errs:
            raise UsageError(f"score sheet invalid: {errs[0].path}: {errs[0].message}")
        if not a.check:
            atomic_write_json(path, out)
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    print(f"{a.rubric}: soft_pct={out['soft_pct']} passed={out['passed']}")
    for p in out["problems"]:
        print(f"  - {p}")
    return EXIT_OK if out["passed"] else EXIT_PROBLEMS


if __name__ == "__main__":
    sys.exit(main())
