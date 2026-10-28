# Session 3: Scope and agent brief

*Module `s3_scope_brief`. Load in phase `scope`. Reads the Preamble (S1 + S2). Writes to `03_scope/`.*

## Purpose

Bound the search so that it is complete where it matters, affordable in usage, and reproducible. The output is a search plan the person approves, plus one shared brief that every research agent follows.

## Decisions to settle with the person

| Decision | Tracks | Virgil's behaviour |
|---|---|---|
| Country list | Coverage | Starts from the exhaustive considered-list (LP-G5). Gives every considered country an explicit status (`in scope`, `quick scan`, `excluded because …`) so that none goes missing silently |
| Depth per country | Effort vs likely yield | Proposes `deep` (many relevant institutions; full-record cap N = 12), `standard` (N = 8) or `quick` (N = 4), with a reason for each. The person adjusts |
| Cross-cuts | Schemes that span countries | Adds one agent per scheme family: regional or joint-degree programmes, donor/foundation/government awards open to the person's nationality, home-country funding (scholarships, loan funds). Notes where funding mainly comes through assistantships or employer sponsorship, which Path B finds rather than scholarship lists |
| Funded definition | The funding axis | Copies LP-G3 into `funded_definition`, sets `min_funding_score` for the stop rule, and decides the overlay policy |
| Overlay policy | Honest funding scores | Default: schemes with strings attached (return obligations, income tests, loans, employer bonds) are **overlays** shown next to the base score, never folded into it. Loans are debt, not funding |
| Admission models | Search method | Flags countries where admission is supervisor-first, research-only, portfolio-based or employer-sponsored, so that agents look for those routes |
| Wave plan | Usage windows | Assigns countries to waves using the unit rules in `engine/persistence.md` and gets the person's "go" (R8) |

## Outputs

- `03_scope/search_plan.json` (`schemas/search_plan.schema.json`). Essentials:
  - `countries[]` {slug, name, depth, cap_n, wave}
  - `crosscuts[]` {slug, name, kind: programme_scan | funding_route, description}
  - `funded_definition` {type, max_total_tuition, max_out_of_pocket, living_support_required_monthly, household_size, currency, min_funding_score}
  - `overlay_policy`
  - `exclusions[]` {country, reason}
  - `session_plan.waves[]`
- `03_scope/AGENT_BRIEF.md`: instantiate `protocol/templates/AGENT_BRIEF.md` from the Preamble and the plan. Paste the PM-G5 anchors into it verbatim: they are the single source of truth for scoring.

## Default agent budgets (tune after wave 1)

| Agent type | Searches | Page fetches | Path B share |
|---|---|---|---|
| Deep country | 60 | 80 | ≥ 30% |
| Standard country | 40 | 60 | ≥ 30% |
| Quick country | 15 | 20 | ≥ 30% |
| Follow-up / cross-cut | 25 | 40 | as the triggers require |

## Default scoring anchors (used when PM-G5 doesn't override them)

| Score | Funding | Programme | Pathway |
|---|---|---|---|
| 3 | Total cost within the funded definition, with **confirmed** support the person is eligible for (household size included) | Confirmed strong coverage of several *critical* domains plus *high* ones | A named person, partner or scheme in the exact target area, **with a confirmed route** for students of this programme (supervision, placement, internship, sponsored project) |
| 2 | Within the definition only with a very likely but unconfirmed route (e.g. a near-automatic merit award or guaranteed assistantship) | Strong on a coherent subset, with clear gaps | A relevant group or partner, but adjacent focus or an unconfirmed route |
| 1 | Within reach only through competitive or partial awards | Thin | Generic |
| 0 | Beyond the ceiling, with no route | None | None |
| ? | Insufficient evidence; never guess | | |

## Exit

The person approves the plan and the wave schedule. Update the state vector with `phase: scope → search`, and set `next.virgil` to "launch wave 1 on a fresh window".
