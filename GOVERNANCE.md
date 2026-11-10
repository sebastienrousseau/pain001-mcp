<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

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
  a maintainer in the PR, and should start as an issue.
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
3. Open an issue (or email the lead maintainer) expressing interest.

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

### Continuity plan

What happens to each piece of the project if the lead maintainer becomes
unavailable. Items marked **Not yet arranged** have no continuity
arrangement today; the plan is incomplete until they do.

| Asset | Today | Continuity |
| :--- | :--- | :--- |
| Signing keys | SSH keys listed in [`KEYS.asc`](KEYS.asc); commits and tags are signed with them | A new maintainer signs with their own key, added to `KEYS.asc` in a reviewed change; old releases stay verifiable because the file's history is kept. **Not yet arranged:** a documented key backup. |
| PyPI project `pain001-mcp` | Published by trusted publishing from `release.yml`; owned by the lead maintainer | Add a second PyPI owner. **Not yet arranged:** there is no second owner. |
| MCP Registry entry `io.github.sebastienrousseau/pain001-mcp` | Published by `publish-mcp.yml` with GitHub OIDC; the namespace is the lead maintainer's GitHub account | **Not yet arranged:** the namespace moves only with the repository's owner. |
| Container image `ghcr.io/sebastienrousseau/pain001-mcp` | Published by `docker.yml` under the lead maintainer's account | **Not yet arranged:** no second account can publish it. |
| GitHub repository | Owned by the lead maintainer's account | Transfer to an organisation or foundation with at least two owners, keeping redirects. **Not yet arranged:** no target account has been chosen. |
| Domain `pain001.com` (the security contact address) | Registered by the lead maintainer, served through Cloudflare | **Not yet arranged:** no one else is named to renew or transfer it. |
| Releases and CI | Documented in `RELEASING.md` and run by GitHub Actions | Anyone with release rights can cut a release from the documented process. |
| The code | Apache-2.0 OR MIT, public history | Anyone can fork and continue it, with or without the project. |

### Review policy

`main` requires a pull request and the required status checks, with
administrator enforcement on and zero required approving reviews: a
solo-maintainer setting, so a merge has no independent reviewer. Agents
need explicit authorization naming a particular pull request before
merging; green checks alone do not authorize a merge.

## Code of conduct & security

Participation is governed by
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Security issues follow the
private disclosure process in [`SECURITY.md`](SECURITY.md) - please do
not open public issues for vulnerabilities.
