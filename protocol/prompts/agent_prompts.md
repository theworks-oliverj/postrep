# Prompts: resume and hand-off

*Module `agent_prompts`. Copy these prompts verbatim; fill in the `<placeholders>`.*

**P1: Resume a run** (paste into a new chat together with START_HERE.md or the bundle)
```
Virgil, resume run <run_id>. The workspace is <path | attached files>. Load protocol/preamble.md and
protocol/state_vector.md, then read run_state.json. Resolve the AMBIGUITIES, print the "Where we are" brief,
and continue from next.virgil[0]. Do not redo completed records.
```

**P2: Resume an interrupted country agent**
```
Resume country <slug> for run <run_id>. Read 03_scope/AGENT_BRIEF.md and 04_search/countries/<slug>.json.
Keep every existing record. Continue from the first incomplete step (screening, Path B, preliminary vectors,
top N, ranked_out, context). Append each new record as you go. Set the final status honestly.
```

**P3: Follow-up agent**
```
Follow-up for <slug> (run <run_id>). Triggers: <from 04_search/followup_plan.json>. Read the country file and
03_scope/AGENT_BRIEF.md. Work ONLY on these triggers. Write 04_search/followups/<slug>_followup.json (same
schema), skeleton first. Write full records for promoted entries; mark replacements with "replaces": "<id>".
```

**P4: Independent verifier**
```
You have not seen this research. For each item in 06_verify/verification_sample.json, check the claim on an
OFFICIAL page for the current cycle. Write 06_verify/verification.json as you go. Do not fix records; only
give verdicts (confirmed | wrong | not_found | disputed) with evidence URLs.
```

**P5: Benchmark scout (S2)**
```
Read 01_life_plan/life_plan.json and the draft 02_map/study_pathway_map.json. Find at most 10 master's
programmes the person is eligible for, using Path A (programme-first) and Path B (people/partner-first).
Propose ONE provisional benchmark per axis (funding, programme, pathway). Verify each on official pages, give
it a baseline vector, and add one line on why it is the "3". Write 02_map/benchmarks.json (status: provisional).
Reply in under 200 words.
```

**P6: Connectedness check (optional, S2)**
```
Read 02_map/study_pathway_map.json. Build a topic network. Nodes: the objective, the domains and the pathway
signals. Edges: relationships supported by evidence (one source per edge; mark unsupported edges "assumed").
Report the 3 weakest links between the objective and the rest, and what would strengthen each.
Write 02_map/connectedness.md. Stay under 40 tool calls.
```
