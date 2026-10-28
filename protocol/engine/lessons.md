# Engine: lessons from the reference run

*Module `lessons`. Not loaded during runs. It's for maintainers and curious readers: it explains why the rules exist. The reference run (Oct 2026) covered 12 countries and 2 cross-cuts, with about 25 agent runs. Specifics are anonymised.*

| # | What went wrong or was missing | Discovered by | Rule it produced |
|---|---|---|---|
| 1 | No written life plan; constraints were scattered; eligibility facts were unknown until mid-search | Open questions piling up | S1 interview + rubric with hard gates |
| 2 | A country the applicant cared about was never searched | The applicant asked | Exhaustive considered-list; explicit status per country |
| 3 | A single long agent ran out of context and lost countries | Missing records | One agent per country; write per record |
| 4 | 12 parallel agents vs the usage limit: 5 finished in window 1 | Interrupted files | Fresh-window waves, unit caps, measure and adapt |
| 5 | Path B was the first thing skipped when budgets ran out | Follow-ups found missed people | Path B gets its own budget share; `path_b_done` flag |
| 6 | Strong programmes found after the cap; a first-pass "fail" was wrong | Orchestrator triage | Preliminary vectors for all passes; `promote` flags; false-negative trigger |
| 7 | Free-text enums drifted and broke aggregation | Merge | Fixed enums; schema validation on write |
| 8 | Corrections lived in code and chat | Script review | `overrides.json` as dated records |
| 9 | The merge dropped follow-up extras | Script review | The merge keeps extras |
| 10 | Hand-typed summary counts were wrong | Consistency pass | Every count computed |
| 11 | Fees and deadlines wrong about 1 in 3; last year's dates shown as this year's | Independent fact-check | Perishable-claim rules; `confirmed`/`pattern` dates |
| 12 | A verifier's flag was itself wrong | Primary-source check | The verifier flags; the orchestrator adjudicates |
| 13 | A scheme obligation was summarised as "confirmed" when the call text defined none | Reading the call text | Quote clause and page |
| 14 | Cross-country schemes didn't fit per-country files | Merge | Cross-cut record type |
| 15 | The verification sample was top-ranked records only | Due-diligence review | Top-N + random sample |
| 16 | "Best fit" mostly rested on unconfirmed supervision (13% confirmed) | Metrics | `contact_actions`; caveat in D7 |
| 17 | Follow-up budget went to countries whose outcome couldn't change | Orchestrator judgement | Stop rule |
| 18 | "Zero tuition" vs "affordable" was left open | Final comparison | LP-G3 requires numbers |
| 19 | The protocol's first draft assumed one field (science, thesis-led) | Independent dry run with a different persona | Pathway axis; practical-component field; field-purpose rules instead of examples |
