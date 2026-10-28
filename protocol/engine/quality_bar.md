# Engine: quality bar

*Module `quality_bar`. Load with any research or verification work. Each rule states the claim type it governs and the required behaviour.*

| Claim type | Behaviour |
|---|---|
| Any fact about a programme, person, partner, fee, award or deadline | Cite a URL actually opened, plus `source_type` and `accessed_date`. Otherwise label it `inferred`, `verification_needed` or `unknown`. Never invent a URL, person, programme or partner. |
| Fees and deadlines (perishable) | Use the current cycle's official page. Mark dates as `confirmed` or `pattern`. Re-verify inside 60 days. |
| Curriculum coverage | Grade from named modules in an official curriculum. A missing module name means "inferred absent", not "confirmed absent". |
| Language of instruction | Use the official regulations or admissions page, never the language of the webpage. Record the three-way split. |
| People and partners | "Exists at the institution" is not "available to this programme's students". Record `takes_students` evidence separately. |
| Conditional funding (return obligations, income tests, loans, bonds) | Put it in `overlays`, never in the base funding score. |
| Scheme terms read from long documents | Quote the clause and page. An agent's summary is not primary evidence. |
| Scores without evidence | Use "?". Never guess. |
| Counts and tables in deliverables | Compute them from data. Never type them by hand. |
| File status | Report it honestly. Never write `complete` while gaps remain. |
| Interdisciplinary goals | Don't require any single programme to cover every domain. |
| Discovery | Filter once, at the end. Never skip the pathway axis because the curriculum looks weak. |
