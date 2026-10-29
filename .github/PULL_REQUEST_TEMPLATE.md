## What and why

<!-- Briefly describe the change and the reason for it. -->

## Checklist

- [ ] Tests pass: `python3 tests/run_tests.py` (and with `VIRGIL_BUILTIN_VALIDATOR=1`)
- [ ] `python3 tools/build_bundle.py --check` passes (rebuild with `python3 tools/build_bundle.py` if protocol files changed)
- [ ] If fields changed: schemas in `schemas/` and `docs/appendix_a_examples.md` are updated
- [ ] `CHANGELOG.md` is updated under `[Unreleased]`
- [ ] No personal data (names, employer, nationality, contact details, real life-plan text) anywhere in the change
