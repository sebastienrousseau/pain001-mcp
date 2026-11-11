<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# Security Policy

## Supported versions

Security fixes land on the latest published release. Older 0.0.x
releases do not receive them; upgrade to the latest release, which
ships in lockstep with the core
[`pain001`](https://github.com/sebastienrousseau/pain001) library.

## Reporting a vulnerability

**Do not open a public issue for security reports.**

Use one of the following private channels, in this order of
preference:

1. **GitHub Private Vulnerability Reporting**
   <https://github.com/sebastienrousseau/pain001-mcp/security/advisories/new>
   (the maintainers are notified automatically; do this first)
2. **Email**: `security@pain001.com`
3. **Direct message** to a maintainer listed in
   [MAINTAINERS.md](MAINTAINERS.md)

Please include:

1. Description of the vulnerability and its potential impact
2. Steps to reproduce (preferably a failing test case)
3. The version affected
   (`python -c "import pain001_mcp; print(pain001_mcp.__version__)"`)
4. Suggested fix (if available)

These are goals, not guarantees: the pain001 suite is maintained in a
personal capacity, with no SLA and no out-of-hours cover.

**Acknowledgement**: the goal is within 5 working days.
**Triage**: a severity assessment and remediation plan after
acknowledgement.
**Fix windows** (best effort): critical 7 days, high 30 days, medium 60
days, low best-effort. The clock starts at triage, not at report.

## Threat Model

`pain001-mcp` is a Model Context Protocol server that wraps the
[`pain001`](https://github.com/sebastienrousseau/pain001) library and
exposes it as agent tools. By default it runs over stdio, spawned by
the client, with no network listener. `--transport streamable-http` and
`--transport sse` start an HTTP listener on the loopback interface
(`127.0.0.1:8000` unless told otherwise), with no authentication of its
own. The security surface is:

- **Untrusted arguments** - tool calls (`validate_records`,
  `generate_message`, `parse_camt053`, `parse_pain002`, …) can come from
  any MCP client an agent has access to.
- **Filesystem reads** - `parse_camt053(xml_file_path)` and
  `parse_pain002(xml_file_path)` open paths supplied by the caller.
- **Bundled XSDs / templates** - `generate_message` reads templates
  shipped by `pain001`; the tool must not allow callers to escape that
  directory.

## Hardening

- **Path Safety** - file-path arguments are validated by `pain001`'s
  shared `validate_path()` helper (see [`pain001` security policy][p001-sec]),
  which rejects absolute paths outside the workspace and `..`-style
  traversals. `pain001-mcp` adds an explicit regression test that
  parser tools return `{"error": ...}` for traversal attempts rather than
  reading arbitrary files.
- **XXE Prevention** - XML parsing goes through `pain001`, which uses
  `defusedxml`.
- **Error containment** - every tool returns `{"error": …}` rather than
  raising; tracebacks and stack frames are not surfaced over the wire.
- **Loopback by default** - the HTTP transports bind `127.0.0.1`. They
  have no authentication or TLS: put the server behind a gateway you
  trust before binding a routable address with `--host`.
- **No secrets** - the package does not embed credentials or call out to
  external services.

## Continuous Integration

- `ci.yml` runs the full quality matrix (ruff, mypy, pytest with the
  100% coverage gate, interrogate).
- `security.yml` runs `bandit` against the package on every push and
  weekly via cron.
- `codeql.yml` runs GitHub's CodeQL Python analysis weekly.
- `security.yml` also runs `pip-audit` against the hash-pinned CI
  dependency set.
- Dependabot (`.github/dependabot.yml`) proposes weekly updates for pip
  dependencies, GitHub Actions and the Docker base image.

## Cryptography Status

`pain001-mcp` does not perform cryptographic operations. It does not
sign, encrypt, verify certificates, or hash passwords. Any crypto-bearing
package in the dependency tree is transitive via `pain001`.

## Contact

- **Email**: <security@pain001.com>
- **GitHub Advisories**: <https://github.com/sebastienrousseau/pain001-mcp/security/advisories>
- **GitHub issues** (not for vulnerabilities): <https://github.com/sebastienrousseau/pain001-mcp/issues>

[p001-sec]: https://github.com/sebastienrousseau/pain001/blob/main/SECURITY.md
