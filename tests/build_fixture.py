#!/usr/bin/env python3
"""
build_fixture.py - regenerate the two SYNTHETIC test workspaces under tests/fixtures/.

PURPOSE
    Every script is tested end-to-end against realistic files, but the files must not come from a
    real run (a real run reveals a real person's plan and third parties). Everything here is
    fictional: made-up institutions, the made-up countries Northland / Eastmark / Southvale, made-up
    applicants. Two personas keep the tooling honest about being field-agnostic:

    run/            "Applicant T" - science route (computational neuroscience, thesis-based master's,
                    EUR, ECTS credits). Exercises every follow-up trigger, merge rule and crosscut.
    run_business/   "Applicant B" - business/design route (service design leadership, internship-based
                    master's, GBP, UK-style credits, a partner who moves with the applicant).
                    Exercises practical_component = internship, household_fit and the
                    dependant_pathway warning, with a non-research pathway axis.

INPUTS   none (the content is below).
OUTPUTS  tests/fixtures/run/ and tests/fixtures/run_business/ (replaced on every run).
USAGE    python3 tests/build_fixture.py        # run after changing a schema, then commit the folders

What fixture A contains (and which behaviour each part exercises)
  northland.json            first pass, partial_budget_exhausted, path B missing, '?' axis,
                            ranked_out entry with promote=true, a 'no people found' failure,
                            an 'unscreened' row                       -> followups.py triggers
  northland_followup.json   replaces NL26-02, promotes NL26-04 out of ranked_out, upserts a
                            screening row, carries urgent_deadlines / path_b_people / extras
                                                                       -> merge.py fold rules
  eastmark.json             complete_with_gaps, nothing above funding 1 / pathway 1
                                                                       -> stop rule
  crosscuts/joint_masters   programme scan; XC26-02 is an exact duplicate of NL26-03
  crosscuts/home_scheme     funding-route cross-cut
  overrides.json            caps XC26-01 funding 3 -> 2
  baseline_ledger.json      prior ledger for delta / prior_not_revisited
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import init_workspace  # noqa: E402
import rubric  # noqa: E402
from _common import rp, validate  # noqa: E402

OUT = HERE / "fixtures" / "run"
OUT_B = HERE / "fixtures" / "run_business"


class Persona:
    """Everything that differs between the two fixtures: domains, wording, currency, credit system."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


SCIENCE = Persona(
    domains=["NEURO", "STAT", "LEARN", "SIG", "PROG"], currency="EUR", degree="MSc 120 ECTS / 2 yrs", fee_scope="international",
    practical=("thesis", 30, False, False, "30 ECTS thesis"), progression="Informal via thesis group.",
    ptype="research_group", pname="Group of {inst}", role="modelling lead", focus="neural population models",
    action="Do you supervise MSc theses on neural data analysis?", who="PI of the group")
BUSINESS = Persona(
    domains=["STRAT", "DES", "FIN", "OPS", "LEAD", "ANA"], currency="GBP", degree="MSc 180 credits / 12 months", fee_scope="international",
    practical=("internship", 60, True, True, "60-credit paid internship; the student may find the host (UK credits)"), progression="Graduate scheme route via partner employers.",
    ptype="internship_programme", pname="Placement office of {inst}", role="placement lead", focus="studio and consultancy placements",
    action="Can students arrange their own internship host?", who="placement lead")


def sources(prefix: str, with_types: bool = True) -> list[dict]:
    out = []
    for field in ["programme", "study_plan", "pathway", "admissions_language", "tuition", "scholarship"]:
        s = {"claim_field": field, "url": f"https://example.edu/{prefix}/{field}", "note": f"{field} page"}
        if with_types:
            s["source_type"] = "official" if field != "scholarship" else "aggregator"
            s["accessed_date"] = "2026-10-20"
        out.append(s)
    out.append({"claim_field": "deadline", "url": None, "source_type": "other", "accessed_date": "2026-10-20", "note": "not located"})
    return out


def cand(P: Persona, cid, inst, prog, vec, *, track="", city="Springfield", prior=None, status="net_new", deadlines=None,
         sup=("confirmed",), elig="confirmed", verdict="competitive_scholarship_only", extra=None) -> dict:
    f, p, w = vec
    ptype, credits, selfp, ext, pnote = P.practical
    rec = {
        "id": cid, "prior_id": prior, "status": status, "institution": inst, "programme": prog, "track": track, "city": city,
        "degree_type_and_length": P.degree,
        "sources": sources(cid.lower()),
        "axis_1_curriculum": {d: {"grade": ["None", "Weak", "Moderate", "Strong"][(i + p) % 4], "evidence": f"module list for {d}",
                                  "confidence": "confirmed" if i % 2 == 0 else "inferred"} for i, d in enumerate(P.domains)},
        "axis_1_verdict": "Synthetic verdict.",
        "axis_2_pathway": {"people_and_partners": [{"name": P.pname.format(inst=inst), "type": P.ptype, "url": f"https://example.edu/{cid.lower()}/group",
                                                    "contacts": [{"name": f"Contact {k + 1} (role: {P.role})", "role": P.role, "focus": P.focus, "recent_work": "n/a",
                                                                  "url": None, "takes_students": s} for k, s in enumerate(sup)]}],
                           "summary": "Synthetic pathway summary."},
        "practical_component": {"type": ptype, "credits": credits, "self_proposed": selfp, "external_host_allowed": ext, "notes": pnote},
        "progression": P.progression,
        "language": {"core": "English", "electives": "English", "admission_requirement": "IELTS 6.5", "source_url": f"https://example.edu/{cid.lower()}/lang",
                     "source_note": "admissions page"},
        "tuition": {"amount_text": f"{P.currency} 1,000 per year (2026/27)", "applies_to": P.fee_scope, "currency": P.currency, "annual_amount": 1000, "academic_year": "2026/27", "confidence": "confirmed"},
        "funding": {"routes": [{"name": "Excellence scholarship", "amount": f"{P.currency} 10,000/yr", "applicant_eligible": elig,
                                "eligibility_detail": "open to all international master's applicants", "competitiveness": "competitive", "url": f"https://example.edu/{cid.lower()}/schol"}],
                    "verdict": verdict},
        "deadlines": deadlines or [],
        "state_vector": {"funding": f, "programme": p, "pathway": w, "rubric_version": "1.0", "notes": "synthetic"},
        "benchmark_comparison": {"vs_funding_benchmark": "weaker", "vs_programme_benchmark": "similar", "vs_pathway_benchmark": "weaker"},
        "confidence": {"curriculum": "confirmed", "pathway": "inferred", "funding": "inferred"},
        "open_questions": ["Does the group take MSc students?", "Is the scholarship open to the applicant?"][: 1 + (cid[-1] in "13")],
        "contact_actions": [{"question": P.action, "who": P.who, "channel": "email"}],
    }
    if extra:
        rec.update(extra)
    return rec


def screen(inst, decision, reason, path="A") -> dict:
    return {"institution": inst, "programmes_considered": "MSc programmes", "decision": decision, "entry_path": path, "reason": reason}


def ranked(inst, prog, vec, why, promote=False, reason=None) -> dict:
    d = {"institution": inst, "programme": prog, "prelim_state_vector": dict(zip(("funding", "programme", "pathway"), vec)),
         "why_below_cut": why, "promote": promote}
    if promote:
        d["promote_reason"] = reason or "strong fit, evidence incomplete"
    return d


def jw(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def anchors() -> dict:
    return {ax: {"0": "none", "1": "weak", "2": "good", "3": "benchmark level"} for ax in ("funding", "programme", "pathway")}


def vector(run, session, phase, objective, nxt_user, nxt_virgil, *, completed=(), unknowns=(), assumptions=(), blockers=(), artifacts=("run_state.json",)) -> dict:
    """A continuation state vector (protocol/state_vector.md); NOT the F/P/W score vector."""
    return {"run": run, "session": session, "date": "2026-10-25", "phase": phase, "session_objective": objective,
            "context": ["Synthetic fixture."], "unknowns": list(unknowns), "ambiguities": [], "assumptions": list(assumptions),
            "completed": list(completed), "active": {"user": [], "virgil": []}, "next": {"user": list(nxt_user), "virgil": list(nxt_virgil)},
            "blockers": list(blockers), "artifacts": list(artifacts)}


def finish(out: Path, schemas: list[tuple[Path, str]]) -> int:
    """Gate sheets from the REAL files (so a fixture that stops satisfying the mechanical checks fails loudly
    here instead of in some test), then validate every fixture file."""
    for key, which in (("life_plan_score", "life_plan"), ("map_score", "pathway_map")):
        doc = json.loads(rp(out, key).read_text())
        for g in doc["gates"]:
            g["status"], g["note"] = "pass", "synthetic fixture"
        for x in doc["soft"]:
            x["score"], x["note"] = 2, "synthetic fixture"
        res = rubric.evaluate(doc, which, out)
        if not res["passed"]:
            print("FIXTURE GATE DID NOT PASS", which, res["problems"])
            sys.exit(1)
        jw(rp(out, key), res)
    bad = 0
    for path, schema in schemas + [(rp(out, "run_state"), "run_state"), (rp(out, "study_pathway_map"), "study_pathway_map"), (rp(out, "search_plan"), "search_plan"),
                                   (rp(out, "life_plan"), "life_plan"), (rp(out, "benchmarks"), "benchmarks"),
                                   (rp(out, "life_plan_score"), "rubric_score"), (rp(out, "map_score"), "rubric_score")]:
        for e in validate(json.loads(path.read_text()), schema)[:5]:
            bad += 1
            print(f"INVALID {path.name}: {e.path}: {e.message}")
    print("fixture written to", out, "- invalid:", bad)
    return bad


# --------------------------------------------------------------------------------------------- fixture A

def build_science() -> int:
    P = SCIENCE
    if OUT.exists():
        shutil.rmtree(OUT)
    init_workspace.main([str(OUT), "--alias", "Applicant T", "--mode", "local", "--run-id", "fixture-run"])
    w = lambda key, obj: jw(rp(OUT, key), obj)

    w("life_plan", {"schema_version": "1.0", "applicant_alias": "Applicant T", "profile_summary": "Applicant T, first degree in Biology, residence Exampleland", "updated_at": "2026-10-01T09:00:00Z",
                    "purpose_horizon": {"purpose": "Research career in computational neuroscience", "horizon_years": 5},
                    "post_degree_intent": {"intent": "doctorate", "routes_open": ["doctorate"], "detail": "Doctorate within 2 years of the master's"},
                    "money": {"funded_type": "tuition_only", "max_total_tuition": 4000, "max_out_of_pocket": 9000, "living_support_required_monthly": None, "household_size": 1,
                              "currency": "EUR", "debt_acceptable": False, "debt_limit": None, "income_during_degree": 0, "dependants_on_income": 0,
                              "hardness": "keep_and_flag", "notes": "Savings cover living costs."},
                    "eligibility_facts": {"citizenships": ["Exampleland"], "residence_country": "Exampleland", "residence_region": "",
                                          "highest_degree": {"field": "Biology", "country": "Exampleland", "graduation_year": 2020, "grade": "first class", "grade_scale": "honours classes"},
                                          "language_certificates": [{"test": "IELTS Academic", "score": "7.0", "date_taken": "2026-03-10", "expires": "2028-03-10"}],
                                          "age_bracket": "30-34", "fee_status": "international"},
                    "geography": {"considered": ["Northland", "Eastmark"], "excluded": [{"country": "Westland", "reason": "excluded by the applicant"}],
                                  "languages_willing_c1": [], "teaching_languages_accepted": ["English"]},
                    "timeline": {"earliest_start": "2027-09", "latest_start": "2028-09", "immovable_dates": [], "wait_one_cycle": True},
                    "household": {"dependants": 0, "partner_moves": False, "partner_work_needed": None, "return_obligation_stance": "depends", "deal_breakers": ["tuition above 4000 EUR total"]},
                    "risk_tolerance": {"money": "low", "long_shots": "medium"}})
    w("study_pathway_map", {
        "schema_version": "1.0", "generated": "2026-10-02",
        "objective": {"one_line": "Learn to model neural population activity and move into a doctorate.", "nearest_frameworks": ["computational neuroscience master's"],
                      "commitments": ["thesis-based master's"], "non_goals": ["pure software engineering degrees"]},
        "domains": [{"id": d, "label": f"Domain {d}", "priority": "critical" if i < 2 else "high", "coverage_keywords": [d.lower()], "self_teachable": ["no", "no", "partly", "yes", "unknown"][i]}
                    for i, d in enumerate(P.domains)],
        "pathway_signals": {"people_topic_signals": ["spiking network models", "neural population dynamics", "Bayesian inference for neural data", "brain-computer interfaces", "neuroimaging analysis"],
                            "organisation_type_signals": ["neuroscience institutes", "computational neuroscience centres"], "known_people_or_orgs": []},
        "practical_component_needed": {"type": "thesis", "credits": 30, "credit_system": "ECTS", "notes": "Self-proposed topic preferred."},
        "false_positive_traps": ["generic 'AI' degrees without neuroscience content"],
        "connectedness_check": {"connected": True, "notes": "Domains cover modelling, inference and data skills."},
        "progression": {"intent": "doctorate", "notes": "Thesis group should be able to host doctoral applicants."},
        "scoring_anchors": anchors(),
        "screening_rule": {"description": "Pass if curriculum covers >= 2 critical domains OR a named person's recent work hits a pathway signal.", "min_domains_for_pass": 2, "research_signal_pass": True, "unsure_policy": "pass"},
        "benchmarks_ref": "02_map/benchmarks.json"})
    w("benchmarks", {"benchmarks": [
        {"axis": "funding", "institution": "Bench University A", "programme": "MSc Funded Science", "baseline_vector": {"funding": 3, "programme": 1, "pathway": 2, "rubric_version": "1.0"}, "evidence_urls": ["https://example.edu/benchA"], "status": "verified"},
        {"axis": "programme", "institution": "Bench University B", "programme": "MSc Computational Neuroscience", "baseline_vector": {"funding": 2, "programme": 3, "pathway": 1, "rubric_version": "1.0"}, "evidence_urls": ["https://example.edu/benchB"], "status": "verified"},
        {"axis": "pathway", "institution": "Bench University C", "programme": "MSc Neural Systems", "baseline_vector": {"funding": 1, "programme": 2, "pathway": 3, "rubric_version": "1.0"}, "evidence_urls": ["https://example.edu/benchC"], "status": "provisional"}]})
    w("search_plan", {
        "schema_version": "1.0", "rubric_version": "1.0", "created": "2026-10-03",
        "countries": [{"slug": "northland", "name": "Northland", "depth": "deep", "cap_n": 3, "wave": 1}, {"slug": "eastmark", "name": "Eastmark", "depth": "standard", "cap_n": 2, "wave": 1}],
        "crosscuts": [{"slug": "joint_masters", "name": "Joint master's catalogue", "kind": "programme_scan", "description": "Multi-country joint degrees"},
                      {"slug": "home_scheme", "name": "Home-country scholarship", "kind": "funding_route", "description": "Outbound scholarship of the applicant's government"}],
        "benchmarks_ref": "02_map/benchmarks.json",
        "funded_definition": {"type": "tuition_only", "max_total_tuition": 4000, "max_out_of_pocket": 9000, "living_support_required_monthly": None, "household_size": 1,
                              "currency": "EUR", "min_funding_score": 2},
        "overlay_policy": "overlay only: never raise the base funding score; show effect and obligations next to it",
        "wave_weights": {"deep": 1.5, "standard": 1, "quick": 0.5, "crosscut": 0.75},
        "eligibility_facts_ref": "01_life_plan/life_plan.json#eligibility_facts", "exclusions": [{"country": "Westland", "reason": "excluded by the applicant"}],
        "session_plan": {"waves": [{"wave": 1, "countries": ["northland", "eastmark"], "expected_windows": 1}], "agents_per_window_estimate": 6}})

    # ---- Northland first pass
    nl01 = cand(P, "NL26-01", "Northfield University", "MSc Computational Science", (2, 2, 3), prior="NP1", status="update_of_existing",
                deadlines=[{"name": "Application autumn 2027", "date": "2026-12-01", "date_type": "confirmed", "source_url": "https://example.edu/nl26-01/dates", "cycle": "2027/28"},
                           {"name": "Scholarship round 2", "date": "2027-01-15", "date_type": "pattern", "source_url": "https://example.edu/nl26-01/dates"}],
                sup=("confirmed", "inferred"), elig="confirmed", verdict="tuition_free_no_stipend",
                extra={"household_fit": {"dependants_allowed": "yes", "partner_work_rights": "conditional", "family_allowance": "EUR 200/month per child", "notes": "Income proof needed.", "confidence": "inferred"}})
    nl02 = cand(P, "NL26-02", "Westbrook Institute of Technology", "MSc Applied Mathematics", (1, 2, "?"), sup=("verification_needed",), elig="unknown", verdict="unknown")
    nl03 = cand(P, "NL26-03", "Lakeside University", "MSc Complex Systems Science", (1, 1, 1), sup=("inferred",), elig="inferred")
    w_nl = {"country": "Northland", "slug": "northland", "run_date": "2026-10-20", "status": "partial_budget_exhausted", "path_b_done": False,
            "budget_notes": "Search budget exhausted after 3 records; Path B not run.",
            "screening": [screen("Northfield University", "pass", "covers NEURO and STAT modules", "both"), screen("Westbrook Institute of Technology", "pass", "applied maths group", "A"),
                          screen("Lakeside University", "pass", "unsure -> pass", "B"), screen("Hillcrest College", "fail", "no relevant people found on the staff pages", "none"),
                          screen("Marsh Polytechnic", "unscreened", "NOT SCREENED (budget)", "none")],
            "candidates": [nl01, nl02, nl03],
            "ranked_out": [ranked("Northfield University", "MSc Computational Data Science", ("?", 2, 2), "below the cap", True, "late-found; evidence incomplete"),
                           ranked("Lakeside University", "MSc Statistics", (1, 1, 1), "generic")],
            "corrections_to_prior": [{"prior_id": "NP1", "correction": "Tuition figure was stale (2023 value).", "source": "https://example.edu/nl26-01/fees"}],
            "country_context": {"funding_system": "Northland charges differentiated fees for international students.", "home_country_schemes": "None found.", "residence_pathway": "Job-seeker permit 12 months.",
                                "dependant_pathway": "Family reunification after 6 months; partner may work.", "application_cycle": "Dec-Jan for autumn."},
            "searched_not_surfaced": ["Marsh Polytechnic not screened (budget)."],
            "country_summary": "Northland has two strong-curriculum programmes.",
            "run_meta": {"agent_model": "synthetic-agent", "started_at": "2026-10-20T10:00:00Z", "ended_at": "2026-10-20T11:30:00Z", "tool_calls": 120,
                         "limit_events": [{"at": "2026-10-20T11:30:00Z", "kind": "search_budget", "detail": "stopped before Path B"}]}}
    jw(rp(OUT, "countries_dir") / "northland.json", w_nl)

    # ---- Northland follow-up
    nl02r = cand(P, "NL26-05", "Westbrook Institute of Technology", "MSc Applied Mathematics", (1, 2, 2), sup=("confirmed",), elig="inferred", verdict="competitive_scholarship_only",
                 extra={"replaces": "NL26-02", "status": "net_new"})
    nl04 = cand(P, "NL26-04", "Northfield University", "MSc Computational Data Science", (1, 2, 2), sup=("inferred",),
                deadlines=[{"name": "Application autumn 2027", "date": "2026-12-15", "date_type": "inferred", "source_url": None}])
    fu = {"country": "Northland", "slug": "northland", "followup_of": "northland", "run_date": "2026-10-22", "status": "complete", "path_b_done": True,
          "screening": [screen("Marsh Polytechnic", "pass", "numerical analysis group", "B")],
          "candidates": [nl02r, nl04], "ranked_out": [],
          "country_context": {"funding_system": "Fee waiver applies to scholarship holders only."},
          "country_summary": "Follow-up: Path B found two groups; Westbrook replaced with confirmed supervision.",
          "urgent_deadlines": [{"record_id": "NL26-01", "name": "Scholarship round 1", "date": "2026-11-20", "date_type": "confirmed", "source_url": "https://example.edu/nl26-01/dates"}],
          "path_b_people": [{"name": "Group leader, neural modelling (role descriptor)", "affiliation": "Northfield University", "focus": "population models", "url": None, "msc_link": "hosts MSc thesis students"}],
          "still_open": ["Confirm 2027/28 scholarship call."], "notes": "Marsh Polytechnic portal blocked for non-local IPs.",
          "extras": {"scheme_terms": {"name": "Northland Master Grant", "five_year_rule": True}},
          "run_meta": {"agent_model": "synthetic-agent", "started_at": "2026-10-22T09:00:00Z", "ended_at": "2026-10-22T10:00:00Z", "limit_events": []}}
    jw(rp(OUT, "followups_dir") / "northland_followup.json", fu)

    # ---- Eastmark
    ea = {"country": "Eastmark", "slug": "eastmark", "run_date": "2026-10-21", "status": "complete_with_gaps", "path_b_done": False,
          "screening": [screen("Eastmark Polytechnic", "pass", "biomedical engineering", "A"), screen("University of Ashgrove", "pass", "mathematics", "A"),
                        screen("Riverton University", "fail", "site blocked, not found", "none")],
          "candidates": [cand(P, "EA26-01", "Eastmark Polytechnic", "MSc Biomedical Engineering", (1, 1, 1), city="Eastgate", verdict="low_cost"),
                         cand(P, "EA26-02", "University of Ashgrove", "MSc Mathematics", (0, 2, 1), city="Ashgrove", verdict="fails")],
          "ranked_out": [ranked("Eastmark Polytechnic", "MSc Materials", (0, 1, 0), "weak fit")],
          "corrections_to_prior": [], "searched_not_surfaced": ["Riverton University site blocked (403)."],
          "country_summary": "Eastmark is expensive and has no stipends.",
          "run_meta": {"agent_model": "synthetic-agent", "started_at": "2026-10-21T09:00:00Z", "ended_at": "2026-10-21T10:30:00Z", "limit_events": []}}
    jw(rp(OUT, "countries_dir") / "eastmark.json", ea)

    # ---- crosscuts
    d = rp(OUT, "crosscuts_dir")
    xc01 = cand(P, "XC26-01", "Joint consortium Northfield-Eastmark", "Joint MSc Data and Brain Science", (3, 2, 2), track="Mobility track A", city="Multiple",
                verdict="funded_confirmed", extra={"consortium": {"full_members": ["Northfield University", "Eastmark Polytechnic"], "path": "year 1 Northfield, year 2 Eastmark", "source": "https://example.edu/joint"},
                                                    "overlays": [{"scheme": "Home-country outbound scholarship", "effect": 3, "obligations": "return within 12 months", "status": "unknown"}]})
    xc02 = cand(P, "XC26-02", "Lakeside University", "MSc Complex Systems Science", (1, 1, 1), sup=("inferred",), elig="inferred")
    xc02["sources"] = xc02["sources"][:2]
    jw(d / "joint_masters.json", {
        "crosscut_kind": "programme_scan", "country": "Joint master's catalogue", "slug": "joint_masters", "run_date": "2026-10-23", "status": "complete", "path_b_done": True,
        "catalogue_scan": [screen("Joint consortium Northfield-Eastmark", "pass", "joint degree", "A")], "screening": [screen("Joint consortium Northfield-Eastmark", "pass", "joint degree", "A")],
        "candidates": [xc01, xc02], "ranked_out": [], "searched_not_surfaced": [], "country_summary": "One joint master's of interest.", "scope_note": "Spans countries."})
    jw(d / "home_scheme.json", {
        "crosscut_kind": "funding_route", "route": "Home-country outbound scholarship", "route_type": "home_country_scheme", "checked_at": "2026-10-24", "status": "complete",
        "findings": [{"question": "Return obligation?", "answer": "Return within 12 months.", "confidence": "confirmed", "urls": ["https://example.gov/scheme"]},
                     {"question": "2027 call dates?", "answer": "Not published.", "confidence": "unknown", "urls": []}],
        "obligations": "Return within 12 months.", "verdict": "Overlay only; do not fold into base scores.", "open_questions": ["Confirm 2027 window."]})

    # ---- overrides, baseline, verification
    w("overrides", [{"target_id": "XC26-01", "field": "state_vector.funding", "original_value": 3, "new_value": 2,
                     "reason": "Competitive consortium awards are capped at 2 for consistency with other competitive stipends.", "decided_by": "orchestrator", "date": "2026-10-25"}])
    jw(OUT / "baseline_ledger.json", {"generated": "2026-10-01", "rubric_version": "1.0", "rows": [
        {"id": "NP1", "country": "Northland", "label": "Northfield University MSc Computational Science", "funding": 1, "programme": 2, "pathway": "?", "in_scope": True},
        {"id": "NP2", "country": "Northland", "label": "Old Hall MSc Mathematics", "funding": 1, "programme": 1, "pathway": 1, "in_scope": True},
        {"id": "B1", "country": "Elsewhere", "label": "Bench University A MSc Funded Science", "funding": 3, "programme": 1, "pathway": 2, "benchmark": True, "in_scope": False}]})
    w("verification", {"items": [
        {"id": "NL26-01", "claim": "Tuition EUR 1,000", "claim_type": "fee", "verdict": "confirmed", "evidence_url": "https://example.edu/nl26-01/fees", "note": "matches", "sampled_by": "top_n"},
        {"id": "NL26-01", "claim": "Deadline 1 Dec 2026", "claim_type": "deadline", "verdict": "wrong", "evidence_url": "https://example.edu/nl26-01/dates", "note": "1 Nov 2026", "sampled_by": "top_n"},
        {"id": "EA26-01", "claim": "Group supervises MSc", "claim_type": "people_partner", "verdict": "not_found", "evidence_url": None, "note": "no page", "sampled_by": "random"}],
        "summary": {"notes": "synthetic", "checked_by": "verifier-agent"}})
    # run_state: one finished session so status.py has something to show
    st = json.loads(rp(OUT, "run_state").read_text())
    st.update(current_phase="followups", next_action="Run followups.py then merge.py.", agents_per_window_observed=3.0,
              sessions=[{"n": 1, "started_at": "2026-10-20T09:00:00Z", "ended_at": "2026-10-20T11:30:00Z", "phase": "search", "outcome": "limit_hit", "limit_hit": True, "agents_run": 3, "wave": 1}],
              assumptions=[{"id": "A1", "text": "Savings cover living costs for the whole degree.", "made_in": "session 1, life_plan", "revisit": True}],
              overrides_of_protocol=[],
              checkpoints=[{"file": "04_search/countries/northland.json", "status": "partial_budget_exhausted", "updated_at": "2026-10-20T11:30:00Z", "records": 3},
                           {"file": "04_search/countries/eastmark.json", "status": "complete_with_gaps", "updated_at": "2026-10-21T10:30:00Z", "records": 2},
                           {"file": "04_search/followups/northland_followup.json", "status": "complete", "updated_at": "2026-10-22T10:00:00Z", "records": 2}],
              state_vector=vector("fixture-run", 1, "search -> followups", "Run follow-ups for the Northland gaps.",
                                  ["Review the follow-up triggers"], ["Run followups.py, then merge.py"],
                                  completed=["Life plan and pathway map passed", "Northland first pass (partial)", "Eastmark pass"],
                                  unknowns=["Northland Path B"], assumptions=[{"text": "Savings cover living costs.", "basis": "stated in the interview"}],
                                  blockers=[{"item": "Marsh Polytechnic portal blocked", "owner": "EXTERNAL"}],
                                  artifacts=["04_search/countries/northland.json", "04_search/countries/eastmark.json"]))
    w("run_state", st)

    schemas = [(rp(OUT, "countries_dir") / "northland.json", "country_run_file"), (rp(OUT, "countries_dir") / "eastmark.json", "country_run_file"),
               (rp(OUT, "followups_dir") / "northland_followup.json", "country_run_file"),
               (rp(OUT, "crosscuts_dir") / "joint_masters.json", "crosscut_scan_file"), (rp(OUT, "crosscuts_dir") / "home_scheme.json", "funding_route_crosscut"),
               (rp(OUT, "overrides"), "override"), (rp(OUT, "verification"), "verification_record"), (OUT / "baseline_ledger.json", "baseline_ledger")]
    return finish(OUT, schemas)


# --------------------------------------------------------------------------------------------- fixture B

def build_business() -> int:
    P = BUSINESS
    if OUT_B.exists():
        shutil.rmtree(OUT_B)
    init_workspace.main([str(OUT_B), "--alias", "Applicant B", "--mode", "local", "--run-id", "fixture-business"])
    w = lambda key, obj: jw(rp(OUT_B, key), obj)

    w("life_plan", {"schema_version": "1.0", "applicant_alias": "Applicant B", "profile_summary": "Applicant B, BA Design Management, six years in product teams, partner moves too", "updated_at": "2026-10-01T09:00:00Z",
                    "purpose_horizon": {"purpose": "Move from product management into service design leadership", "horizon_years": 7},
                    "post_degree_intent": {"intent": "career_switch", "routes_open": ["industry", "own_venture"], "keep_open_is": "hedge", "detail": "A leadership role at a design consultancy within a year"},
                    "money": {"funded_type": "affordable", "max_total_tuition": None, "max_out_of_pocket": 20000, "living_support_required_monthly": 1200, "household_size": 2,
                              "currency": "GBP", "debt_acceptable": True, "debt_limit": 10000, "income_during_degree": 800, "dependants_on_income": 0,
                              "hardness": "hard", "notes": "A paid internship counts towards living costs."},
                    "eligibility_facts": {"citizenships": ["Exampleland"], "residence_country": "Exampleland", "residence_region": "",
                                          "highest_degree": {"field": "Design Management", "country": "Exampleland", "graduation_year": 2018, "grade": "upper second", "grade_scale": "UK-style classes"},
                                          "language_certificates": [], "language_certificates_note": "None needed: degree taught in English",
                                          "age_bracket": "30-34", "fee_status": "overseas"},
                    "geography": {"considered": ["Southvale", "Westmarch"], "excluded": [], "languages_willing_c1": [], "teaching_languages_accepted": ["English"]},
                    "timeline": {"earliest_start": "2027-09", "latest_start": "2027-09", "immovable_dates": ["Partner's contract ends 2027-06"], "wait_one_cycle": False},
                    "household": {"dependants": 0, "partner_moves": True, "partner_work_needed": True, "return_obligation_stance": "acceptable", "deal_breakers": ["no work rights for the partner"]},
                    "risk_tolerance": {"money": "medium", "long_shots": "low"}})
    w("study_pathway_map", {
        "schema_version": "1.0", "generated": "2026-10-02",
        "objective": {"one_line": "Lead service-design teams at a consultancy after a one-year master's with a real client placement.", "nearest_frameworks": ["MSc Service Design", "MSc Innovation Management"],
                      "commitments": ["a paid placement or internship of at least 3 months"], "non_goals": ["purely theoretical management degrees"]},
        "domains": [{"id": d, "label": f"Domain {d}", "priority": "critical" if i < 2 else "high", "coverage_keywords": [d.lower()], "self_teachable": ["no", "no", "partly", "yes", "unknown", "yes"][i]}
                    for i, d in enumerate(P.domains)],
        "pathway_signals": {"people_topic_signals": ["service design studios", "consultancy placements", "client projects", "innovation labs", "employer-sponsored capstones", "design thinking"],
                            "organisation_type_signals": ["design schools with agency partners", "business schools with studio partners"], "known_people_or_orgs": []},
        "practical_component_needed": {"type": "internship", "credits": 60, "credit_system": "UK credits (CATS)", "notes": "Host may be chosen by the student; paid."},
        "false_positive_traps": ["general MBA programmes without a design strand"],
        "connectedness_check": {"connected": True, "notes": "Strategy and design methods connect to the leadership goal."},
        "progression": {"intent": "graduate scheme or consultancy hire", "notes": "Placement partners should recruit from the programme."},
        "scoring_anchors": anchors(),
        "screening_rule": {"description": "Pass if the curriculum covers >= 2 critical domains OR a named placement partner hits a pathway signal.", "min_domains_for_pass": 2, "research_signal_pass": True, "unsure_policy": "pass"},
        "benchmarks_ref": "02_map/benchmarks.json"})
    w("benchmarks", {"benchmarks": [
        {"axis": "funding", "institution": "Bench Business School A", "programme": "MSc Funded Innovation", "baseline_vector": {"funding": 3, "programme": 1, "pathway": 2, "rubric_version": "1.0"}, "evidence_urls": ["https://example.edu/benchA"], "status": "verified"},
        {"axis": "programme", "institution": "Bench Design School B", "programme": "MSc Service Design", "baseline_vector": {"funding": 2, "programme": 3, "pathway": 1, "rubric_version": "1.0"}, "evidence_urls": ["https://example.edu/benchB"], "status": "verified"},
        {"axis": "pathway", "institution": "Bench Design School C", "programme": "MSc Design Leadership with Placement", "baseline_vector": {"funding": 1, "programme": 2, "pathway": 3, "rubric_version": "1.0"}, "evidence_urls": ["https://example.edu/benchC"], "status": "verified"}]})
    w("search_plan", {
        "schema_version": "1.0", "rubric_version": "1.0", "created": "2026-10-03",
        "countries": [{"slug": "southvale", "name": "Southvale", "depth": "deep", "cap_n": 4, "wave": 1}, {"slug": "westmarch", "name": "Westmarch", "depth": "quick", "cap_n": 4, "wave": 1}],
        "crosscuts": [], "benchmarks_ref": "02_map/benchmarks.json",
        "funded_definition": {"type": "affordable", "max_total_tuition": None, "max_out_of_pocket": 20000, "living_support_required_monthly": 1200, "household_size": 2, "currency": "GBP", "min_funding_score": 2},
        "overlay_policy": "overlay only: never raise the base funding score; show effect and obligations next to it",
        "eligibility_facts_ref": "01_life_plan/life_plan.json#eligibility_facts", "exclusions": [],
        "session_plan": {"waves": [{"wave": 1, "countries": ["southvale", "westmarch"], "expected_windows": 1}], "agents_per_window_estimate": 4}})

    hf = {"dependants_allowed": "yes", "partner_work_rights": "yes", "family_allowance": "", "notes": "Partner may work full time on a student's family permit.", "confidence": "confirmed"}
    sv01 = cand(P, "SV26-01", "Harbour School of Design", "MSc Service Design with Placement", (2, 3, 3), city="Harbourton",
                deadlines=[{"name": "Main round", "date": "2027-01-31", "date_type": "confirmed", "source_url": "https://example.edu/sv26-01/dates", "cycle": "2027/28"}],
                verdict="competitive_scholarship_only", extra={"household_fit": hf})
    sv02 = cand(P, "SV26-02", "Southvale Business School", "MSc Innovation Management", (2, 2, 2), city="Southgate", sup=("inferred",), elig="inferred",
                deadlines=[{"name": "Placement-track deadline", "date": "2026-12-10", "date_type": "confirmed", "source_url": "https://example.edu/sv26-02/dates"}],
                extra={"household_fit": dict(hf, partner_work_rights="conditional", confidence="inferred")})
    sv03 = cand(P, "SV26-03", "Vale Institute of Technology", "MSc Design Management", (1, 2, 1), city="Valeton", sup=("verification_needed",), elig="inferred")
    sv04 = cand(P, "SV26-04", "Harbour School of Design", "MSc Creative Entrepreneurship", (1, 1, 2), city="Harbourton", sup=("confirmed",), elig="confirmed")
    sv = {"country": "Southvale", "slug": "southvale", "run_date": "2026-10-20", "status": "complete", "path_b_done": True,
          "screening": [screen("Harbour School of Design", "pass", "service design strand and agency partners", "both"), screen("Southvale Business School", "pass", "innovation placements", "A"),
                        screen("Vale Institute of Technology", "pass", "design management", "B"), screen("Old Town College", "fail", "no practical component offered", "none")],
          "candidates": [sv01, sv02, sv03, sv04],
          "ranked_out": [ranked("Southvale Business School", "MBA General", (0, 1, 1), "no design strand")],
          "corrections_to_prior": [], "searched_not_surfaced": [],
          "country_context": {"funding_system": "Fees are set per institution; most scholarships need a separate application.", "home_country_schemes": "None found.",
                              "residence_pathway": "Graduate visa for 24 months after the degree.",
                              "dependant_pathway": "Partner may join on a family permit and work.", "application_cycle": "Rolling from October, main round January."},
          "country_summary": "Southvale has two strong placement-based programmes.",
          "run_meta": {"agent_model": "synthetic-agent", "started_at": "2026-10-20T09:00:00Z", "ended_at": "2026-10-20T11:00:00Z", "limit_events": []}}
    jw(rp(OUT_B, "countries_dir") / "southvale.json", sv)
    wm = {"country": "Westmarch", "slug": "westmarch", "run_date": "2026-10-21", "status": "complete", "path_b_done": True,
          "screening": [screen("Westmarch Academy of Arts", "pass", "design leadership", "A")],
          "candidates": [cand(P, "WM26-01", "Westmarch Academy of Arts", "MSc Design Leadership", (1, 2, 2), city="Marchton", sup=("confirmed",), elig="inferred", verdict="low_cost",
                              extra={"household_fit": dict(hf, dependants_allowed="conditional", notes="Income threshold applies to partners.", confidence="inferred")})],
          "ranked_out": [], "corrections_to_prior": [], "searched_not_surfaced": [],
          "country_context": {"funding_system": "Low tuition; no stipends.", "home_country_schemes": "None found.", "residence_pathway": "Post-study permit 12 months.",
                              "dependant_pathway": "Partner permit above an income threshold.", "application_cycle": "March."},
          "country_summary": "Westmarch is cheap but thin on placements.",
          "run_meta": {"agent_model": "synthetic-agent", "started_at": "2026-10-21T09:00:00Z", "ended_at": "2026-10-21T09:45:00Z", "limit_events": []}}
    jw(rp(OUT_B, "countries_dir") / "westmarch.json", wm)

    st = json.loads(rp(OUT_B, "run_state").read_text())
    st.update(current_phase="merge", next_action="Run merge.py, then sample_verification.py.", agents_per_window_observed=4.0,
              sessions=[{"n": 1, "started_at": "2026-10-20T09:00:00Z", "ended_at": "2026-10-21T09:45:00Z", "phase": "search", "outcome": "complete", "limit_hit": False, "agents_run": 4, "wave": 1}],
              checkpoints=[{"file": "04_search/countries/southvale.json", "status": "complete", "updated_at": "2026-10-20T11:00:00Z", "records": 4},
                           {"file": "04_search/countries/westmarch.json", "status": "complete", "updated_at": "2026-10-21T09:45:00Z", "records": 1}],
              state_vector=vector("fixture-business", 1, "search -> merge", "Merge the two country files.", [], ["Run merge.py, then sample_verification.py"],
                                  completed=["Life plan and pathway map passed", "Southvale and Westmarch searched"], artifacts=["04_search/countries/southvale.json"]))
    w("run_state", st)
    schemas = [(rp(OUT_B, "countries_dir") / "southvale.json", "country_run_file"), (rp(OUT_B, "countries_dir") / "westmarch.json", "country_run_file")]
    return finish(OUT_B, schemas)


def main() -> None:
    bad = build_science() + build_business()
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
