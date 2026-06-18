# Security Policy

## Reporting Security Vulnerabilities

If you discover a security vulnerability in pain001-mcp, please email
**security@pain001.com** instead of using the issue tracker.

Please include:
1. Description of the vulnerability
2. Steps to reproduce
3. Potential impact
4. Suggested fix (if available)

We will acknowledge receipt within 48 hours and provide updates on
remediation timeline.

## Threat Model

`pain001-mcp` is a Model Context Protocol server that wraps the
[`pain001`](https://github.com/sebastienrousseau/pain001) library and
exposes it as agent tools. It runs locally over stdio (no network listener
of its own), so the security surface is:

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
- **No network sockets** - the server only speaks stdio. No HTTP listener
  to harden, no TLS to manage.
- **No secrets** - the package does not embed credentials or call out to
  external services.

## Continuous Integration

- `ci.yml` runs the full quality matrix (ruff, mypy, pytest with the
  100% coverage gate, interrogate).
- `security.yml` runs `bandit` against the package on every push and
  weekly via cron.
- `codeql.yml` runs GitHub's CodeQL Python analysis weekly.
- Dependency updates are picked up via Dependabot (config inherited from
  `pain001`).

## Cryptography Status

`pain001-mcp` does not perform cryptographic operations. It does not
sign, encrypt, verify certificates, or hash passwords. Any crypto-bearing
package in the dependency tree is transitive via `pain001`.

## Contact

- **Email**: security@pain001.com
- **GitHub Advisories**: https://github.com/sebastienrousseau/pain001-mcp/security/advisories
- **GitHub Discussions**: https://github.com/sebastienrousseau/pain001/discussions

[p001-sec]: https://github.com/sebastienrousseau/pain001/blob/main/SECURITY.md
