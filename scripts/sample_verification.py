#!/usr/bin/env python3
"""
sample_verification.py - draw the sample of claims an INDEPENDENT checker must verify.

PURPOSE
    The reference run verified only its top-12 records (not random), so the headline
    "78% of claims confirmed" could not be generalised. This script mixes the top-N ranked
    records (the ones the decision will rest on) with M records drawn at random from the
    rest (so the error rate of the whole dataset can be estimated). The random draw is
    seeded: the same --seed on the same merged.json gives the same sample.

INPUTS
    05_merge/merged.json      (run merge.py first)

OUTPUT
    06_verify/verification_sample.json   one item per (record, claim type):
      fee         tuition amount + academic year          (highest-error claim type in the reference run)
      deadline    first listed deadline and its date_type  (forward-dated claims were the second weakest)
      people_partner  first named contact (supervisor, partner lead, placement lead ...) and the
                  takes_students status
      language    admission language requirement
      funding     first funding route and the applicant-eligibility call
    A claim type is skipped for a record that has no value for it.
    The file also carries `extrapolable`: true only when the sample includes a random draw. With
    --random 0 (or fewer records than top + random) it is false / warned: the confirmed share of a
    top-N-only sample says nothing about the records outside it. Warnings go to stderr and into
    the file's `warnings` list.
    The checker then writes 06_verify/verification.json (schema: verification_record) with a
    verdict per item; due_diligence.py reads it.

USAGE
    python3 scripts/sample_verification.py RUN_DIR --top 10 --random 10 --seed 42
                                           [--claims fee,deadline,people_partner,language,funding]

EXIT CODES
    0 ok | 2 usage error (merged.json missing, bad arguments)
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (EXIT_OK, EXIT_USAGE, UsageError, atomic_write_json, load_json, now_iso, rp, validate)  # noqa: E402

ALL_CLAIMS = ["fee", "deadline", "people_partner", "language", "funding"]
# Which `sources[].claim_field` normally backs each claim type.
SOURCE_FIELD = {"fee": "tuition", "deadline": "deadline", "people_partner": "pathway", "language": "admissions_language", "funding": "scholarship"}


def source_for(rec: dict, claim_type: str) -> str | None:
    want = SOURCE_FIELD[claim_type]
    for s in rec.get("sources", []):
        if s.get("claim_field") == want and s.get("url"):
            return s["url"]
    return None


def claims_for(rec: dict, wanted: list[str]) -> list[dict]:
    out = []

    def add(ctype, claim, value, url=None):
        out.append({"id": rec["id"], "claim_type": ctype, "claim": claim, "value": value, "source_url": url or source_for(rec, ctype)})

    t = rec.get("tuition") or {}
    if "fee" in wanted and t.get("amount_text"):
        add("fee", f"Tuition for {t.get('applies_to', 'the applicant')}: {t['amount_text']}", t["amount_text"])
    dl = (rec.get("deadlines") or [None])[0]
    if "deadline" in wanted and dl:
        add("deadline", f"{dl['name']}: {dl['date']} ({dl['date_type']})", dl["date"], dl.get("source_url"))
    if "people_partner" in wanted:
        # First entry that names a person: that is the claim a verifier can check on one page.
        for g in (rec.get("axis_2_pathway") or {}).get("people_and_partners", []):
            if g.get("contacts"):
                f = g["contacts"][0]
                add("people_partner", f"{f['name']} ({f['role']}; {f['focus']}) at {g['name']} - available to students of this programme: {f['takes_students']}",
                    f["name"], f.get("url") or g.get("url"))
                break
    lang = (rec.get("language") or {}).get("admission_requirement")
    if "language" in wanted and lang:
        add("language", f"Admission language requirement: {lang}", lang, rec["language"].get("source_url"))
    routes = (rec.get("funding") or {}).get("routes") or []
    if "funding" in wanted and routes:
        r = routes[0]
        add("funding", f"{r['name']}: {r['amount']}; applicant eligible: {r['applicant_eligible']}", r["name"], r.get("url"))
    return out


def build_sample(merged: dict, top: int, rand_m: int, seed: int, wanted: list[str]) -> dict:
    cands = sorted(merged["candidates"], key=lambda c: c.get("_rank", 10**9))
    top_recs = cands[:top]
    rest = cands[top:]
    rng = random.Random(seed)
    pick = rng.sample(rest, min(rand_m, len(rest))) if rest else []
    items = []
    for how, recs in (("top_n", top_recs), ("random", sorted(pick, key=lambda c: c.get("_rank", 10**9)))):
        for r in recs:
            for it in claims_for(r, wanted):
                it["sampled_by"] = how
                items.append(it)
    warnings = []
    if len(cands) < top + rand_m:
        warnings.append(f"population ({len(cands)} records) is smaller than top + random ({top} + {rand_m}): "
                        f"the sample holds {len(top_recs)} top and {len(pick)} random records")
    if not pick:
        warnings.append("no random draw: this sample covers the top-ranked records only; do NOT extrapolate its error rate to other records")
    return {"generated": now_iso(), "seed": seed, "top_n": len(top_recs), "random_m": len(pick), "population_size": len(cands),
            "extrapolable": bool(pick), "warnings": warnings,
            "method": f"{len(top_recs)} highest-ranked records plus {len(pick)} records drawn uniformly at random (seed {seed}) from the remaining {len(rest)}; "
                      f"claim types: {', '.join(wanted)}.",
            "items": items}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the verification sample (top-N + seeded random).")
    ap.add_argument("run_dir")
    ap.add_argument("--top", type=int, default=10, help="records from the top of the ranking")
    ap.add_argument("--random", type=int, default=10, dest="rand_m", help="records drawn at random from the rest")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--claims", default=",".join(ALL_CLAIMS), help="comma list of claim types")
    a = ap.parse_args(argv)
    try:
        wanted = [c.strip() for c in a.claims.split(",") if c.strip()]
        bad = [c for c in wanted if c not in ALL_CLAIMS]
        if bad or a.top < 0 or a.rand_m < 0:
            raise UsageError(f"invalid arguments (claims must be among {ALL_CLAIMS}; counts >= 0)")
        run_dir = Path(a.run_dir)
        merged_path = rp(run_dir, "merged")
        if not merged_path.exists():
            raise UsageError("05_merge/merged.json not found - run merge.py first")
        sample = build_sample(load_json(merged_path), a.top, a.rand_m, a.seed, wanted)
        errs = validate(sample, "verification_sample")
        if errs:
            raise UsageError(f"internal: sample invalid: {errs[0].path}: {errs[0].message}")
        atomic_write_json(rp(run_dir, "verification_sample"), sample)
        for w in sample["warnings"]:
            print(f"warning: {w}", file=sys.stderr)
        print(f"sample: {sample['top_n']} top + {sample['random_m']} random records of {sample['population_size']}; {len(sample['items'])} claims -> 06_verify/verification_sample.json")
        return EXIT_OK
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
