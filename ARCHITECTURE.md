<!-- SPDX-License-Identifier: Apache-2.0 -->

# pain001-mcp Architecture

A map of the codebase for new contributors and maintainers. The goal is
that anyone can navigate, extend, and reason about pain001-mcp without
prior context.

## The pipeline

```
MCP client (Claude Desktop, IDE, agent)
        |  stdio (JSON-RPC)
        v
pain001_mcp/server.py        (FastMCP server: tools, resources, prompts)
        |  thin typed wrappers
        v
pain001 public API           (pain001.generate_xml_string,
        |                     pain001.validate_scheme, pain001.parse_camt053_statement,
        |                     pain001.parse_pain002_report,
        |                     pain001.validation.{validate_iban, validate_bic})
        v
ISO 20022 XML / structured data
```

Tools are deliberately thin: every one is a small adapter that
delegates to the
[`pain001`](https://github.com/sebastienrousseau/pain001) library and
returns a JSON-serialisable result. The agent surface is the entire
public API of that library, exposed in a way an MCP client can call.

## Module map

| Area | Module | Responsibility |
| :--- | :--- | :--- |
| **Server** | `pain001_mcp/server.py` | The FastMCP server, all tool / resource / prompt registrations |
| **Entry point** | `pain001_mcp.server:main` (console script: `pain001-mcp`) | Launches the server over stdio |
| **Version** | `pain001_mcp/__init__.py` | Single source of truth (`__version__`); the LSP reads it for the protocol handshake |
| **Tests** | `tests/test_mcp_server.py`, `tests/test_stdio_e2e.py` | In-process + end-to-end-via-subprocess regressions |
| **Fixtures** | `tests/fixtures/` | Bundled `camt053_sample.xml` and `pain002_sample.xml` for reproducible parser tests |
| **Examples** | `examples/` | One runnable script per usage shape (tool walkthrough, validation pipeline, parsers) |
| **Release helpers** | `scripts/verify_versions.py` | Asserts `__version__`, `pyproject.toml`, and `CHANGELOG.md` agree |

## Tools, resources, prompts

The current MCP surface:

- **Tools** - `list_message_types`, `get_required_fields`,
  `get_input_schema`, `validate_records`, `validate_identifier`,
  `generate_message`, `generate_message_async`,
  `generate_message_from_file`, `list_supported_formats`,
  `parse_camt053`, `parse_pain002`, `inspect_template`,
  `validate_payment_scheme`.
- **Resources** - `pain001://schema/{message_type}` (returns the bundled
  XSD text).
- **Prompts** - `build_payment_batch(message_type=...)` (guided
  instruction template).

## Key design decisions

- **Delegation, not duplication.** Every tool is a thin wrapper over the
  `pain001` public API. If you want a new tool, port the matching helper
  from `pain001` rather than re-implementing it here.
- **Errors as data.** Tools never raise. A `ValueError` (or a
  `pain001.exceptions` subclass thereof) is turned into an
  `{"error": ...}` payload so the agent can reason about failure
  without parsing tracebacks.
- **No network sockets.** The server only speaks stdio. No HTTP listener
  to harden, no TLS to manage.
- **Path safety reused.** File-path tools (`parse_camt053`,
  `parse_pain002`, `generate_message_from_file`) delegate to
  `pain001.security.validate_path()`, the same guard the CLI and REST
  API use.
- **Coverage enforced at 100%** line+branch and docstring; only
  defensive guards against bundled-asset removal are
  `# pragma: no cover`.

## Extension points

- **Add a tool:** add a `@server.tool()`-decorated function in
  `pain001_mcp/server.py`; pair it with tests in
  `tests/test_mcp_server.py` and add it to `EXPECTED_TOOLS` there.
- **Add a resource:** `@server.resource("pain001://...")` decorator.
- **Add a prompt:** `@server.prompt()` decorator.
- **Match a new `pain001` feature:** when a new public helper lands
  upstream, port it as a tool here in the same release window.

## Where to look first

- Runnable examples: [`examples/`](examples/)
- Roadmap: [`ROADMAP.md`](ROADMAP.md)
- Release process: [`RELEASING.md`](RELEASING.md)
- Parent library: [`pain001`](https://github.com/sebastienrousseau/pain001)
