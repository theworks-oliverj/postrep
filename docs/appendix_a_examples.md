# Appendix A examples: minimal, schema-valid files

Each block below is a complete, valid instance of the schema named in its heading
(`schemas/<name>.schema.json`). They are deliberately short: the required fields plus the key
fields agents most often get wrong. `tests/run_tests.py` validates every block, so they cannot drift
from the schemas. Where a protocol gate needs more than the example shows (for example five
knowledge domains for PM-G2), the text above the block says so.

All names are invented. The fictional applicant ("Applicant K") is a practising urban designer who
wants to move into transport planning through a master's with a capstone project, so the examples
also show that nothing in the tooling assumes a thesis, a research career or a particular region.

### 01_life_plan/life_plan.json (schema: life_plan)

Gate LP-G3 wants the numbers its `funded_type` needs, a currency and a debt answer; LP-G4 wants citizenship, residence, the highest degree with year, grade and scale, and the language-certificate status. `fee_status` is optional free text (there is no fee-category gate).

```json
{
  "schema_version": "1.0",
  "applicant_alias": "Applicant K",
  "profile_summary": "Applicant K, six years in urban design practice, partner moves too",
  "purpose_horizon": {"purpose": "Move from urban design into transport planning leadership", "horizon_years": 6},
  "post_degree_intent": {"intent": "career_switch", "routes_open": ["industry", "public_sector"], "keep_open_is": "hedge", "detail": "A planning role at a transport agency or consultancy within a year"},
  "money": {
    "funded_type": "affordable", "max_total_tuition": null, "max_out_of_pocket": 15000,
    "living_support_required_monthly": 1100, "household_size": 2, "currency": "USD",
    "debt_acceptable": true, "debt_limit": 8000, "income_during_degree": 600, "dependants_on_income": 0
  },
  "eligibility_facts": {
    "citizenships": ["Exampleland"], "residence_country": "Exampleland", "residence_region": "",
    "highest_degree": {"field": "Architecture", "country": "Exampleland", "graduation_year": 2019, "grade": "upper second", "grade_scale": "UK-style honours classes"},
    "language_certificates": [], "language_certificates_note": "None held; the first degree was taught in English",
    "age_bracket": "30-34", "fee_status": "overseas student, three years of residence abroad"
  },
  "geography": {
    "considered": ["Eastvale", "Lowmark"],
    "excluded": [{"country": "Farland", "reason": "partner cannot work there"}],
    "languages_willing_c1": [], "teaching_languages_accepted": ["English"]
  },
  "timeline": {"earliest_start": "2028-09", "latest_start": "2028-09", "immovable_dates": ["Partner's contract ends 2028-06"], "wait_one_cycle": false},
  "household": {"dependants": 0, "partner_moves": true, "partner_work_needed": true, "return_obligation_stance": "acceptable", "deal_breakers": ["No work rights for the partner"]},
  "risk_tolerance": {"money": "medium", "long_shots": "low"}
}
```

If the applicant holds no language certificate, leave `language_certificates` empty and write `"none"` in `language_certificates_note`: gate LP-G4 accepts that, and nothing else, as an answer. When the partner does not move, write `"partner_moves": false` (LP-G7 wants a true/false answer, not a missing field).

### 02_map/map_score.json (schema: rubric_score)

`rubric.py RUN_DIR pathway_map` writes this file (and `life_plan` writes `01_life_plan/life_plan_score.json` in the same shape). It recomputes `auto_checks` from the real files and downgrades a claimed pass that the files do not support. A life plan may leave two gates `declared_unknown` (LP-G3 and LP-G4 only with `user_accepted_consequence`); the pathway map may leave one, never PM-G2 or PM-G4. The block below is the pathway-map sheet (PM-G1..G5, soft PM-S1..S6, weights 1,2,1,1,1,1).

```json
{
  "rubric": "pathway_map",
  "rubric_version": "1.0",
  "gates": [
    {"id": "PM-G1", "status": "pass", "note": "objective.one_line present"},
    {"id": "PM-G2", "status": "pass", "note": "6 domains with keywords"},
    {"id": "PM-G3", "status": "pass", "note": "6 people/topic signals, 2 organisation types"},
    {"id": "PM-G4", "status": "pass", "note": "three real benchmarks, one per axis"},
    {"id": "PM-G5", "status": "pass", "note": "12 anchors and a screening rule"}
  ],
  "soft": [
    {"id": "PM-S1", "weight": 1, "score": 2, "note": "nearest frameworks named"},
    {"id": "PM-S2", "weight": 2, "score": 2, "note": "commitments and non-goals stated"},
    {"id": "PM-S3", "weight": 1, "score": 1, "note": "one trap named"},
    {"id": "PM-S4", "weight": 1, "score": 2, "note": "capstone needed, credit system stated"},
    {"id": "PM-S5", "weight": 1, "score": 2, "note": "domains connect to the objective"},
    {"id": "PM-S6", "weight": 1, "score": 1, "note": "progression only sketched"}
  ],
  "soft_pct": 85.7,
  "passed": true,
  "scored_at": "2027-10-02T10:00:00Z"
}
```

### run_state.json (schema: run_state)

`state_vector` is the continuation vector of `protocol/state_vector.md` (what the next session needs to resume); it is not the F/P/W score vector of a programme. Replace it as a whole with `checkpoint.py RUN_DIR update-vector --file vector.json`.

```json
{
  "protocol_version": "1.0.0",
  "run_id": "applicant-k-20271001",
  "applicant_alias": "Applicant K",
  "mode": "local",
  "current_phase": "search",
  "sessions": [
    {"n": 1, "started_at": "2027-10-01T09:00:00Z", "ended_at": "2027-10-01T11:00:00Z", "phase": "life_plan", "outcome": "ok", "limit_hit": false},
    {"n": 2, "started_at": "2027-10-02T09:00:00Z", "ended_at": null, "phase": "search", "outcome": "open", "limit_hit": false, "agents_run": 4, "wave": 1}
  ],
  "checkpoints": [
    {"file": "04_search/countries/eastvale.json", "status": "in_progress", "updated_at": "2027-10-02T09:30:00Z", "records": 2}
  ],
  "assumptions": [
    {"id": "A1", "text": "A paid internship covers part of the living costs.", "made_in": "session 1, life_plan", "revisit": true}
  ],
  "overrides_of_protocol": [
    {"date": "2027-10-02", "rule": "no gate, no search", "override": "searched one country before the pathway map passed", "reason": "applicant wanted an early signal"}
  ],
  "next_action": "Resume eastvale: finish screening, then run Path B.",
  "agents_per_window_observed": null,
  "state_vector": {
    "run": "applicant-k-20271001",
    "session": 2,
    "date": "2027-10-02",
    "phase": "search",
    "session_objective": "Search wave 1: Eastvale",
    "context": ["Urban designer moving into transport planning", "Partner moves too"],
    "unknowns": ["Whether the partner may work on a student family permit"],
    "ambiguities": [],
    "assumptions": [{"text": "A paid internship covers part of the living costs.", "basis": "stated in interview block 3"}],
    "completed": ["Life plan passed", "Pathway map passed", "Search brief written"],
    "active": {"user": [], "virgil": ["Eastvale screening"]},
    "next": {"user": ["Check the shortlisted deadlines when the rundown arrives"], "virgil": ["Finish Eastvale, then run Path B"]},
    "blockers": [{"item": "Eastvale ministry site blocks automated access", "owner": "EXTERNAL"}],
    "artifacts": ["02_map/study_pathway_map.json", "03_scope/search_plan.json", "04_search/countries/eastvale.json"]
  }
}
```

### 02_map/study_pathway_map.json (schema: study_pathway_map)

Gate PM-G2 needs 5 to 12 domains, each with coverage keywords, and PM-G3 at least 5 people/topic signals and 2 organisation-type signals; two and two are shown here to keep the example short (the file would not pass the gate as shown).

```json
{
  "schema_version": "1.0",
  "generated": "2027-10-02",
  "objective": {"one_line": "Lead transport-planning teams after a master's with a real client capstone.", "nearest_frameworks": ["MSc Transport Planning", "MSc Urban Mobility"], "commitments": ["a capstone or placement of at least 3 months"], "non_goals": ["purely theoretical policy degrees"]},
  "domains": [
    {"id": "NET", "label": "Network and demand modelling", "priority": "critical", "coverage_keywords": ["traffic assignment", "demand forecasting"], "self_teachable": "no"},
    {"id": "POL", "label": "Transport policy and appraisal", "priority": "high", "coverage_keywords": ["cost-benefit", "appraisal"], "self_teachable": "partly"}
  ],
  "pathway_signals": {
    "people_topic_signals": ["agency-sponsored capstones", "consultancy placements"],
    "organisation_type_signals": ["transport agencies", "planning consultancies"],
    "known_people_or_orgs": []
  },
  "practical_component_needed": {"type": "capstone", "credits": 6, "credit_system": "US semester credits", "notes": "Client project; the host may be external."},
  "false_positive_traps": ["general urban studies degrees without a quantitative strand"],
  "connectedness_check": {"connected": true, "notes": "Modelling and appraisal both serve the planning objective."},
  "progression": {"intent": "agency graduate scheme", "notes": "Placement partners should recruit from the programme."},
  "scoring_anchors": {
    "funding": {"0": "Applicant pays full tuition and living costs", "1": "Tuition reduced, no living support", "2": "Tuition-free or paid placement covering part of living costs", "3": "Tuition-free and household living support"},
    "programme": {"0": "No transport content", "1": "One relevant module", "2": "Several relevant modules", "3": "Modelling and appraisal both taught"},
    "pathway": {"0": "No relevant partner", "1": "Partner exists, no student access shown", "2": "Named placement lead with student cohort", "3": "Named partner, recent projects on the signals, placement route confirmed"}
  },
  "screening_rule": {"description": "Pass if the curriculum covers a critical domain OR a named partner's recent work hits a pathway signal.", "unsure_policy": "pass"},
  "benchmarks_ref": "02_map/benchmarks.json"
}
```

### 02_map/benchmarks.json (schema: benchmarks)

Exactly three entries, one per axis. The names below are invented; a real run uses real programmes (gate PM-G4 rejects placeholder names and all-"?" vectors).

```json
{
  "benchmarks": [
    {"axis": "funding", "institution": "Example University A", "programme": "MSc Transport Systems", "baseline_vector": {"funding": 3, "programme": 1, "pathway": 2, "rubric_version": "1.0"}, "evidence_urls": ["https://example.edu/a"], "status": "verified"},
    {"axis": "programme", "institution": "Example University B", "programme": "MSc Transport Planning", "baseline_vector": {"funding": 2, "programme": 3, "pathway": 1, "rubric_version": "1.0"}, "evidence_urls": ["https://example.edu/b"], "status": "verified"},
    {"axis": "pathway", "institution": "Example Institute C", "programme": "MSc Urban Mobility with Placement", "baseline_vector": {"funding": 1, "programme": 2, "pathway": 3, "rubric_version": "1.0"}, "evidence_urls": ["https://example.edu/c"], "status": "provisional", "notes": "Placement partners not yet confirmed"}
  ]
}
```

### 03_scope/search_plan.json (schema: search_plan)

```json
{
  "schema_version": "1.0",
  "rubric_version": "1.0",
  "created": "2027-10-02",
  "countries": [
    {"slug": "eastvale", "name": "Eastvale", "depth": "deep", "cap_n": 12, "wave": 1},
    {"slug": "lowmark", "name": "Lowmark", "depth": "quick", "wave": 2}
  ],
  "crosscuts": [
    {"slug": "regional_joint_degrees", "name": "Regional and joint degrees", "kind": "programme_scan", "description": "Joint master's programmes that span countries"},
    {"slug": "donor_scholarships", "name": "Donor-funded scholarships", "kind": "funding_route", "description": "Verify the scholarships the applicant could combine with a place"}
  ],
  "overlay_policy": "overlay only: never raise the base funding score; show effect and obligations next to it",
  "wave_weights": {"deep": 1.5, "standard": 1, "quick": 0.5, "crosscut": 0.75},
  "funded_definition": {
    "type": "affordable", "max_total_tuition": null, "max_out_of_pocket": 15000,
    "living_support_required_monthly": 1100, "household_size": 2, "currency": "USD", "min_funding_score": 2
  },
  "exclusions": [{"country": "Farland", "reason": "partner cannot work there"}, "Programmes taught only in a language the applicant will not learn"],
  "session_plan": {"waves": [{"wave": 1, "countries": ["eastvale"], "expected_windows": 1}, {"wave": 2, "countries": ["lowmark"], "expected_windows": 1}], "agents_per_window_estimate": 6}
}
```

A `quick` country may omit `cap_n` (the default is 4); `deep` and `standard` countries should state it. A `funded_definition` for `stipend_and_tuition` needs `living_support_required_monthly` and `household_size`; for `tuition_only` it needs `max_total_tuition`; for `affordable` it needs `max_out_of_pocket` plus the two living fields. All amounts are in `currency`.

### 04_search/countries/eastvale.json, one candidate (schema: candidate_record)

The record shows the pathway axis for a non-research route: a placement office as the partner, a named contact, and an external-host capstone. `axis_1_curriculum` is keyed by the domain ids of the pathway map. Every claim carries a source with its type and the date the page was opened; a claim without a page is written with `"url": null`, never an invented URL.

```json
{
  "id": "EV27-01",
  "prior_id": null,
  "status": "net_new",
  "institution": "Harbour School of Planning",
  "programme": "MSc Transport Planning with Capstone",
  "track": "",
  "city": "Harbourton",
  "degree_type_and_length": "MSc 36 credits / 12 months",
  "sources": [
    {"claim_field": "programme", "url": "https://example.edu/ev27-01/programme", "source_type": "official", "accessed_date": "2027-10-02", "note": "programme page"},
    {"claim_field": "tuition", "url": "https://example.edu/ev27-01/fees", "source_type": "official", "accessed_date": "2027-10-02", "note": "fee table"},
    {"claim_field": "deadline", "url": null, "source_type": "other", "accessed_date": "2027-10-02", "note": "not located"}
  ],
  "axis_1_curriculum": {
    "NET": {"grade": "Strong", "evidence": "two modelling modules in the study plan", "confidence": "confirmed"},
    "POL": {"grade": "Moderate", "evidence": "one appraisal module", "confidence": "inferred"}
  },
  "axis_1_verdict": "Covers both domains; appraisal is thin.",
  "axis_2_pathway": {
    "people_and_partners": [
      {"name": "Placement office of Harbour School of Planning", "type": "placement_scheme", "url": "https://example.edu/ev27-01/placements",
       "contacts": [{"name": "Placement lead (role descriptor)", "role": "placement lead", "focus": "agency and consultancy capstones", "recent_work": "n/a", "url": null, "takes_students": "confirmed"}]}
    ],
    "summary": "A placement office with a named lead and a cohort-wide capstone scheme."
  },
  "practical_component": {"type": "capstone", "credits": 6, "self_proposed": false, "external_host_allowed": true, "notes": "US semester credits; client project of 12 weeks"},
  "progression": "Agency graduate scheme via partner employers.",
  "language": {"core": "English", "electives": "English", "admission_requirement": "not stated", "source_url": "https://example.edu/ev27-01/language", "source_note": "admissions page"},
  "tuition": {"amount_text": "USD 14,000 per year (2027/28)", "applies_to": "overseas students", "currency": "USD", "annual_amount": 14000, "academic_year": "2027/28", "confidence": "confirmed"},
  "funding": {"routes": [{"name": "Capstone stipend", "amount": "USD 3,000", "applicant_eligible": "inferred", "eligibility_detail": "paid by the host agency", "competitiveness": "competitive", "url": "https://example.edu/ev27-01/stipend"}], "verdict": "competitive_scholarship_only"},
  "deadlines": [{"name": "Main round", "date": "2028-01-31", "date_type": "confirmed", "source_url": "https://example.edu/ev27-01/dates", "cycle": "2028/29"}],
  "state_vector": {"funding": 2, "programme": 3, "pathway": 2, "rubric_version": "1.0", "notes": "stipend not guaranteed"},
  "benchmark_comparison": {"vs_funding_benchmark": "weaker", "vs_programme_benchmark": "similar", "vs_pathway_benchmark": "similar"},
  "confidence": {"curriculum": "confirmed", "pathway": "inferred", "funding": "inferred"},
  "open_questions": ["Is the stipend paid for every capstone host?"],
  "contact_actions": [{"question": "Can students arrange their own capstone host?", "who": "placement lead", "channel": "email"}]
}
```

### 04_search/crosscuts/donor_scholarships.json (schema: funding_route_crosscut)

```json
{
  "crosscut_kind": "funding_route",
  "route": "Donor-funded master's scholarship",
  "route_type": "other",
  "checked_at": "2027-10-05",
  "status": "complete",
  "findings": [
    {"question": "Is the applicant's citizenship eligible?", "answer": "Yes, listed countries include the applicant's.", "confidence": "confirmed", "urls": ["https://example.org/scheme/eligibility"]},
    {"question": "Does it cover a partner?", "answer": "A family allowance exists; amount not stated.", "confidence": "verification_needed", "urls": []}
  ],
  "obligations": "Return to the home region for two years after the degree.",
  "verdict": "Plausible overlay; family cover and the return obligation must be confirmed with the scheme office.",
  "open_questions": ["Amount of the family allowance", "Is the obligation waivable for further study?"]
}
```

Write it with `checkpoint.py init-country --crosscut donor_scholarships --kind funding_route --name "Donor-funded master's scholarship"`, then one `add-finding` per question and `set-status --crosscut donor_scholarships --status complete`.

### 06_verify/verification.json (schema: verification_record)

```json
{
  "items": [
    {"id": "EV27-03", "claim": "Tuition USD 9,000 per year (2027/28)", "claim_type": "fee", "verdict": "wrong", "evidence_url": "https://example.edu/fees", "note": "Official page says USD 11,000 for overseas students.", "sampled_by": "top_n"},
    {"id": "LM27-01", "claim": "Placement lead takes students from this programme", "claim_type": "people_partner", "verdict": "confirmed", "evidence_url": "https://example.edu/placements", "note": "Listed on the placement page with two current host agencies.", "sampled_by": "random"}
  ],
  "summary": {"notes": "Fees and deadlines were the weakest claims; placement contacts were solid.", "checked_by": "independent verifier agent"}
}
```
