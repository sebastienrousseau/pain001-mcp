<!-- SPDX-License-Identifier: Apache-2.0 -->

# pain001-mcp Governance

This document describes how pain001-mcp is run, how decisions are made,
and how to take on responsibility for it. It exists to make the project
legible and sustainable - and, candidly, to reduce its dependence on any
single person.

## Mission and scope

pain001-mcp is the Model Context Protocol surface for the
[`pain001`](https://github.com/sebastienrousseau/pain001) ISO 20022
library. It exposes generation, validation, identifier checking, and
bank-reply parsing as MCP tools / resources / prompts so AI agents and
assistants can drive payment file flows. Changes are weighed against that
scope: correctness, security, and clarity over feature breadth.

## Roles

| Role | Who | Can |
| :--- | :--- | :--- |
| **Maintainer** | Listed in [`MAINTAINERS.md`](MAINTAINERS.md) | Merge PRs, cut releases, triage, set direction |
| **Contributor** | Anyone with a merged PR | Propose changes, review, discuss |
| **User** | Everyone | File issues, ask questions, request features |

## Decision making

- **Day-to-day changes** (fixes, docs, tests, additive features within
  scope) proceed by **lazy consensus**: open a PR; if no maintainer
  objects and CI is green, a maintainer merges it.
- **Significant changes** (new public APIs, breaking changes, new
  dependencies, new tools/resources/prompts) need explicit approval from
  a maintainer in the PR, and should start as an issue or discussion.
- **Disagreement** is resolved by discussion aiming for consensus; if
  none is reached, the lead maintainer decides and records the rationale.

Every change must pass the full quality gate (100% line+branch coverage,
100% docstring coverage, mypy --strict, ruff, black, bandit, CodeQL)
before merge - enforced in CI, not by trust.

## Releases

Releases follow [`RELEASING.md`](RELEASING.md). pain001-mcp tracks
[`pain001`](https://github.com/sebastienrousseau/pain001) version-for-
version: when pain001 cuts `0.0.X`, pain001-mcp ships a matching
`0.0.X`. Only maintainers publish to PyPI; release authority rests with
the lead maintainer and is expanding to a second maintainer as a
standing goal.

## Becoming a maintainer

We actively want more maintainers - it is the single biggest thing that
would de-risk the project.

1. Contribute a few reviewed PRs in an area
   ([`ARCHITECTURE.md`](ARCHITECTURE.md) is the map; good first areas:
   new MCP tool wrappers over the `pain001` public API, examples).
2. Help triage issues and review others' PRs.
3. Open a discussion (or email the lead maintainer) expressing interest.

A maintainer proposes you; with no objection from existing maintainers
within a week, you are added to `MAINTAINERS.md` for your area.

## Sustainability (bus factor)

pain001-mcp today has **one** maintainer, which is a real risk for a
library used in payments. The mitigations in place:

- **The work is legible:** [`ARCHITECTURE.md`](ARCHITECTURE.md) maps the
  codebase, [`RELEASING.md`](RELEASING.md) documents the release process,
  and every public tool ships a runnable example.
- **Quality is enforced by CI,** not by one person's memory.
- **The goal is >= 2 maintainers** with independent release authority.

## Code of conduct & security

Participation is governed by
[`CODE-OF-CONDUCT.md`](CODE-OF-CONDUCT.md). Security issues follow the
private disclosure process in [`SECURITY.md`](SECURITY.md) - please do
not open public issues for vulnerabilities.
