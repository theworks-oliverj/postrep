# Virgil Protocol

[![CI](https://github.com/theworks-oliverj/postrep/actions/workflows/ci.yml/badge.svg)](https://github.com/theworks-oliverj/postrep/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
[![License: CC BY 4.0](https://img.shields.io/badge/docs-CC%20BY%204.0-lightgrey.svg)](LICENSE-docs)

An open, AI-guided protocol for finding and assessing postgraduate programmes (MSc, MA, MRes, MPhil, MBA, LLM, professional master's; any field) against **your own** life plan, money and goals. The evidence trail comes with it.

An AI interviewer, **Virgil**, gets to know you, plans the search, runs research agents country by country, saves everything to disk as it goes, and hands you two documents:

- **Options Rundown**: your live options, the decisions to make first, and what to do in the next 90 days.
- **Due-Diligence One-Pager**: how wide and deep the search went, and how much of it was independently verified.

[![How a Virgil run flows](docs/assets/flow.png)](docs/assets/flow.svg)

## Quick start

1. Open [`START_HERE.md`](START_HERE.md). It explains what to expect (Session 0) and how to load the protocol.
2. Use an AI client that can **search the web** and, ideally, **read and write files on disk**, such as the Claude desktop app with Cowork, Claude Code, or a similar agent harness.
3. Say **"Virgil, let's begin."**

Three ways to load it:
- **Clone** this repo into your working folder (best).
- **Thin:** attach `START_HERE.md`; Virgil fetches modules as needed.
- **Full bundle:** attach [`dist/VIRGIL_PROTOCOL_FULL.md`](dist/VIRGIL_PROTOCOL_FULL.md), one file with no fetching.

You don't need to write code. If your AI client can run code, it uses the scripts here for merging and reporting. If it can't, it applies the same rules by hand and tells you which numbers it counted.

## How it is built

| Layer | Where | Role |
|---|---|---|
| Entry | `START_HERE.md` | What to expect, setup, boot sequence, module index |
| Rules | `protocol/preamble.md` | Virgil's rules, written as *field purpose → behaviour*, not examples |
| Progress | `protocol/state_vector.md` | A continuation state vector that agents read and write; you see a short "where we are" brief |
| Sessions | `protocol/sessions/` | One module per session (S0-S9), loaded only when needed |
| Engine | `protocol/engine/` | Persistence and usage-limit partitioning, quality bar, data contract, scripts, lessons |
| Templates and prompts | `protocol/templates/`, `protocol/prompts/` | Life plan, map, agent brief, deliverables; resume, follow-up and verifier prompts |
| Graph | `protocol/index.json` | Modules as nodes (purpose, inputs, outputs, dependencies) for selective loading |
| Contract | `schemas/` | JSON Schemas (draft 2020-12) for every file a run writes |
| Tooling | `scripts/`, `tests/`, `tools/` | Standard-library Python: init, checkpoint, validate, merge, follow-ups, verification sample, shortlist, due diligence, rubric, status; bundle builder |
| Evidence | `examples/reference_run/` | Aggregate metrics from the real run the protocol was distilled from |

**Designed around usage limits.** Every interview answer and research record is written to disk the moment it exists. Search agents run in waves sized to your usage windows and resume from files after any limit. The reference run (12 countries, about 25 agent runs) needed about 4 usage windows for the search alone.

## Privacy

Virgil asks personal questions (money, family, nationality, degree year) because they decide which programmes and scholarships actually fit. All of them are optional.

- Your answers are processed by the AI service you use, and research agents receive a summary of your plan.
- Your files stay in your workspace.
- Web searches contain your topics, never your name or family details.
- Use an alias, and share your deliverables deliberately.
- **Never commit a personal run to a public repo.**

## Scripts (optional)

```bash
python3 scripts/init_workspace.py my_run --alias "Applicant" --mode local
python3 scripts/status.py my_run --brief
python3 tests/run_tests.py
```

Python 3.10+. `jsonschema` is used if it's installed; otherwise a built-in validator runs. The full CLI reference is in [`protocol/engine/scripts.md`](protocol/engine/scripts.md).

## Limitations

- **Not advice.** Admissions, funding and immigration facts change. Confirm on official pages before acting.
- Fees and deadlines are the least reliable claims. In the reference run's fact-check, about 1 in 3 was wrong or not found.
- A pathway score of 3 means a relevant person, partner or scheme exists. Whether it is open to *you* usually needs a direct question, which the rundown lists for you.
- Calibration (rubric thresholds, wave sizes) comes from **one** run. Contributions from more runs are the most valuable help.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md). Security or privacy issues: [`SECURITY.md`](SECURITY.md). To cite this work, see [`CITATION.cff`](CITATION.cff).

## License

Protocol text, templates and docs: [CC BY 4.0](LICENSE-docs). Code: [MIT](LICENSE).
