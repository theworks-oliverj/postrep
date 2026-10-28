# Contributing to the Virgil Protocol

Thank you for helping. This project is a protocol (Markdown modules), a data contract (JSON Schemas) and tooling (stdlib Python). Contributions to any of the three are welcome. By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to contribute

1. **Share a run report (most wanted).** Calibration of the rubric thresholds and wave sizes currently rests on one run. Open a *Run report* issue with an anonymised due-diligence one-pager (`scripts/due_diligence.py --no-examples`) and your observed agents per usage window.
2. **Propose a protocol improvement.** Open a *Protocol improvement* issue that names the module and session, says what happened in your run, and gives the evidence.
3. **Fix or extend the tooling.** Open a pull request (checklist below).
4. **Generalise.** Non-European credit systems, funding schemes, admission models (supervisor-first, portfolio-based, employer-sponsored) and non-research pathways (internships, placements, accreditation).

## Source of truth and structure

- `protocol/` holds the modules. `protocol/index.json` is the module graph. `START_HERE.md` is the thin entry point.
- `dist/VIRGIL_PROTOCOL_FULL.md` is **generated**, so never edit it by hand. Rebuild it with `python3 tools/build_bundle.py`.
- `schemas/` is the contract between modules, agents and scripts. If you change a field, update these in the same pull request:
  - the module text that names it;
  - `protocol/engine/data_contract.md` and `docs/appendix_a_examples.md`;
  - the fixtures and tests;
  - the CHANGELOG.
- **Writing style for modules:** rules are written as *field/purpose → behaviour* ("Field X tracks Y; Virgil should Z"). Avoid example-driven procedures, which overfit to one field of study. Put anecdotes in `protocol/engine/lessons.md`.

## Before opening a pull request

```bash
python3 tests/run_tests.py                         # both validators are exercised
python3 tools/test_build_bundle.py
python3 tools/build_bundle.py && python3 tools/build_bundle.py --check
```

- Add a line under `## [Unreleased]` in `CHANGELOG.md`.
- **Versioning (SemVer):** bump the protocol version in `START_HERE.md` and `protocol/index.json` on release. Bump `rubric_version` (LP-x.y / PM-x.y) whenever gates or weights change, so old scores remain interpretable.
- **No personal data:** never commit a personal run (`runs/` and `my_run*/` are git-ignored). Example data must be aggregate or synthetic.

## Commit style

Use short, imperative subject lines (e.g. "Add dependant_pathway to country context"). Reference issues where relevant.

## Releasing (maintainers)

1. Update the version in `START_HERE.md`, `protocol/index.json`, `CITATION.cff` and `CHANGELOG.md`.
2. Rebuild the bundle and run all checks.
3. Tag `vX.Y.Z` and create a GitHub release with the changelog excerpt.
