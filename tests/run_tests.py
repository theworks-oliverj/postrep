#!/usr/bin/env python3
"""
run_tests.py - end-to-end tests for the virgil-protocol scripts (stdlib unittest only).

HOW IT WORKS
    Every test copies the synthetic fixture workspace (tests/fixtures/run, fictional data
    only) into a fresh temp folder and then drives the real command-line scripts through
    subprocess, exactly as an agent or a human would. Nothing is mocked.

USAGE
    python3 tests/run_tests.py            # runs the suite twice: with `jsonschema` (if installed)
                                         # and again with the built-in validator
    python3 tests/run_tests.py --once     # run once with whatever validator is available
    python3 tests/run_tests.py -k merge   # unittest options are passed through

    To regenerate the fixture after changing a schema:  python3 tests/build_fixture.py
"""
from __future__ import annotations

import concurrent.futures
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
FIXTURE = HERE / "fixtures" / "run"
FIXTURE_B = HERE / "fixtures" / "run_business"
sys.path.insert(0, str(SCRIPTS))
import _common as C  # noqa: E402


def run(script: str, *args, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], input=stdin, capture_output=True, text=True, env=os.environ.copy())


def jload(p) -> object:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def jsave(p, obj) -> None:
    Path(p).write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


class WS(unittest.TestCase):
    """Base class: a private copy of the fixture workspace in self.run_dir."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.run_dir = Path(self._tmp.name) / "run"
        shutil.copytree(FIXTURE, self.run_dir)

    def p(self, key):
        return C.rp(self.run_dir, key)

    def merge(self, *extra):
        return run("merge.py", self.run_dir, "--baseline", self.run_dir / "baseline_ledger.json", "--now", "2026-10-27T12:00:00Z", *extra)

    def merged(self):
        return jload(self.p("merged"))

    def cand(self, cid):
        return next(c for c in self.merged()["candidates"] if c["id"] == cid)


class TestSchemas(unittest.TestCase):
    def test_every_schema_is_wellformed_and_documented(self):
        schemas = C.load_schemas()
        self.assertGreaterEqual(len(schemas), 20)
        try:
            import jsonschema
            check = jsonschema.Draft202012Validator.check_schema
        except ImportError:
            check = lambda s: None

        def walk(node, where):
            if isinstance(node, dict):
                for name, sub in (node.get("properties") or {}).items():
                    if isinstance(sub, dict) and "$ref" not in sub:
                        self.assertIn("description", sub, f"{where}.{name} lacks a description")
                    walk(sub, f"{where}.{name}")
                for key in ("items", "additionalProperties"):
                    if isinstance(node.get(key), dict):
                        walk(node[key], f"{where}[{key}]")
        for name, s in schemas.items():
            check(s)
            self.assertEqual(s["$schema"], "https://json-schema.org/draft/2020-12/schema", name)
            for k in ("$id", "title", "description"):
                self.assertTrue(s.get(k), f"{name} lacks {k}")
            self.assertTrue(s["$id"].endswith(f"{name}.schema.json"))
            walk(s, name)

    def test_expected_schemas_exist(self):
        want = """candidate_record state_vector screening_entry ranked_out_entry country_run_file crosscut_scan_file funding_route_crosscut merged_file merge_report
                  override followup_trigger verification_record study_pathway_map benchmarks life_plan rubric_score search_plan run_state session_log_entry
                  people_reading_list prior_programme_record continuation_state_vector""".split()
        self.assertFalse(set(want) - set(C.load_schemas()))
        self.assertFalse({"research" + "_domain_map", "advisor_" + "research_papers"} & set(C.load_schemas()), "old schema names must be gone (no alias)")

    def test_state_vector_rules(self):
        ok = {"funding": 0, "programme": "?", "pathway": 3}
        self.assertEqual(C.validate(ok, "state_vector"), [])
        for bad in ({"funding": 4, "programme": 1, "pathway": 1}, {"funding": "n/a", "programme": 1, "pathway": 1}, {"funding": True, "programme": 1, "pathway": 1},
                    {"funding": 1, "programme": 1}, {"funding": 1, "programme": 1, "pathway": 1, "extra": 1}):
            self.assertTrue(C.validate(bad, "state_vector"), bad)

    def test_domain_ids_are_user_defined(self):
        rec = jload(FIXTURE / "04_search/countries/northland.json")["candidates"][0]
        self.assertEqual(C.validate(rec, "candidate_record"), [])
        rec["axis_1_curriculum"]["lower_case"] = rec["axis_1_curriculum"].pop("NEURO")
        errs = C.validate(rec, "candidate_record")
        self.assertTrue(any(e.kind == "additionalProperties" for e in errs), errs)

    def test_validators_agree(self):
        """The built-in validator must give the same verdict (path, keyword) as jsonschema."""
        try:
            import jsonschema  # noqa: F401
        except ImportError:
            self.skipTest("jsonschema not installed")
        good = jload(FIXTURE / "04_search/countries/northland.json")
        mutations = [lambda d: d, lambda d: d.update(status="done"), lambda d: d["candidates"][0].update(id="bad id"), lambda d: d["candidates"][0].pop("tuition"),
                     lambda d: d["candidates"][0]["state_vector"].update(funding=9), lambda d: d["screening"][0].update(decision="pass (weak)"),
                     lambda d: d["candidates"][0]["deadlines"].append({"name": "x", "date": "2026-13-45", "date_type": "confirmed", "source_url": None}),
                     lambda d: d["candidates"][0].update(surprise=1), lambda d: d.update(run_date="yesterday")]
        saved = os.environ.get("VIRGIL_BUILTIN_VALIDATOR")
        try:
            for mut in mutations:
                doc = copy.deepcopy(good)
                mut(doc)
                os.environ.pop("VIRGIL_BUILTIN_VALIDATOR", None)
                C._LIB = None
                a = {(e.path, e.kind) for e in C.validate(doc, "country_run_file")}
                os.environ["VIRGIL_BUILTIN_VALIDATOR"] = "1"
                C._LIB = None
                b = {(e.path, e.kind) for e in C.validate(doc, "country_run_file")}
                self.assertEqual(a, b)
        finally:
            if saved is None:
                os.environ.pop("VIRGIL_BUILTIN_VALIDATOR", None)
            else:
                os.environ["VIRGIL_BUILTIN_VALIDATOR"] = saved
            C._LIB = None

    def test_helpers(self):
        self.assertEqual(C.vector_total({"funding": 2, "programme": "?", "pathway": 3}), 5)
        self.assertIsNone(C.vector_total({"funding": "?", "programme": "?", "pathway": "?"}))
        self.assertEqual(C.unscored_axes({"funding": 2, "programme": "?", "pathway": "?"}), 2)
        self.assertEqual(C.norm_text("Université de Lausanne (UNIL)"), "universite de lausanne unil")
        d = {"a": [{"b": 1}]}
        self.assertEqual(C.set_path(d, "a.0.b", 5), 1)
        self.assertEqual(C.get_path(d, "a.0.b"), 5)


class TestSchemaAdditions(unittest.TestCase):
    """Fields added after the first dry run of the protocol (see CHANGES in each schema description)."""

    def ok(self, doc, schema):
        self.assertEqual([(e.path, e.message) for e in C.validate(doc, schema)], [])

    def bad(self, doc, schema, kind=None):
        errs = C.validate(doc, schema)
        self.assertTrue(errs)
        if kind:
            self.assertIn(kind, {e.kind for e in errs}, errs)

    def test_run_state_assumptions_overrides_and_wave(self):
        st = jload(FIXTURE / "run_state.json")
        self.ok(st, "run_state")
        self.assertTrue(st["assumptions"] and "wave" in st["sessions"][0])
        st["overrides_of_protocol"] = [{"date": "2026-10-27", "rule": "r", "override": "o"}]
        self.bad(st, "run_state", "required")                          # reason is mandatory
        st["overrides_of_protocol"] = []
        st["current_phase"] = "S4_wave_1"                              # the phase enum is unchanged: free-form phases are rejected
        self.bad(st, "run_state", "enum")

    def test_search_plan_additions(self):
        plan = jload(FIXTURE / "03_scope/search_plan.json")
        self.ok(plan, "search_plan")
        plan["countries"].append({"slug": "tiny", "name": "Tiny", "depth": "quick", "wave": 2})          # quick: cap_n optional
        plan["exclusions"] = ["X: reason", {"country": "Y", "reason": "reason"}]                         # both forms
        plan["wave_weights"] = {"deep": 1.5, "standard": 1, "quick": 0.5, "crosscut": 0.75}
        self.ok(plan, "search_plan")
        plan["exclusions"] = [{"country": "Y"}]
        self.bad(plan, "search_plan")
        plan["exclusions"] = []
        plan["wave_weights"] = {"deep": 2, "huge": 3}
        self.bad(plan, "search_plan", "additionalProperties")
        plan["wave_weights"] = {"deep": 2}
        plan["funded_definition"]["min_funding_score"] = 4
        self.bad(plan, "search_plan")
        import _common
        self.assertEqual(_common.cap_n_of({"depth": "quick"}), 4)
        self.assertEqual(_common.cap_n_of({"depth": "quick", "cap_n": 6}), 6)
        self.assertIsNone(_common.cap_n_of({"depth": "deep"}))

    def test_life_plan_structured_fields(self):
        lp = jload(FIXTURE / "01_life_plan/life_plan.json")
        self.ok(lp, "life_plan")
        for path, val in ((("household", "return_obligation_stance"), "maybe"), (("risk_tolerance", "money"), "extreme"), (("money", "funded_type"), "free"),
                          (("eligibility_facts", "language_certificates"), [{"score": "7"}]), (("eligibility_facts", "highest_degree", "graduation_year"), "2018")):
            bad = copy.deepcopy(lp)
            node = bad
            for k in path[:-1]:
                node = node[k]
            node[path[-1]] = val
            self.bad(bad, "life_plan")
        # the legacy blocks and the fee_category gate are gone; free-text fee_status is the optional replacement
        old = {"schema_version": "1.0", "applicant_alias": "A", "eligibility_facts": {"fee_category": "overseas", "years_since_degree": 4},
               "money_operationalised": {"funded_definition": {"type": "tuition_only", "currency": "EUR"}}, "timeline": {"target_start": "2027-09"}}
        self.bad(old, "life_plan", "additionalProperties")
        fs = copy.deepcopy(lp)
        fs["eligibility_facts"]["fee_status"] = "any free text, e.g. 'overseas, 3 years resident'"
        self.ok(fs, "life_plan")
        fs["eligibility_facts"].pop("fee_status")
        self.ok(fs, "life_plan")

    def test_pathway_map_self_teachable_and_practical_component(self):
        dm = jload(FIXTURE / "02_map/study_pathway_map.json")
        self.ok(dm, "study_pathway_map")
        for v in ("yes", "no", "partly", "unknown"):
            dm["domains"][0]["self_teachable"] = v
            self.ok(dm, "study_pathway_map")
        for v in ("maybe", True, False, None):                          # the old boolean form is gone
            dm["domains"][0]["self_teachable"] = v
            self.bad(dm, "study_pathway_map", "enum")
        dm["domains"][0]["self_teachable"] = "yes"
        for pc in ({"type": "internship", "credits": 60, "credit_system": "US semester credits", "notes": "paid"}, {"type": "none"}, {"type": "studio_or_clinic", "credits": None, "credit_system": "UK CATS"}):
            dm["practical_component_needed"] = pc
            self.ok(dm, "study_pathway_map")
        dm["practical_component_needed"] = {"type": "dissertation"}
        self.bad(dm, "study_pathway_map", "enum")
        dm["practical_component_needed"] = {"type": "thesis"}
        dm["research_signals"] = {"priority_signals": ["x"]}            # renamed to pathway_signals
        self.bad(dm, "study_pathway_map", "additionalProperties")
        del dm["research_signals"]
        dm["pathway_signals"] = {"people_topic_signals": ["a"], "organisation_type_signals": ["b"], "known_people_or_orgs": []}
        self.ok(dm, "study_pathway_map")
        dm["pathway_signals"] = {"people_topic_signals": ["a"]}         # both lists are required
        self.bad(dm, "study_pathway_map", "required")

    def test_candidate_pathway_fields_and_renames(self):
        rec = jload(FIXTURE / "04_search/countries/northland.json")["candidates"][0]
        self.ok(rec, "candidate_record")
        for old in ("axis_2_" + "research", "research_" + "credit", "phd_" + "pathway"):
            self.assertNotIn(old, rec)
        self.assertEqual(set(rec["state_vector"]) - {"rubric_version", "notes"}, {"funding", "programme", "pathway"})
        self.assertIn("vs_pathway_benchmark", rec["benchmark_comparison"])
        for ptype in ("research_group", "lab", "industry_partner", "internship_programme", "placement_scheme", "professional_body", "other"):
            r2 = copy.deepcopy(rec)
            r2["axis_2_pathway"]["people_and_partners"][0]["type"] = ptype
            self.ok(r2, "candidate_record")
        for ctype in ("thesis", "internship", "industry_placement", "capstone", "co_op", "studio_or_clinic", "none", "other"):
            r2 = copy.deepcopy(rec)
            r2["practical_component"]["type"] = ctype
            self.ok(r2, "candidate_record")
        for mutate, kind in ((lambda r: r["axis_2_pathway"]["people_and_partners"][0].update(type="faculty"), "enum"),
                             (lambda r: r["axis_2_pathway"]["people_and_partners"][0]["contacts"][0].update(takes_students="yes"), "enum"),
                             (lambda r: r["axis_2_pathway"]["people_and_partners"][0]["contacts"][0].pop("takes_students"), "required"),
                             (lambda r: r["practical_component"].pop("credits"), "required"),
                             (lambda r: r["practical_component"].update(type="dissertation"), "enum"),
                             (lambda r: r["practical_component"].update(self_proposed="yes"), "type"),
                             (lambda r: r.update(**{"axis_2_" + "research": {}}), "additionalProperties"),
                             (lambda r: r.update(**{"research_" + "credit": "30 ECTS"}), "additionalProperties"),
                             (lambda r: r.update(phd_pathway="x"), "additionalProperties"),
                             (lambda r: r.update(progression=None), "type"),
                             (lambda r: r["benchmark_comparison"].update(**{"vs_research_" + "benchmark": "weaker"}), "additionalProperties")):
            r2 = copy.deepcopy(rec)
            mutate(r2)
            self.bad(r2, "candidate_record", kind)

    def test_continuation_state_vector_schema(self):
        v = jload(FIXTURE / "run_state.json")["state_vector"]
        self.ok(v, "continuation_state_vector")
        self.assertEqual(set(v), {"run", "session", "date", "phase", "session_objective", "context", "unknowns", "ambiguities", "assumptions", "completed", "active", "next", "blockers", "artifacts"})
        for phase in ("search", "search -> followups", "map → scope", "done"):
            self.ok(dict(v, phase=phase), "continuation_state_vector")
        for bad in (dict(v, phase="S4_wave_1"), dict(v, phase="research"), dict(v, blockers=[{"item": "x", "owner": "NOBODY"}]), dict(v, blockers=[{"item": "x"}]),
                    dict(v, assumptions=[{"text": "t"}]), dict(v, active={"user": []}), dict(v, extra=1), {k: x for k, x in v.items() if k != "next"}):
            self.bad(bad, "continuation_state_vector")
        for owner in ("USER", "VIRGIL", "EXTERNAL"):
            self.ok(dict(v, blockers=[{"item": "x", "owner": owner}]), "continuation_state_vector")
        st = jload(FIXTURE / "run_state.json")
        self.ok(st, "run_state")
        del st["state_vector"]
        self.bad(st, "run_state", "required")
        for ph in ("init", "life_plan", "map", "scope", "search", "followups", "merge", "verify", "deliverables", "done"):
            self.ok(dict(jload(FIXTURE / "run_state.json"), current_phase=ph), "run_state")
        self.bad(dict(jload(FIXTURE / "run_state.json"), current_phase="domain_map"), "run_state", "enum")

    def test_candidate_language_household_and_context(self):
        rec = jload(FIXTURE / "04_search/countries/northland.json")["candidates"][0]
        self.ok(rec, "candidate_record")
        self.assertIn("household_fit", rec)
        rec["language"]["source_url"] = None
        self.ok(rec, "candidate_record")
        rec["language"]["source_url"] = "official"                    # text is not a URL
        self.bad(rec, "candidate_record", "pattern")
        rec["language"]["source_url"] = "https://example.edu/l"
        rec["language"]["source"] = "official"                         # the old key is gone
        self.bad(rec, "candidate_record", "additionalProperties")
        del rec["language"]["source"]
        rec["household_fit"]["dependants_allowed"] = "maybe"
        self.bad(rec, "candidate_record", "enum")
        ctx = jload(FIXTURE / "04_search/countries/northland.json")["country_context"]
        self.assertIn("dependant_pathway", ctx)

    def test_funding_route_crosscut_status(self):
        fr = jload(FIXTURE / "04_search/crosscuts/home_scheme.json")
        self.ok(fr, "funding_route_crosscut")
        fr["status"] = "done"
        self.bad(fr, "funding_route_crosscut", "enum")
        fr["status"] = "in_progress"
        fr["notes"], fr["budget_notes"] = "n", "b"
        self.ok(fr, "funding_route_crosscut")


class TestInit(unittest.TestCase):
    def test_creates_valid_skeleton_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "r"
            r = run("init_workspace.py", d, "--alias", "Applicant Q", "--mode", "api")
            self.assertEqual(r.returncode, 0, r.stderr)
            for rel in ("run_state.json", "01_life_plan/life_plan.md", "01_life_plan/life_plan_score.json", "02_map/benchmarks.json", "03_scope/search_plan.json",
                        "04_search/overrides.json", "04_search/countries", "04_search/followups", "04_search/crosscuts", "05_merge", "06_verify", "07_deliverables", "logs/session_log.jsonl"):
                self.assertTrue((d / rel).exists(), rel)
            v = run("validate.py", d)
            self.assertEqual(v.returncode, 0, v.stdout + v.stderr)
            state = jload(d / "run_state.json")
            self.assertEqual((state["applicant_alias"], state["mode"], state["current_phase"]), ("Applicant Q", "api", "init"))
            jsave(d / "01_life_plan/life_plan.json", {"schema_version": "1.0", "applicant_alias": "Applicant Q", "marker": 1})
            self.assertEqual(run("init_workspace.py", d, "--alias", "Applicant Q", "--mode", "api").returncode, 0)
            self.assertEqual(jload(d / "01_life_plan/life_plan.json")["marker"], 1, "existing file must be kept")
            # an unfilled score sheet can never pass
            self.assertEqual(run("rubric.py", d, "life_plan", "--check").returncode, 1)

    def test_documents_are_copied_from_templates(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "r"
            self.assertEqual(run("init_workspace.py", d, "--alias", "Applicant Q", "--mode", "local").returncode, 0)
            T = ROOT / "protocol" / "templates"
            for tpl, dest in (("life_plan.md", "01_life_plan/life_plan.md"), ("pathway_map.md", "02_map/pathway_map.md"), ("AGENT_BRIEF.md", "03_scope/AGENT_BRIEF.md"),
                              ("options_rundown.md", "07_deliverables/options_rundown_template.md"), ("due_diligence.md", "07_deliverables/due_diligence_template.md")):
                self.assertEqual((d / dest).read_text(encoding="utf-8"), (T / tpl).read_text(encoding="utf-8"), dest)
            notes = (d / "01_life_plan/interview_notes.md").read_text(encoding="utf-8")
            self.assertIn("append-only", notes.lower())
            self.assertLess(len(notes.splitlines()), 8, "header only")
            st = jload(d / "run_state.json")
            self.assertEqual((st["assumptions"], st["overrides_of_protocol"]), ([], []))
            # an existing document is kept on a second run (the interview may already be in it)
            (d / "01_life_plan/life_plan.md").write_text("# mine\n", encoding="utf-8")
            run("init_workspace.py", d, "--alias", "Applicant Q", "--mode", "local")
            self.assertEqual((d / "01_life_plan/life_plan.md").read_text(encoding="utf-8"), "# mine\n")

    def test_bad_mode_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(run("init_workspace.py", Path(t) / "r", "--alias", "A", "--mode", "weird").returncode, 2)


class TestValidate(WS):
    def test_fixture_is_valid(self):
        r = run("validate.py", self.run_dir)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("RESULT: OK", r.stdout)

    def test_reports_enum_drift_and_missing_required(self):
        f = self.p("countries_dir") / "eastmark.json"
        d = jload(f)
        d["screening"][0]["decision"] = "pass (weak)"
        d["screening"][1]["decision"] = "pass (weak)"
        del d["candidates"][0]["tuition"]
        jsave(f, d)
        r = run("validate.py", self.run_dir)
        self.assertEqual(r.returncode, 1)
        self.assertIn("ENUM DRIFT", r.stdout)
        self.assertIn("'pass (weak)' x2", r.stdout)
        self.assertIn("MISSING REQUIRED", r.stdout)
        self.assertIn("tuition", r.stdout)
        js = json.loads(run("validate.py", self.run_dir, "--json").stdout)
        self.assertTrue(js["enum_drift"] and js["missing_required"])

    def test_semantic_errors_and_strict(self):
        f = self.p("countries_dir") / "northland.json"
        d = jload(f)
        d["slug"] = "wrongname"
        d["ranked_out"][0]["promote_reason"] = ""
        del d["ranked_out"][0]["promote_reason"]
        jsave(f, d)
        r = run("validate.py", self.run_dir)
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not match file name", r.stdout)
        self.assertIn("without promote_reason", r.stdout)
        # warnings alone pass, but fail under --strict
        shutil.rmtree(self.run_dir)
        shutil.copytree(FIXTURE, self.run_dir)
        d = jload(f)
        del d["candidates"][0]["sources"][0]["source_type"]
        jsave(f, d)
        self.assertEqual(run("validate.py", self.run_dir).returncode, 0)
        self.assertEqual(run("validate.py", self.run_dir, "--strict").returncode, 1)

    def test_new_warnings_cap_n_and_household_fit(self):
        plan = jload(self.p("search_plan"))
        plan["countries"][0].pop("cap_n")
        plan["countries"].append({"slug": "tiny", "name": "Tiny", "depth": "quick", "wave": 2})
        jsave(self.p("search_plan"), plan)
        out = run("validate.py", self.run_dir).stdout
        self.assertIn("country 'northland' (depth deep) has no cap_n", out)
        self.assertNotIn("country 'tiny'", out)
        self.assertNotIn("household_fit although", out)
        lp = jload(self.p("life_plan"))
        lp["household"].update(dependants=2, partner_moves=True)
        jsave(self.p("life_plan"), lp)
        out = run("validate.py", self.run_dir).stdout
        self.assertRegex(out, r"\d+ records without household_fit although the life plan has dependants")

    def test_missing_run_dir(self):
        self.assertEqual(run("validate.py", self.run_dir / "nope").returncode, 2)


class TestCheckpoint(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.d = Path(self._tmp.name) / "r"
        run("init_workspace.py", self.d, "--alias", "Applicant Q", "--mode", "local")
        self.pass_gates()
        self.cand = jload(FIXTURE / "04_search/countries/northland.json")["candidates"][0]
        self.cf = self.d / "04_search/countries/ardenia.json"

    def cp(self, *a, stdin=None):
        return run("checkpoint.py", self.d, *a, stdin=stdin)

    def pass_gates(self):
        """Mark both gate sheets passed (the real scoring path is tested in TestStatusAndRubric)."""
        for key in ("life_plan_score", "map_score"):
            d = jload(C.rp(self.d, key))
            d["passed"] = True
            jsave(C.rp(self.d, key), d)

    def test_full_agent_cycle(self):
        self.assertEqual(self.cp("log-session", "--start", "--phase", "search").returncode, 0)
        r = self.cp("init-country", "--country", "ardenia", "--name", "Ardenia", "--agent-model", "test-model")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.cp("init-country", "--country", "ardenia", "--name", "Ardenia").returncode, 2, "re-init must not clobber")
        self.assertEqual(self.cp("init-country", "--country", "ardenia", "--name", "Ardenia", "--resume").returncode, 0)
        # screening: --json, upsert by institution
        row = {"institution": "Northfield University", "decision": "pass", "entry_path": "A", "reason": "ok"}
        self.assertEqual(self.cp("add-screening", "--country", "ardenia", "--json", json.dumps(row)).returncode, 0)
        row["decision"] = "fail"
        r = self.cp("add-screening", "--country", "ardenia", "--json", json.dumps(row))
        self.assertIn('"action": "replaced"', r.stdout)
        self.assertEqual(len(jload(self.cf)["screening"]), 1)
        # candidate via --file and via stdin
        f = self.d / "rec.json"
        jsave(f, self.cand)
        self.assertEqual(self.cp("add-candidate", "--country", "ardenia", "--file", f).returncode, 0)
        rec2 = dict(self.cand, id="NL26-09", institution="Other University")
        r = self.cp("add-candidate", "--country", "ardenia", stdin=json.dumps(rec2))
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = jload(self.cf)
        self.assertEqual([c["id"] for c in doc["candidates"]], ["NL26-01", "NL26-09"])
        self.assertEqual(doc["candidates"][0]["provenance"]["pass"], "first_pass")
        self.assertEqual(doc["candidates"][0]["provenance"]["session"], 1)
        self.assertTrue(self.cf.with_name("ardenia.json.bak").exists(), "previous version must be kept")
        # ranked_out incl. promote
        ro = {"institution": "X", "programme": "Y", "prelim_state_vector": {"funding": 1, "programme": "?", "pathway": 2}, "why_below_cut": "cap", "promote": True, "promote_reason": "late"}
        self.assertEqual(self.cp("add-ranked-out", "--country", "ardenia", "--json", json.dumps(ro)).returncode, 0)
        # complete refused while path B not done
        r = self.cp("set-status", "--country", "ardenia", "--status", "complete")
        self.assertEqual(r.returncode, 2)
        self.assertIn("path_b_done", r.stderr)
        r = self.cp("set-status", "--country", "ardenia", "--path-b-done", "true", "--status", "complete", "--add-gap", "Marsh City not searched", "--limit-event", "search_budget:stopped early",
                    "--budget-notes", "budget hit")
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = jload(self.cf)
        self.assertEqual((doc["status"], doc["path_b_done"], doc["searched_not_surfaced"]), ("complete", True, ["Marsh City not searched"]))
        self.assertEqual(doc["run_meta"]["limit_events"][0]["kind"], "search_budget")
        self.assertIn("ended_at", doc["run_meta"])
        # run_state tracks the file
        st = jload(self.d / "run_state.json")
        cp = next(c for c in st["checkpoints"] if c["file"] == "04_search/countries/ardenia.json")
        self.assertEqual((cp["status"], cp["records"]), ("complete", 2))
        self.assertEqual(st["heartbeat"]["file"], "04_search/countries/ardenia.json")
        self.assertEqual(run("validate.py", self.d).returncode, 0)

    def test_invalid_record_is_rejected_and_parked(self):
        self.cp("init-country", "--country", "ardenia", "--name", "Ardenia")
        before = self.cf.read_text()
        bad = dict(self.cand, state_vector={"funding": 7, "programme": 1, "pathway": 1})
        r = self.cp("add-candidate", "--country", "ardenia", "--json", json.dumps(bad))
        self.assertEqual(r.returncode, 1)
        self.assertIn("REJECTED", r.stderr)
        self.assertEqual(self.cf.read_text(), before, "file must be untouched")
        parked = [json.loads(l) for l in (self.d / "04_search/rejected_records.jsonl").read_text().splitlines()]
        self.assertEqual(parked[0]["record"]["id"], "NL26-01")
        self.assertTrue(parked[0]["errors"])
        # validate.py warns about parked records
        self.assertIn("rejected_records", run("validate.py", self.d).stdout)

    def test_new_records_must_carry_source_type_and_date(self):
        self.cp("init-country", "--country", "ardenia", "--name", "Ardenia")
        rec = copy.deepcopy(self.cand)
        del rec["sources"][0]["source_type"]
        r = self.cp("add-candidate", "--country", "ardenia", "--json", json.dumps(rec))
        self.assertEqual(r.returncode, 1)
        self.assertIn("source_type", r.stderr)

    def test_followup_and_crosscut_targets(self):
        self.assertEqual(self.cp("init-country", "--country", "ardenia", "--name", "Ardenia").returncode, 0)
        self.assertEqual(self.cp("init-country", "--country", "ardenia", "--followup", "a", "--name", "Ardenia").returncode, 0)
        self.assertEqual(self.cp("init-country", "--country", "ardenia", "--followup", "--name", "Ardenia").returncode, 0)
        self.assertTrue((self.d / "04_search/followups/ardenia_followup_a.json").exists())
        self.assertTrue((self.d / "04_search/followups/ardenia_followup.json").exists())
        self.assertEqual(jload(self.d / "04_search/followups/ardenia_followup_a.json")["followup_of"], "ardenia")
        self.assertEqual(self.cp("init-country", "--crosscut", "em", "--name", "Joint masters", "--kind", "programme_scan").returncode, 0)
        self.assertEqual(jload(self.d / "04_search/crosscuts/em.json")["crosscut_kind"], "programme_scan")
        fr = jload(FIXTURE / "04_search/crosscuts/home_scheme.json")
        self.assertEqual(self.cp("put-crosscut", "--crosscut", "scheme", "--json", json.dumps(fr)).returncode, 0)
        self.assertEqual(run("validate.py", self.d).returncode, 0)

    def test_parallel_agents_do_not_lose_updates(self):
        self.cp("init-country", "--country", "ardenia", "--name", "Ardenia")
        jobs = [("add-screening", "--country", "ardenia", "--json", json.dumps({"institution": f"Univ {i}", "decision": "pass", "entry_path": "A", "reason": "r"})) for i in range(8)]
        with concurrent.futures.ThreadPoolExecutor(8) as ex:
            res = list(ex.map(lambda j: self.cp(*j), jobs))
        self.assertTrue(all(r.returncode == 0 for r in res), [r.stderr for r in res])
        self.assertEqual(len(jload(self.cf)["screening"]), 8)
        cps = [c for c in jload(self.d / "run_state.json")["checkpoints"] if c["file"].endswith("ardenia.json")]
        self.assertEqual(len(cps), 1)

    def test_sessions_and_agents_per_window(self):
        self.assertEqual(self.cp("log-session", "--start", "--phase", "search").returncode, 0)
        self.assertEqual(self.cp("log-session", "--event", "agent_start", "--country", "ardenia", "--agent", "a1", "--detail", "go").returncode, 0)
        self.assertEqual(self.cp("log-session", "--end", "--limit-hit", "--agents-run", "5", "--next-action", "resume ardenia").returncode, 0)
        self.assertEqual(self.cp("log-session", "--start", "--phase", "search").returncode, 0)
        r = self.cp("log-session", "--end", "--agents-run", "9")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = jload(self.d / "run_state.json")
        self.assertEqual([s["limit_hit"] for s in st["sessions"]], [True, False])
        self.assertEqual(st["agents_per_window_observed"], 5.0, "only windows that hit a limit show real capacity")
        self.assertEqual(st["next_action"], "resume ardenia")
        lines = [json.loads(l) for l in (self.d / "logs/session_log.jsonl").read_text().splitlines()]
        self.assertEqual([l["event"] for l in lines], ["note", "session_start", "agent_start", "session_end", "session_start", "session_end"])
        self.assertEqual(self.cp("log-session", "--end").returncode, 2, "no open session")

    def test_agent_brief_commands_work_literally(self):
        """protocol/templates/AGENT_BRIEF.md passes FILES to --file and --country-context; the script must take them."""
        self.cp("init-country", "--country", "ardenia", "--name", "Ardenia")
        jsave(self.d / "screening.json", {"institution": "Northfield University", "decision": "pass", "entry_path": "A", "reason": "ok"})
        jsave(self.d / "ctx.json", {"funding_system": "Fees waived for scholarship holders.", "dependant_pathway": "Partner may work."})
        jsave(self.d / "pb.json", {"name": "Placement lead (role descriptor)", "affiliation": "Northfield University", "focus": "placements", "url": None, "msc_link": "takes students"})
        self.assertEqual(self.cp("add-screening", "--country", "ardenia", "--file", self.d / "screening.json").returncode, 0)
        r = self.cp("set-status", "--country", "ardenia", "--path-b-done", "true", "--country-context", self.d / "ctx.json", "--add-path-b-person", self.d / "pb.json", "--status", "complete_with_gaps")
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = jload(self.d / "04_search/countries/ardenia.json")
        self.assertEqual(doc["country_context"]["dependant_pathway"], "Partner may work.")
        self.assertEqual(doc["path_b_people"][0]["affiliation"], "Northfield University")
        r = self.cp("set-status", "--country", "ardenia", "--country-context", '{"application_cycle": "Rolling"}')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(jload(self.d / "04_search/countries/ardenia.json")["country_context"]["funding_system"], "Fees waived for scholarship holders.")

    def test_errors(self):
        self.assertEqual(self.cp("add-candidate", "--country", "nowhere", "--json", json.dumps(self.cand)).returncode, 2)
        self.cp("init-country", "--country", "ardenia", "--name", "Ardenia")
        self.assertEqual(self.cp("add-screening", "--country", "ardenia", "--json", "{not json").returncode, 2)
        self.assertEqual(self.cp("add-screening", "--json", "{}").returncode, 2)


class TestCheckpointGatesAndCrosscuts(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.d = Path(self._tmp.name) / "r"
        run("init_workspace.py", self.d, "--alias", "Applicant Q", "--mode", "local")
        self.cand = jload(FIXTURE / "04_search/countries/northland.json")["candidates"][0]
        self.cf = self.d / "04_search/countries/ardenia.json"

    def cp(self, *a, stdin=None):
        return run("checkpoint.py", self.d, *a, stdin=stdin)

    def pass_gates(self):
        for key in ("life_plan_score", "map_score"):
            d = jload(C.rp(self.d, key))
            d["passed"] = True
            jsave(C.rp(self.d, key), d)

    def test_init_refuses_until_both_gates_passed(self):
        r = self.cp("init-country", "--country", "ardenia", "--name", "Ardenia")
        self.assertEqual(r.returncode, 2)
        self.assertIn("gate(s) not passed (life_plan=pending, pathway_map=pending)", r.stderr)
        self.assertFalse(self.cf.exists())
        d = jload(C.rp(self.d, "life_plan_score"))
        d["passed"] = True
        jsave(C.rp(self.d, "life_plan_score"), d)
        r = self.cp("init-country", "--country", "ardenia", "--name", "Ardenia")
        self.assertEqual(r.returncode, 2)
        self.assertIn("pathway_map=pending", r.stderr)
        self.assertNotIn("life_plan=", r.stderr)
        self.pass_gates()
        self.assertEqual(self.cp("init-country", "--country", "ardenia", "--name", "Ardenia").returncode, 0)

    def test_force_proceeds_and_records_the_deviation(self):
        r = self.cp("init-country", "--country", "ardenia", "--name", "Ardenia", "--force", "--reason", "applicant wants an early signal")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.cf.exists())
        st = jload(self.d / "run_state.json")
        self.assertEqual(len(st["overrides_of_protocol"]), 1)
        o = st["overrides_of_protocol"][0]
        self.assertIn("no gate, no search", o["rule"])
        self.assertIn("04_search/countries/ardenia.json", o["override"])
        self.assertEqual(o["reason"], "applicant wants an early signal")
        self.assertEqual(C.validate(st, "run_state"), [])
        # --resume on an existing file does not need the gate again and writes no second override
        self.assertEqual(self.cp("init-country", "--country", "ardenia", "--name", "Ardenia", "--resume").returncode, 0)
        self.assertEqual(len(jload(self.d / "run_state.json")["overrides_of_protocol"]), 1)

    def test_crosscut_needs_an_explicit_kind(self):
        self.pass_gates()
        r = self.cp("init-country", "--crosscut", "x", "--name", "X")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--kind", r.stderr)
        self.assertFalse((self.d / "04_search/crosscuts/x.json").exists())
        self.assertEqual(self.cp("init-country", "--country", "ardenia", "--name", "Ardenia", "--kind", "funding_route").returncode, 2)

    def test_funding_route_crosscut_incremental_flow(self):
        self.pass_gates()
        f = self.d / "04_search/crosscuts/home_scheme.json"
        r = self.cp("init-country", "--crosscut", "home_scheme", "--kind", "funding_route", "--route-type", "home_country_scheme", "--name", "Home scheme")
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = jload(f)
        self.assertEqual((doc["status"], doc["route_type"], doc["findings"]), ("in_progress", "home_country_scheme", []))
        cp = next(c for c in jload(self.d / "run_state.json")["checkpoints"] if c["file"].endswith("home_scheme.json"))
        self.assertEqual(cp["status"], "in_progress")
        fin = {"question": "Return obligation?", "answer": "Two years.", "confidence": "confirmed", "urls": ["https://example.gov/s"]}
        self.assertEqual(self.cp("add-finding", "--crosscut", "home_scheme", "--json", json.dumps(fin)).returncode, 0)
        fin["answer"] = "Two years, waivable for a PhD."
        r = self.cp("add-finding", "--crosscut", "home_scheme", "--json", json.dumps(fin))
        self.assertIn('"action": "replaced"', r.stdout)
        self.assertEqual(self.cp("add-finding", "--crosscut", "home_scheme", "--json", json.dumps(dict(fin, question="Amount?"))).returncode, 0)
        self.assertEqual([x["question"] for x in jload(f)["findings"]], ["Return obligation?", "Amount?"])
        # a bad finding is rejected as part of the whole file and parked
        r = self.cp("add-finding", "--crosscut", "home_scheme", "--json", json.dumps({"question": "Q?", "answer": "A", "confidence": "sure", "urls": []}))
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(jload(f)["findings"]), 2)
        # set-status works on cross-cuts; country-only flags are refused
        r = self.cp("set-status", "--crosscut", "home_scheme", "--path-b-done", "true")
        self.assertEqual(r.returncode, 2)
        self.assertIn("funding_route cross-cut accepts only", r.stderr)
        r = self.cp("set-status", "--crosscut", "home_scheme", "--status", "complete", "--note", "all questions answered")
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = jload(f)
        self.assertEqual((doc["status"], doc["notes"]), ("complete", "all questions answered"))
        cp = next(c for c in jload(self.d / "run_state.json")["checkpoints"] if c["file"].endswith("home_scheme.json"))
        self.assertEqual(cp["status"], "complete")
        # the wrong verbs for this file kind are refused with a pointer
        self.assertEqual(self.cp("add-candidate", "--crosscut", "home_scheme", "--json", json.dumps(self.cand)).returncode, 2)
        self.cp("init-country", "--country", "ardenia", "--name", "Ardenia")
        self.assertEqual(self.cp("add-finding", "--country", "ardenia", "--json", json.dumps(fin)).returncode, 2)

    def test_put_crosscut_stores_status_complete_by_default(self):
        self.pass_gates()
        fr = jload(FIXTURE / "04_search/crosscuts/home_scheme.json")
        fr.pop("status")
        r = self.cp("put-crosscut", "--crosscut", "scheme", "--json", json.dumps(fr))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(jload(self.d / "04_search/crosscuts/scheme.json")["status"], "complete")

    def test_programme_scan_crosscut_set_status(self):
        self.pass_gates()
        self.assertEqual(self.cp("init-country", "--crosscut", "em", "--kind", "programme_scan", "--name", "Joint masters").returncode, 0)
        r = self.cp("set-status", "--crosscut", "em", "--status", "complete_with_gaps", "--path-b-done", "true", "--add-gap", "catalogue B not read")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(jload(self.d / "04_search/crosscuts/em.json")["status"], "complete_with_gaps")

    def test_rejected_records_can_be_cleared_and_clear_themselves(self):
        self.pass_gates()
        self.cp("init-country", "--country", "ardenia", "--name", "Ardenia")
        rej = self.d / "04_search/rejected_records.jsonl"
        bad = dict(self.cand, state_vector={"funding": 7, "programme": 1, "pathway": 1})
        other = dict(self.cand, id="NL26-07", state_vector={"funding": 9, "programme": 1, "pathway": 1})
        for rec in (bad, other):
            self.assertEqual(self.cp("add-candidate", "--country", "ardenia", "--json", json.dumps(rec)).returncode, 1)
        self.assertEqual(len(rej.read_text().splitlines()), 2)
        self.assertIn("rejected_records", run("validate.py", self.d).stdout)
        # automatic: the corrected record with the same id clears its parked copy (only that one)
        r = self.cp("add-candidate", "--country", "ardenia", "--json", json.dumps(self.cand))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"cleared_rejected": 1', r.stdout)
        left = [json.loads(l) for l in rej.read_text().splitlines()]
        self.assertEqual([e["record"]["id"] for e in left], ["NL26-07"])
        # explicit: by id, then everything
        r = self.cp("clear-rejected", "--id", "NL26-99")
        self.assertIn('"cleared": 0', r.stdout)
        r = self.cp("clear-rejected", "--id", "NL26-07")
        self.assertIn('"cleared": 1', r.stdout)
        self.assertEqual(rej.read_text().strip(), "")
        self.assertNotIn("rejected_records", run("validate.py", self.d).stdout)
        self.cp("add-candidate", "--country", "ardenia", "--json", json.dumps(bad))
        self.assertIn('"cleared": 1', self.cp("clear-rejected").stdout)
        self.assertEqual(rej.read_text().strip(), "")

    def test_screening_rejection_clears_when_the_row_is_fixed(self):
        self.pass_gates()
        self.cp("init-country", "--country", "ardenia", "--name", "Ardenia")
        row = {"institution": "Northfield University", "decision": "maybe", "entry_path": "A", "reason": "r"}
        self.assertEqual(self.cp("add-screening", "--country", "ardenia", "--json", json.dumps(row)).returncode, 1)
        row["decision"] = "pass"
        r = self.cp("add-screening", "--country", "ardenia", "--json", json.dumps(row))
        self.assertIn('"cleared_rejected": 1', r.stdout)

    def test_assumptions_protocol_overrides_and_wave(self):
        self.assertEqual(self.cp("add-assumption", "--id", "A1", "--text", "Savings last the degree", "--made-in", "session 1", "--revisit").returncode, 0)
        self.assertEqual(self.cp("add-assumption", "--id", "A1", "--text", "Savings last 18 months").returncode, 0)
        self.assertEqual(self.cp("add-protocol-override", "--rule", "S3 before S2", "--override", "scoped early", "--reason", "time", "--date", "2026-10-27").returncode, 0)
        self.cp("log-session", "--start", "--phase", "search", "--wave", "2")
        st = jload(self.d / "run_state.json")
        self.assertEqual(st["assumptions"], [{"id": "A1", "text": "Savings last 18 months", "revisit": False}])
        self.assertEqual(st["overrides_of_protocol"][0]["rule"], "S3 before S2")
        self.assertEqual(st["sessions"][0]["wave"], 2)
        self.assertEqual(C.validate(st, "run_state"), [])


class TestMerge(WS):
    def test_merge_fixture(self):
        r = self.merge()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        m = self.merged()
        self.assertEqual(C.validate(m, "merged_file"), [])
        self.assertEqual(C.validate(jload(self.p("merge_report")), "merge_report"), [])
        ids = [c["id"] for c in m["candidates"]]
        self.assertEqual(ids, ["NL26-01", "XC26-01", "NL26-02", "NL26-04", "EA26-01", "NL26-03", "EA26-02"])  # ranked
        self.assertEqual([c["_rank"] for c in m["candidates"]], list(range(1, 8)))
        # replacement keeps the ORIGINAL id and remembers its own
        nl02 = self.cand("NL26-02")
        self.assertEqual((nl02["_followup_id"], nl02["_replaces"]), ("NL26-05", "NL26-02"))
        self.assertEqual(nl02["_replaced_first_pass_vector"]["pathway"], "?")
        self.assertEqual((nl02["state_vector"]["pathway"], nl02["_total"], nl02["_unscored_axes"]), (2, 5, 0))
        # override applied, original recorded, agent record otherwise intact
        xc = self.cand("XC26-01")
        self.assertEqual(xc["state_vector"]["funding"], 2)
        ov = xc["_overrides_applied"][0]
        self.assertEqual((ov["original_value"], ov["new_value"], ov["decided_by"]), (3, 2, "orchestrator"))
        self.assertEqual(xc["_total"], 6)
        self.assertEqual(len(m["overrides_applied"]), 1)
        # exact duplicate dropped, flag on keeper; near duplicate only flagged
        rep = jload(self.p("merge_report"))
        self.assertEqual([(d["kept"], d["dropped"]) for d in rep["exact_duplicates_dropped"]], [("NL26-03", "XC26-02")])
        self.assertEqual(self.cand("NL26-03")["_also_listed_as"], ["XC26-02"])
        self.assertTrue(any({n["a"], n["b"]} == {"NL26-01", "NL26-04"} for n in rep["near_duplicates"]))
        self.assertIn("NL26-04", ids)
        # promoted ranked_out entry purged, other one kept
        ro = m["countries"]["northland"]["ranked_out"]
        self.assertEqual([r["programme"] for r in ro], ["MSc Statistics"])
        self.assertEqual(rep["counts"]["ranked_out_purged"], 1)
        # screening deduplicated: 5 base rows, Marsh upserted by the follow-up
        scr = {s["institution"]: s["decision"] for s in m["countries"]["northland"]["screening"]}
        self.assertEqual(len(scr), 5)
        self.assertEqual(scr["Marsh Polytechnic"], "pass")
        self.assertEqual(rep["counts"]["screening_rows_in"], 5 + 1 + 3 + 1)
        # follow-up extras are KEPT
        nl = m["countries"]["northland"]
        self.assertEqual(nl["urgent_deadlines"][0]["name"], "Scholarship round 1")
        self.assertIn("neural modelling", nl["path_b_people"][0]["name"])
        self.assertEqual(nl["still_open"], ["Confirm 2027/28 scholarship call."])
        self.assertEqual(nl["followups"]["northland_followup.json"]["extras"]["scheme_terms"]["five_year_rule"], True)
        self.assertIn("blocked", nl["followups"]["northland_followup.json"]["notes"])
        self.assertEqual(nl["country_context"]["additions"][0]["source"], "northland_followup.json")
        self.assertIsInstance(nl["country_context"], dict)
        self.assertIsInstance(nl["country_summary"], str)
        self.assertIn("[Follow-up northland_followup.json]", nl["country_summary"])
        self.assertEqual((nl["status"], nl["status_effective"], nl["path_b_done"]), ("partial_budget_exhausted", "complete", True))
        # cross-cuts as own section; programme-scan candidates join the ranking
        self.assertEqual(set(m["crosscuts"]), {"joint_masters", "home_scheme"})
        self.assertEqual(m["crosscuts"]["home_scheme"]["kind"], "funding_route")
        self.assertEqual(m["crosscuts"]["joint_masters"]["candidate_ids"], ["XC26-01", "XC26-02"])
        self.assertEqual(xc["_origin"], {"kind": "crosscut", "slug": "joint_masters"})
        # baseline
        self.assertEqual(nl02.get("_delta_vs_baseline"), None)
        self.assertEqual(self.cand("NL26-01")["_delta_vs_baseline"], {"funding": [1, 2], "pathway": ["?", 3]})
        self.assertEqual(m["prior_not_revisited"], ["NP2"])
        self.assertEqual(rep["delta_vs_baseline"]["axes"]["funding"]["up"], 1)
        self.assertEqual(rep["delta_vs_baseline"]["axes"]["pathway"]["filled_from_unknown"], 1)
        self.assertEqual(m["benchmarks"]["benchmarks"][0]["axis"], "funding")

    def test_in_progress_blocks_merge_unless_allowed(self):
        f = self.p("countries_dir") / "eastmark.json"
        d = jload(f)
        d["status"] = "in_progress"
        jsave(f, d)
        r = self.merge()
        self.assertEqual(r.returncode, 1)
        self.assertIn("in_progress_file", r.stdout)
        self.assertEqual(self.merge("--allow-partial").returncode, 0)

    def test_invalid_file_is_skipped_and_reported(self):
        f = self.p("countries_dir") / "eastmark.json"
        d = jload(f)
        d["candidates"][0]["state_vector"]["funding"] = 11
        jsave(f, d)
        r = self.merge()
        self.assertEqual(r.returncode, 1)
        self.assertIn("invalid_file", r.stdout)
        self.assertNotIn("EA26-01", [c["id"] for c in self.merged()["candidates"]], "a half-valid file must not be half-merged")
        self.assertIn("NL26-01", [c["id"] for c in self.merged()["candidates"]])

    def test_override_problems(self):
        ov = jload(self.p("overrides"))
        ov.append(dict(ov[0], target_id="ZZ99-99"))
        ov.append(dict(ov[0], original_value=1, field="state_vector.pathway", new_value=1, target_id="NL26-01"))
        jsave(self.p("overrides"), ov)
        r = self.merge()
        self.assertEqual(r.returncode, 1)
        rep = jload(self.p("merge_report"))
        codes = [i["code"] for i in rep["issues"]]
        self.assertIn("override_target_missing", codes)
        self.assertIn("override_original_mismatch", codes)
        self.assertEqual(len(rep["overrides_unmatched"]), 1)
        self.assertEqual(self.cand("NL26-01")["state_vector"]["pathway"], 1, "stale override still applied but flagged")

    def test_replace_target_missing_and_orphan_followup(self):
        f = self.p("followups_dir") / "northland_followup.json"
        d = jload(f)
        d["candidates"][0]["replaces"] = "NL26-77"
        jsave(f, d)
        shutil.copy(f, self.p("followups_dir") / "atlantis_followup.json")
        r = self.merge()
        self.assertEqual(r.returncode, 1)
        codes = [i["code"] for i in jload(self.p("merge_report"))["issues"]]
        self.assertIn("replace_target_missing", codes)
        self.assertIn("orphan_followup", codes)

    def test_planned_country_missing_is_an_error(self):
        (self.p("countries_dir") / "eastmark.json").unlink()
        (self.p("crosscuts_dir") / "joint_masters.json").unlink()
        self.p("overrides").unlink()                       # its target lived in the removed cross-cut
        r = self.merge()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("planned_country_missing", r.stdout)
        rep = jload(self.p("merge_report"))
        miss = [i for i in rep["issues"] if i["code"] == "planned_country_missing"]
        self.assertEqual(sorted(i["ref"] for i in miss), ["eastmark", "joint_masters"])
        self.assertTrue(all(i["level"] == "error" for i in miss))
        self.assertFalse(rep["ok"])
        self.assertEqual(rep["counts"]["planned_missing"], 2)
        # --allow-partial downgrades it to a warning
        r = self.merge("--allow-partial")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(all(i["level"] == "warning" for i in jload(self.p("merge_report"))["issues"] if i["code"] == "planned_country_missing"))

    def test_funding_route_crosscut_in_progress_blocks_merge(self):
        f = self.p("crosscuts_dir") / "home_scheme.json"
        d = jload(f)
        d["status"] = "in_progress"
        jsave(f, d)
        r = self.merge()
        self.assertEqual(r.returncode, 1)
        self.assertIn("in_progress_file", r.stdout)
        self.assertEqual(self.merge("--allow-partial").returncode, 0)

    def test_without_baseline_or_overrides(self):
        self.p("overrides").write_text("[]")
        r = run("merge.py", self.run_dir)
        self.assertEqual(r.returncode, 0, r.stdout)
        m = self.merged()
        self.assertEqual(m["prior_not_revisited"], [])
        self.assertIsNone(m["baseline_used"])
        self.assertEqual(self.cand("XC26-01")["state_vector"]["funding"], 3)

    def test_unscored_total_ignores_question_mark(self):
        f = self.p("followups_dir") / "northland_followup.json"
        f.unlink()
        self.assertEqual(self.merge("--allow-partial").returncode, 0)
        c = self.cand("NL26-02")
        self.assertEqual((c["_total"], c["_unscored_axes"]), (3, 1))


class TestFollowups(WS):
    def fu(self, *a):
        r = run("followups.py", self.run_dir, "--today", "2026-10-27", *a)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(C.validate(out, "followup_trigger"), [])
        return out

    def types(self, out):
        return sorted((t["country"], t["trigger_type"]) for t in out["triggers"])

    def test_after_followup_resolved(self):
        out = self.fu()
        self.assertEqual(self.types(out), [("eastmark", "complete_with_gaps"), ("eastmark", "path_b_missing"), ("eastmark", "suspected_false_negative"),
                                           ("northland", "deadline_soon"), ("northland", "suspected_false_negative")])
        dl = next(t for t in out["triggers"] if t["trigger_type"] == "deadline_soon")
        self.assertEqual(dl["record_ids"], ["NL26-01", "NL26-04"])
        self.assertIn("1 not 'confirmed'", dl["detail"])
        # stop rule: eastmark can never reach funding 2 nor research 2
        self.assertEqual([s["country"] for s in out["stop_rule_decisions"]], ["eastmark"])
        self.assertEqual(out["stop_rule_decisions"][0]["decision"], "no_followup")
        self.assertEqual(out["countries_needing_followup"], ["northland"])

    def test_before_followup_all_trigger_types(self):
        (self.p("followups_dir") / "northland_followup.json").unlink()
        out = self.fu()
        got = {t for c, t in self.types(out) if c == "northland"}
        self.assertEqual(got, {"budget_exhausted", "path_b_missing", "unscored_axis", "promote_flag", "suspected_false_negative", "deadline_soon"})
        ua = next(t for t in out["triggers"] if t["trigger_type"] == "unscored_axis")
        self.assertEqual(ua["record_ids"], ["NL26-02"])
        pf = next(t for t in out["triggers"] if t["trigger_type"] == "promote_flag")
        self.assertEqual(pf["record_ids"], ["ranked_out:Northfield University | MSc Computational Data Science"])
        fn = next(t for t in out["triggers"] if t["country"] == "northland" and t["trigger_type"] == "suspected_false_negative")
        self.assertEqual(sorted(fn["record_ids"]), ["Hillcrest College", "Marsh Polytechnic"])  # 'no relevant people found' + unscreened
        self.assertNotIn("northland", [s["country"] for s in out["stop_rule_decisions"]])

    def test_parameters(self):
        self.assertEqual([t for t in self.fu("--deadline-days", "10")["triggers"] if t["trigger_type"] == "deadline_soon"], [])
        out = self.fu("--min-funding", "1")
        self.assertEqual(out["stop_rule_decisions"], [], "funding 1 reaches the minimum, so the decision could still flip")
        # '?' is conservative: an unknown research score blocks the stop rule unless told to ignore it
        f = self.p("countries_dir") / "eastmark.json"
        d = jload(f)
        d["ranked_out"][0]["prelim_state_vector"]["pathway"] = "?"
        jsave(f, d)
        self.assertEqual(self.fu()["stop_rule_decisions"], [])
        self.assertEqual([s["country"] for s in self.fu("--unknowns", "ignore")["stop_rule_decisions"]], ["eastmark"])

    def test_false_negative_regex_broadened(self):
        import followups
        for t in ("no relevant faculty found", "no PI identified", "could not access the study plan", "unable to open the page", "HTTP 403 on staff pages",
                  "paywalled catalogue", "robots.txt forbids it", "timeout on every fetch", "site blocked", "module list not found", "No relevant people found"):
            self.assertTrue(followups.FALSE_NEG_RE.search(t), t)
        for t in ("curriculum has no overlap with the domains", "tuition far above the ceiling", "weak on merit", "fee of 1403 EUR"):
            self.assertFalse(followups.FALSE_NEG_RE.search(t), t)

    def test_min_funding_score_source_is_printed(self):
        r = run("followups.py", self.run_dir, "--today", "2026-10-27")
        self.assertIn("min funding score: 2 (source: search_plan.funded_definition.min_funding_score)", r.stderr)
        sp = self.p("search_plan")
        plan = jload(sp)
        for ftype, want in (("stipend_and_tuition", 3), ("tuition_only", 2), ("affordable", 1)):
            plan["funded_definition"].pop("min_funding_score", None)
            plan["funded_definition"]["type"] = ftype
            jsave(sp, plan)
            r = run("followups.py", self.run_dir, "--today", "2026-10-27")
            self.assertIn(f"min funding score: {want} (source: default for funded type {ftype})", r.stderr)
            params = json.loads(r.stdout)["params"]
            self.assertEqual((params["min_funding_score"], params["min_funding_source"]), (want, f"default for funded type {ftype}"))
        r = run("followups.py", self.run_dir, "--today", "2026-10-27", "--min-funding", "1")
        self.assertIn("(source: --min-funding)", r.stderr)

    def test_write_flag_and_bad_date(self):
        self.fu("--write")
        self.assertEqual(C.validate(jload(self.p("followup_plan")), "followup_trigger"), [])
        self.assertEqual(run("followups.py", self.run_dir, "--today", "soon").returncode, 2)


class TestVerificationSampling(WS):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.merge().returncode, 0)

    def sample(self, *a):
        r = run("sample_verification.py", self.run_dir, *a)
        self.assertEqual(r.returncode, 0, r.stderr)
        return jload(self.p("verification_sample"))

    def test_mix_and_reproducibility(self):
        s = self.sample("--top", "2", "--random", "3", "--seed", "7")
        self.assertEqual(C.validate(s, "verification_sample"), [])
        top = {i["id"] for i in s["items"] if i["sampled_by"] == "top_n"}
        rnd = {i["id"] for i in s["items"] if i["sampled_by"] == "random"}
        self.assertEqual(top, {"NL26-01", "XC26-01"})
        self.assertEqual(len(rnd), 3)
        self.assertFalse(top & rnd, "random draw excludes the top-N")
        self.assertEqual((s["top_n"], s["random_m"], s["population_size"], s["seed"]), (2, 3, 7, 7))
        again = self.sample("--top", "2", "--random", "3", "--seed", "7")
        self.assertEqual([(i["id"], i["claim_type"]) for i in s["items"]], [(i["id"], i["claim_type"]) for i in again["items"]])
        types = {i["claim_type"] for i in s["items"]}
        self.assertEqual(types, {"fee", "deadline", "people_partner", "language", "funding"})
        self.assertTrue(all(i["source_url"] for i in s["items"] if i["claim_type"] == "fee"))
        others = {tuple((i["id"], i["claim_type"]) for i in self.sample("--top", "2", "--random", "3", "--seed", str(k))["items"]) for k in range(1, 8)}
        self.assertGreater(len(others), 1, "different seeds should give different draws")

    def test_claim_filter_and_limits(self):
        s = self.sample("--top", "1", "--random", "50", "--claims", "fee,deadline")
        self.assertEqual({i["claim_type"] for i in s["items"]}, {"fee", "deadline"})
        self.assertEqual(s["random_m"], 6)
        self.assertEqual(run("sample_verification.py", self.run_dir, "--claims", "nonsense").returncode, 2)

    def test_needs_merge_first(self):
        self.p("merged").unlink()
        self.assertEqual(run("sample_verification.py", self.run_dir).returncode, 2)

    def test_small_population_warns_and_zero_random_is_not_extrapolable(self):
        r = run("sample_verification.py", self.run_dir, "--top", "10", "--random", "8")        # only 7 records exist
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("warning: population (7 records) is smaller than top + random (10 + 8)", r.stderr)
        s = jload(self.p("verification_sample"))
        self.assertEqual((s["top_n"], s["random_m"], s["extrapolable"]), (7, 0, False))
        self.assertEqual(len(s["warnings"]), 2)
        self.assertEqual(C.validate(s, "verification_sample"), [])
        s = self.sample("--top", "3", "--random", "0")
        self.assertFalse(s["extrapolable"])
        self.assertIn("do NOT extrapolate", s["warnings"][0])
        s = self.sample("--top", "2", "--random", "3")
        self.assertTrue(s["extrapolable"])
        self.assertEqual(s["warnings"], [])


class TestDueDiligence(WS):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.merge().returncode, 0)

    def dd(self, *a):
        r = run("due_diligence.py", self.run_dir, "--today", "2026-10-27", "--metrics-json", self.run_dir / "metrics.json", *a)
        self.assertEqual(r.returncode, 0, r.stderr)
        return self.p("due_diligence").read_text(encoding="utf-8"), jload(self.run_dir / "metrics.json")

    def test_numbers_are_computed(self):
        md, m = self.dd()
        for n in range(1, 10):
            self.assertRegex(md, rf"## {n}\. ")
        self.assertLessEqual(len(md.splitlines()), 80, "must fit about one page")
        f = m["funnel"]
        self.assertEqual((f["full_records"], f["ranked_out"], f["programme_level_entries"]), (7, 2, 9))
        self.assertEqual(f["screened_unique"], f["pass"] + f["fail"] + f["unscreened"])
        self.assertEqual(f["screened_raw_rows"], 10)
        self.assertEqual(m["novelty"]["net_new"] + m["novelty"]["update_of_existing"] + m["novelty"]["reconfirmed"], 7)
        self.assertEqual(m["novelty"]["prior_not_revisited"], 1)
        e = m["evidence"]
        self.assertEqual(e["route_entries"], 8)
        self.assertEqual(e["pct_routes_confirmed"], 62.5)
        self.assertEqual(e["takes_students"], {"confirmed": 5, "inferred": 3})
        self.assertGreater(e["pct_official"], 0)
        self.assertGreater(e["pct_null_sources"], 0)
        self.assertEqual(m["benchmark_position"]["benchmark_max_total"], 6)
        self.assertEqual(m["benchmark_position"]["records_ge_benchmark_max"], 2)
        self.assertEqual(m["benchmark_position"]["max_total"], 7)
        self.assertEqual(m["caveats"]["overrides_applied"], 1)
        v = m["verification"]
        self.assertTrue(v["available"])
        self.assertEqual((v["claims_checked"], v["records_checked"]), (3, 2))
        self.assertEqual(v["verdicts"], {"confirmed": 1, "wrong": 1, "not_found": 1})
        self.assertAlmostEqual(v["pct_confirmed"], 33.3, 1)
        self.assertTrue(v["random_sample_present"])
        t = m["time_sensitivity"]
        self.assertEqual((t["structured_deadlines"], t["within_window"]), (3, 3))
        self.assertEqual(t["rows"][0]["id"], "NL26-01")
        self.assertIn("Applicant: Applicant T, first degree in Biology, residence Exampleland.", md)
        self.assertIn("Fees and deadlines", md)
        self.assertIn("| 2026-12-01 |", md)
        g = m["gaps"]
        self.assertEqual((g["searched_not_surfaced"], g["agents_hit_budget"]), (2, 1))
        self.assertEqual(g["blocked_site_mentions"], 1)

    def test_missing_fields_reported_as_not_recorded(self):
        for f in self.p("countries_dir").glob("*.json"):
            d = jload(f)
            for c in d["candidates"]:
                for s in c["sources"]:
                    s.pop("source_type", None)
                    s.pop("accessed_date", None)
                c["deadlines"] = []
            jsave(f, d)
        for f in list(self.p("followups_dir").glob("*.json")) + list(self.p("crosscuts_dir").glob("joint*.json")):
            d = jload(f)
            for c in d["candidates"]:
                c["deadlines"] = []
                for s in c["sources"]:
                    s.pop("source_type", None)
                    s.pop("accessed_date", None)
            jsave(f, d)
        self.assertEqual(self.merge().returncode, 0)
        md, m = self.dd("--run-label", "reference run")
        self.assertIn("not recorded in reference run", md)
        self.assertIsNone(m["evidence"]["pct_official"])
        self.assertIn("Structured deadlines: not recorded in reference run", md)

    def test_no_verification_and_no_examples(self):
        self.p("verification").unlink()
        md, m = self.dd("--no-examples")
        self.assertIn("no claim has been independently checked", md)
        self.assertEqual(m["gaps"]["examples"], [])
        self.assertNotIn("Riverton", md)

    def test_top_only_sample_is_labelled(self):
        v = jload(self.p("verification"))
        for i in v["items"]:
            i["sampled_by"] = "top_n"
        jsave(self.p("verification"), v)
        self.assertIn("NOT random", self.dd()[0])

    def test_needs_merge(self):
        self.p("merged").unlink()
        self.assertEqual(run("due_diligence.py", self.run_dir).returncode, 2)

    def test_header_and_effort_line(self):
        md, m = self.dd()
        self.assertEqual(md.splitlines()[0], "# Search due diligence: run fixture-run (2026-10-27; protocol v1.0.0; rubrics LP-1.0 / PM-1.0)")
        self.assertEqual((m["header"]["life_plan_rubric_version"], m["header"]["pathway_map_rubric_version"], m["header"]["protocol_version"]), ("1.0", "1.0", "1.0.0"))
        self.assertEqual(md.rstrip().splitlines()[-1], "**Effort**: 3 agent runs, 1 usage windows (1 planned), 1 sessions, 1 of which ended at a usage limit.")
        self.assertEqual((m["effort"]["agent_runs"], m["effort"]["sessions"], m["effort"]["limit_hits"], m["effort"]["waves_logged"]), (3, 1, 1, [1]))
        # nothing recorded -> says so instead of inventing numbers
        st = jload(self.p("run_state"))
        st["sessions"] = []
        jsave(self.p("run_state"), st)
        pl = jload(self.p("search_plan"))
        pl["session_plan"]["waves"] = []
        jsave(self.p("search_plan"), pl)
        md, m = self.dd("--run-label", "reference run")
        last = md.rstrip().splitlines()[-1]
        self.assertTrue(last.startswith("**Effort**: agent runs not recorded in reference run"), last)
        self.assertIn("sessions not recorded in reference run", last)

    def test_budget_count_ignores_complete_with_gaps(self):
        # eastmark is complete_with_gaps without limit events: not a budget hit. northland (partial + limit event) is.
        self.assertEqual(self.dd()[1]["gaps"]["agents_hit_budget_countries"], ["northland"])
        f = self.p("countries_dir") / "northland.json"
        d = jload(f)
        d["status"], d["run_meta"]["limit_events"] = "complete_with_gaps", []
        jsave(f, d)
        self.assertEqual(self.merge().returncode, 0)
        self.assertEqual(self.dd()[1]["gaps"]["agents_hit_budget"], 0)
        # any limit event counts, whatever its kind
        f = self.p("countries_dir") / "eastmark.json"
        d = jload(f)
        d["run_meta"]["limit_events"] = [{"kind": "usage_window", "detail": "cut off"}]
        jsave(f, d)
        self.assertEqual(self.merge().returncode, 0)
        self.assertEqual(self.dd()[1]["gaps"]["agents_hit_budget_countries"], ["eastmark"])

    def test_only_http_values_count_as_urls(self):
        import due_diligence
        rec = {"sources": [{"claim_field": "x", "url": "official"}, {"claim_field": "y", "url": "https://a.example/p"}],
               "language": {"source_url": "not a url"}, "deadlines": [{"source_url": "http://b.example/d"}],
               "funding": {"routes": [{"url": None}, {"url": "see website"}]}}
        self.assertEqual(sorted(due_diligence.all_urls(rec)), ["http://b.example/d", "https://a.example/p"])

    def test_publish_safe_mode_is_aggregates_only(self):
        md, m = self.dd("--no-examples")
        blob = md + json.dumps(m)
        for leak in ("Northland", "Eastmark", "northland", "eastmark", "Joint master", "joint_masters", "home_scheme", "Bench University", "MSc Funded Science", "Westland",
                     "NL26", "EA26", "XC26", "Marsh", "Hillcrest", "example.edu", "fixture-run", "Applicant T", "first degree in Biology", "Exampleland", "4000", "9000", "neuro", "Neuro"):
            self.assertNotIn(leak, blob, leak)
        self.assertIn("Country A", md)
        self.assertIn("Cross-cut A (programme_scan)", md)
        self.assertIn("funding benchmark", md)
        self.assertIn("1 region(s)/type(s) excluded, not listed", md)
        self.assertTrue(m["publish_safe"])
        # the numbers are untouched
        self.assertEqual(m["funnel"]["full_records"], 7)
        self.assertEqual(m["benchmark_position"]["benchmark_max_total"], 6)
        self.assertEqual(m["time_sensitivity"]["within_window"], 3)
        # normal mode keeps the names
        md2, _ = self.dd()
        self.assertIn("Northland", md2)


class TestStatusAndRubric(WS):
    def test_status(self):
        r = run("status.py", self.run_dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        # the default output STARTS with the 6-line brief of protocol/templates/where_we_are.md, then the checkpoint table
        self.assertEqual(lines[0], "VIRGIL | Run fixture-run | Session 1 | Phase: search -> followups | Gates: Life Plan \u2713 \u00b7 Map \u2713")
        self.assertEqual(lines[5], "Saved: 04_search/countries/eastmark.json")
        self.assertEqual(lines[6], "")
        self.assertTrue(lines[7].startswith("File "), lines[7])
        for s_ in ("04_search/countries/northland.json", "partial_budget_exhausted", "Sessions used: 1", "limit hits: 1", "agents per window observed: 3.0"):
            self.assertIn(s_, r.stdout)
        self.assertIn("joint_masters", r.stdout)  # in the plan, no checkpoint yet
        js = json.loads(run("status.py", self.run_dir, "--json").stdout)
        self.assertEqual(js["limit_hits"], 1)
        self.assertEqual(js["gates"], {"life_plan": "pass", "pathway_map": "pass"})
        self.assertEqual(run("status.py", self.run_dir / "nope").returncode, 2)

    def test_status_banner_gate_words(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "r"
            run("init_workspace.py", d, "--alias", "Applicant Q", "--mode", "local")
            first = run("status.py", d).stdout.splitlines()
            self.assertTrue(first[0].startswith("VIRGIL | Run applicant_q-"), first[0])
            self.assertTrue(first[0].endswith("| Session 0 | Phase: init | Gates: Life Plan pending \u00b7 Map pending"), first[0])
            self.assertTrue(first[3].startswith("My next step: Read 00_orientation/notes.md"), first[3])
            self.assertEqual(first[4], "Waiting on: nothing")
            self.assertEqual(run("rubric.py", d, "life_plan").returncode, 1)          # evaluated and not passed
            self.assertIn("Life Plan \u2717 \u00b7 Map pending", run("status.py", d).stdout.splitlines()[0])

    def test_brief_is_exactly_six_lines_in_the_template_format(self):
        r = run("status.py", self.run_dir, "--brief")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        self.assertEqual(len(lines), 6, r.stdout)
        self.assertEqual([ln.split(":")[0].split(" | ")[0] for ln in lines], ["VIRGIL", "Done since last time", "Your move", "My next step", "Waiting on", "Saved"])
        tpl = (ROOT / "protocol/templates/where_we_are.md").read_text(encoding="utf-8")
        for label in ("Done since last time:", "Your move:", "My next step:", "Waiting on:", "Saved:"):
            self.assertIn(label, tpl)                                                  # the labels come from the template
        self.assertEqual(lines[1], "Done since last time: Northland first pass (partial); Eastmark pass.")   # last two of completed[]
        self.assertEqual(lines[2], "Your move: Review the follow-up triggers")
        self.assertEqual(lines[4], "Waiting on: Marsh Polytechnic portal blocked (EXTERNAL)")
        self.assertNotIn("File", r.stdout)                                              # no table with --brief
        # the default output is the brief, a blank line, then the table
        full = run("status.py", self.run_dir).stdout.splitlines()
        self.assertEqual(full[:6], lines)
        self.assertEqual(full[6], "")

    def test_brief_follows_the_state_vector_and_gate_files(self):
        sv = jload(self.p("run_state"))["state_vector"]
        sv.update(phase="verify", session=4, completed=["a", "b", "c"], blockers=[{"item": "x", "owner": "USER"}, {"item": "y", "owner": "VIRGIL"}],
                  next={"user": [], "virgil": ["Sample claims"]})
        jsave(self.run_dir / "v.json", sv)
        self.assertEqual(run("checkpoint.py", self.run_dir, "update-vector", "--file", self.run_dir / "v.json").returncode, 0)
        lines = run("status.py", self.run_dir, "--brief").stdout.splitlines()
        self.assertIn("| Session 4 | Phase: verify |", lines[0])
        self.assertEqual(lines[1], "Done since last time: b; c.")
        self.assertEqual(lines[2], "Your move: nothing needed from you right now")
        self.assertEqual(lines[4], "Waiting on: x (USER); y (VIRGIL)")
        d = jload(self.p("map_score"))
        d["passed"] = False
        jsave(self.p("map_score"), d)
        self.assertIn("Life Plan \u2713 \u00b7 Map \u2717", run("status.py", self.run_dir, "--brief").stdout.splitlines()[0])

    def fill(self, rubric, statuses=None, soft_score=2):
        key = {"life_plan": "life_plan_score", "pathway_map": "map_score"}[rubric]
        d = jload(self.p(key))
        for g in d["gates"]:
            g["status"] = (statuses or {}).get(g["id"], "pass")
            g["note"] = "evidence"
        for s in d["soft"]:
            s["score"] = soft_score if not isinstance(soft_score, dict) else soft_score.get(s["id"], 2)
        jsave(self.p(key), d)
        return key

    def rub(self, rubric):
        r = run("rubric.py", self.run_dir, rubric)
        key = {"life_plan": "life_plan_score", "pathway_map": "map_score"}[rubric]
        return r, jload(self.p(key))

    def test_pass_and_soft_pct(self):
        self.fill("pathway_map")
        r, d = self.rub("pathway_map")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual((d["soft_pct"], d["passed"]), (100.0, True))
        self.assertEqual(C.validate(d, "rubric_score"), [])
        # DM soft weights are 1,2,1,1,1,1 (sum 7 => 14 points). Losing PM-S2 (2x2) leaves 10/14 = 71.4% => still passes.
        self.fill("pathway_map", soft_score={"PM-S2": 0})
        r, d = self.rub("pathway_map")
        self.assertEqual((r.returncode, d["soft_pct"]), (0, 71.4))
        # losing PM-S1 as well leaves 8/14 = 57.1% => fails on soft_pct only
        self.fill("pathway_map", soft_score={"PM-S2": 0, "PM-S1": 0})
        r, d = self.rub("pathway_map")
        self.assertEqual((r.returncode, d["soft_pct"], d["passed"]), (1, 57.1, False))
        self.assertEqual(d["problems"], ["soft_pct 57.1 < 70.0"])

    def test_soft_threshold(self):
        self.fill("life_plan", soft_score={"LP-S2": 0, "LP-S3": 0, "LP-S4": 0})        # weights 2+2+2 lost of 14 => 6/14 lost => 57.1% retained
        r, d = self.rub("life_plan")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(d["soft_pct"], 57.1)
        self.assertFalse(d["passed"])
        self.fill("life_plan", soft_score={"LP-S10": 0, "LP-S1": 0})                   # lose 1+1 of 14 => 85.7
        r, d = self.rub("life_plan")
        self.assertEqual((r.returncode, d["soft_pct"], d["passed"]), (0, 85.7, True))

    def test_declared_unknown_rules(self):
        self.fill("life_plan", {"LP-G1": "declared_unknown", "LP-G6": "declared_unknown"})
        r, d = self.rub("life_plan")
        self.assertEqual(r.returncode, 0, r.stdout)                                     # two allowed
        self.fill("life_plan", {"LP-G1": "declared_unknown", "LP-G6": "declared_unknown", "LP-G7": "declared_unknown"})
        r, d = self.rub("life_plan")
        self.assertEqual(r.returncode, 1)
        self.assertIn("3 gates declared_unknown", r.stdout)
        key = self.fill("life_plan", {"LP-G3": "declared_unknown"})
        r, d = self.rub("life_plan")
        self.assertEqual(r.returncode, 1)
        self.assertIn("LP-G3", r.stdout)
        d = jload(self.p(key))
        next(g for g in d["gates"] if g["id"] == "LP-G3")["user_accepted_consequence"] = True
        jsave(self.p(key), d)
        self.assertEqual(self.rub("life_plan")[0].returncode, 0)

    def test_fail_gate_and_mechanical_downgrade(self):
        self.fill("pathway_map", {"PM-G5": "fail"})
        self.assertEqual(self.rub("pathway_map")[0].returncode, 1)
        # claim 'pass' for PM-G2 but only 3 domains exist -> auto-check downgrades it
        self.fill("pathway_map")
        dm = jload(self.p("study_pathway_map"))
        dm["domains"] = dm["domains"][:3]
        jsave(self.p("study_pathway_map"), dm)
        r, d = self.rub("pathway_map")
        self.assertEqual(r.returncode, 1)
        g2 = next(g for g in d["gates"] if g["id"] == "PM-G2")
        self.assertEqual(g2["status"], "fail")
        self.assertIn("auto-check failed", g2["note"])
        self.assertFalse(next(a for a in d["auto_checks"] if a["id"] == "PM-G2")["ok"])

    def lp_edit(self, fn):
        """Apply ONE edit to a pristine copy of the fixture life plan (edits never accumulate)."""
        d = jload(FIXTURE / "01_life_plan/life_plan.json")
        fn(d)
        jsave(self.p("life_plan"), d)

    def gate(self, rubric, gid):
        self.fill(rubric)
        r, d = self.rub(rubric)
        return r, next(g for g in d["gates"] if g["id"] == gid), d

    def test_domain_map_limits_differ_from_life_plan(self):
        self.fill("pathway_map", {"PM-G1": "declared_unknown"})
        self.assertEqual(self.rub("pathway_map")[0].returncode, 0, "one declared_unknown is allowed")
        self.fill("pathway_map", {"PM-G1": "declared_unknown", "PM-G3": "declared_unknown"})
        r, d = self.rub("pathway_map")
        self.assertEqual(r.returncode, 1)
        self.assertIn("2 gates declared_unknown (max 1 for pathway_map)", r.stdout)
        for gid in ("PM-G2", "PM-G4"):
            self.fill("pathway_map", {gid: "declared_unknown"})
            r, d = self.rub("pathway_map")
            self.assertEqual(r.returncode, 1, gid)
            self.assertIn(f"{gid}", r.stdout)
            self.assertIn("may never be declared_unknown", r.stdout)
        self.fill("life_plan", {"LP-G1": "declared_unknown", "LP-G2": "declared_unknown"})
        self.assertEqual(self.rub("life_plan")[0].returncode, 0, "life plan still allows two")

    def test_lp_g3_money_needs_type_number_currency_and_debt_stance(self):
        r, g, _ = self.gate("life_plan", "LP-G3")
        self.assertEqual((r.returncode, g["status"]), (0, "pass"))
        cases = {"debt_acceptable": None, "currency": "", "funded_type": None}
        for key, val in cases.items():
            self.fill("life_plan")
            self.lp_edit(lambda d: d["money"].__setitem__(key, val))
            r, d = self.rub("life_plan")
            g = next(g for g in d["gates"] if g["id"] == "LP-G3")
            self.assertEqual(g["status"], "fail", key)
            self.assertIn("auto-check failed", g["note"])
        self.fill("life_plan")
        self.lp_edit(lambda d: d["money"].update(max_total_tuition=None, max_out_of_pocket=None, living_support_required_monthly=None))
        r, d = self.rub("life_plan")
        self.assertIn("a number", next(a for a in d["auto_checks"] if a["id"] == "LP-G3")["detail"])
        # 'affordable' needs a tuition or out-of-pocket ceiling, living support alone is not enough
        self.fill("life_plan")
        self.lp_edit(lambda d: d["money"].update(funded_type="affordable", max_total_tuition=None, max_out_of_pocket=None, living_support_required_monthly=900))
        r, d = self.rub("life_plan")
        self.assertFalse(next(a for a in d["auto_checks"] if a["id"] == "LP-G3")["ok"])
        # debt stated as False is a legitimate answer
        self.fill("life_plan")
        self.lp_edit(lambda d: d["money"].update(debt_acceptable=False))
        self.assertTrue(next(a for a in self.rub("life_plan")[1]["auto_checks"] if a["id"] == "LP-G3")["ok"])

    def test_lp_g3_old_money_layout_cannot_pass_without_debt_stance(self):
        self.fill("life_plan")
        self.lp_edit(lambda d: (d.pop("money"), d.update(money_operationalised={"funded_definition": {"type": "tuition_only", "max_total_tuition": 4000, "currency": "EUR"}})))
        r, d = self.rub("life_plan")
        a = next(a for a in d["auto_checks"] if a["id"] == "LP-G3")
        self.assertFalse(a["ok"])
        self.assertIn("debt_acceptable", a["detail"])

    def test_lp_g4_eligibility_facts(self):
        # fee_status is NOT required any more
        self.fill("life_plan")
        self.lp_edit(lambda d: d["eligibility_facts"].pop("fee_status"))
        self.assertEqual(self.rub("life_plan")[0].returncode, 0)
        for label, edit in (("citizenships", lambda e: e.pop("citizenships")), ("residence_country", lambda e: e.update(residence_country="")),
                            ("graduation_year", lambda e: e["highest_degree"].pop("graduation_year")),
                            ("certificates", lambda e: e.update(language_certificates=[]))):
            self.fill("life_plan")
            self.lp_edit(lambda d: edit(d["eligibility_facts"]))
            r, d = self.rub("life_plan")
            a = next(a for a in d["auto_checks"] if a["id"] == "LP-G4")
            self.assertFalse(a["ok"], label)
            self.assertEqual(r.returncode, 1, label)
        # an empty certificate list is fine only when the note says 'none'
        self.fill("life_plan")
        self.lp_edit(lambda d: d["eligibility_facts"].update(language_certificates=[], language_certificates_note="IELTS pending"))
        self.assertFalse(next(a for a in self.rub("life_plan")[1]["auto_checks"] if a["id"] == "LP-G4")["ok"])
        self.fill("life_plan")
        self.lp_edit(lambda d: d["eligibility_facts"].update(language_certificates=[], language_certificates_note="None held"))
        r, d = self.rub("life_plan")
        self.assertTrue(next(a for a in d["auto_checks"] if a["id"] == "LP-G4")["ok"])
        self.assertEqual(r.returncode, 0)

    def test_lp_g6_timeline_needs_both_starts_and_an_immovable_list(self):
        for label, edit in (("latest", lambda t: t.pop("latest_start")), ("earliest", lambda t: t.update(earliest_start="")),
                            ("list missing", lambda t: t.pop("immovable_dates"))):
            self.fill("life_plan")
            self.lp_edit(lambda d: edit(d["timeline"]))
            r, d = self.rub("life_plan")
            self.assertFalse(next(a for a in d["auto_checks"] if a["id"] == "LP-G6")["ok"], label)
            self.assertEqual(r.returncode, 1, label)
        self.fill("life_plan")                                   # fixture has an EMPTY immovable_dates list: allowed
        self.lp_edit(lambda d: None)
        self.assertEqual(self.rub("life_plan")[0].returncode, 0)

    def test_dm_g4_benchmarks_must_be_real(self):
        def edit(fn):
            b = jload(self.p("benchmarks"))
            fn(b["benchmarks"])
            jsave(self.p("benchmarks"), b)

        def ok():
            self.fill("pathway_map")
            r, d = self.rub("pathway_map")
            return next(a for a in d["auto_checks"] if a["id"] == "PM-G4"), r.returncode
        a, rc = ok()
        self.assertEqual((a["ok"], rc), (True, 0))
        edit(lambda bm: bm[2].update(institution="Provisional (benchmark scout not run)"))
        a, rc = ok()
        self.assertFalse(a["ok"])
        self.assertIn("placeholder name", a["detail"])
        self.assertEqual(rc, 1)
        edit(lambda bm: bm[2].update(institution="TBD", programme="TBD"))
        self.assertFalse(ok()[0]["ok"])
        # restore, then all-'?' vector: only with status provisional AND a note
        self.assertEqual(self.run_dir.exists(), True)
        shutil.copy(FIXTURE / "02_map/benchmarks.json", self.p("benchmarks"))
        qv = {"funding": "?", "programme": "?", "pathway": "?", "rubric_version": "1.0"}
        edit(lambda bm: bm[0].update(baseline_vector=qv, status="verified"))
        a, _ = ok()
        self.assertFalse(a["ok"])
        self.assertIn("all-'?' vector", a["detail"])
        edit(lambda bm: bm[0].update(status="provisional"))
        self.assertFalse(ok()[0]["ok"], "provisional without a note is still not enough")
        edit(lambda bm: bm[0].update(notes="Scout could not reach official pages; to be verified in S5"))
        a, rc = ok()
        self.assertEqual((a["ok"], rc), (True, 0))
        # two benchmarks on the same axis
        edit(lambda bm: bm[1].update(axis="funding"))
        self.assertFalse(ok()[0]["ok"])

    def test_wrong_rubric_name(self):
        d = jload(self.p("life_plan_score"))
        d["rubric"] = "pathway_map"
        jsave(self.p("life_plan_score"), d)
        self.assertEqual(run("rubric.py", self.run_dir, "life_plan").returncode, 2)


class TestShortlist(WS):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.merge().returncode, 0)

    def sl(self, *a):
        r = run("shortlist.py", self.run_dir, "--today", "2026-10-27", *a)
        self.assertEqual(r.returncode, 0, r.stderr)
        return self.p("rundown_tables").read_text(encoding="utf-8")

    def rows(self, md, heading):
        """Table rows (list of cell lists) of the section whose heading starts with `heading`."""
        sec = md.split(heading, 1)[1].split("\n## ", 1)[0]
        return [[c.strip() for c in ln.strip().strip("|").split(" | ")] for ln in sec.splitlines() if ln.startswith("| ") and not ln.startswith("| ---")]

    def test_sections_and_benchmark_max_total_are_computed(self):
        md = self.sl()
        for h in ("## 1. Benchmarks", "## 2. Shortlist", "## 3. Overlays", "## 4. Deadlines within 90 days of 2026-10-27", "## 5. Ruled out", "## 6. Stop-rule notes"):
            self.assertIn(h, md)
        self.assertIn("**benchmark_max_total = 6**", md)
        self.assertIn("A total of 6 = benchmark-class; 2 of 7 records reach it.", md)
        bench = self.rows(md, "## 1. Benchmarks")
        self.assertEqual(bench[0], ["Axis", "Benchmark", "F/P/W", "Sum", "Status"])
        self.assertEqual([b[2] for b in bench[1:]], ["3/1/2", "2/3/1", "1/2/3"])
        # changing a benchmark changes the number (it is not a constant)
        b = jload(self.p("benchmarks"))
        b["benchmarks"][0]["baseline_vector"] = {"funding": 3, "programme": 3, "pathway": 3, "rubric_version": "1.0"}
        jsave(self.p("benchmarks"), b)
        self.assertIn("**benchmark_max_total = 9**", self.sl())

    def test_shortlist_table(self):
        md = self.sl("--top", "3")
        rows = self.rows(md, "## 2. Shortlist")
        self.assertEqual(rows[0], ["ID", "Programme", "Institution, country", "F", "P", "W", "Total", "Practical component", "Funding route", "Language core/admission", "Next deadline", "Confidence", "Next action"])
        self.assertEqual([r[0] for r in rows[1:]], ["NL26-01", "XC26-01", "NL26-02"])
        top = dict(zip(rows[0], rows[1]))
        self.assertEqual((top["F"], top["P"], top["W"], top["Total"]), ("2", "2", "3", "7"))
        self.assertEqual(top["Practical component"], "thesis (30 credits)")
        self.assertEqual(top["Institution, country"], "Northfield University, Northland")
        self.assertEqual(top["Language core/admission"], "English / IELTS 6.5")
        self.assertEqual(top["Next deadline"], "2026-12-01 (confirmed)")
        self.assertEqual(top["Confidence"], "inferred (pathway)")
        self.assertTrue(top["Next action"].endswith("-> PI of the group (email)"), top["Next action"])
        self.assertIn("Excellence scholarship", top["Funding route"])
        self.assertIn("top 3 of 6 records not ruled out", md)
        # NL26-02 carries a '?' axis in the first pass but was replaced; add a '?' record to see the asterisk
        f = self.p("countries_dir") / "eastmark.json"
        d = jload(f)
        d["candidates"][0]["state_vector"]["pathway"] = "?"
        jsave(f, d)
        self.assertEqual(self.merge().returncode, 0)
        rows = self.rows(self.sl("--top", "15"), "## 2. Shortlist")
        ea = next(dict(zip(rows[0], r)) for r in rows[1:] if r[0] == "EA26-01")
        self.assertEqual(ea["Total"], "2*")

    def test_ruled_out_overlays_and_deadlines(self):
        md = self.sl()
        ids_short = [r[0] for r in self.rows(md, "## 2. Shortlist")[1:]]
        self.assertNotIn("EA26-02", ids_short, "funding verdict 'fails' is ruled out, not shortlisted")
        ruled = self.rows(md, "## 5. Ruled out")
        self.assertTrue(any(r[0] == "EA26-02" and "fails" in r[3] for r in ruled))
        self.assertTrue(any(r[0] == "MSc Statistics" for r in ruled), "ranked-out entries are listed")
        self.assertIn("2 institution(s) failed screening", md)
        ov = self.rows(md, "## 3. Overlays")
        self.assertEqual(ov[1][:2] + ov[1][3:5], ["XC26-01", "Joint MSc Data and Brain Science", "2", "3"])        # base F 2 (override), 3 if awarded
        self.assertIn("Home-country outbound scholarship", md.split("## 3. Overlays")[1])
        dl = self.rows(md, "## 4. Deadlines")
        self.assertEqual([r[0] for r in dl[1:]], ["2026-11-20", "2026-12-01", "2026-12-15", "2027-01-15"])
        types = {r[0]: (r[2], r[3]) for r in dl[1:]}
        self.assertEqual(types["2026-12-15"], ("inferred", "yes"))
        self.assertEqual(types["2026-12-01"], ("confirmed", "no"))
        short = self.sl("--deadline-days", "30")
        self.assertEqual([r[0] for r in self.rows(short, "## 4. Deadlines")[1:]], ["2026-11-20"])
        self.assertEqual(len([r for r in self.rows(self.sl("--ruled-out-max", "1"), "## 5. Ruled out") if r[0] in ("MSc Statistics", "MSc Materials")]), 1)

    def test_stop_rule_notes(self):
        md = self.sl()
        notes = md.split("## 6. Stop-rule notes")[1]
        self.assertIn("- eastmark: more work cannot change the decision.", notes)
        self.assertIn("- northland: open follow-up triggers:", notes)

    def test_cells_are_pipe_safe_and_errors(self):
        f = self.p("countries_dir") / "eastmark.json"
        d = jload(f)
        d["candidates"][0]["programme"] = "MSc A | B"
        jsave(f, d)
        self.assertEqual(self.merge().returncode, 0)
        md = self.sl()
        self.assertIn("MSc A \\| B", md)
        self.p("merged").unlink()
        self.assertEqual(run("shortlist.py", self.run_dir).returncode, 2)
        self.assertEqual(run("shortlist.py", self.run_dir, "--today", "x").returncode, 2)


class TestWorkspaceLayoutAndVector(unittest.TestCase):
    """protocol/engine/persistence.md is the spec of the workspace; protocol/state_vector.md the spec of the vector."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.d = Path(self._tmp.name) / "r"
        self.assertEqual(run("init_workspace.py", self.d, "--alias", "Applicant Q", "--mode", "local", "--run-id", "q-run").returncode, 0)

    def test_layout_is_exactly_the_one_in_persistence_md(self):
        for rel in ("run_state.json", "00_orientation/notes.md", "01_life_plan/interview_notes.md", "01_life_plan/life_plan.md", "01_life_plan/life_plan.json",
                    "01_life_plan/life_plan_score.json", "02_map/interview_notes.md", "02_map/pathway_map.md", "02_map/study_pathway_map.json", "02_map/map_score.json",
                    "02_map/benchmarks.json", "03_scope/search_plan.json", "03_scope/AGENT_BRIEF.md", "04_search/overrides.json", "04_search/orchestrator_notes.md",
                    "07_deliverables/options_rundown_template.md", "07_deliverables/due_diligence_template.md", "logs/session_log.jsonl"):
            self.assertTrue((self.d / rel).exists(), rel)
        for rel in ("02_domain_map", "templates", "02_map/domain_map.md", "02_map/research" + "_domain_map.json"):
            self.assertFalse((self.d / rel).exists(), rel)
        # drift guard: every file init creates is named in the workspace tree of persistence.md (templates are the documented exception)
        spec = (ROOT / "protocol/engine/persistence.md").read_text(encoding="utf-8").split("```")[1]
        import re
        named = {m.split("/")[-1] for m in re.findall(r"[\w<>\[\]./-]+\.(?:jsonl|json|md)", spec)}
        made = {f.name for f in self.d.rglob("*") if f.is_file()}
        self.assertFalse(made - named - {"options_rundown_template.md", "due_diligence_template.md"}, made - named)
        for dirname in ("00_orientation", "01_life_plan", "02_map", "03_scope", "04_search", "05_merge", "06_verify", "07_deliverables", "logs"):
            self.assertIn(dirname, spec)

    def test_notes_files_are_header_only_and_templates_are_not_the_old_top_level_ones(self):
        for rel in ("00_orientation/notes.md", "01_life_plan/interview_notes.md", "02_map/interview_notes.md"):
            lines = (self.d / rel).read_text(encoding="utf-8").splitlines()
            self.assertTrue(lines[0].startswith("# "), rel)
            self.assertLess(len(lines), 8, rel)
        src = (SCRIPTS / "init_workspace.py").read_text(encoding="utf-8")
        self.assertNotIn('"templates"', src.replace('"protocol" / "templates"', ""), "init_workspace must not depend on a top-level templates/ folder")

    def test_initial_vector_is_valid_and_matches_the_run(self):
        st = jload(self.d / "run_state.json")
        self.assertEqual(C.validate(st, "run_state"), [])
        v = st["state_vector"]
        self.assertEqual((v["run"], v["session"], v["phase"]), ("q-run", 0, "init"))
        self.assertEqual(st["current_phase"], "init")
        self.assertEqual(v["active"], {"user": [], "virgil": []})

    def test_update_vector_replaces_only_the_vector(self):
        before = jload(self.d / "run_state.json")
        v = dict(before["state_vector"], session=1, phase="life_plan", session_objective="Interview blocks 1-3",
                 completed=["Orientation"], next={"user": ["Answer block 4"], "virgil": ["Ask block 4"]},
                 assumptions=[{"text": "Partner moves too", "basis": "stated in block 2"}], blockers=[{"item": "Degree certificate", "owner": "USER"}])
        jsave(self.d / "vec.json", v)
        r = run("checkpoint.py", self.d, "update-vector", "--file", self.d / "vec.json")
        self.assertEqual(r.returncode, 0, r.stderr)
        after = jload(self.d / "run_state.json")
        self.assertEqual(after["state_vector"], v)
        strip = lambda d: {k: x for k, x in d.items() if k not in ("state_vector", "heartbeat")}
        self.assertEqual(strip(after), strip(before), "update-vector bumps nothing else")
        self.assertEqual(C.validate(after, "run_state"), [])
        # the same record through stdin and --json
        r = run("checkpoint.py", self.d, "update-vector", stdin=json.dumps(dict(v, session=2)))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(jload(self.d / "run_state.json")["state_vector"]["session"], 2)
        r = run("checkpoint.py", self.d, "update-vector", "--json", json.dumps(dict(v, session=3)))
        self.assertEqual(jload(self.d / "run_state.json")["state_vector"]["session"], 3)

    def test_update_vector_rejects_invalid_and_foreign_vectors_without_touching_the_file(self):
        good = jload(self.d / "run_state.json")["state_vector"]
        raw = (self.d / "run_state.json").read_text(encoding="utf-8")
        cases = {"missing field": {k: x for k, x in good.items() if k != "blockers"}, "bad owner": dict(good, blockers=[{"item": "x", "owner": "BOB"}]),
                 "bad phase": dict(good, phase="S1"), "extra key": dict(good, mood="ok"), "wrong run": dict(good, run="another-run")}
        for label, bad in cases.items():
            r = run("checkpoint.py", self.d, "update-vector", "--json", json.dumps(bad))
            self.assertNotEqual(r.returncode, 0, label)
            self.assertEqual((self.d / "run_state.json").read_text(encoding="utf-8"), raw, label)
        self.assertIn("another-run", run("checkpoint.py", self.d, "update-vector", "--json", json.dumps(cases["wrong run"])).stderr + run("checkpoint.py", self.d, "update-vector", "--json", json.dumps(cases["wrong run"])).stdout)

    def test_log_session_start_stamps_the_vector(self):
        self.assertEqual(run("checkpoint.py", self.d, "log-session", "--start", "--phase", "life_plan").returncode, 0)
        st = jload(self.d / "run_state.json")
        self.assertEqual(st["state_vector"]["session"], 1)
        self.assertRegex(st["state_vector"]["date"], r"^\d{4}-\d\d-\d\d$")
        self.assertEqual(C.validate(st, "run_state"), [])

    def test_validate_flags_a_vector_for_another_run_and_a_phase_mismatch(self):
        st = jload(self.d / "run_state.json")
        st["state_vector"]["run"] = "someone-else"
        jsave(self.d / "run_state.json", st)
        r = run("validate.py", self.d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("state_vector.run", r.stdout)
        st["state_vector"]["run"] = "q-run"
        st["state_vector"]["phase"] = "search"
        jsave(self.d / "run_state.json", st)
        r = run("validate.py", self.d)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("state_vector.phase", r.stdout)                  # a warning, not an error


class TestRenamesAreComplete(unittest.TestCase):
    """The axis is `pathway` everywhere; the old names are gone (no alias)."""
    OLD = ("research" + "_domain_map", "axis_2_" + "research", "research_" + "credit", "vs_research_" + "benchmark", "phd_" + "pathway", "domain_map_" + "score", "02_domain" + "_map")

    def test_no_old_names_in_scripts_schemas_tests_fixtures_or_appendix(self):
        files = [f for d in ("scripts", "schemas", "tests", "examples") for f in (ROOT / d).rglob("*") if f.is_file() and f.suffix in (".py", ".json", ".md")]
        files.append(ROOT / "docs/appendix_a_examples.md")
        for f in files:
            if f.name == "run_tests.py":
                continue                                               # this file names the old strings on purpose
            text = f.read_text(encoding="utf-8")
            for old in self.OLD:
                self.assertNotIn(old, text, f"{f.relative_to(ROOT)} still contains {old}")

    def test_axes_and_tiebreak_order(self):
        self.assertEqual(C.AXES, ("funding", "programme", "pathway"))
        a = {"state_vector": {"funding": 1, "programme": 1, "pathway": 3}, "id": "A"}
        b = {"state_vector": {"funding": 3, "programme": 1, "pathway": 1}, "id": "B"}
        c = {"state_vector": {"funding": 2, "programme": 2, "pathway": 1}, "id": "C"}
        # all three total 5: the tie goes to pathway (A=3), then to funding (B=3 beats C=2)
        self.assertEqual([x["id"] for x in sorted([c, b, a], key=C.rank_sort_key)], ["A", "B", "C"])
        d = {"state_vector": {"funding": 3, "programme": 3, "pathway": 0}, "id": "D"}       # a higher total beats everything
        self.assertEqual(sorted([a, d], key=C.rank_sort_key)[0]["id"], "D")

    def test_merge_report_and_merged_use_pathway(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "r"
            shutil.copytree(FIXTURE, d)
            self.assertEqual(run("merge.py", d, "--baseline", d / "baseline_ledger.json", "--now", "2026-10-27T12:00:00Z").returncode, 0)
            m = jload(C.rp(d, "merged"))
            self.assertIn("pathway", m["candidates"][0]["state_vector"])
            self.assertNotIn("research", m["candidates"][0]["state_vector"])
            self.assertEqual({b["axis"] for b in m["benchmarks"]["benchmarks"]}, {"funding", "programme", "pathway"})
            self.assertIn("pathway", jload(C.rp(d, "merge_report"))["delta_vs_baseline"]["axes"])


class TestPlannedCountryAndGates(WS):
    def test_planned_country_missing_is_an_error_or_a_warning(self):
        self.p("countries_dir").joinpath("eastmark.json").unlink()
        r = self.merge()
        self.assertEqual(r.returncode, 1)
        self.assertIn("[error] planned_country_missing: search_plan lists country 'eastmark'", r.stdout)
        r = self.merge("--allow-partial")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("[warning] planned_country_missing", r.stdout)
        self.assertNotIn("EA26-01", [c["id"] for c in self.merged()["candidates"]])
        rep = jload(self.p("merge_report"))
        issue = next(i for i in rep["issues"] if i["code"] == "planned_country_missing")
        self.assertEqual((issue["level"], issue["ref"]), ("warning", "eastmark"))

    def test_planned_crosscut_missing_too(self):
        self.p("crosscuts_dir").joinpath("home_scheme.json").unlink()
        r = self.merge()
        self.assertIn("planned_country_missing", r.stdout)
        self.assertIn("home_scheme", r.stdout)

    def test_gate_refusal_names_the_rubric_commands_and_force_logs(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "r"
            run("init_workspace.py", d, "--alias", "Applicant Q", "--mode", "local")
            r = run("checkpoint.py", d, "init-country", "--country", "ardenia", "--name", "Ardenia")
            self.assertEqual(r.returncode, 2)
            self.assertIn("rubric.py RUN life_plan|pathway_map", r.stderr)
            self.assertFalse((d / "04_search/countries/ardenia.json").exists())
            # a sheet that exists but did not pass is still a refusal
            run("rubric.py", d, "life_plan")
            self.assertIn("life_plan=fail", run("checkpoint.py", d, "init-country", "--country", "ardenia", "--name", "Ardenia").stderr)
            r = run("checkpoint.py", d, "init-country", "--country", "ardenia", "--name", "Ardenia", "--force", "--reason", "test")
            self.assertEqual(r.returncode, 0, r.stderr)
            o = jload(d / "run_state.json")["overrides_of_protocol"]
            self.assertEqual((len(o), o[0]["reason"]), (1, "test"))


class TestRubricMechanicalChecks(WS):
    """Mechanical checks mirror the gate wording of s1_life_plan.md / s2_pathway_map.md: a claimed pass that the files do not support is downgraded."""

    def score(self, rubric):
        key = {"life_plan": "life_plan_score", "pathway_map": "map_score"}[rubric]
        d = jload(self.p(key))
        for g in d["gates"]:
            g["status"], g["note"] = "pass", "claimed"
        for x in d["soft"]:
            x["score"] = 2
        jsave(self.p(key), d)
        r = run("rubric.py", self.run_dir, rubric)
        return r, jload(self.p(key))

    def failing(self, d, gid):
        return not next(a for a in d["auto_checks"] if a["id"] == gid)["ok"]

    def test_life_plan_gates_each_have_a_mechanical_check(self):
        base = jload(self.p("life_plan"))
        edits = {"LP-G1": lambda d: d["purpose_horizon"].update(horizon_years=None), "LP-G2": lambda d: d["post_degree_intent"].update(routes_open=["industry", "doctorate"], keep_open_is=None),
                 "LP-G3": lambda d: d["money"].update(currency=""), "LP-G4": lambda d: d["eligibility_facts"].update(citizenships=[]),
                 "LP-G5": lambda d: d["geography"].update(considered=[]), "LP-G6": lambda d: d["timeline"].update(wait_one_cycle=None),
                 "LP-G7": lambda d: d["household"].update(deal_breakers=None)}
        for gid, edit in edits.items():
            d = copy.deepcopy(base)
            edit(d)
            jsave(self.p("life_plan"), d)
            r, sc = self.score("life_plan")
            self.assertTrue(self.failing(sc, gid), gid)
            self.assertEqual(r.returncode, 1, gid)
            self.assertEqual(next(g for g in sc["gates"] if g["id"] == gid)["status"], "fail", gid)
        jsave(self.p("life_plan"), base)
        r, sc = self.score("life_plan")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(all(a["ok"] for a in sc["auto_checks"]))

    def test_keep_open_and_partner_rules(self):
        base = jload(self.p("life_plan"))
        d = copy.deepcopy(base)
        d["post_degree_intent"].update(routes_open=["doctorate", "industry"], keep_open_is="hedge")
        jsave(self.p("life_plan"), d)
        self.assertEqual(self.score("life_plan")[0].returncode, 0)
        d["household"].update(partner_moves=True, partner_work_needed=None)           # a moving partner needs the work answer
        jsave(self.p("life_plan"), d)
        r, sc = self.score("life_plan")
        self.assertTrue(self.failing(sc, "LP-G7"))
        d["household"].update(partner_work_needed=False)
        jsave(self.p("life_plan"), d)
        self.assertEqual(self.score("life_plan")[0].returncode, 0)

    def test_money_requirements_per_funded_type(self):
        base = jload(self.p("life_plan"))
        for ftype, ok_fields, missing in (("stipend_and_tuition", {"living_support_required_monthly": 1100, "household_size": 1}, "living_support_required_monthly"),
                                          ("tuition_only", {"max_total_tuition": 5000}, "max_total_tuition"),
                                          ("affordable", {"max_out_of_pocket": 8000, "living_support_required_monthly": 900, "household_size": 2}, "max_out_of_pocket")):
            d = copy.deepcopy(base)
            d["money"].update(funded_type=ftype, max_total_tuition=None, max_out_of_pocket=None, living_support_required_monthly=None)
            d["money"].update(ok_fields)
            jsave(self.p("life_plan"), d)
            self.assertFalse(self.failing(self.score("life_plan")[1], "LP-G3"), ftype)
            d["money"][missing] = None
            jsave(self.p("life_plan"), d)
            self.assertTrue(self.failing(self.score("life_plan")[1], "LP-G3"), ftype)

    def test_pathway_map_gates_each_have_a_mechanical_check(self):
        base = jload(self.p("study_pathway_map"))
        edits = {"PM-G1": lambda d: d["objective"].update(one_line="", research_question={"text": "q", "status": "maybe"}) if False else d["objective"].update(one_line=""),
                 "PM-G2": lambda d: d["domains"][0].update(coverage_keywords=[]),
                 "PM-G3": lambda d: d["pathway_signals"].update(people_topic_signals=["a", "b", "c", "d"]),
                 "PM-G5": lambda d: d["scoring_anchors"]["pathway"].update({"3": ""})}
        for gid, edit in edits.items():
            d = copy.deepcopy(base)
            edit(d)
            jsave(self.p("study_pathway_map"), d)
            r, sc = self.score("pathway_map")
            self.assertTrue(self.failing(sc, gid), gid)
            self.assertEqual(r.returncode, 1, gid)
        jsave(self.p("study_pathway_map"), base)
        d = copy.deepcopy(base)
        d["pathway_signals"].update(organisation_type_signals=["only one"])
        jsave(self.p("study_pathway_map"), d)
        self.assertTrue(self.failing(self.score("pathway_map")[1], "PM-G3"))
        d = copy.deepcopy(base)
        d["domains"] = d["domains"] + [dict(d["domains"][0], id=f"X{i}") for i in range(8)]       # 13 domains > 12
        jsave(self.p("study_pathway_map"), d)
        self.assertTrue(self.failing(self.score("pathway_map")[1], "PM-G2"))
        d = copy.deepcopy(base)
        d["objective"]["research_question"] = {"text": "How does X work?", "status": "working"}
        jsave(self.p("study_pathway_map"), d)
        self.assertFalse(self.failing(self.score("pathway_map")[1], "PM-G1"))

    def test_unknown_limits_are_per_rubric(self):
        r, sc = self.score("pathway_map")
        self.assertEqual(r.returncode, 0)
        d = jload(self.p("map_score"))
        for g in d["gates"]:
            g["status"] = "declared_unknown" if g["id"] == "PM-G3" else "pass"
        jsave(self.p("map_score"), d)
        self.assertEqual(run("rubric.py", self.run_dir, "pathway_map").returncode, 0, "one declared_unknown is allowed on the map")
        for gid in ("PM-G2", "PM-G4"):
            for g in d["gates"]:
                g["status"] = "declared_unknown" if g["id"] == gid else "pass"
            jsave(self.p("map_score"), d)
            r = run("rubric.py", self.run_dir, "pathway_map")
            self.assertEqual(r.returncode, 1, gid)
            self.assertIn("may never be declared_unknown", r.stdout)
        l = jload(self.p("life_plan_score"))
        for g in l["gates"]:
            g["status"] = "declared_unknown" if g["id"] in ("LP-G1", "LP-G2") else "pass"
        jsave(self.p("life_plan_score"), l)
        self.assertEqual(run("rubric.py", self.run_dir, "life_plan").returncode, 0, "the life plan allows two")

    def test_soft_weights_and_cli_names(self):
        import rubric
        self.assertEqual(list(rubric.SOFT["life_plan"].values()), [1, 2, 2, 2, 1, 1, 2, 1, 1, 1])
        self.assertEqual(list(rubric.SOFT["pathway_map"].values()), [1, 2, 1, 1, 1, 1])
        self.assertEqual(list(rubric.GATES["pathway_map"]), ["PM-G1", "PM-G2", "PM-G3", "PM-G4", "PM-G5"])
        self.assertEqual(list(rubric.GATES["pathway_map"].values()), ["objective", "knowledge_domains", "pathway_signals", "benchmarks", "scoring_anchors"])
        self.assertEqual(run("rubric.py", self.run_dir, "domain_map").returncode, 2, "the old rubric name is gone")
        sc = jload(self.p("map_score"))
        self.assertEqual((sc["rubric"], [g["id"] for g in sc["gates"]], [x["id"] for x in sc["soft"]]), ("pathway_map", [f"PM-G{i}" for i in range(1, 6)], [f"PM-S{i}" for i in range(1, 7)]))


class TestNonScienceAndCountryContext(unittest.TestCase):
    """Fixture B: a business/design applicant whose practical component is a paid internship, in GBP with UK-style credits.
    The tooling must work without any thesis / ECTS / EU assumption."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.d = Path(self._tmp.name) / "run"
        shutil.copytree(FIXTURE_B, self.d)

    def p(self, key):
        return C.rp(self.d, key)

    def test_validates_with_the_expected_household_warning(self):
        r = run("validate.py", self.d)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("2 records without household_fit although the life plan has dependants or a partner who moves", r.stdout)
        self.assertEqual(run("validate.py", self.d, "--strict").returncode, 1)
        # the dependant_pathway check: delete it and the warning appears
        f = self.p("countries_dir") / "westmarch.json"
        doc = jload(f)
        doc["country_context"].pop("dependant_pathway")
        jsave(f, doc)
        self.assertIn("dependant_pathway", run("validate.py", self.d).stdout)

    def test_both_gates_re_evaluate_to_pass_on_a_non_research_persona(self):
        for rub in ("life_plan", "pathway_map"):
            r = run("rubric.py", self.d, rub, "--check")
            self.assertEqual(r.returncode, 0, r.stdout)
        lp = jload(self.p("life_plan"))
        self.assertNotIn("fee_category", json.dumps(lp))
        self.assertEqual(lp["money"]["currency"], "GBP")
        self.assertEqual(jload(self.p("study_pathway_map"))["practical_component_needed"]["type"], "internship")

    def test_pipeline_end_to_end(self):
        self.assertEqual(run("merge.py", self.d, "--now", "2026-10-27T12:00:00Z").returncode, 0)
        m = jload(self.p("merged"))
        self.assertEqual(sorted(c["id"] for c in m["candidates"]), ["SV26-01", "SV26-02", "SV26-03", "SV26-04", "WM26-01"])
        self.assertEqual(m["candidates"][0]["id"], "SV26-01")
        self.assertEqual({c["practical_component"]["type"] for c in m["candidates"]}, {"internship"})
        fu = json.loads(run("followups.py", self.d, "--today", "2026-10-27").stdout)
        self.assertEqual([(t["trigger_type"], t["record_ids"]) for t in fu["triggers"]], [("deadline_soon", ["SV26-02"])])
        r = run("sample_verification.py", self.d, "--top", "2", "--random", "2", "--seed", "3")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = jload(self.p("verification_sample"))
        self.assertEqual(C.validate(s, "verification_sample"), [])
        self.assertTrue(any(i["claim_type"] == "people_partner" for i in s["items"]))
        self.assertTrue(s["extrapolable"])
        self.assertEqual(run("shortlist.py", self.d, "--today", "2026-10-27").returncode, 0)
        md = self.p("rundown_tables").read_text(encoding="utf-8")
        self.assertIn("internship (60 credits)", md)
        self.assertIn("GBP", md)
        self.assertEqual(run("due_diligence.py", self.d, "--today", "2026-10-27", "--metrics-json", self.d / "m.json").returncode, 0)
        dd = self.p("due_diligence").read_text(encoding="utf-8")
        for text in (md, dd):
            for banned in ("ECTS", "non-" + "EU", "thesis", "supervis"):
                self.assertNotIn(banned, text, banned)
        met = jload(self.d / "m.json")
        self.assertEqual(met["evidence"]["route_entries"], 5)
        self.assertEqual(met["evidence"]["takes_students"], {"confirmed": 3, "inferred": 1, "verification_needed": 1})

    def test_status_brief_on_the_business_run(self):
        lines = run("status.py", self.d, "--brief").stdout.splitlines()
        self.assertEqual(lines[0], "VIRGIL | Run fixture-business | Session 1 | Phase: search -> merge | Gates: Life Plan \u2713 \u00b7 Map \u2713")
        self.assertEqual(lines[4], "Waiting on: nothing")

    def test_no_hard_coded_region_defaults_in_scripts_and_schemas(self):
        import re
        for f in list((ROOT / "scripts").glob("*.py")) + list((ROOT / "schemas").glob("*.json")):
            text = f.read_text(encoding="utf-8")
            for m in re.finditer(r"\bnon-" r"EU\b|\"EUR\"|\bfee_category\b", text):
                ctx = text[max(0, m.start() - 80): m.end() + 40].replace("\n", " ")
                self.assertTrue(False, f"{f.name}: hard-coded region default near: {ctx}")


class TestPublicationHygiene(unittest.TestCase):
    """Nothing published from scripts/, schemas/, tests/, examples/ or the appendix may reveal the person the protocol was
    distilled from. The words are assembled from pieces so that this file does not itself contain them."""
    WORDS = ["koop" + "man", "operator " + "inference", "pi" + "nn", "cli" + "mate", "thermo" + "dynam", "order " + "reduction", "reduced" + "-order", "stoch" + "astic",
             "surro" + "gate", "atmo" + "spher", "eras" + "mus", "phy" + "sics", "non-" + "eu", "industry " + "professional", "aus" + "tralia", "bel" + "gium", "den" + "mark",
             "fra" + "nce", "it" + "aly", "jap" + "an", "nether" + "lands", "new " + "zealand", "nor" + "way", "sp" + "ain", "swe" + "den", "switzer" + "land", "ke" + "nya",
             "can" + "ada", "south " + "africa", "hydro" + "log", "fl" + "ood", "palerm" + "o", "applicant " + "r,"]

    def files(self):
        out = [f for d in ("scripts", "schemas", "tests", "examples") for f in (ROOT / d).rglob("*") if f.is_file() and f.suffix in (".py", ".json", ".md", ".jsonl")]
        return out + [ROOT / "docs/appendix_a_examples.md"]

    def test_no_reference_applicant_details(self):
        hits = []
        for f in self.files():
            low = f.read_text(encoding="utf-8").lower()
            hits += [f"{f.relative_to(ROOT)}: {w}" for w in self.WORDS if w in low]
        self.assertEqual(hits, [])

    def test_no_emails_or_real_looking_urls_in_published_examples(self):
        import re
        for f in self.files():
            text = f.read_text(encoding="utf-8")
            self.assertFalse(re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", text), f"e-mail address in {f.relative_to(ROOT)}")
            for url in re.findall(r"https?://([a-z0-9.-]+)", text):
                self.assertTrue(url.startswith(("example.", "json-schema.org")) or url.endswith(("example.edu", ".example")) or ".example." in url, f"{f.relative_to(ROOT)}: {url}")

    def test_reference_run_is_aggregates_only_and_regenerable(self):
        d = ROOT / "examples" / "reference_run"
        self.assertEqual(sorted(p.name for p in d.iterdir()), ["README.md", "due_diligence.md", "metrics.json"])
        self.assertFalse((d / "sample_candidate_records.json").exists())
        import due_diligence
        m = jload(d / "metrics.json")
        self.assertTrue(m["publish_safe"])
        self.assertEqual((d / "due_diligence.md").read_text(encoding="utf-8"), due_diligence.render(m), "run due_diligence.render over metrics.json to refresh the page")
        self.assertIsNone(m["scope"]["run_id"])
        self.assertTrue(all(r["name"].startswith(("Country ", "Cross-cut ")) for r in m["funnel"]["per_country"]))
        text = (d / "README.md").read_text(encoding="utf-8")
        self.assertIn("individual records are withheld", text.replace("**", ""))
        self.assertIn("tests/fixtures/run", text)


class TestAppendixExamples(unittest.TestCase):
    """docs/appendix_a_examples.md: every fenced json block must be valid for the schema named in its heading."""
    SEEN = {"run_state", "search_plan", "life_plan", "study_pathway_map", "benchmarks", "candidate_record", "funding_route_crosscut", "verification_record", "rubric_score"}

    def test_every_example_validates(self):
        import re
        text = (ROOT / "docs" / "appendix_a_examples.md").read_text(encoding="utf-8")
        seen = set()
        for block in re.split(r"(?m)^### ", text)[1:]:
            head = block.splitlines()[0]
            m = re.search(r"\(schema: ([a-z_]+)\)\s*$", head)
            self.assertTrue(m, f"heading without (schema: name): {head}")
            j = re.search(r"```json\n([\s\S]*?)```", block)
            self.assertTrue(j, f"no json block under {head}")
            errs = C.validate(json.loads(j.group(1)), m.group(1))
            self.assertEqual([(e.path, e.message) for e in errs], [], head)
            seen.add(m.group(1))
        self.assertEqual(seen, self.SEEN)


def main() -> int:
    argv = sys.argv[1:]
    once = "--once" in argv
    argv = [a for a in argv if a != "--once"]
    loader = unittest.defaultTestLoader
    result_ok = True
    runner = unittest.TextTestRunner(verbosity=1)
    selected = loader.loadTestsFromModule(sys.modules[__name__])
    if "-k" in argv:
        pat = argv[argv.index("-k") + 1]
        def filt(s):
            for t in s:
                if isinstance(t, unittest.TestSuite):
                    yield from filt(t)
                elif pat in t.id():
                    yield t
        selected = unittest.TestSuite(filt(selected))
    print(f"== validator: {C.validator_name()}")
    result_ok &= runner.run(selected).wasSuccessful()
    if not once and not os.environ.get("VIRGIL_BUILTIN_VALIDATOR") and C.validator_name() == "jsonschema":
        print("\n== validator: built-in (VIRGIL_BUILTIN_VALIDATOR=1)")
        env = dict(os.environ, VIRGIL_BUILTIN_VALIDATOR="1")
        rc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--once", *argv], env=env).returncode
        result_ok &= rc == 0
    return 0 if result_ok else 1


if __name__ == "__main__":
    sys.exit(main())
