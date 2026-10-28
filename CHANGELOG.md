# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-10-27

### Added

- Protocol modules under `protocol/`, a thin entry point (`START_HERE.md`) and a bundled single-file version (`dist/VIRGIL_PROTOCOL_FULL.md`) for chats that cannot fetch from GitHub.
- Virgil, the AI interviewer and orchestrator persona that guides the whole run.
- Life and Career Plan gate and Study and Pathway Map gate, each with a scoring rubric, that must pass before any search starts.
- Continuation state vector and `run_state.json`, so a run can resume after any usage limit.
- Per-country research agent waves with usage-window partitioning, using programme-first and people/partner-first search paths.
- JSON schemas for run state and records.
- Standard-library Python scripts for merging, scoring and reporting.
- Tests for the scripts and schemas.
- Anonymised reference-run metrics.
- Flow diagram of the journey (`docs/assets/flow.svg` and `flow.png`).
- Repository standards: code of conduct, security policy, citation metadata, issue and pull request templates, and CI.

[Unreleased]: https://github.com/theworks-oliverj/postrep/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/theworks-oliverj/postrep/releases/tag/v1.0.0
