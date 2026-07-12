# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.55] - 2026-07-12

The **MT→MX migration** cut. Adds a single new tool that bridges the
legacy SWIFT FIN world to ISO 20022 ahead of the November-2025+ MT/MX
coexistence cutover. 16 tools become 17; no other API changes.

### Added

- **`convert_mt101` tool.** Converts a legacy SWIFT **MT101** (*Request
  for Transfer*) message into pain.001-ready flat records — one record
  per sequence-B transaction, since an MT101 can request many transfers
  in a single message. The output feeds straight into `validate_records`
  / `validate_payment_scheme` and `generate_message` to emit
  `pain.001.001.09` XML. Compute-only (no file I/O); on a malformed or
  incomplete MT101 it returns `{"error": ...}` like the other tools.
  Wraps the newly published
  [`pain001-loader-mt101`](https://pypi.org/project/pain001-loader-mt101/)
  library (`parse_mt101`), added as a runtime dependency.

## [0.0.54] - 2026-07-02

The **discoverability** cut. Registers `pain001-mcp` with the official
Model Context Protocol Registry, adds MCP-spec conformance CI, and
positions the server as part of the ISO 20022 MCP Suite. No functional
or API changes — the same 16 tools, 1 resource, and 1 prompt as
v0.0.53.

### Added

- **Official MCP Registry integration.** `pain001-mcp` is now
  registered with the official Model Context Protocol Registry
  (`registry.modelcontextprotocol.io`) as
  `io.github.sebastienrousseau/pain001-mcp`. A new `server.json` at
  the repo root provides the registry metadata (PyPI package
  identifier, stdio transport), and the README carries an
  `mcp-name: io.github.sebastienrousseau/pain001-mcp` marker that the
  registry uses to verify PyPI package ownership. Discoverable in
  Claude Desktop's built-in "Add server" catalog once the registry
  entry is live.
- **Auto-publish workflow** (`.github/workflows/publish-mcp.yml`).
  Authenticates to the MCP Registry via GitHub OIDC (no secrets
  required) on every `v*.*.*` tag push, syncs the tag version into
  `server.json`, and runs `mcp-publisher publish`. Registry metadata
  now stays in lockstep with each PyPI release automatically.
- **Protocol conformance CI** (`.github/workflows/mcp-inspect.yml`).
  Runs `@modelcontextprotocol/inspector --cli` against `tools/list`,
  `resources/list`, and `prompts/list` on every push and PR. A green
  run is the spec-compliance evidence that enterprise buyers ask for.
- **Glama directory manifest** (`glama.json`). Moves the Glama listing
  from anonymous-crawl into the verified-owner tier so the
  description, tags, and install commands are author-controlled.
- **Suite discoverability.** The README now cross-links the sibling
  banking MCP servers under a "Related MCP Servers" section,
  positioning `pain001-mcp` as part of the ISO 20022 MCP Suite
  alongside `bankstatementparser-mcp`, `camt053-mcp`, `acmt001-mcp`,
  and `noyalib-mcp`.

### Changed

- GitHub repository description and topics refreshed: description now
  positions the server as part of the ISO 20022 MCP Suite; topics
  extended with `mcp-server`, `financial-services`, and `cbpr-plus`.

### No functional / API changes

- Same 16 MCP tools, 1 resource, and 1 prompt as v0.0.53. This release
  is metadata, CI, and discoverability only. Existing Claude Desktop /
  Cursor / Zed configurations continue to work unchanged.

## [0.0.53] - 2026-06-19

### Added

Three new MCP tools that surface previously-CLI-only capabilities of
the `pain001` v0.0.53 public API:

- `migrate_records` - migrate flat records between pain.001 schema
  versions (e.g. `pain.001.001.03` to `.09`). Wraps
  `pain001.migration.VersionMapper`; returns the migrated rows plus a
  `{from, to, migrated}` summary, or an `{error: ...}` payload for
  unsupported versions.
- `validate_xml_against_schema` - validate a raw pain.001 / pain.008
  XML string against its bundled XSD without writing it to disk.
  Wraps `pain001.xml.validate_via_xsd.validate_xml_string_via_xsd`.
- `sanitize_to_iso20022_charset` - transliterate accents and remove
  symbols outside the ISO 20022 Latin set. Wraps
  `pain001.sanitize_to_charset`; returns the cleaned string plus a
  `changed` flag so an agent can surface the diff to the user before
  writing it back.

Total MCP surface: **16 tools** (was 13 in v0.0.52), 1 resource, 1
prompt.

### Changed

- Pinned to `pain001 >= 0.0.53` so the new public-API symbols
  (`sanitize_to_charset`, `VersionMapper`, the SEPA B2B profile,
  Redis-backed stores) are available.

### Quality gates

- pytest: **54 tests**, 100% line + branch coverage (was 47, +7 new).
- interrogate: 100% docstring coverage.
- ruff + black + mypy all clean.

## [0.0.52] - 2026-06-18

### Added

- Initial release of `pain001-mcp`, a Model Context Protocol (MCP) server that
  exposes the [`pain001`](https://github.com/sebastienrousseau/pain001) ISO
  20022 Customer Credit Transfer Initiation library as tools for AI agents and
  assistants
- `pain001-mcp` console script that runs the FastMCP server over stdio
- Eleven MCP tools, all delegating to the `pain001` public API so they
  behave identically to the CLI and REST API:
  - `list_message_types` - list the supported `pain.001` / `pain.008` versions
  - `get_required_fields` - required input fields for a message type
  - `get_input_schema` - full input JSON Schema for a message type
  - `validate_records` - validate flat records against a message type
  - `validate_identifier` - validate an IBAN or BIC
  - `generate_message` - generate a validated `pain.001` XML message
  - `generate_message_async` - async variant for long batches (delegates
    to `pain001.async_adapter.generate_xml_string_async`)
  - `generate_message_from_file` - render directly from a CSV path on
    disk (path-validated by `pain001.security.validate_path`)
  - `list_supported_formats` - list the data formats `pain001` can load
    (CSV, SQLite, JSON, JSONL, Parquet)
  - `parse_camt053` - parse a `camt.053` bank statement XML into
    structured data
  - `parse_pain002` - parse a `pain.002` payment-status report XML into
    structured data
- **Multi-stage `Dockerfile`** - a `python:3.12-slim`-based image runs
  the server over stdio as a non-root `mcp` user, suitable for
  containerised MCP clients (`docker run -i --rm pain001-mcp`).
- **Quality workflows** - `ci.yml` enforces ruff, mypy, the 100% pytest
  coverage gate, the 100% docstring gate, and the example scripts on
  Python 3.10/3.11/3.12; `security.yml` runs bandit + pip-audit;
  `codeql.yml` runs GitHub's CodeQL Python analysis weekly.
- **Security policy** (`SECURITY.md`) describing the threat model,
  hardening (`validate_path` enforcement, defused XML parsing, no
  network listener, no secrets), and disclosure contact.
- `scripts/verify_versions.py` - pre-release script asserting
  `__version__`, `pyproject.toml`, and `CHANGELOG.md` agree.
- Graceful error handling: tools return an `{"error": ...}` payload on a
  `ValueError` (or a `pain001.exceptions` subclass thereof) rather than
  raising
- Python 3.10+ support; depends on `pain001` (>=0.0.52) and `mcp` (>=1.2)
- Runnable examples (`examples/01_mcp_tools.py`,
  `examples/02_validate_pipeline.py`, `examples/03_parse_bank_replies.py`)
  invoking the tools in-process, plus bundled `camt.053` / `pain.002`
  fixtures for offline reproducibility
- **Quality gates pinned at 100%** from the initial release:
  - `pytest --cov=pain001_mcp --cov-branch --cov-fail-under=100` (40 tests
    exercising every line and branch in `pain001_mcp/server.py`,
    including async tools, file-driven generation, path-traversal
    regressions on the bank-reply parsers, and an end-to-end stdio
    handshake driven by the official MCP `ClientSession`)
  - `interrogate --fail-under=100` for module and function docstring
    coverage
  - Every example script is also exercised by pytest so breakage is
    caught at the test-suite level
- Versioning aligned with `pain001` and `pain001-lsp`: the three packages
  in the suite ship under matching release numbers

[0.0.54]: https://github.com/sebastienrousseau/pain001-mcp/releases/tag/v0.0.54
[0.0.53]: https://github.com/sebastienrousseau/pain001-mcp/releases/tag/v0.0.53
[0.0.52]: https://github.com/sebastienrousseau/pain001-mcp/releases/tag/v0.0.52
