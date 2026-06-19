<!-- SPDX-License-Identifier: Apache-2.0 -->

# Releasing pain001-mcp

This document defines **what merits a release** and **how to cut one**,
so versions are deliberate rather than ad-hoc.

## Versioning scheme

pain001-mcp tracks
[`pain001`](https://github.com/sebastienrousseau/pain001) version-for-
version: when pain001 ships `0.0.X`, pain001-mcp ships a matching
`0.0.X`. This keeps the agent surface aligned with the core library's
public API and lets a user install both at compatible versions with a
single pin. Out-of-band patch releases (e.g. `0.0.X.post1`) are reserved
for MCP-only bug fixes that don't require a pain001 bump.

## What merits a release

Cut a new version when there is user-visible change to ship - bug fixes,
security or dependency patches, new tools / resources / prompts, or
documentation that ships in the package.

Do **not** cut a release that contains only a version-number bump with
no functional, security, or documentation change.

## Pre-flight checklist

A release is ready only when **all** of the following hold on `main`:

1. `make check` is green (lint + 100% coverage + interrogate + examples).
2. `mypy --strict`, `ruff`, `black` are clean.
3. Every Dependabot / CodeQL / bandit / pip-audit alert is resolved or
   has a documented, expiring suppression.
4. `CHANGELOG.md` has a dated section for the new version describing the
   change set (this is the single source of truth for the release).
5. The version is identical in `pyproject.toml` and
   `pain001_mcp/__init__.py` (enforced by `scripts/verify_versions.py`).

## Cutting the release

1. Bump the version in `pyproject.toml` and `pain001_mcp/__init__.py`
   and add the `CHANGELOG.md` section in a single PR.
2. Merge the PR to `main` once CI is green.
3. Push a signed tag:

   ```bash
   git tag -s vX.Y.Z -m "pain001-mcp vX.Y.Z" <merge-commit>
   git push origin vX.Y.Z
   ```

4. The tag triggers the `publish` job in `release.yml`, which fails fast
   if the tag does not match the package version, then builds, runs
   `twine check`, creates the GitHub release from the `CHANGELOG.md`
   section, and publishes to PyPI via OIDC trusted publishing.

## After releasing

- Confirm the version is live on
  [PyPI](https://pypi.org/project/pain001-mcp/) and the GitHub release is
  published (not draft).
- Verify a clean install: `pip install pain001-mcp==X.Y.Z`.
- The `docker.yml` workflow publishes a matching multi-arch image to
  `ghcr.io/sebastienrousseau/pain001-mcp:X.Y.Z` (and refreshes
  `:latest` when the release lands on `main`). The workflow smoke-tests
  the pulled image by running the `pain001_mcp` import check, so a
  green run means the image actually launches.

## Optional CI integrations

These are deliberately gated so an empty / un-set secret skips the
step rather than failing the build:

- **Codecov upload** (`pr.yml`): set the `CODECOV_TOKEN` repository
  secret and the PR Gate will start publishing branch coverage to
  [codecov.io](https://about.codecov.io). Without the secret the
  step skips silently; the 100% coverage gate is still enforced
  in-CI by pytest's `--cov-fail-under=100`.
- **PyPI trusted publisher** (`release.yml`): configured at
  <https://pypi.org/manage/account/publishing/>. The publisher claim
  set is `repo:sebastienrousseau/pain001-mcp:environment:pypi` with
  `workflow_ref` pointing at `.github/workflows/release.yml`. A
  Pending Publisher is auto-converted to a permanent Trusted
  Publisher on the first successful publish.
- **GHCR multi-arch image** (`docker.yml`): published with the
  default `GITHUB_TOKEN`; no extra setup needed. To consume the
  image: `docker run -i --rm ghcr.io/sebastienrousseau/pain001-mcp:X.Y.Z`.
