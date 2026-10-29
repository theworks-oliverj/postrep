#!/usr/bin/env python3
"""
shortlist.py - render the numbers of the Options Rundown as Markdown tables.

PURPOSE
    The Options Rundown (07_deliverables/options_rundown.md) is the document the applicant
    actually reads. Its numbers (ranking, benchmark class, funding routes, deadlines, what was
    ruled out) must come from the merged data, not from a person or an LLM typing them: hand-typed
    counts were the commonest error in the reference run. This script computes every table; the
    Rundown author adds the prose around them (copy the tables in, or link the file).

INPUTS (under RUN_DIR)
    05_merge/merged.json        required - run merge.py first
    02_map/benchmarks.json          optional - falls back to the copy inside merged.json
    The stop-rule notes are recomputed on the fly with followups.py's logic (nothing is stored).

OUTPUT
    07_deliverables/rundown_tables.md        (override with --out)

SECTIONS (the numbering is stable)
    1 Benchmarks      each benchmark's baseline F/P/W and sum; `benchmark_max_total` = the best sum
                      (computed, never a constant - 6 in the reference run was an observation, not a rule)
    2 Shortlist       top --top records by rank (records whose funding verdict is 'fails' are listed
                      under section 5 instead): ID | Programme | Institution, country | F | P | R | Total |
                      Funding route | Language core/admission | Next deadline | Confidence | Next action
    3 Overlays        schemes with strings attached, next to the base funding score they do NOT change
                      (plus the funding-route cross-cuts: obligations and verdict)
    4 Deadlines       every structured deadline within --deadline-days of --today, with its date_type
                      ('pattern' and 'inferred' dates repeat or guess last year's: re-check them)
    5 Ruled out       records with funding verdict 'fails' (funding CONFIRMED absent), then the
                      ranked-out programmes (promote=true first), at most --ruled-out-max rows
    6 Stop-rule notes countries where more searching cannot change the decision, and countries that
                      still have open follow-up triggers

COLUMN NOTES
    Total        unweighted sum of the scored axes; '*' = the record has a '?' axis, so its Total is
                 understated ('?' = missing data, skipped, never counted as 0).
    Confidence   the WEAKEST level among the record's per-claim confidences, with the claim name.
    Next action  the first entry of the record's contact_actions (question -> who, channel).
    Funding route the first route the applicant is confirmed eligible for, else the first route.
    Practical component  type and credits of the record's practical_component (thesis, internship ...).

USAGE
    python3 scripts/shortlist.py RUN_DIR [--top 15] [--today YYYY-MM-DD] [--deadline-days 90]
                                         [--out PATH] [--ruled-out-max 15]

EXIT CODES
    0 written | 2 usage error (merged.json missing, bad date)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import followups as followups_mod  # noqa: E402
from _common import (EXIT_OK, EXIT_USAGE, UsageError, atomic_write_text, load_json, parse_date, rp,  # noqa: E402
                     today_iso, vector_total)

CONF_ORDER = ["confirmed", "inferred", "verification_needed", "unknown"]     # strongest -> weakest
DEADLINE_MAX_ROWS = 30
OVERLAY_MAX_ROWS = 20


def esc(x) -> str:
    """Make a value safe for a Markdown table cell (pipes and newlines break the table)."""
    return str(x if x is not None else "").replace("|", "\\|").replace("\n", " ").strip()


def clip(x, n: int) -> str:
    x = str(x or "").strip()
    return x if len(x) <= n else x[: n - 3].rstrip() + "..."


def table(headers: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    return out


def vec(sv: dict) -> str:
    return "/".join(str(sv.get(a)) for a in ("funding", "programme", "pathway"))


def place(c: dict, merged: dict) -> str:
    """'Institution, country' (cross-cut records show the cross-cut's name instead of a country)."""
    slug = c.get("_country_slug")
    blk = merged["countries"].get(slug) or merged["crosscuts"].get(slug) or {}
    where = blk.get("country") or c.get("country") or ""
    return f"{c['institution']}, {where}" if where else c["institution"]


def funding_route_text(c: dict) -> str:
    f = c.get("funding") or {}
    routes = f.get("routes") or []
    if not routes:
        return f"none listed [{f.get('verdict', 'unknown')}]"
    r = next((x for x in routes if x.get("applicant_eligible") == "confirmed"), routes[0])
    return f"{clip(r['name'], 40)} ({clip(r['amount'], 30)}) [{f.get('verdict', 'unknown')}]"


def practical_text(c: dict) -> str:
    """'internship (12 credits)' - the practical component in one cell ('-' when the record has none)."""
    pc = c.get("practical_component") or {}
    if not pc.get("type") or pc["type"] == "none":
        return "none" if pc.get("type") == "none" else "-"
    return pc["type"].replace("_", " ") + (f" ({pc['credits']:g} credits)" if isinstance(pc.get("credits"), (int, float)) else "")


def next_deadline(c: dict, today) -> str:
    ds = [(parse_date(d["date"]), d) for d in c.get("deadlines") or []]
    ds = [(dd, d) for dd, d in ds if dd]
    if not ds:
        return "not recorded"
    upcoming = sorted((x for x in ds if x[0] >= today), key=lambda x: x[0])
    if upcoming:
        dd, d = upcoming[0]
        return f"{d['date']} ({d['date_type']})"
    dd, d = max(ds, key=lambda x: x[0])
    return f"past: {d['date']} ({d['date_type']})"


def weakest_confidence(c: dict) -> str:
    conf = c.get("confidence") or {}
    if not conf:
        return "not recorded"
    key, level = max(conf.items(), key=lambda kv: CONF_ORDER.index(kv[1]) if kv[1] in CONF_ORDER else 99)
    return f"{level} ({key})"


def next_action(c: dict) -> str:
    acts = c.get("contact_actions") or []
    if not acts:
        return "-"
    a = acts[0]
    return f"{clip(a['question'], 70)} -> {a['who']} ({a['channel']})"


def benchmark_block(merged: dict, run_dir: Path) -> tuple[list[str], int | None, list[dict]]:
    bp = rp(run_dir, "benchmarks")
    bms = (load_json(bp) if bp.exists() else (merged.get("benchmarks") or {})).get("benchmarks", [])
    rows, totals = [], []
    for b in bms:
        v = b["baseline_vector"]
        t = vector_total(v)
        totals.append(t)
        rows.append([b["axis"], f"{b['institution']}, {b['programme']}", vec(v), t if t is not None else "?", b["status"]])
    known = [t for t in totals if t is not None]
    bmax = max(known) if known else None
    # One-line form used at the top of the Options Rundown (protocol/templates/options_rundown.md).
    line = " · ".join(f"{b['axis']} = {b['institution']} ({vec(b['baseline_vector'])})" for b in bms)
    out = ["## 1. Benchmarks", "", f"Benchmarks: {line}." + (f" Highest benchmark total = {bmax} (\"benchmark-class\")." if bmax is not None else ""), ""] \
        + table(["Axis", "Benchmark", "F/P/W", "Sum", "Status"], rows) + [""]
    if bmax is None:
        out.append("benchmark_max_total: not computable (no benchmark has a scored axis).")
    else:
        n_ge = sum(1 for c in merged["candidates"] if c.get("_total") is not None and c["_total"] >= bmax)
        out.append(f"**benchmark_max_total = {bmax}** (best benchmark sum, from benchmarks.json). A total of {bmax} = benchmark-class; "
                   f"{n_ge} of {len(merged['candidates'])} records reach it.")
    return out, bmax, bms


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Render the Options Rundown tables from merged.json (see module docstring).")
    ap.add_argument("run_dir")
    ap.add_argument("--top", type=int, default=15, help="records in the shortlist table")
    ap.add_argument("--today", default=today_iso(), help="reference date YYYY-MM-DD (default: today)")
    ap.add_argument("--deadline-days", type=int, default=90)
    ap.add_argument("--out", help="output path (default 07_deliverables/rundown_tables.md)")
    ap.add_argument("--ruled-out-max", type=int, default=15, help="max ranked-out rows in section 5")
    a = ap.parse_args(argv)
    try:
        run_dir = Path(a.run_dir)
        today = parse_date(a.today)
        if not run_dir.is_dir() or today is None or a.top < 1:
            raise UsageError("bad RUN_DIR, --today (YYYY-MM-DD) or --top (>= 1)")
        mp = rp(run_dir, "merged")
        if not mp.exists():
            raise UsageError("05_merge/merged.json not found - run merge.py first")
        merged = load_json(mp)
        cands = merged["candidates"]                       # already sorted by rank
        o = ["# Options Rundown: computed tables",
             f"_Computed {today.isoformat()} from merged.json ({len(cands)} records). No number is typed by hand: regenerate after every merge._", ""]

        bl, bmax, _bms = benchmark_block(merged, run_dir)
        o += bl + [""]

        ruled = [c for c in cands if (c.get("funding") or {}).get("verdict") == "fails"]
        ruled_ids = {c["id"] for c in ruled}
        pool = [c for c in cands if c["id"] not in ruled_ids]
        short = pool[: a.top]
        o += [f"## 2. Shortlist (top {len(short)} of {len(pool)} records not ruled out)", ""]
        o += table(["ID", "Programme", "Institution, country", "F", "P", "W", "Total", "Practical component", "Funding route", "Language core/admission",
                    "Next deadline", "Confidence", "Next action"],
                   [[c["id"], c["programme"] + (f" - {c['track']}" if c.get("track") else ""), place(c, merged),
                     c["state_vector"]["funding"], c["state_vector"]["programme"], c["state_vector"]["pathway"],
                     f"{c['_total']}{'*' if c['_unscored_axes'] else ''}" if c.get("_total") is not None else "?",
                     practical_text(c), funding_route_text(c), f"{clip((c.get('language') or {}).get('core'), 25)} / {clip((c.get('language') or {}).get('admission_requirement'), 30)}",
                     next_deadline(c, today), weakest_confidence(c), next_action(c)] for c in short])
        o += ["", "`*` = a '?' axis: the Total skips it and is understated. Overlays are NOT included in F (see section 3).", ""]

        # ---- 3 overlays
        o += ["## 3. Overlays (schemes with strings attached)", ""]
        ov_rows = [[c["id"], c["programme"], ov["scheme"], c["state_vector"]["funding"], ov["effect"], ov["obligations"], ov["status"]]
                   for c in cands for ov in c.get("overlays") or []]
        if ov_rows:
            o += table(["ID", "Programme", "Scheme", "Base F", "F if awarded", "Obligations", "Status"], ov_rows[:OVERLAY_MAX_ROWS])
            if len(ov_rows) > OVERLAY_MAX_ROWS:
                o.append(f"... and {len(ov_rows) - OVERLAY_MAX_ROWS} more overlay rows in merged.json.")
        else:
            o.append("No record carries an overlay.")
        routes = [(slug, cc) for slug, cc in merged["crosscuts"].items() if cc.get("kind") == "funding_route"]
        if routes:
            o += [""] + table(["Funding-route cross-cut", "Type", "Status", "Obligations", "Verdict"],
                              [[cc["route"], cc.get("route_type", ""), cc.get("status", "not recorded"), clip(cc.get("obligations"), 80), clip(cc.get("verdict"), 100)]
                               for _slug, cc in routes])
        o.append("")

        # ---- 4 deadlines
        rows = []
        by_id = {c["id"]: c["programme"] for c in cands}
        for c in cands:
            for d in c.get("deadlines") or []:
                dd = parse_date(d["date"])
                if dd and 0 <= (dd - today).days <= a.deadline_days:
                    rows.append((d["date"], (dd - today).days, d["date_type"], c["id"], c["programme"], d["name"]))
        for blk in merged["countries"].values():
            for d in blk.get("urgent_deadlines") or []:
                dd = parse_date(d["date"])
                if dd and 0 <= (dd - today).days <= a.deadline_days and d.get("record_id"):
                    rows.append((d["date"], (dd - today).days, d["date_type"], d["record_id"], by_id.get(d["record_id"], "(see follow-up)"), d["name"]))
        rows = sorted(set(rows))
        o += [f"## 4. Deadlines within {a.deadline_days} days of {today.isoformat()}", ""]
        if rows:
            o += table(["Date", "Days", "Date type", "Re-check?", "ID", "Programme", "Deadline"],
                       [[r[0], r[1], r[2], "yes" if r[2] != "confirmed" else "no", r[3], r[4], r[5]] for r in rows[:DEADLINE_MAX_ROWS]])
            if len(rows) > DEADLINE_MAX_ROWS:
                o.append(f"... and {len(rows) - DEADLINE_MAX_ROWS} more.")
            o += ["", "'pattern' = last cycle's date used as a proxy; 'inferred' = guessed. Both must be reconfirmed on the official page."]
        else:
            o.append("No structured deadline falls inside the window (deadlines recorded as free text are not counted).")
        o.append("")

        # ---- 5 ruled out
        o += ["## 5. Ruled out", ""]
        if ruled:
            o += table(["ID", "Programme", "Institution, country", "Why"],
                       [[c["id"], c["programme"], place(c, merged), "funding verdict 'fails' (funding confirmed absent); route: " + funding_route_text(c)] for c in ruled]) + [""]
        ro = []
        for slug, blk in merged["countries"].items():
            for r in blk.get("ranked_out") or []:
                sv = r["prelim_state_vector"]
                ro.append((not r.get("promote"), -(vector_total(sv) if vector_total(sv) is not None else -1),
                           [r["programme"], f"{r['institution']}, {blk['country']}", vec(sv), r["why_below_cut"], "yes: " + r.get("promote_reason", "") if r.get("promote") else "no"]))
        for slug, blk in merged["crosscuts"].items():
            for r in blk.get("ranked_out") or []:
                sv = r["prelim_state_vector"]
                ro.append((not r.get("promote"), -(vector_total(sv) if vector_total(sv) is not None else -1),
                           [r["programme"], f"{r['institution']}, {blk.get('country', slug)}", vec(sv), r["why_below_cut"], "yes: " + r.get("promote_reason", "") if r.get("promote") else "no"]))
        ro.sort(key=lambda x: (x[0], x[1], x[2][0]))
        if ro:
            o += table(["Programme", "Institution, country", "Prelim F/P/W", "Why below the cut", "Promote?"], [x[2] for x in ro[: a.ruled_out_max]])
            if len(ro) > a.ruled_out_max:
                o.append(f"... and {len(ro) - a.ruled_out_max} more ranked-out programmes in merged.json.")
        elif not ruled:
            o.append("Nothing ruled out or ranked out.")
        failed = sum(1 for blk in merged["countries"].values() for s in blk.get("screening", []) if s["decision"] == "fail")
        o += ["", f"{failed} institution(s) failed screening (rows with reasons: merged.json, countries.<slug>.screening).", ""]

        # ---- 6 stop rule
        o += ["## 6. Stop-rule notes", ""]
        try:
            plan = followups_mod.compute(run_dir, today, 60, None, None, "conservative")
            stops = plan["stop_rule_decisions"]
            for s in stops:
                o.append(f"- {s['country']}: more work cannot change the decision. {s['reason']}")
            for slug in plan["countries_needing_followup"]:
                kinds = sorted({t["trigger_type"] for t in plan["triggers"] if t["country"] == slug})
                o.append(f"- {slug}: open follow-up triggers: {', '.join(kinds)}")
            if not stops and not plan["countries_needing_followup"]:
                o.append("No open follow-up triggers.")
            o += ["", "The stop rule is a suggestion: the orchestrator confirms it in orchestrator_notes.md."]
        except Exception as e:                       # the tables above must still be written
            o.append(f"Stop-rule analysis unavailable: {e}")

        text = "\n".join(o) + "\n"
        out = Path(a.out) if a.out else rp(run_dir, "rundown_tables")
        atomic_write_text(out, text, keep_backup=False)
        print(f"wrote {out} ({len(text.splitlines())} lines; benchmark_max_total={bmax}; shortlist {len(short)} rows)")
        return EXIT_OK
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
