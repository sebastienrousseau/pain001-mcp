<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- The release build tooling (`requirements/build.txt`) floors
  `filelock >= 4.2.1` (GHSA-9vhv-jxww-xfm5, GHSA-567q-5qvw-pf92,
  GHSA-v4x8-3wr5-3wq8; it pinned 4.0.10) and `virtualenv >= 21.14.13`
  (GHSA-cx6f-vjhg-g3cc; it pinned 21.14.11). filelock 4.2.1 needs
  Python 3.11, so the tree is compiled for 3.12, the Python of every job
  that installs it.
- The CI tree (`requirements/ci.txt`) pinned filelock 4.1.0 on Python
  3.10, for which no fixed filelock exists. With the 3.11 floor (below)
  pip-audit, which pulls it in, installs on every supported Python with
  `filelock >= 4.2.1`.
- The same tree floors `dulwich >= 1.2.19` (it pinned 1.2.17), in place
  of Dependabot #130, whose recompile dropped the platform markers.
- The release SBOMs (CycloneDX and the pip-licenses manifest) describe
  the locked runtime environment. The SBOM tools are installed outside
  Poetry's venv, so `poetry run` pointed them at their own interpreter
  and the SBOM listed the tooling, not the runtime set; both now take
  the venv's interpreter explicitly.
- The MCP Inspector conformance job pins `@modelcontextprotocol/inspector`
  to 2.10.1, so a new npm publish cannot change what CI runs.

### Removed

- Python 3.10 support. The floor is 3.11 (`python = ">=3.11,<4.0"`),
  the pain001 suite's decision for 0.0.75: 3.10 reaches end of life in
  October 2026, and current hypothesis releases need 3.11, which broke
  Dependabot's resolver for siblings on a 3.10 floor. CI tests 3.11 to
  3.14; ruff, black and mypy target 3.11; the `tomli` backport and the
  3.10 branch in `scripts/check_suite_consistency.py` are gone, and
  `poetry.lock` and the 3.11 requirement sets are re-locked (only the
  packages for 3.10 leave). pip keeps 3.10 users on pain001-mcp 0.0.74.

## [0.0.74] - 2026-10-20

Hygiene release: every advised dependency floored in the manifest,
every CI and container install pinned, a complexity gate, and Atheris
fuzzing of the text-taking tools.

### Security

- Constrain the advised runtime dependencies so no affected release can
  resolve: `mcp >= 1.30.0, != 2.0.*, != 2.1.*` (GHSA-84m7-p3x7-pcfv,
  streamable HTTP), `httpx2 >= 2.12.0`, `httpcore2 >= 2.10.0`,
  `pyjwt[crypto] >= 2.15.0`, `cryptography >= 50.0.0` and
  `opentelemetry-api >= 1.45.1` (GHSA-xcq7-p3pf-p88h). The earlier
  fixes (#107-#109) only moved `poetry.lock`.
- Floor `certifi >= 2026.10.19` in the release build tooling
  (`requirements/build.in`, PYSEC-2026-4320); `build.txt` had resolved
  2026.7.22.
- Pin every `pip install` in the workflows and the Dockerfile by hash
  (`requirements/{runtime,ci,docs,fuzz}.txt`, installed through
  `scripts/ci-install.sh`) and the `python:3.14-slim` base image by
  digest (OpenSSF Scorecard Pinned-Dependencies).

### Added

- Atheris fuzzing of the text-taking tools (`fuzz/fuzz_tools.py`,
  `fuzz.yml`), with a seeded run of the same harness in the test suite.
- A complexity gate (`scripts/check_complexity.py`, complexipy) against
  committed baselines that may only shrink; `make complexity`.

### Changed

- Require `pain001 >= 0.0.74, < 1`: the family releases 0.0.74 together,
  the core first. The floor had stayed at 0.0.71.
- Require `pain001-loader-mt101 >= 0.0.74, < 1`, the first release that
  parses MT101 block-4 envelopes in linear time (GHSA-phvr-mjg8-m2qq). The
  floor had been 0.0.1.
- Dependencies: mcp 2.3.0, mypy 2.4.0, ruff 0.17.1, black 26.10.1,
  tomli 2.5.0, types-jsonschema 4.26.0.20261006, virtualenv 21.14.11 in
  the build set, and the github-actions group (upload-artifact 7.0.2,
  setup-node 7.1.0, scorecard-action 2.5.0, codeql-action 4.39.0,
  sbom-action 0.24.3).
- The Docker build takes the core branch as `PAIN001_REF` instead of a
  pip spec in `PAIN001_PIP_SPEC`.
- `CITATION.cff` carries the current version again (it had stayed at
  0.0.72).
- README badges follow the canonical layout; the Build badge points at
  the `ci.yml` workflow and the Docs badge is a valid static badge.

### Fixed

- The suite-consistency check compared this tree with the core's PyPI
  version and so reported a released tree as never released.
- Quoted the error-output description in `.github/ISSUE_TEMPLATE/bug_report.yml`;
  the unquoted `{"error": ...}` made the file invalid YAML, so GitHub could not
  load the bug-report form. `tests/test_repository_yaml.py` now parses every
  shipped YAML file.
- `.pre-commit-config.yaml` now runs ruff, black and mypy from the Poetry
  environment, so hook versions follow `poetry.lock`. The old pinned hooks
  (black 24, ruff 0.4, an isolated mypy without dependencies) failed on a clean
  tree and rewrote the vendored `tests/test_suite_conformance.py`, the rendered
  README and the parser fixtures.
- Docstrings of `simulate_payment_batch` and `stage_payment_batch` now render
  their numbered lists in the API reference without docutils errors.

## [0.0.73] - 2026-10-04

### Added

- Added animated terminal demo (`.github/demo.gif`) and `.github/demo.tape` with `make demo` target.
- Added normalized dual-licensing structure with `LICENSES/Apache-2.0.txt` and `LICENSES/MIT.txt`.

### Changed

- Updated `glama.json` manifest with normalized `Apache-2.0 OR MIT` SPDX license and bumped version to `0.0.73`.

## [0.0.72] - 2026-09-28

Aligns on pain001 0.0.72: ISO 20022 schemas and Schematron validation rules,
SLSA Level 3 provenance attestations, and dual-control simulation tools.

### Added

- Dual-control execution tools: `stage_payment_batch`, `simulate_clearing`,
  and `commit_payment_batch` MCP tools to govern autonomous agent execution
  with zero upfront fund movement, fee calculations, risk scores, and
  cryptographic tokens for human-in-the-loop sign-off.
- Multi-rail clearing simulation covering SEPA, FedNow, US-ACH, SWIFT-MX,
  CHAPS, and BACS payment rails before final execution.
- SLSA Level 3 provenance attestations for container images and package distributions.

### Changed

- Version aligned to `0.0.72` across all `pain001` suite packages.
- The README and the documentation index link
  [What is pain.001?](https://pain001.com/pain-001/), an explainer of the
  message's structure, versions and a schema-valid example.

## [0.0.71] - 2026-09-26

Aligns on pain001 0.0.71: request-local CEL policy rules, review-only
correction suggestions, explicit SFTP delivery, and release artifact
inspection.

### Security

- Require patched AnyIO and regenerate runtime/build locks to address the
  nine Dependabot findings across those manifests (#12–#20).

### Fixed

- Use the coordinated core main branch after merging, as well as matching
  feature branches, across CI, mutation, documentation and image builds.
  Release tags continue to select the declared published dependency.
- Include correction-tool tests in mutation selection and use the matching
  core feature branch in that job; retain the 85% mutation score floor.

### Documentation

- Generate the canonical README, check drift in CI, and replace stale feature,
  tool-count and safety claims with current source-backed guidance.

### Added

- `suggest_record_fix` delegates deterministic, review-only corrections to
  the matching core feature build. Financial fields are always refused;
  older core builds return an actionable error without disabling other tools
  (pain001#185).

- `--transport streamable-http` and `--transport sse`, with `--host` and
  `--port`. Streamable HTTP serves both current protocol revisions
  (2026-07-28 stateless with `server/discover`, and 2025-11-25 with the
  `initialize` handshake) on one endpoint and streams responses as
  server-sent events; `sse` serves the older HTTP+SSE transport. stdio
  stays the default and is unchanged. `--version` prints the version.
  ADR 0004 records the decision and supersedes ADR 0002 (stdio only).

## [0.0.70] - 2026-09-13

Aligns on pain001 0.0.70: importing the core no longer loads its CLI, and
the rail rules behind `validate_payment_scheme` read the CSV pipeline's
column names as well as the short ones.

### Changed

- `pain001` floor raised to `>=0.0.70`.
- Version aligned to `0.0.70` across all five `pain001` packages.

## [0.0.69] - 2026-09-12

Aligns on pain001 0.0.69, the third example-corpus release: the tier 2
and 3 market packs and the pain.001 twin foundation reach
`list_corpus_files` and `get_corpus_file` unchanged.

### Changed

- `pain001` floor raised to `>=0.0.69`.
- Version aligned to `0.0.69` across all five `pain001` packages.

## [0.0.68] - 2026-09-12

Aligns on pain001 0.0.68, the second example-corpus release, and makes
bank variants real in the corpus tools.

### Changed

- `pain001` floor raised to `>=0.0.68`. `list_corpus_files` reports the
  `variant` the core now records, and `get_corpus_file` and
  `get_corpus_provenance` pass the requested variant straight through;
  the 0.0.67 fallback that answered a variant request on an older core
  with an error payload is gone.
- Version aligned to `0.0.68` across all five `pain001` packages.

## [0.0.67] - 2026-09-12

The example corpus reaches the agent tools: the validated pain.001
files pain001 0.0.67 ships, with their provenance, are listable and
readable through MCP.

### Added

- **Example corpus tools.** `list_corpus_files`, `get_corpus_file`,
  `get_corpus_provenance` and `get_corpus_coverage` expose the corpus
  that ships in pain001 from 0.0.67: realistic market scenarios per
  country and rail (with bank variants), the schema coverage sets, each
  file's provenance sidecar and each edition's coverage verdict. They
  delegate to `pain001.corpus`; the dependency floor is now 0.0.67, and
  with an older pain001 they still return an `{"error": ...}` payload
  rather than failing at import.

### Changed

- `pain001` floor raised to `>=0.0.67`, the first release with
  `pain001.corpus`.
- Version aligned to `0.0.67` across all five `pain001` packages.
- `mcp` 2.2.0; `httpx2` and `httpcore2` 2.12.0, which close the six
  Dependabot advisories on the 0.0.66 lock file; `pain001-loader-mt101`
  0.0.65; `cyclonedx-bom` 7.3.1; `poetry` 2.4.3. Dev tools: `ruff`
  0.16.6, `packaging` 26.3, `pytest-benchmark` 5.3.0. GitHub Actions
  group bumped.

## [0.0.66] - 2026-09-12

Aligns the `pain001` suite on `0.0.66`, the core release that adds
cross-record duplicate detection, the `/api/v1/ui` dashboard, GPG
flags and OpenTelemetry spans. Nothing in this package changed.

### Changed

- Version aligned to `0.0.66` across all five `pain001` packages.

## [0.0.65] - 2026-08-29

Aligns the `pain001` suite on one version number, and adds the scheduled
drift check this repository was missing.

### Added

- `scripts/check_suite_consistency.py` and a scheduled `Suite
  Consistency` workflow compare this tree, and every published member of
  the suite, against PyPI. A member left a release behind still installs
  and still passes its own tests; only the index disagrees, and only if
  somebody looks.

### Changed

- Version aligned to `0.0.65` across all five `pain001` packages, which
  had drifted to `0.0.62`, `0.0.64`, `0.0.63`, `0.0.62` and `0.0.63`.
- Refreshed the vendored `tests/test_suite_conformance.py` to the
  current canonical copy. Its drift-check probe now matches the bare
  word `pypi` rather than the hostname, which CodeQL read as an
  incomplete URL sanitisation.

## [0.0.63] - 2026-08-29

Brings this repository onto the **suite conformance gate**.

### Added

- **`benches/bench_generate.py`** — a payroll run is thousands of
  records submitted once, under a cut-off, by a job that must not still
  be running when the window closes.

  **Generation is linear** once the fixed per-call cost has amortised:
  `us/record` settles around 15–25 us, and the one-record row is almost
  entirely fixed cost rather than a scaling signal.

  **`validate_records` costs up to 4.6x `generate_message`** — and that
  is worth a second look. `generate_message` XSD-validates its own output
  before returning, so the standalone validator being several times
  dearer means the two are not doing the same work. Either the extra is
  checking something generation does not, or there is a cheaper path
  being missed. Nothing is changed here; the ratio is now measured and
  watched.

  The **cold-start** cost is reported separately, measured in a fresh
  interpreter, because the XSD compiles once per process and a mean hides
  it entirely.

  Nothing asserts a timing threshold — wall-clock is not comparable
  between machines, and a flaky performance gate teaches people to ignore
  red. CI runs `--quick`, so a benchmark that stops compiling fails the
  build rather than rotting into a file that reads as verified.

- **`tests/test_suite_conformance.py`** — invariants shared by every
  repository in the suite, vendored from one canonical copy and
  checksummed by its own test.

### Changed

- CI lints, formats and runs `benches/` alongside everything else.
- `tomli` (on 3.10) and `packaging` are named as dev dependencies; the
  conformance gate parses `pyproject.toml` and needs both.
- `tests/test_suite_conformance.py` is excluded from black: it is
  generated, and the suite uses three different line lengths.

- **The `pain001` floor moves to `>=0.0.62`**, matching this package's
  own version. Nothing here requires 0.0.62 — the `fast` extra it
  depends on has existed since 0.0.61 — so this is alignment rather than
  a technical requirement: the suite ships one version number, and a
  member requiring an older core than it ships reads as an
  inconsistency even when it resolves fine.

  The trade is that anyone installing this package now takes `pain001`
  0.0.62 or newer rather than 0.0.61 or newer. Both are already
  published together, so in practice nobody is narrowed by it.

  Takes effect in the next release; 0.0.62 shipped with `>=0.0.61`.

## [0.0.62] - 2026-08-21

### Performance

- **The bundled JSON Schema is cached.** `_load_schema` re-read and
  re-parsed it on every call, and the read-only discovery tools do
  essentially nothing else:

  | tool | before | after |
  |---|---|---|
  | `get_required_fields` | 0.0788ms | **0.0002ms** (475x) |
  | `get_input_schema` | 0.0736ms | **0.0001ms** (888x) |

  `validate_identifier` and `list_message_types` never touch the schema
  and are unchanged, which is the control that makes those numbers a
  real effect rather than a measurement artefact.

  **This corrects a decision from 0.0.61**, where the load was left
  uncached because it costs 0.18ms against ~92ms for a 200-record
  `generate_message` — 0.2% of the work. The arithmetic was right and
  the comparison was wrong: `generate_message` is not what those
  milliseconds are a fraction of when a model is calling the discovery
  tools repeatedly.

### Added

- **Benchmarks for the read-only tools**, plus a guard asserting the
  schema is not re-read across repeated calls. At sub-microsecond scale
  a wall-clock threshold cannot detect the cache being deleted; the
  cache-info assertion can.

## [0.0.61] - 2026-08-20

Suite release with `pain001` 0.0.61.

### Performance

- **`generate_message` is ~6x faster.** pain001 0.0.61 validates
  generated XML with libxml2 when `lxml` is installed, and XSD
  validation was 93% of generation cost.

  | | before | after |
  |---|---|---|
  | `generate_message`, 200 records | 93.3ms | **15.4ms** |

### Changed

- **Depends on `pain001[fast]`** rather than plain `pain001`. The
  speed-up above only happens when `lxml` is present, and an MCP server
  answering repeated tool calls is exactly the workload that wants it —
  leaving it to whatever happens to be installed would mean a server
  silently running 6x slower. Measured both ways to confirm that is what
  the extra buys.

- **The `pain001` floor moves to `>=0.0.61`,** because the `fast` extra
  does not exist before then. This is a deliberate raise, not routine
  churn: an extra that the pinned version does not provide installs
  quietly without it.

## [0.0.60] - 2026-08-20

Lockstep release with `pain001` 0.0.60. No functional change in this
package.

`pain001-mcp` is a lockstep member of the suite: its version tracks the
core so an operator can pair `pain001-mcp==X` with `pain001==X` without
consulting a table. `pain001.suite` records which members follow that
rule and `scripts/check_suite_consistency.py` in the core enforces it
daily; leaving this package at 0.0.59 against a 0.0.60 core would open
the same drift that check exists to catch.

The `pain001>=0.0.55` floor is deliberately unchanged. The core's 0.0.60
changes are the SPDX licence headers, the plugin registration of the
bundled schemes and writer, and a pygls 1.x -> 2.x migration confined to
`pain001.lsp.server` — none of which this package imports. It uses
`pain001.async_adapter` and `pain001.constants`, whose public surface is
byte-identical between 0.0.59 and 0.0.60 apart from the version string.
Raising a floor without a reason only narrows what users can resolve.

## [0.0.59] - 2026-08-20

Lockstep release with `pain001` 0.0.59. Brings this package back into
line with the core: it had been published at 0.0.58 against a 0.0.59
core, which is the drift `pain001`'s suite-consistency check now
reports.

### Fixed

- `cryptography` moved to 50.0.0, taking the patched release for the
  high-severity advisory (#34).

### Added

- SWIFT-Z charset option in the charset sanitizer (#22).

### Changed

- Dependency updates: `cyclonedx-bom` 7.3.1, `ruff` 0.16.2, `mypy`
  2.3.0, `pain001-loader-mt101` 0.0.2, the base image to
  `python:3.14-slim`, and the grouped GitHub Actions bump (#28-#33).
- Dependabot config repaired — an invalid key meant github-actions
  updates were never grouped (#27).

## [0.0.58] - 2026-07-30

Backfilled: released and tagged without a changelog entry at the time.

### Changed

- Consolidated dependency updates (#25), and the `poetry.lock`
  regeneration after the `mcp<2` cap.

## [0.0.57] - 2026-07-18

The **security-propagation** cut. Raises the `pain001` floor to pull in
an upstream security fix; no API changes.

### Changed

- **Require `pain001` >= 0.0.55.** Propagates a security fix released in
  pain001 0.0.55 by lifting the dependency floor from `>= 0.0.54`. No
  behavioural change to the 17 tools; the lockfile is regenerated to
  pin the patched release.

## [0.0.56] - 2026-07-16

The **LLM-ergonomic generate** cut. Driven by a real Claude Code
transcript in which the natural first-try call — `amount`/`currency`
keys, a bare `YYYY-MM-DD` date, a JSON boolean `batch_booking`, no
`nb_of_txs` — needed 5+ retries through the iso20022-mcp gateway.
Requires pain001 >= 0.0.54.

### Added

- **Bare family aliases**: `pain.001` -> `pain.001.001.09` and
  `pain.008` -> `pain.008.001.02` are accepted everywhere a
  `message_type` is, and are listed in the parameter's enum.
- **First-try field guide in the tool schema**: the `records` parameter
  of `generate_message` / `generate_message_async` now documents the
  key fields, formats, accepted aliases, computed fields and defaults,
  so an agent can build a correct call without a discovery round-trip.

### Fixed

- **Raised errors -> structured payloads**: `generate_message`,
  `generate_message_async` and `generate_message_from_file` now catch
  the library's `Pain001Error` hierarchy and the XSD `RuntimeError`
  and return a JSON `{"error": ...}` payload that lists *all* missing
  or invalid fields (with element paths on XSD failures) instead of
  leaking one raised KeyError per retry.
- **validate/generate coherence**: `validate_records` canonicalizes
  alias keys (`amount`, `currency`, lower-case IBAN/BIC spellings) the
  same way generation does, so a record that generates cleanly also
  validates cleanly. IBAN/BIC validation itself is unchanged.
- **Unknown message types** name the valid options in the error.

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

[0.0.74]: https://github.com/sebastienrousseau/pain001-mcp/releases/tag/v0.0.74
[0.0.73]: https://github.com/sebastienrousseau/pain001-mcp/releases/tag/v0.0.73
[0.0.72]: https://github.com/sebastienrousseau/pain001-mcp/releases/tag/v0.0.72
[0.0.54]: https://github.com/sebastienrousseau/pain001-mcp/releases/tag/v0.0.54
[0.0.53]: https://github.com/sebastienrousseau/pain001-mcp/releases/tag/v0.0.53
[0.0.52]: https://github.com/sebastienrousseau/pain001-mcp/releases/tag/v0.0.52
