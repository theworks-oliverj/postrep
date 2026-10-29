# Session 1: Life & Career Plan

*Module `s1_life_plan`. Load in phase `life_plan`. Reads `00_orientation/notes.md`. Writes to `01_life_plan/`.*

## Purpose

Produce a plan precise enough that a research agent with no other context can judge whether a programme fits this person's **life**: money, eligibility, geography, timeline, household and what the degree is for. This is half of the run's Preamble. Funding fit and programme fit are scored against it.

## Interview behaviour

- **Start from the S0 notes.** Confirm what they already settle, and ask only what is missing or contradictory (R7).
- **Go deep where it changes the search.** Money, eligibility facts and household constraints decide which programmes and scholarships are even possible, so probe them until they are concrete numbers and facts.
- **Group by theme, any length.** Quality matters more than brevity. Follow interesting threads, and come back to the field list.
- **Explain sensitive questions.** Say why each is asked. Offer ranges. A declined answer is recorded as `declined`, with its consequence.
- **Save after each theme.** Append it to `01_life_plan/interview_notes.md`.
- **Contest before closing.** At the end, name up to three contradictions or untested assumptions (R6).

## Fields (what the plan must track)

Gate fields (`G`) must be `pass`, or explicitly `declared_unknown`. Soft fields (`S`) are scored 0-2 × weight. In `life_plan.json` the gates live under `purpose_horizon`, `post_degree_intent`, `money`, `eligibility_facts`, `geography`, `timeline` and `household` (see `engine/data_contract.md`). Soft fields use the IDs' names as JSON keys (e.g. `gaps_self_teachable`, `support_assets`).

| ID | Field | Tracks | Done when | Seed question |
|---|---|---|---|---|
| LP-G1 | purpose_horizon | What the degree is for, and the 3-5 year picture | The purpose is stated as work or outcomes, not a title; a horizon is given | "What should this degree make possible, and what does a normal working day look like five years from now?" |
| LP-G2 | post_degree_intent | The route after the degree: doctorate, industry, public sector, own venture, career switch, undecided | The intent is stated. If several are open, it's clear whether keeping them open is a requirement or a hedge | "After the degree: which routes are open, and must the programme keep them all open?" |
| LP-G3 | money_operationalised | What "funded" means for this person | One definition with numbers and a currency: (a) tuition + living support, (b) tuition only, or (c) a max total out-of-pocket amount and the living support needed per month for a household of N. Debt stance stated | "What is the most you could pay yourself in total, and what monthly support would you need, for how many people?" |
| LP-G4 | eligibility_facts | Facts that decide scholarship and admission eligibility | Citizenship(s), residence (country and region), highest degree (field, country, graduation year, grade and scale), and language certificates (held or planned, with dates) are recorded | "Some scholarships depend on nationality, residence, or how recently you graduated; can we record these?" |
| LP-G5 | geography_language | Where the person could live and study | An exhaustive considered-list (regions expanded into countries with keep/drop), exclusions with reasons, accepted teaching languages, and languages the person is willing to learn | "Every country you've ever considered, even half-seriously?" |
| LP-G6 | timeline | When the person can start | Earliest and latest start, immovable dates, and whether waiting one cycle is acceptable | "What's the earliest and latest start that works?" |
| LP-G7 | household_dealbreakers | Dependants, partner, obligations | Dependants and partner situation (who moves, work rights needed), stance on post-degree return obligations, and deal-breakers are stated. An explicit "none" counts | "Who moves with you, and what would make you turn down an otherwise perfect programme?" |
| LP-S1 | strengths (×1) | Assets the person brings | Three concrete strengths | |
| LP-S2 | gaps_self_teachable (×2) | Knowledge or skill gaps, and which are self-teachable | Gaps are listed, each marked self-teachable or not | |
| LP-S3 | long_term_role (×2) | A concrete target role or sector | Specific enough to judge pathway fit | |
| LP-S4 | tradeoff_ranking (×2) | The relative weight of funding, curriculum, pathway (people, partners, placements), location, prestige, post-study work rights | A ranked list | |
| LP-S5 | risk_tolerance (×1) | Appetite for financial risk and for long-shot options | Low, medium or high for each | |
| LP-S6 | study_format (×1) | Acceptable formats: full-time, part-time, online, research-only, work-integrated | Accepted and rejected formats listed | |
| LP-S7 | decision_criteria (×2) | What would make the person say yes immediately | Explicit conditions | |
| LP-S8 | support_assets (×1) | Referees, portfolio, publications, existing contacts | Listed | |
| LP-S9 | assumptions_log (×1) | Pivots and assumptions surfaced during the interview | Logged, each with a basis | |
| LP-S10 | lifestyle (×1) | City size, climate, distance from home, community | Stated, or "no preference" | |

## Outputs

- `01_life_plan/life_plan.md`: the human view (`protocol/templates/life_plan.md`).
- `01_life_plan/life_plan.json`: the machine view (`schemas/life_plan.schema.json`).
- `01_life_plan/life_plan_score.json`: the rubric result (`schemas/rubric_score.schema.json`).

## Rubric (`LP-1.0`)

The plan passes when **both** of these hold:
- Every gate is `pass` or `declared_unknown`, with at most 2 gates `declared_unknown`. LP-G3 and LP-G4 can be `declared_unknown` only when the note records the person's explicit acceptance of the consequence.
- The soft score is at least **70%**. Soft % = Σ(score × weight) / (2 × Σweight) × 100, and the maximum is 28.

`scripts/rubric.py RUN_DIR life_plan` computes the result and checks the gate fields mechanically. Virgil scores the soft fields.

**Calibration (n = 1):** the reference run's implicit plan, scored after the fact, fails LP-G4 (graduation year unknown) and is only partial on LP-G3 ("zero tuition" vs "affordable" unresolved). Its soft score is about 55-65%. Those gaps caused open questions to pile up mid-search. The 70% threshold means "the reference run with its known holes fixed".

**If the plan fails:** show which items cost the most points, and offer to fix them now.

## Exit

The rubric passes, or the person overrides the gate (logged under R3). Update the state vector with `phase: life_plan → map`.
