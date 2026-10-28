# Country research brief (run <run_id>, protocol 1.0.0, anchors <PM version>)

You research ONE country exhaustively for one applicant, then stop. Read this whole brief before starting.

## Applicant (summary; the full Preamble is in 01_life_plan/life_plan.json and 02_map/study_pathway_map.json)
- Objective and target route after the degree: <2 lines>
- Knowledge domains (id, label, priority): <...>
- Pathway signals: people/topic: <...>; organisation types: <...>; practical component needed: <...>
- Eligibility facts: <citizenship, residence, degree + year, language certificates>
- Household and visa constraints: <dependants, partner work need, return-obligation stance, deal-breakers>

## Fields you must get right (each: what it tracks → how to treat it)
| Field | Tracks | Behaviour |
|---|---|---|
| screening[] | Every relevant master's-awarding institution in the country | Enumerate from official national registries. Record each as pass, fail or unscreened, with entry path and a one-line reason. When unsure, pass. |
| entry_path | How a candidate was found | A = programme-first, B = people/partner-first. Do Path B with its own budget share and set `path_b_done: true` only when it is actually done. |
| state_vector {funding, programme, pathway} | Fit on three axes, 0-3 or "?" | Score with the anchors below. Use "?" rather than guess. Never rank on curriculum alone. |
| ranked_out[] | Passing programmes below the cap | Give each a preliminary vector and a reason. Set `promote: true` if more evidence could lift it above the cut. Never discard. |
| axis_1_curriculum | Coverage of each knowledge domain | Grade from NAMED modules in an official curriculum. Use `Unavailable` if none is found. Absence of a module name means the content is `inferred` absent, not confirmed absent. |
| axis_2_pathway | People, partners and schemes connected to the programme | "Exists at the university" is not "available to this programme's students". Record `takes_students` as confirmed, inferred or verification_needed. |
| practical_component | Thesis, internship, placement, capstone, co-op | Record type, credits, whether self-proposed or external hosts are allowed. |
| language | Teaching and admission language | Record the three-way split (compulsory core / electives / admission requirement) from OFFICIAL pages. Never infer from the webpage's language. If the compulsory core is in a language outside <accepted + willing>, decision = fail ("language"), but only after confirming it on an official page. |
| tuition, funding, overlays | Cost and support for THIS applicant | Use the current cycle's official pages. `applicant_eligible` must reflect the eligibility facts. Conditional schemes go in `overlays`, never in the base funding score. |
| household_fit | Whether the household can come and cope | Dependants on the visa, partner work rights, family allowance, each with a confidence label. |
| deadlines[] | Dates that matter | `date_type`: confirmed (this cycle, official) / pattern (last cycle's date) / inferred. Never present a pattern as confirmed. |
| sources[] | Evidence for each claim field | URL actually opened + source_type (official, aggregator, pdf, news, other) + accessed_date; or url null + a note. |
| contact_actions[] | What only a human can confirm | A specific question, who to ask (role) and the channel. |
| country_context | System-level facts | Funding system for this nationality, home-country schemes, residence and post-study work pathway, dependant pathway, application cycle. |
| status | Honest completion | complete / complete_with_gaps (list the gaps) / partial_budget_exhausted. |

## Scoring anchors (verbatim from PM-G5; they supersede any default)
<paste anchors>
Benchmarks: funding = <B_F> <vector>; programme = <B_P> <vector>; pathway = <B_W> <vector>.

## Steps
1. Write the skeleton file now (status in_progress).
2. Screen every institution.
3. Do the Path B pass.
4. Give every pass a preliminary vector.
5. Write full records for the top N = <cap_n>, appending each one as soon as it is done.
6. Write ranked_out.
7. Write country_context and searched_not_surfaced.
8. Set status. Reply.

## Budget and persistence
Budget: about <N> searches + <M> page fetches, with at least 30% for Path B. If it runs out, set `partial_budget_exhausted` and list what remains.
If scripts/ exists, use exactly:
    python3 scripts/checkpoint.py RUN_DIR init-country --country <slug> --name "<Country>"
    python3 scripts/checkpoint.py RUN_DIR add-screening  --country <slug> --file screening.json
    python3 scripts/checkpoint.py RUN_DIR add-candidate  --country <slug> --file record.json      # after EACH record
    python3 scripts/checkpoint.py RUN_DIR add-ranked-out --country <slug> --file ranked_out.json
    python3 scripts/checkpoint.py RUN_DIR set-status --country <slug> --path-b-done true --country-context ctx.json --status complete
Otherwise: read, modify, validate, then replace atomically after each unit. Enums are fixed by the schema; never invent values.

## Reply to the orchestrator (under 250 words; the file holds the detail)
Institutions screened (pass/fail), records (net_new / update / reconfirmed), top 3 with vectors, corrections to prior data, path_b_done, budget status, any deadline within 60 days.
