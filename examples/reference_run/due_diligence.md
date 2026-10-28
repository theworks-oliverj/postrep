# Search due diligence: run withheld (2026-10-27; protocol v1.0.0; rubrics LP-n/a / PM-n/a)
_Applicant alias: withheld. Computed from merged.json and verification.json; no figure is typed by hand. State-vector rubric: ref-2026-10._

## 1. Scope
- Applicant: withheld.
- 12 countries (Country A, Country B, Country C, Country D, Country E, Country F, Country G, Country H, Country I, Country J, Country K, Country L) + 2 cross-cut(s) (programme_scan: 1, funding_route: 1); protocol 1.0.0, mode cloud.
- 'Funded' means: stipend_and_tuition; minimum funding score 2. Exclusions: 1 region(s)/type(s) excluded, not listed.

| Benchmark axis | Programme | Vector F/P/W | Sum | Status |
|---|---|---|---|---|
| funding | funding benchmark, identity withheld | 3/1/2 | 6 | provisional |
| programme | programme benchmark, identity withheld | 2/3/1 | 6 | provisional |
| pathway | pathway benchmark, identity withheld | 1/2/3 | 6 | provisional |

## 2. Coverage funnel
353 institutions screened (385 raw rows before de-duplication) -> **194 pass**, 159 fail, 0 unscreened -> **314 programme-level entries** = 128 full records + 186 ranked-out (preliminary vector only).

| Country | Depth | Cap | Screened | Pass | Fail | Unscr. | Records | Ranked-out | Follow-up (or stop-rule reason) | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| Country A | deep | 12* | 96 | 23 | 73 | 0 | 12 | 14 | 1 file(s) done, 2 open trigger(s) | complete |
| Country B | deep | 12* | 43 | 15 | 28 | 0 | 12 | 8 | 0 file(s) done, 1 open trigger(s) | complete |
| Country C | deep | 12 | 38 | 34 | 4 | 0 | 11 | 22 | 2 file(s) done, 2 open trigger(s) | complete |
| Country D | deep | 12* | 30 | 29 | 1 | 0 | 12 | 21 | 1 file(s) done, 1 open trigger(s) | complete |
| Country E | deep | 12* | 27 | 24 | 3 | 0 | 12 | 19 | 1 file(s) done, 0 open trigger(s) | complete |
| Country F | standard | 8* | 16 | 11 | 5 | 0 | 9 | 12 | 1 file(s) done, 2 open trigger(s) | complete |
| Country G | standard | 8* | 16 | 11 | 5 | 0 | 9 | 18 | 1 file(s) done, 2 open trigger(s) | complete |
| Country H | standard | 8* | 14 | 9 | 5 | 0 | 10 | 22 | 1 file(s) done, 1 open trigger(s) | complete |
| Country I | standard | 8* | 14 | 10 | 4 | 0 | 9 | 12 | 1 file(s) done, 0 open trigger(s) | complete |
| Country J | standard | 8* | 14 | 7 | 7 | 0 | 8 | 10 | 0 file(s) done, 2 open trigger(s) | complete |
| Country K | standard | 8* | 11 | 4 | 7 | 0 | 8 | 13 | 0 file(s) done, 1 open trigger(s) | complete |
| Country L | standard | 8* | 8 | 8 | 0 | 0 | 8 | 5 | 0 file(s) done, 1 open trigger(s) | complete |
| Cross-cut A (programme_scan) | - | - | 26 | 9 | 17 | 0 | 8 | 10 | 0 file(s) done, 0 open trigger(s) | complete |

`*` = cap reached.

## 3. Novelty vs prior run
95 net-new, 33 updates of prior entries, 0 reconfirmed; 96 corrections to prior entries; 2 in-scope prior entries not revisited.
Vector changes of revisited entries (up/down/same): funding 11/4/11; programme 3/0/20; pathway 8/1/21.

## 4. Benchmark position
Benchmark sums [6, 6, 6] (no benchmark need be 3/3/3). Records with a sum >= the best benchmark sum (6): 14; strictly above it: 1; highest sum 7. Records scoring 3: funding 0, programme 0, pathway 19.

## 5. Evidence quality
- People/partner routes confirmed (takes_students): 13% of 293 named contacts; verification_needed 58.7% (a group or company existing is not the same as it taking students of this programme).
- Funding: applicant eligibility confirmed for 45.1% of 293 routes.
- Sources: 789 entries, 15.1% with no URL; 732 distinct URLs on 299 domain(s); official vs aggregator: not recorded in reference run; accessed_date: not recorded in reference run.
- Open questions per record: 3.2; 26 records have a '?' axis.

## 6. Independent verification
36 claims on 12 records (9.4% of records): **77.8% confirmed**, 8.3% wrong, 13.9% not found, 0% disputed. Fees and deadlines unreliable in 33.3% of cases. Sample = top-N only (NOT random): do not extrapolate to other records.

| Claim type | confirmed | wrong | not_found | disputed |
|---|---|---|---|---|
| deadline | 7 | 1 | 4 | 0 |
| fee | 9 | 2 | 1 | 0 |
| people_partner | 12 | 0 | 0 | 0 |

## 7. Known gaps
- 95 items logged as searched-but-not-surfaced or not searched.
- 1 agent file(s) hit a budget/limit (Country C); 0 institutions unscreened; path B not done in: none; 15 mention(s) of blocked/unreachable sites.

## 8. Time sensitivity (next 90 days)
Structured deadlines: not recorded in reference run (deadlines were free text).

## 9. Method caveats
- Rubric version(s): ref-2026-10 (x128); unweighted sum of the three axes (ties: pathway, then funding).
- 8 orchestrator override(s) on 8 record(s) (fields: state_vector.funding); original values kept in the merged file.
- '?' = missing data: skipped in _total (understates unscored records), never counted as 0.
- 0 exact duplicate(s) dropped, 7 near-duplicate pair(s) flagged for a human; 3 provisional benchmark(s).

**Effort**: about 25 agent runs, about 4 usage windows, sessions not recorded in reference run.
