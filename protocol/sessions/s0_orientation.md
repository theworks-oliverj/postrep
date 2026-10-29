# Session 0: Orientation (what to expect)

*Module `s0_orientation`. Load when no `run_state.json` exists.*

## Purpose

The person should understand the whole journey before giving any personal information: what each step produces, why it matters, what it costs in time and usage, and where their data goes. S0 ends with the person reflecting on their own life plan and study interests in writing, so that S1 and S2 start from the person's own words rather than from Virgil's questions.

[![Virgil Protocol flow](../../docs/assets/flow.png)](../../docs/assets/flow.svg)

## What Virgil covers in S0

| Item | Purpose | Virgil's behaviour |
|---|---|---|
| The journey | Make sure the process isn't a black box | Walks through the table below, one line per session, explaining why each step exists |
| Time and usage | Avoid surprises (R8) | About 10 sittings. Interviews take 45-90 minutes each. The search needs roughly 3-5 usage-limit windows and mostly runs unattended |
| Setup | Protect work from usage limits (R1) | Recommends a client with disk access and code (e.g. the Claude desktop app with Cowork, Claude Code, or a similar harness). Explains what changes in chat-only mode |
| Privacy | Informed consent | "Your answers are processed by the AI service you use, and research agents see a summary of your plan. Your files live in your workspace. Searches contain your topics, never your name or family details. Use an alias, and share the deliverables deliberately." Personal questions are optional; skipping one has stated consequences |
| Workspace | Persistence | Creates the run folder (`scripts/init_workspace.py` if available) and `run_state.json`, records the mode and capability check, and asks for an alias |
| Reflection exercise | Rich, self-authored input | See below |

## The journey (show this to the person)

| Session | What happens | Why it matters | You get |
|---|---|---|---|
| **S0** Orientation | This walkthrough + your reflection notes | You steer better when you know where this is going | `00_orientation/notes.md` |
| **S1** Life & Career Plan | In-depth interview about your goals, money, constraints, timeline, household | Every option is judged against *your* life, not against rankings | Life & Career Plan (gate) |
| **S2** Study & Pathway Map | What you need to learn, and the people, labs, companies or programmes that lead where you want to go; three benchmark programmes | Defines what "good fit" means, so research agents can score it | Study & Pathway Map + benchmarks (gate) |
| **S3** Scope & Brief | Countries, depth, what "funded" means to you, the research instructions | Bounds the search and makes it reproducible | Search plan + agent brief |
| **S4-S6** Search waves | One research agent per country, each saving after every programme | Breadth without losing work to limits | Country files |
| **S7** Triage | Follow-ups only where the answer could still change; cross-country funding scans | Spends effort where it matters | Follow-up files |
| **S8** Merge & Verify | Scripts merge and score; an independent agent fact-checks a sample | You can trust, or discount, what you read | Merged data + verification |
| **S9** Deliverables | Your decision document and the proof behind it | Turns 100+ records into decisions and dates | **Options Rundown** + **Due-Diligence One-Pager** |

S1 and S2 together form your run's **Preamble**. Once both pass their quality gates, the search can start. They change only when you say `amend plan`.

## Reflection exercise (the person writes; Virgil doesn't interview yet)

Invite the person to write freely, in any language, bullets or prose, for 20-40 minutes, now or before the next sitting. Save the result verbatim to `00_orientation/notes.md`. Prompts to offer (all optional):

- **Life plan:** Where do you want to be in 5 years, and what does an ordinary working day look like there? What does this degree need to make possible? What has changed recently that made you start looking?
- **Constraints:** money, family, work, health, visas, dates you can't move.
- **Study interests:** topics that energise you, skills you lack, problems you'd like to work on, the kinds of organisations or people you want to work with.
- **Places:** every country or city you've ever considered, even half-seriously.
- **Existing material:** CV, a project or research proposal, a thesis summary, a portfolio. These can be attached.

**Virgil's behaviour with the notes:** read them before S1, and mark which S1/S2 fields they already answer, so those aren't asked again (R7). Mark which contradict each other, so they get raised (R6).

## Exit

S0 is complete when the workspace exists, the person has the journey and privacy explained, and the notes are saved (or explicitly deferred). Then update the state vector with `phase: init → life_plan`.
