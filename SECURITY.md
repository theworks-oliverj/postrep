# Security policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.x     | Yes       |
| < 1.0   | No        |

## Scope

In scope:

- **Scripts** (`scripts/`, `tools/`): anything that could execute unintended code, read or write files outside the run directory, or mishandle untrusted input (for example a crafted JSON file from an agent or a downloaded run).
- **Schemas** (`schemas/`): flaws that let malformed or hostile data pass validation in a way the scripts then mishandle.
- **Privacy of personal data in runs**: a Virgil run contains a life plan, finances, nationality and similar details. Report anything in the protocol, scripts or examples that could leak, persist or publish that data unintentionally (for example a default that writes personal data into a shareable file).

Out of scope: the accuracy of programme, funding or admissions information that agents find during a run (report those as ordinary issues, and always verify with the institution), and the behaviour of third-party AI products.

## How to report

Please use GitHub **private vulnerability reporting**: open the repository's **Security** tab, choose **Report a vulnerability**, and describe the problem. Do not open a public issue for a security problem.

Please include the affected file or module, steps to reproduce, and the impact you expect. Do not include real personal data in your report; use synthetic data.

You can expect an acknowledgement within a few days. Fixes are released as a patch version and noted in `CHANGELOG.md`.
