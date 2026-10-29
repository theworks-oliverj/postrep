# Session 2: Study & Pathway Map

*Module `s2_pathway_map`. Load in phase `map`. Reads the S0 notes and the S1 plan. Writes to `02_map/`.*

## Purpose

Translate "what I want to learn and where I want it to lead" into criteria a research agent can search and score:
- **knowledge domains**, which determine programme (curriculum) fit;
- **pathway signals**, which determine pathway fit: the people, labs, companies, internship or placement schemes and professional links that connect a programme to the person's goal;
- **three benchmark programmes**, which anchor the 0-3 scales;
- **traps** to avoid.

This is the second half of the run's Preamble.

## The two entry paths this map feeds

- **Path A, programme-first:** find programmes whose curricula cover the knowledge domains.
- **Path B, people/partner-first:** find the people and organisations active in the pathway signals (research groups and supervisors; industry partners; internship, co-op and placement programmes; professional bodies), then the programmes connected to them.

Path B exists because a programme with an ordinary-looking curriculum can offer the best route to the goal. Examples: a thesis with the right supervisor, a placement with the right company, an accreditation that a career requires.

## Interview behaviour

Same as S1: start from what is already known, go deep, and save each theme to `02_map/interview_notes.md`. Virgil drafts the decomposition (domains, signals, anchors) from the person's goal and material, and the person corrects it. Attachments such as a proposal, a portfolio or a job advert for the target role are mined first.

## Fields

| ID | Field | Tracks | Done when |
|---|---|---|---|
| PM-G1 | objective | The study and career objective in one line. A research question, if there is one | A one-line objective; any research question has a status (settled, working, exploratory) |
| PM-G2 | knowledge_domains | What the person must learn, in 5-12 domains | Each domain has an id, label, priority (critical, high, medium, low), coverage keywords (words a module title or syllabus would use) and a self-teachable flag (yes, no, partly, unknown) |
| PM-G3 | pathway_signals | What indicates a programme connects to the goal | At least 5 people/topic signals (for research-led goals: methods or topics with recent publications; for industry-led goals: employers, sectors, roles, partner types) and at least 2 organisation-type signals (e.g. "institutes co-located with a university", "industry-sponsored capstones", "accredited by body X") |
| PM-G4 | benchmarks | Three real programmes that define "3": funding (best package the person is eligible for), programme (best curriculum match), pathway (best route to the goal: supervisor, partner or placement) | Each is verified on official pages, or explicitly `provisional`, and each has a baseline vector |
| PM-G5 | scoring_anchors | The 0-3 scale per axis, plus the screening rule | Anchors are written in terms of this person's benchmarks and funded definition (template in `sessions/s3_scope_brief.md`). The screening rule is stated |
| PM-S1 | nearest_frameworks (×1) | Existing programmes, fields or bodies of work closest to the goal | Named |
| PM-S2 | commitments_non_goals (×2) | What the person is committed to and what is explicitly out of scope | Both listed |
| PM-S3 | false_positive_traps (×1) | Patterns that look like a match but aren't (name collisions, an affiliate counted as faculty, marketing pages promising placements that don't exist) | Listed |
| PM-S4 | practical_component (×1) | What practical element the person needs (thesis, internship, industry placement, capstone, co-op, studio or clinic) and constraints on it | Stated |
| PM-S5 | connectedness_check (×1) | Whether the objective is supported by the domains and signals (optional subagent, prompt P6) | Done, or skipped with a reason |
| PM-S6 | progression (×1) | Preferences for what comes next (integrated doctorate, fast-track, graduate scheme, licensing) | Stated |

**Benchmark scout.** If the person has no benchmarks, run prompt P5: one agent looks at no more than about 10 programmes, uses both paths, and proposes provisional benchmarks with baseline vectors. Tell the person their benchmark totals. A candidate that matches the highest benchmark total is "benchmark-class". In the reference run each benchmark summed to 6 and none was 3/3/3; treat that as one observation, not a rule.

## Outputs

- `02_map/pathway_map.md`: the human view (`protocol/templates/pathway_map.md`).
- `02_map/study_pathway_map.json`: the machine view (`schemas/study_pathway_map.schema.json`).
- `02_map/benchmarks.json`.
- `02_map/map_score.json`.

## Rubric (`PM-1.0`)

The map passes when **both** of these hold:
- Every gate is `pass` or `declared_unknown`, with at most 1 gate `declared_unknown`, and never PM-G2 or PM-G4.
- The soft score is at least **70%** (the maximum is 14).

`scripts/rubric.py RUN_DIR pathway_map` computes the result.

**Calibration (n = 1):** the reference run's map would pass every gate, with a soft score of about 70-80%. It was the strongest input of that run.

## Exit

The rubric passes. The run's Preamble (S1 + S2) is now locked and changes only via `amend plan`. Update the state vector with `phase: map → scope`.
