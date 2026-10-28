# Reference run: aggregate results only

The protocol was distilled from one real search run. Its **individual records are withheld**: a programme-level list would
show one person's plan, and it would name third parties (staff, programmes, funding schemes). What is published here is what
can be shared safely: the aggregate numbers and the one-page report generated from them. Full, invented, field-by-field
examples of every file are in `tests/fixtures/run` (a science route) and `tests/fixtures/run_business` (a business/design
route with an internship), and in `docs/appendix_a_examples.md`.

| File | What it is |
|---|---|
| `due_diligence.md` | The one-page due-diligence report in publish-safe mode (`scripts/due_diligence.py --no-examples`): neutral labels (Country A ...), no names, ids, amounts, deadlines or applicant summary. |
| `metrics.json` | The numbers behind that page (`--metrics-json`), with the same neutral labels. |

Nothing else from the run is published: no applicant description, no institution, programme, person, scheme or software names,
no benchmark identities, no free text from the records.

## What the reference run was

* 12 countries searched (a first-pass agent each, 5 at a depth cap of 12 records and 7 at a cap of 8) plus 2 cross-cuts:
  a catalogue scan of joint degrees and a verification of one funding scheme.
* 9 follow-up agents to close gaps and 1 independent verifier: roughly 25 agent runs over about 4 usage windows
  (5 of the 12 first-pass agents finished before the first usage limit). These two figures are estimates and are
  printed as "about" in the report.
* Result: 353 institutions screened, 128 fully evidenced programme records, 186 further passing programmes with only a
  preliminary vector.
* The run used a hand-rolled schema and two ad-hoc scripts. For this example the aggregate numbers were converted to the
  current vocabulary (the third axis is `pathway`; named-contact counts are `takes_students`; `people_partner` claims) and
  rendered by the current `due_diligence.py`. The merge re-derived the headline numbers of the original audit (156 raw records
  -> 128 after 28 replacements, 385 screening rows -> 353, funding moves up 11 / down 4 on the 32 revisited prior entries).
  Nothing was re-computed from raw files in this repository, because the raw files are not published.

## Fields the reference run did not record (shown as "not recorded in reference run")

`source_type` and `accessed_date` per source, structured deadlines (they were free text), `contact_actions`, `overlays`,
run metadata (start/end, tool calls, limit events), a formal `funded_definition`, a random verification sample and rubric
versions. The report therefore shows "n/a" for the two rubric versions and "not recorded" for sessions.

## Known flaws of the reference run (what the protocol and scripts were built to fix)

1. **Funding was never operationally defined.** No record reaches funding 3; 65% sit at 1. "Funded" (stipend vs tuition-only)
   must be defined in the life plan before agents run, and home-country schemes kept as an overlay with their obligations.
2. **Budgets, not difficulty, set coverage.** Every first-pass agent hit a search or fetch budget; the people-first path
   (Path B) was skipped first. Late-found programmes beat the cap (hence `promote` flags and `followups.py`).
3. **Free-text enums.** Decisions, entry paths, eligibility and contact labels drifted; aggregation needed manual repair
   (hence schemas, `validate.py`, and validation on every `checkpoint.py` write).
4. **Weak numeric facts.** Fees and forward-dated deadlines carried almost all verification failures (3 wrong and 5 not found
   of 24 such claims); people claims were strong. The verification sample was the top 12 records, not random.
5. **Contact availability was mostly unconfirmed**: 13% of named contacts confirmed, 59% verification_needed. A "pathway 3"
   often meant that a person or partner exists, not that the programme's students can reach them.
6. **Overrides lived in code and chat**; follow-up extras (deadlines, scheme terms, people) were dropped by the old merge; the
   baseline vectors were typed by hand, so deltas mixed method change with real change.
7. **Unweighted sum ranks.** `_total` skips `?` axes, which understates unscored records; no benchmark scores 3/3/3, so a sum of 7 is
   already exceptional and a 6 only equals the benchmarks.
