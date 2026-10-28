#!/usr/bin/env python3
"""
due_diligence.py - the one-page "how far can you trust this search?" report.

PURPOSE
    A reader who did not watch the search needs one page that says how wide it was, how
    solid the evidence is, how much was independently checked, what is missing and what is
    about to expire. EVERY number on the page is computed from the run's files - nothing is
    typed by hand - so the page can be regenerated after each follow-up or verification.

INPUTS (under RUN_DIR)
    05_merge/merged.json (+ merge_report.json)      required - run merge.py first
    03_scope/search_plan.json                       optional - caps, funded definition, exclusions
    06_verify/verification.json (+ _sample.json)    optional - independent verification block
    run_state.json                                  optional - alias, run id, mode, sessions (Effort line)
    01_life_plan/life_plan_score.json, 02_map/map_score.json
                                                    optional - rubric versions shown in the header (LP-x / PM-y)
    01_life_plan/life_plan.json                     optional - only `profile_summary` (a public-safe one-liner) is used

OUTPUT
    07_deliverables/due_diligence.md                (override with --out; --stdout prints instead)
    --metrics-json PATH                             writes all computed numbers as JSON

BLOCKS (same order as protocol/templates/due_diligence.md; the numbering is stable)
    1 Scope              2 Coverage funnel      3 Novelty vs prior      4 Benchmark position
    5 Evidence quality   6 Independent verification  7 Known gaps       8 Time sensitivity
    9 Method caveats     then one closing line, Effort.
    The title line is "Search due diligence: run <id> (<date>; protocol v<x>; rubrics LP-<v> / PM-<v>)".

HOW MISSING DATA IS REPORTED
    A metric that needs a field the run did not record (e.g. source_type in data from
    before the field existed) prints "not recorded in <label>" instead of a made-up number.
    --run-label sets <label> (default "this run").

OPTIONS
    --today YYYY-MM-DD      reference date for deadline windows (default today)
    --deadline-days N       window for block 8 (default 90)
    --no-examples           PUBLISH-SAFE mode: aggregates only. Besides dropping free-text examples it
                            replaces country, cross-cut and benchmark names by neutral labels
                            ("Country A", "Cross-cut A", "funding benchmark"; labels follow the size of the
                            country, not its name), withholds the applicant summary, money amounts, exclusion
                            text, record ids and the deadline list. Use it for anything that leaves
                            the workspace; the same applies to --metrics-json.

THE TWO EXTRA LINES
    Header  protocol version and the LP / PM rubric versions (from the two score files).
    Effort  agent runs (sum of run_state.sessions[].agents_run), usage windows (sessions that launched
            agents; the plan's expected_windows is shown as the plan), sessions, sessions that ended in a
            usage limit. Fields the run did not record print as "not recorded in <label>".
    "agent file(s) hit a budget/limit" counts ONLY files with status partial_budget_exhausted or
    with limit_events; a complete_with_gaps file is not a budget hit.

USAGE
    python3 scripts/due_diligence.py RUN_DIR [--today D] [--deadline-days 90] [--out PATH]
                                     [--metrics-json PATH] [--run-label TEXT] [--no-examples] [--stdout]

EXIT CODES
    0 written | 2 usage error (merged.json missing ...)
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import followups as followups_mod  # noqa: E402
from _common import (AXES, EXIT_OK, EXIT_USAGE, UsageError, atomic_write_text, cap_n_of, exclusion_text, is_url,  # noqa: E402
                     load_json, parse_date, rp, score_int, today_iso, vector_total)

BLOCKED_RE = re.compile(r"block|403|paywall|captcha|unreachable|could not be (?:fetched|opened)", re.I)


def pct(n: int, d: int) -> float | None:
    return round(100.0 * n / d, 1) if d else None


def fmt_pct(v: float | None, label: str = "n/a") -> str:
    return label if v is None else f"{v:g}%"


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def all_urls(c: dict) -> list[str]:
    """Every http(s) URL cited by a record. Descriptive text in a url field is NOT counted."""
    urls = [s.get("url") for s in c.get("sources", [])]
    for g in (c.get("axis_2_pathway") or {}).get("people_and_partners", []):
        urls.append(g.get("url"))
        urls += [f.get("url") for f in g.get("contacts", [])]
    urls.append((c.get("language") or {}).get("source_url"))
    urls += [r.get("url") for r in (c.get("funding") or {}).get("routes", [])]
    urls += [d.get("source_url") for d in c.get("deadlines", [])]
    return [u for u in urls if is_url(u)]


def compute_metrics(run_dir: Path, today, deadline_days: int, label: str, examples: bool) -> dict:
    mp = rp(run_dir, "merged")
    if not mp.exists():
        raise UsageError("05_merge/merged.json not found - run merge.py first")
    merged = load_json(mp)
    report = load_json(rp(run_dir, "merge_report")) if rp(run_dir, "merge_report").exists() else {}
    plan = load_json(rp(run_dir, "search_plan")) if rp(run_dir, "search_plan").exists() else {}
    state = load_json(rp(run_dir, "run_state")) if rp(run_dir, "run_state").exists() else {}
    lp = load_json(rp(run_dir, "life_plan")) if rp(run_dir, "life_plan").exists() else {}
    cands = merged["candidates"]
    caps = {c["slug"]: cap_n_of(c) for c in plan.get("countries", [])}
    depths = {c["slug"]: c.get("depth") for c in plan.get("countries", [])}
    names = {c["slug"]: c["name"] for c in plan.get("countries", []) + plan.get("crosscuts", [])}

    # ---- 1 scope
    bms = []
    for b in ((merged.get("benchmarks") or {}).get("benchmarks") or []):
        v = b["baseline_vector"]
        bms.append({"axis": b["axis"], "institution": b["institution"], "programme": b["programme"],
                    "vector": [v["funding"], v["programme"], v["pathway"]], "total": vector_total(v), "status": b["status"]})
    scope = {"run_id": state.get("run_id") or merged.get("run_id"), "applicant_alias": state.get("applicant_alias"), "profile_summary": lp.get("profile_summary"), "mode": state.get("mode"),
             "protocol_version": merged.get("protocol_version"), "countries": len(merged["countries"]),
             "country_names": [b["country"] for b in merged["countries"].values()],
             "crosscuts": len(merged["crosscuts"]), "crosscut_kinds": dict(collections.Counter(c.get("kind") for c in merged["crosscuts"].values())),
             "funded_definition": plan.get("funded_definition"), "exclusions": [exclusion_text(x) for x in plan.get("exclusions", [])], "benchmarks": bms}

    # ---- header + effort (run_state sessions; rubric versions from the two score files)
    def score_version(key):
        pth = rp(run_dir, key)
        return load_json(pth).get("rubric_version") if pth.exists() else None
    rv_all = collections.Counter(c["state_vector"].get("rubric_version") for c in cands)
    header = {"protocol_version": merged.get("protocol_version") or state.get("protocol_version"),
              "life_plan_rubric_version": score_version("life_plan_score"), "pathway_map_rubric_version": score_version("map_score"),
              "state_vector_rubric_versions": sorted(str(k) for k in rv_all if k)}
    # Effort: run_state.sessions has one entry per usage window / sitting. A "usage window" here is a
    # session that launched agents (agents_run recorded); interviews are sessions but not windows.
    sess = state.get("sessions") or []
    ag = [x["agents_run"] for x in sess if x.get("agents_run") is not None]
    planned_windows = sum((w.get("expected_windows") or 0) for w in (plan.get("session_plan") or {}).get("waves", []))
    effort = {"sessions": len(sess) or None, "limit_hits": sum(bool(x.get("limit_hit")) for x in sess) if sess else None,
              "agent_runs": sum(ag) if ag else None, "usage_windows": len(ag) or None, "approximate": False,
              "waves_logged": sorted({x["wave"] for x in sess if x.get("wave")}),
              "planned_windows": planned_windows or None, "agents_per_window_observed": state.get("agents_per_window_observed")}

    # ---- 2 funnel
    try:
        trig = followups_mod.compute(run_dir, today, 60, None, None, "conservative")
        open_trig = collections.Counter(t["country"] for t in trig["triggers"] if t["trigger_type"] != "deadline_soon")
        trig_stops = trig["stop_rule_decisions"]
        stopped = {s["country"] for s in trig_stops}
    except Exception:                       # the funnel must still render if follow-up analysis fails
        open_trig, stopped, trig_stops = collections.Counter(), set(), []
    rows = []
    for slug, b in list(merged["countries"].items()) + [(s, c) for s, c in merged["crosscuts"].items() if c.get("kind") == "programme_scan"]:
        scr = b.get("screening", [])
        dec = collections.Counter(s["decision"] for s in scr)
        recs = [c for c in cands if c["_country_slug"] == slug]
        ff = b.get("followup_files", [])
        stop = next((x["reason"] for x in trig_stops if x["country"] == slug), None)
        rows.append({"slug": slug, "name": b.get("country") or names.get(slug, slug), "kind": b.get("kind", "crosscut"), "depth": depths.get(slug), "screened": len(scr), "pass": dec["pass"], "fail": dec["fail"],
                     "unscreened": dec["unscreened"], "records": len(recs), "ranked_out": len(b.get("ranked_out", [])), "cap": caps.get(slug),
                     "cap_reached": bool(caps.get(slug)) and len(recs) >= caps[slug], "followup_files": len(ff), "open_triggers": open_trig.get(slug, 0),
                     "no_followup_suggested": slug in stopped, "stop_reason": stop, "status": b.get("status_effective") or b.get("status")})
    tot = lambda k: sum(r[k] for r in rows)
    ro_total = tot("ranked_out")
    funnel = {"screened_unique": tot("screened"), "screened_raw_rows": (report.get("counts") or {}).get("screening_rows_in"),
              "pass": tot("pass"), "fail": tot("fail"), "unscreened": tot("unscreened"), "full_records": len(cands), "ranked_out": ro_total,
              "programme_level_entries": len(cands) + ro_total, "per_country": rows}

    # ---- 3 novelty
    st = collections.Counter(c["status"] for c in cands)
    corrections = sum(len(b.get("corrections_to_prior", [])) for b in merged["countries"].values())
    novelty = {"net_new": st["net_new"], "update_of_existing": st["update_of_existing"], "reconfirmed": st["reconfirmed"], "corrections_to_prior": corrections,
               "prior_not_revisited": len(merged.get("prior_not_revisited", [])), "baseline_used": bool(merged.get("baseline_used")),
               "delta_vs_baseline": (report.get("delta_vs_baseline") or None)}

    # ---- 4 benchmark position
    totals = [c["_total"] for c in cands if c.get("_total") is not None]
    bt = [b["total"] for b in bms if b["total"] is not None]
    bmax = max(bt) if bt else None
    bench = {"benchmark_totals": bt, "benchmark_max_total": bmax, "records_ge_benchmark_max": sum(t >= bmax for t in totals) if bmax is not None else None,
             "records_gt_benchmark_max": sum(t > bmax for t in totals) if bmax is not None else None, "max_total": max(totals, default=None),
             "records_funding_3": sum(c["state_vector"]["funding"] == 3 for c in cands), "records_programme_3": sum(c["state_vector"]["programme"] == 3 for c in cands),
             "records_pathway_3": sum(c["state_vector"]["pathway"] == 3 for c in cands),
             "total_histogram": dict(sorted(collections.Counter(totals).items())),
             "axis_distribution": {ax: {str(k): v for k, v in sorted(collections.Counter(str(c["state_vector"][ax]) for c in cands).items())} for ax in AXES},
             "top": [{"id": c["id"], "total": c["_total"], "vector": [c["state_vector"][a] for a in AXES]} for c in cands[:5]]}

    # ---- 5 evidence
    # "Route" = a named person at a group/partner and whether students of THIS programme can reach them.
    fac = collections.Counter(f["takes_students"] for c in cands for g in c["axis_2_pathway"]["people_and_partners"] for f in g["contacts"])
    routes = collections.Counter(r["applicant_eligible"] for c in cands for r in c["funding"]["routes"])
    srcs = [s for c in cands for s in c["sources"]]
    typed = [s for s in srcs if s.get("source_type")]
    dated = [s for s in srcs if s.get("accessed_date")]
    urls = {u for c in cands for u in all_urls(c)}
    nulls = collections.Counter(s["claim_field"] for s in srcs if not is_url(s.get("url")))      # only http(s) counts as a URL
    oq = [len(c["open_questions"]) for c in cands]
    evidence = {"route_entries": sum(fac.values()), "takes_students": dict(fac), "pct_routes_confirmed": pct(fac["confirmed"], sum(fac.values())),
                "pct_routes_verification_needed": pct(fac["verification_needed"], sum(fac.values())),
                "funding_routes": sum(routes.values()), "funding_eligibility": dict(routes), "pct_funding_eligibility_confirmed": pct(routes["confirmed"], sum(routes.values())),
                "source_entries": len(srcs), "null_sources": sum(nulls.values()), "pct_null_sources": pct(sum(nulls.values()), len(srcs)), "null_by_claim_field": dict(nulls),
                "source_type_recorded": len(typed), "pct_official": pct(sum(s["source_type"] == "official" for s in typed), len(typed)) if typed else None,
                "pct_aggregator": pct(sum(s["source_type"] == "aggregator" for s in typed), len(typed)) if typed else None,
                "accessed_date_recorded": len(dated), "distinct_urls": len(urls), "distinct_domains": len({domain_of(u) for u in urls}),
                "mean_open_questions": round(sum(oq) / len(oq), 1) if oq else None,
                "records_with_unscored_axis": sum(1 for c in cands if c["_unscored_axes"])}

    # ---- 6 verification
    ver_p, samp_p = rp(run_dir, "verification"), rp(run_dir, "verification_sample")
    ver: dict = {"available": False}
    if ver_p.exists():
        items = load_json(ver_p)["items"]
        samp = load_json(samp_p) if samp_p.exists() else {}
        vc = collections.Counter(i["verdict"] for i in items)
        n = len(items)
        by_type = collections.defaultdict(collections.Counter)
        by_how = collections.defaultdict(collections.Counter)
        for i in items:
            by_type[i["claim_type"]][i["verdict"]] += 1
            by_how[i["sampled_by"]][i["verdict"]] += 1
        numeric = [i for i in items if i["claim_type"] in ("fee", "deadline")]
        how = collections.Counter(i["sampled_by"] for i in items)
        ver = {"available": True, "records_checked": len({i["id"] for i in items}), "claims_checked": n, "coverage_of_records": pct(len({i["id"] for i in items}), len(cands)),
               "pct_confirmed": pct(vc["confirmed"], n), "pct_wrong": pct(vc["wrong"], n), "pct_not_found": pct(vc["not_found"], n), "pct_disputed": pct(vc["disputed"], n),
               "verdicts": dict(vc), "by_claim_type": {k: dict(v) for k, v in by_type.items()}, "by_sampling": {k: dict(v) for k, v in by_how.items()},
               "pct_numeric_claims_unreliable": pct(sum(i["verdict"] != "confirmed" for i in numeric), len(numeric)) if numeric else None,
               "sampled_by": dict(how), "random_sample_present": how["random"] > 0, "seed": samp.get("seed"),
               "method": samp.get("method")}

    # ---- 7 gaps
    gaps = [g for b in merged["countries"].values() for g in b.get("searched_not_surfaced", [])] + \
           [g for b in merged["crosscuts"].values() if b.get("kind") == "programme_scan" for g in b.get("searched_not_surfaced", [])]
    budget_c = []          # ONLY partial_budget_exhausted files and files with limit_events (not complete_with_gaps)
    for slug, b in merged["countries"].items():
        evs = [e for m in b.get("run_meta", []) for e in m.get("limit_events", [])]
        partial = b["status"] == "partial_budget_exhausted" or any(f.get("status") == "partial_budget_exhausted" for f in b.get("followups", {}).values())
        if partial or evs:
            budget_c.append(slug)
    blocked_texts = [t for t in gaps + [b.get("budget_notes", "") for b in merged["countries"].values()] if BLOCKED_RE.search(t or "")]
    gap_block = {"searched_not_surfaced": len(gaps), "examples": [g[:110] + ("..." if len(g) > 110 else "") for g in gaps[:3]] if examples else [],
                 "agents_hit_budget": len(budget_c), "agents_hit_budget_countries": budget_c, "blocked_site_mentions": len(blocked_texts),
                 "unscreened_institutions": funnel["unscreened"], "path_b_not_done": [s for s, b in merged["countries"].items() if not b["path_b_done"]]}

    # ---- 8 time sensitivity
    allds = [(c["id"], d) for c in cands for d in c["deadlines"]]
    soon = []
    for cid, d in allds:
        dd = parse_date(d["date"])
        if dd and 0 <= (dd - today).days <= deadline_days:
            soon.append({"id": cid, "name": d["name"], "date": d["date"], "date_type": d["date_type"], "days": (dd - today).days})
    soon.sort(key=lambda x: (x["date"], x["id"]))
    tsens = {"structured_deadlines": len(allds), "by_date_type": dict(collections.Counter(d["date_type"] for _, d in allds)), "window_days": deadline_days,
             "within_window": len(soon), "within_window_by_type": dict(collections.Counter(s["date_type"] for s in soon)), "rows": soon}

    # ---- 9 caveats
    rv = collections.Counter(c["state_vector"].get("rubric_version") for c in cands)
    ovr = merged.get("overrides_applied", [])
    caveats = {"rubric_versions": {str(k): v for k, v in rv.items()}, "weighting": "unweighted sum of the three axes (ties: pathway, then funding)",
               "overrides_applied": len(ovr), "overridden_records": len({o["target_id"] for o in ovr}), "overridden_fields": sorted({o["field"] for o in ovr}),
               "unknown_axes_handling": "'?' = missing data: skipped in _total (understates unscored records), never counted as 0",
               "near_duplicates_flagged": (report.get("counts") or {}).get("near_duplicates"), "exact_duplicates_dropped": (report.get("counts") or {}).get("exact_duplicates_dropped"),
               "provisional_benchmarks": sum(b["status"] == "provisional" for b in bms)}
    m = {"label": label, "today": today.isoformat(), "header": header, "effort": effort, "scope": scope, "funnel": funnel, "novelty": novelty, "benchmark_position": bench,
            "evidence": evidence, "verification": ver, "gaps": gap_block, "time_sensitivity": tsens, "caveats": caveats}
    return m if examples else publish_safe(m)


def letter(i: int) -> str:
    return chr(ord("A") + i) if i < 26 else str(i + 1)


def publish_safe(m: dict) -> dict:
    """Aggregates only: neutral labels instead of country / cross-cut / benchmark names, no record ids,
    no exclusion text, no deadline rows, no applicant summary, no money amounts. The counts are untouched.

    WHY labels follow size: labelling in alphabetical order would let anyone who knows the country
    list decode "Country C". Sorting by screened institutions (largest first) keeps the table useful
    and breaks that link."""
    lab, ci, xi = {}, 0, 0
    m["funnel"]["per_country"].sort(key=lambda r: (r["kind"] != "country", -r["screened"], -r["records"], r["slug"]))
    for r in m["funnel"]["per_country"]:
        if r["kind"] == "country":
            lab[r["slug"]] = (f"country_{letter(ci).lower()}", f"Country {letter(ci)}")
            ci += 1
        else:
            lab[r["slug"]] = (f"crosscut_{letter(xi).lower()}", f"Cross-cut {letter(xi)} ({r['kind']})")
            xi += 1
    for r in m["funnel"]["per_country"]:
        r["slug"], r["name"] = lab[r["slug"]]
    m["scope"]["country_names"] = [f"Country {letter(i)}" for i in range(m["scope"]["countries"])]
    m["scope"]["profile_summary"] = None
    # The run id and the alias are often derived from a person's name or initials: withhold both.
    m["scope"]["run_id"], m["scope"]["applicant_alias"] = None, None
    fd = m["scope"].get("funded_definition")
    if fd:
        m["scope"]["funded_definition"] = {k: v for k, v in fd.items() if k in ("type", "min_funding_score")}
    for b in m["scope"]["benchmarks"]:
        b["institution"], b["programme"] = f"{b['axis']} benchmark", "identity withheld"
    n_ex = len(m["scope"]["exclusions"])
    m["scope"]["exclusions"] = [f"{n_ex} region(s)/type(s) excluded, not listed"] if n_ex else []
    m["benchmark_position"]["top"] = [{"rank": i + 1, "total": t["total"], "vector": t["vector"]} for i, t in enumerate(m["benchmark_position"]["top"])]
    g = m["gaps"]
    order = {slug: name for slug, (_s, name) in lab.items()}
    g["agents_hit_budget_countries"] = [order.get(x, "withheld") for x in g["agents_hit_budget_countries"]]
    g["path_b_not_done"] = [order.get(x, "withheld") for x in g["path_b_not_done"]]
    m["time_sensitivity"]["rows"] = []
    m["publish_safe"] = True
    return m


# --------------------------------------------------------------------------- rendering

def table(headers: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return out


def render(m: dict) -> str:
    L = m["label"]
    s, f, n, b, e, v, g, t, cv = (m[k] for k in ("scope", "funnel", "novelty", "benchmark_position", "evidence", "verification", "gaps", "time_sensitivity", "caveats"))
    h, ef = m["header"], m["effort"]
    nr = lambda x, suffix="": f"not recorded in {L}" if x is None else f"{x}{suffix}"
    # Title line = protocol/templates/due_diligence.md: run id, date, protocol version, LP / PM rubric versions.
    o = [f"# Search due diligence: run {s.get('run_id') or ('withheld' if m.get('publish_safe') else '?')} ({m['today']}; protocol v{h.get('protocol_version') or 'n/a'}; "
         f"rubrics LP-{h.get('life_plan_rubric_version') or 'n/a'} / PM-{h.get('pathway_map_rubric_version') or 'n/a'})",
         f"_Applicant alias: {s.get('applicant_alias') or ('withheld' if m.get('publish_safe') else 'not stated')}. Computed from merged.json and verification.json; no figure is typed by hand. "
         f"State-vector rubric: {', '.join(h.get('state_vector_rubric_versions') or []) or 'not recorded'}._", ""]
    fd = s.get("funded_definition") or {}
    o += ["## 1. Scope",
          f"- Applicant: {s.get('profile_summary') or s.get('applicant_alias') or ('withheld' if m.get('publish_safe') else 'not stated')}.",
          f"- {s['countries']} countries ({', '.join(s['country_names'])}) + {s['crosscuts']} cross-cut(s) ({', '.join(f'{k}: {c}' for k, c in s['crosscut_kinds'].items()) or 'none'}); protocol {nr(s.get('protocol_version'))}, mode {nr(s.get('mode'))}.",
          f"- 'Funded' means: {fd.get('type', 'not set')}" + (f", total tuition <= {fd['max_total_tuition']} {fd.get('currency', '')}" if fd.get("max_total_tuition") else "") +
          (f", living support >= {fd['living_support_required_monthly']} {fd.get('currency', '')}/month" if fd.get("living_support_required_monthly") else "") +
          (f", out of pocket <= {fd['max_out_of_pocket']} {fd.get('currency', '')}" if fd.get("max_out_of_pocket") else "") +
          (f", household of {fd['household_size']}" if fd.get("household_size") else "") +
          (f"; minimum funding score {fd['min_funding_score']}" if fd.get("min_funding_score") is not None else "") + ". Exclusions: " + ("; ".join(s["exclusions"]) or "none") + ".",
          ""]
    o += table(["Benchmark axis", "Programme", "Vector F/P/W", "Sum", "Status"],
               [[x["axis"], f"{x['institution']}, {x['programme']}", "/".join(map(str, x["vector"])), x["total"], x["status"]] for x in s["benchmarks"]]) + [""]
    raw = f" ({f['screened_raw_rows']} raw rows before de-duplication)" if f.get("screened_raw_rows") else ""
    o += ["## 2. Coverage funnel",
          f"{f['screened_unique']} institutions screened{raw} -> **{f['pass']} pass**, {f['fail']} fail, {f['unscreened']} unscreened -> "
          f"**{f['programme_level_entries']} programme-level entries** = {f['full_records']} full records + {f['ranked_out']} ranked-out (preliminary vector only).", ""]
    def follow(r):
        if r["no_followup_suggested"]:
            return "none: " + (r["stop_reason"] or "stop rule")
        return f"{r['followup_files']} file(s) done, {r['open_triggers']} open trigger(s)"
    o += table(["Country", "Depth", "Cap", "Screened", "Pass", "Fail", "Unscr.", "Records", "Ranked-out", "Follow-up (or stop-rule reason)", "Status"],
               [[r["name"], r.get("depth") or "-", (str(r["cap"]) + ("*" if r["cap_reached"] else "")) if r["cap"] else "-", r["screened"], r["pass"], r["fail"], r["unscreened"],
                 r["records"], r["ranked_out"], follow(r), r["status"]] for r in f["per_country"]]) + ["", "`*` = cap reached.", ""]
    d = n.get("delta_vs_baseline")
    o += ["## 3. Novelty vs prior run",
          f"{n['net_new']} net-new, {n['update_of_existing']} updates of prior entries, {n['reconfirmed']} reconfirmed; {n['corrections_to_prior']} corrections to prior entries; "
          f"{n['prior_not_revisited']} in-scope prior entries not revisited." + ("" if n["baseline_used"] else " No baseline ledger supplied: vector deltas not computed.")]
    if d:
        o.append("Vector changes of revisited entries (up/down/same): " + "; ".join(f"{ax} {x['up']}/{x['down']}/{x['same']}" for ax, x in d["axes"].items()) + ".")
    o.append("")
    o += ["## 4. Benchmark position",
          f"Benchmark sums {b['benchmark_totals']} (no benchmark need be 3/3/3). Records with a sum >= the best benchmark sum ({b['benchmark_max_total']}): {nr(b['records_ge_benchmark_max'])}; "
          f"strictly above it: {nr(b['records_gt_benchmark_max'])}; highest sum {b['max_total']}. Records scoring 3: funding {b['records_funding_3']}, programme {b['records_programme_3']}, pathway {b['records_pathway_3']}.", ""]
    o += ["## 5. Evidence quality",
          f"- People/partner routes confirmed (takes_students): {fmt_pct(e['pct_routes_confirmed'])} of {e['route_entries']} named contacts; verification_needed {fmt_pct(e['pct_routes_verification_needed'])} "
          "(a group or company existing is not the same as it taking students of this programme).",
          f"- Funding: applicant eligibility confirmed for {fmt_pct(e['pct_funding_eligibility_confirmed'])} of {e['funding_routes']} routes.",
          f"- Sources: {e['source_entries']} entries, {fmt_pct(e['pct_null_sources'])} with no URL; {e['distinct_urls']} distinct URLs on {e['distinct_domains']} domain(s); "
          f"official vs aggregator: " + (f"{fmt_pct(e['pct_official'])} / {fmt_pct(e['pct_aggregator'])} (source_type present on {e['source_type_recorded']} of {e['source_entries']} entries)" if e["pct_official"] is not None else f"not recorded in {L}") +
          "; accessed_date: " + (f"{e['accessed_date_recorded']} of {e['source_entries']}" if e["accessed_date_recorded"] else f"not recorded in {L}") + ".",
          f"- Open questions per record: {nr(e['mean_open_questions'])}; {e['records_with_unscored_axis']} records have a '?' axis.", ""]
    o.append("## 6. Independent verification")
    if v["available"]:
        o.append(f"{v['claims_checked']} claims on {v['records_checked']} records ({fmt_pct(v['coverage_of_records'])} of records): **{fmt_pct(v['pct_confirmed'])} confirmed**, {fmt_pct(v['pct_wrong'])} wrong, "
                 f"{fmt_pct(v['pct_not_found'])} not found, {fmt_pct(v['pct_disputed'])} disputed. Fees and deadlines unreliable in {fmt_pct(v['pct_numeric_claims_unreliable'])} of cases. "
                 + ("Sample = top-N plus a seeded random draw (" + "; ".join(
                     f"{how}: {sum(x.values())} claims, {fmt_pct(pct(x.get('confirmed', 0), sum(x.values())))} confirmed" for how, x in sorted(v["by_sampling"].items())) + ")."
                    if v["random_sample_present"] else "Sample = top-N only (NOT random): do not extrapolate to other records."))
        ct = sorted(v["by_claim_type"].items())
        o += [""] + table(["Claim type"] + ["confirmed", "wrong", "not_found", "disputed"], [[k] + [x.get(j, 0) for j in ("confirmed", "wrong", "not_found", "disputed")] for k, x in ct])
    else:
        o.append("No verification.json yet: **no claim has been independently checked.**")
    o += ["", "## 7. Known gaps",
          f"- {g['searched_not_surfaced']} items logged as searched-but-not-surfaced or not searched" + (" (e.g. " + " | ".join(g["examples"]) + ")" if g["examples"] else "") + ".",
          f"- {g['agents_hit_budget']} agent file(s) hit a budget/limit ({', '.join(g['agents_hit_budget_countries']) or 'none'}); {g['unscreened_institutions']} institutions unscreened; "
          f"path B not done in: {', '.join(g['path_b_not_done']) or 'none'}; {g['blocked_site_mentions']} mention(s) of blocked/unreachable sites.", ""]
    o.append(f"## 8. Time sensitivity (next {t['window_days']} days)")
    if t["structured_deadlines"] == 0:
        o.append(f"Structured deadlines: not recorded in {L} (deadlines were free text).")
    else:
        bt = t["by_date_type"]
        o.append(f"{t['structured_deadlines']} structured deadlines (confirmed {bt.get('confirmed', 0)}, pattern {bt.get('pattern', 0)}, inferred {bt.get('inferred', 0)}); "
                 f"{t['within_window']} fall inside the window. 'pattern' dates repeat last year's and must be re-checked.")
        if t["rows"]:
            o += [""] + table(["Date", "Days", "Type", "Record", "Deadline"], [[r["date"], r["days"], r["date_type"], r["id"], r["name"]] for r in t["rows"][:10]])
            if len(t["rows"]) > 10:
                o.append(f"... and {len(t['rows']) - 10} more.")
    o += ["", "## 9. Method caveats",
          f"- Rubric version(s): {', '.join(f'{k} (x{c})' for k, c in cv['rubric_versions'].items())}; {cv['weighting']}.",
          f"- {cv['overrides_applied']} orchestrator override(s) on {cv['overridden_records']} record(s)" + (f" (fields: {', '.join(cv['overridden_fields'])})" if cv["overridden_fields"] else "") + "; original values kept in the merged file.",
          f"- {cv['unknown_axes_handling']}.",
          f"- {nr(cv['exact_duplicates_dropped'])} exact duplicate(s) dropped, {nr(cv['near_duplicates_flagged'])} near-duplicate pair(s) flagged for a human; {cv['provisional_benchmarks']} provisional benchmark(s)."]
    # Effort closes the page, as in protocol/templates/due_diligence.md.
    about = "about " if ef.get("approximate") else ""
    o += ["", "**Effort**: " + (f"{about}{ef['agent_runs']} agent runs" if ef["agent_runs"] is not None else f"agent runs not recorded in {L}") + ", " +
          (f"{about}{ef['usage_windows']} usage windows" if ef["usage_windows"] is not None else f"usage windows not recorded in {L}") +
          (f" ({ef['planned_windows']:g} planned)" if ef["planned_windows"] else "") + ", " +
          (f"{ef['sessions']} sessions" + (f", {ef['limit_hits']} of which ended at a usage limit" if ef["limit_hits"] else "") if ef["sessions"] is not None else f"sessions not recorded in {L}") + "."]
    return "\n".join(o) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate the one-page due-diligence report from computed metrics.")
    ap.add_argument("run_dir")
    ap.add_argument("--today", default=today_iso())
    ap.add_argument("--deadline-days", type=int, default=90)
    ap.add_argument("--out")
    ap.add_argument("--metrics-json")
    ap.add_argument("--run-label", default="this run")
    ap.add_argument("--no-examples", action="store_true", help="publish-safe: aggregates only, neutral labels (see module docstring)")
    ap.add_argument("--stdout", action="store_true")
    a = ap.parse_args(argv)
    try:
        run_dir = Path(a.run_dir)
        today = parse_date(a.today)
        if today is None or not run_dir.is_dir():
            raise UsageError("bad RUN_DIR or --today (YYYY-MM-DD)")
        m = compute_metrics(run_dir, today, a.deadline_days, a.run_label, not a.no_examples)
        md = render(m)
        if a.metrics_json:
            atomic_write_text(a.metrics_json, json.dumps(m, indent=2, ensure_ascii=False) + "\n", keep_backup=False)
        if a.stdout:
            print(md)
        else:
            out = Path(a.out) if a.out else rp(run_dir, "due_diligence")
            atomic_write_text(out, md, keep_backup=False)
            print(f"wrote {out} ({len(md.splitlines())} lines)")
        return EXIT_OK
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
