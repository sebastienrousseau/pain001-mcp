<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

<p align="center">
  <img src="https://cloudcdn.pro/pain001/v1/logos/pain001.svg" alt="pain001-mcp logo" width="128" />
</p>

<h1 align="center">pain001-mcp</h1>

<p align="center">
  Expose pain001 validation, generation and inspection as MCP tools.
</p>

<p align="center">
  <a href="https://github.com/sebastienrousseau/pain001-mcp/actions"><img src="https://github.com/sebastienrousseau/pain001-mcp/workflows/ci/badge.svg?style=for-the-badge&logo=github" alt="Build" /></a>
  <a href="https://pypi.org/project/pain001-mcp/"><img src="https://img.shields.io/pypi/v/pain001-mcp?style=for-the-badge&color=fc8d62&logo=python" alt="Registry" /></a>
  <a href="docs/index.md"><img src="https://img.shields.io/badge/docs-source?style=for-the-badge&labelColor=555555&logo=readthedocs" alt="Docs" /></a>
  <a href="https://scorecard.dev/viewer/?uri=github.com/sebastienrousseau/pain001-mcp"><img src="https://img.shields.io/ossf-scorecard/github.com/sebastienrousseau/pain001-mcp?style=for-the-badge&label=OpenSSF%20Scorecard&logo=openssf" alt="OpenSSF Scorecard" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0%20OR%20MIT-blue.svg?style=for-the-badge" alt="License: Apache-2.0 OR MIT" /></a>
  <a href="https://github.com/sebastienrousseau/pain001-mcp/blob/main/docs/POLICIES.md"><img src="https://img.shields.io/badge/Python-3.10%2B-93450a.svg?style=for-the-badge&logo=python" alt="Python 3.10 or newer" /></a>
</p>

---

## Contents

**Getting started**

- [Install](#install) — PyPI and source
- [Requirements](#requirements) — toolchain floor, platforms
- [Quick Start](#quick-start) — use the installed companion

**The pain001-mcp ecosystem**

- [The pain001-mcp ecosystem](#the-pain001-mcp-ecosystem) — core and this companion

**Library reference**

- [Capabilities at a glance](#capabilities-at-a-glance) — the current surface by theme
- [Ecosystem comparison](#ecosystem-comparison) — short matrix; full table at [`docs/COMPARISON.md`](docs/COMPARISON.md)
- [Benchmarks](#benchmarks) — headline numbers; full table at [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md)
- [Features](#features) — module-level capability list
- [Configuration](#configuration) — core options
- [Examples](#examples) — runnable example index

**Operational**

- [When not to use pain001-mcp](#when-not-to-use-pain001-mcp) — limitations
- [Development](#development) — make targets, fuzzing, CI
- [Security](#security) — guarantees and compliance
- [Documentation](#documentation) — all reference docs
- [Stability guarantees](#stability-guarantees) — SemVer axis, output stability, minimum toolchain discipline
- [License](#license)

---

## Install

### As a Python library

```bash
python -m pip install pain001-mcp
```

Published packages and development branches are distinct. Test unreleased
changes on this companion's `feat/v0.0.71` branch against the matching core
branch. No PyPI release or version bump is part of this work.

---

## Requirements

Python 3.10 or newer. CI tests 3.10–3.14 on Linux. See
[toolchain policy](docs/POLICIES.md); no distro-system-Python claim is made.

---

## Quick Start

```bash
pain001-mcp --help
pain001-mcp
```

The second command starts the stdio MCP server and waits for a client.
Configure your client to launch `pain001-mcp`. Use generated help for optional
HTTP/SSE transports; secure network access before exposing any listener.

---

## The pain001-mcp ecosystem

This independently installed companion delegates payment behavior to core.
Coordinated versioning does not imply branch changes have been released.

| Component | Purpose | Use case |
| :--- | :--- | :--- |
| [pain001](https://github.com/sebastienrousseau/pain001) | Generation and validation | Shared contracts and XML engine |

---

## Capabilities at a glance

| Area | Capability | Status |
| :--- | :--- | :--- |
| Integration | Payment validation and generation tools | Test-gated; new branch work is unreleased |

---

## Ecosystem comparison

This matrix describes the repository's scope, not an independently benchmarked
comparison with competitors.

| Project | Generate payment XML | Real settlement | Synthetic bank replies |
| :--- | :---: | :---: | :---: |
| **pain001-mcp** | Delegates to core | No | Not a bank service |

See [`docs/COMPARISON.md`](docs/COMPARISON.md) for the evidence and complete matrix.

---

## Benchmarks

CI smoke-runs benchmarks. No hardware-independent throughput or latency promise
is made; use the generated run report for measurements.

| Scenario | Result | Environment |
| :--- | ---: | :--- |
| Adapter operations | Run-specific | Python, hardware and dependency versions recorded per run |

See [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md) for methodology and full results.

---

## Features

The authoritative [tool catalogue](docs/tools.md) is generated from the server.
It covers validation, identifiers, generation, migration, bank-report parsing,
corpus access and the unreleased `suggest_record_fix` tool. Suggestions require
review; financial fields are refused, never guessed. Test unreleased tools with
the matching core feature branch. In-tree core MCP is a separate smaller surface.

---

## Configuration

Run `pain001-mcp --help` for transport, host and port options. Stdio is default.
See the [tool catalogue](docs/tools.md) for request shapes rather than a copied
tool count.

---

## Examples

Run the self-checking scripts under [examples/](https://github.com/sebastienrousseau/pain001-mcp/tree/main/examples). Tests cover valid
and malformed inputs and integration with the core contract.

---

## When not to use pain001-mcp

Not a bank, settlement engine or autonomous payment approver. Review outputs
before use. Transport support is not bank certification.

---

## Development

```bash
poetry install
poetry run make check
poetry run make security
poetry run python scripts/tool_catalogue.py --check
poetry run python scripts/render_readme.py --check
```

Coverage is gated at 100% line and branch. See [CONTRIBUTING.md](CONTRIBUTING.md)
and [DEVELOPMENT.md](DEVELOPMENT.md). README is generated from the canonical
layout and `docs/readme-values.json`; CI rejects drift.

---

## Security

Treat requests as untrusted. Protect HTTP listeners and avoid real secrets in
logs. Tools may read authorized input paths. Corrections never patch IBANs,
BICs, amounts or currencies.

Report vulnerabilities according to [`SECURITY.md`](SECURITY.md).

---

## Documentation

[User manual](docs/index.md) · [API reference](docs/index.md) ·
[Developer guide](DEVELOPMENT.md) ·
[Family map](https://github.com/sebastienrousseau/pain001#the-pain001-ecosystem)

---

## Stability guarantees

Versions advance in coordinated `0.0.1` steps with core. The maintainer opens
releases; this branch does not bump versions. Contract and output changes need
compatibility review. No stronger platform or stability guarantee is implied.

---

## License

Dual-licensed under [Apache-2.0](LICENSE-APACHE) OR [MIT](LICENSE-MIT), at your
option. See [LICENSE](LICENSE). Dependencies retain their own licences.
