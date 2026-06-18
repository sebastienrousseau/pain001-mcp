<!-- SPDX-License-Identifier: Apache-2.0 -->

# Getting support

Thanks for using pain001-mcp. Here's the fastest way to get help, by need.

## Questions & how-to

- **Read first:** the [README](README.md), the runnable
  [`examples/`](examples/) (tool walkthrough, validation pipeline,
  bank-reply parsing), and the parent
  [`pain001`](https://github.com/sebastienrousseau/pain001) repo for
  message-type / scheme background.
- **Still stuck?** Open a
  [GitHub Discussion](https://github.com/sebastienrousseau/pain001/discussions)
  on the parent repo (shared with pain001 and pain001-lsp) or a question
  issue here. Include your Python version, `pain001-mcp` version
  (`python -c "import pain001_mcp; print(pain001_mcp.__version__)"`), your
  MCP client (Claude Desktop / IDE / agent), and a minimal reproducer.

## Bugs

Open a bug report at
<https://github.com/sebastienrousseau/pain001-mcp/issues/new> with a
minimal reproducer, the tool name, the arguments, and the full error
payload. A failing record set (with sensitive values redacted) helps
enormously.

## Feature requests

Open a feature request at
<https://github.com/sebastienrousseau/pain001-mcp/issues/new>. New MCP
tools, resources, and prompts on top of the
[`pain001`](https://github.com/sebastienrousseau/pain001) public API are
especially welcome — see [ARCHITECTURE.md](ARCHITECTURE.md) for the
extension points and [ROADMAP.md](ROADMAP.md) for what's planned.

## Security

**Do not** open public issues for vulnerabilities. Follow the private
disclosure process in [SECURITY.md](SECURITY.md).

## Contributing & maintaining

See [CONTRIBUTING.md](CONTRIBUTING.md) and [GOVERNANCE.md](GOVERNANCE.md).

## Supported versions

Fixes land on the latest release line. See [SECURITY.md](SECURITY.md) for
the supported-version policy. pain001-mcp requires Python 3.10+.
