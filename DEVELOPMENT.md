<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# Development

The single entry point for working on `pain001-mcp`: how to set up the
toolchain, how to run every CI gate on your machine, where the tests
live, and how a release is made. [CONTRIBUTING.md](CONTRIBUTING.md)
covers the pull request workflow and [AGENTS.md](AGENTS.md) the
invariants that must not drift.

## Toolchain

- Python 3.11 or newer (CI tests 3.11, 3.12, 3.13 and 3.14).
- [Poetry](https://python-poetry.org/docs/#installation) for the
  development environment. CI installs from the hash-pinned files under
  `requirements/` with pip instead, so the two must agree:
  `poetry check --lock` is a CI job.
- Node.js 22 for `npx markdownlint-cli2` and the MCP Inspector.
- Git with SSH commit signing and `git commit -s` (DCO, checked by
  `dco.yml`).

```bash
git clone git@github.com:sebastienrousseau/pain001-mcp.git
cd pain001-mcp
poetry install --all-extras
make check
```

The dev container (`.devcontainer/devcontainer.json`) does the same
on Python 3.12 with Node, and finishes by running `make check`.

## Running every CI gate locally

`make check` is the gate to run before every push. It runs, in order:
`lint` (ruff, black), `type-check` (mypy), `complexity`, `test`
(pytest with the 100% line and branch coverage floor), `doc-coverage`
(interrogate at 100%) and `examples` (every `examples/[0-9]*.py`).

The other workflows, and how to reproduce each one:

| Workflow | Job | Local command |
| :--- | :--- | :--- |
| `ci.yml` | Lockfile | `poetry check --lock` |
| `ci.yml` | Test | `make test`, plus the three checks below |
| `ci.yml` | Version sources agree | `poetry run python scripts/verify_versions.py` |
| `ci.yml` | Tool catalogue is current | `poetry run python scripts/tool_catalogue.py --check` |
| `ci.yml` | Canonical README is current | `poetry run python scripts/render_readme.py --check` |
| `ci.yml` | Benchmarks and scaling guards | `poetry run pytest tests/test_benchmarks.py --no-cov` |
| `ci.yml` | Lint and type check, complexity | `make lint type-check complexity` |
| `ci.yml` | Examples | `make examples` |
| `pr.yml` | PR gate (lint, types, coverage, docstrings) | `make lint type-check test doc-coverage` |
| `docs-lint.yml` | codespell | `pip install --require-hashes -r requirements/docs-lint.txt && codespell` |
| `docs-lint.yml` | markdownlint | `npx markdownlint-cli2@0.23.3 "**/*.md"` |
| `docs.yml` | Build (warnings are errors) and link check | `make docs` and `make docs-linkcheck` (see below) |
| `security.yml` | bandit, pip-audit | `make security`; pip-audit is in `requirements/ci.txt`, not the Poetry environment: `pipx run pip-audit` |
| `mcp-inspect.yml` | Protocol conformance | `npx @modelcontextprotocol/inspector@2.10.1 --cli pain001-mcp --method tools/list` |
| `fuzz.yml` | Atheris | `pip install --require-hashes -r requirements/fuzz.txt && python fuzz/fuzz_tools.py -max_total_time=60` |
| `mutation.yml` | Mutation floor | `make mutate` |
| `codeql.yml`, `scorecard.yml` | Static analysis, supply chain | GitHub only |
| `dco.yml` | Sign-off on every commit | `git log --format=%B origin/main..` shows a `Signed-off-by:` per commit |

The Sphinx toolchain is not in the Poetry environment, because the docs
build pins its own hash-checked set. Build the manual in a separate
virtual environment:

```bash
python -m venv .docs-venv
.docs-venv/bin/pip install --require-hashes -r requirements/docs.txt
.docs-venv/bin/pip install --no-deps -e .
make docs SPHINXBUILD=.docs-venv/bin/sphinx-build
```

## Test layout

- `tests/` holds every test; `pytest` discovers them with the options in
  `pyproject.toml`. Coverage is measured on `pain001_mcp/` only, at a
  100% line and branch floor.
- `test_mcp_server.py` covers the bulk of the tools; some families have
  their own file (`test_corpus_tools.py`, `test_faces_tools.py`,
  `test_commit_confinement.py`, `test_dual_control_simulation.py`).
  Cross-cutting suites: `test_stdio_e2e.py` drives a real stdio
  subprocess with the MCP client, `test_transports.py` the HTTP and SSE
  transports, `test_tool_result_shapes.py` and
  `test_structured_output.py` the wire contract.
- `test_readme_snippets.py` runs the README Quick Start commands, and
  `test_mcp_server.py` imports and runs every numbered example.
- `test_benchmarks.py` holds pytest-benchmark timings and scaling
  guards; they compare a tool against itself, so they do not depend on
  runner speed.
- `test_suite_conformance.py` is vendored, byte-identical, from the
  suite and checksummed. Change it upstream, never here.
- `tests/fixtures/` holds byte-exact parser inputs (a camt.053 statement
  and a pain.002 report). They are excluded from formatting and spelling
  checks.

A bug fix comes with a test that failed before the fix.

## Documentation

- `docs/` is the only documentation root. Root files
  (`ARCHITECTURE.md`, `ROADMAP.md`, `CHANGELOG.md`, the README) are
  included into the manual, not copied.
- `README.md` is rendered from `docs/readme-template.md` and
  `docs/readme-values.json`: edit the values, then run
  `poetry run python scripts/render_readme.py`; `--check` fails on
  drift.
- `docs/tools.md` is generated by `scripts/tool_catalogue.py` from the
  registered tools.

## Release model

Versions stay on `0.0.x` and move one step at a time, in lockstep with
the core [`pain001`](https://github.com/sebastienrousseau/pain001)
library. The maintainer opens each release on a `feat/v<next-version>`
branch; all work for that version, including Dependabot updates, lands
there and reaches `main` through one pull request.
[RELEASING.md](RELEASING.md) lists every file that carries the version
and the tag-triggered publish pipeline. Never rewrite published
history.
