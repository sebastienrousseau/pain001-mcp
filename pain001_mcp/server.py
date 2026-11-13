# SPDX-FileCopyrightText: 2023-2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Model Context Protocol (MCP) server for pain001.

This server exposes the pain001 library's ISO 20022 ``pain.001`` and
companion-message capabilities as MCP tools so any MCP-compatible client
(Claude Desktop, IDEs, agents) can discover supported message versions,
inspect input schemas, validate payment records and financial identifiers,
generate validated XML, and parse the bank-reply messages (``camt.053``
statements and ``pain.002`` status reports).

Every tool is a thin, typed wrapper over the pain001 public API (the schema
loader, the IBAN/BIC validators, ``generate_xml_string``, and the camt.053
/ pain.002 parsers) so all interfaces behave identically to the CLI and
REST API. Tools return JSON-serializable data (dicts, lists, or strings);
on a :class:`ValueError` (or a ``pain001.exceptions`` subclass thereof)
they return an ``{"error": ...}`` dictionary rather than raising.

The tools live in one module per family (``_catalogue``, ``_records``,
``_generate``, ``_replies``, ``_schemes``, ``_corpus``, ``_faces``,
``_staging``, ``_clearing``), sharing ``_common`` and the result shapes in
``_shapes``. This module builds the server, registers every tool in
listing order (ADR 0003) and re-exports them, so ``server.<tool>`` keeps
working for callers.

Launching the server:
    * As a console script::

        pain001-mcp

    * Programmatically::

        from pain001_mcp.server import main
        main()

    * In an MCP client config (e.g. Claude Desktop ``claude_desktop_config.json``)::

        {
          "mcpServers": {
            "pain001": {
              "command": "pain001-mcp"
            }
          }
        }

The server communicates over stdio (MCPServer's default transport).
"""

from pain001_mcp import __version__, _cli
from pain001_mcp._catalogue import (
    build_payment_batch,
    get_input_schema,
    get_required_fields,
    inspect_template,
    list_message_types,
    list_supported_formats,
    schema_resource,
)
from pain001_mcp._check import check_payment_file
from pain001_mcp._clearing import simulate_clearing
from pain001_mcp._common import (
    _COMMIT_TOOL,
    _FS_READ,
    _MUTATING_SAFE,
    _PURE_READ,
)
from pain001_mcp._corpus import (
    get_corpus_coverage,
    get_corpus_file,
    get_corpus_provenance,
    list_corpus_files,
)
from pain001_mcp._faces import list_faces, project_face
from pain001_mcp._generate import (
    generate_message,
    generate_message_async,
    generate_message_from_file,
    validate_xml_against_schema,
)
from pain001_mcp._mcp_compat import build_server
from pain001_mcp._records import (
    convert_mt101,
    migrate_records,
    sanitize_to_iso20022_charset,
    suggest_record_fix,
    validate_identifier,
    validate_records,
)
from pain001_mcp._replies import parse_camt053, parse_pain002
from pain001_mcp._schemes import (
    list_scheme_profiles,
    simulate_payment_batch,
    validate_payment_scheme,
)
from pain001_mcp._staging import commit_payment_batch, stage_payment_batch

__all__ = [
    "build_payment_batch",
    "check_payment_file",
    "commit_payment_batch",
    "convert_mt101",
    "generate_message",
    "generate_message_async",
    "generate_message_from_file",
    "get_corpus_coverage",
    "get_corpus_file",
    "get_corpus_provenance",
    "get_input_schema",
    "get_required_fields",
    "inspect_template",
    "list_corpus_files",
    "list_faces",
    "list_message_types",
    "list_scheme_profiles",
    "list_supported_formats",
    "main",
    "migrate_records",
    "parse_camt053",
    "parse_pain002",
    "project_face",
    "sanitize_to_iso20022_charset",
    "schema_resource",
    "server",
    "simulate_clearing",
    "simulate_payment_batch",
    "stage_payment_batch",
    "suggest_record_fix",
    "validate_identifier",
    "validate_payment_scheme",
    "validate_records",
    "validate_xml_against_schema",
]

server = build_server("pain001", __version__)

# Tools are registered here, in definition order, rather than with
# decorators on each function: mutmut 3 never mutates a decorated function,
# so the decorator form left every handler outside mutation testing. The
# registered object is the same function, docstring and signature, and
# clients list the tools in this order.
# The resource and the prompt are registered the same way as the tools,
# so mutmut reaches them too (it never mutates a decorated function).
server.resource(
    "pain001://schema/{message_type}", title="pain.001 XSD schema"
)(schema_resource)
server.prompt(title="Build a compliant payment batch")(build_payment_batch)
server.tool(title="List pain message types", annotations=_PURE_READ)(
    list_message_types
)
server.tool(title="Get required fields", annotations=_PURE_READ)(
    get_required_fields
)
server.tool(title="Get input JSON Schema", annotations=_PURE_READ)(
    get_input_schema
)
server.tool(title="Validate records against schema", annotations=_PURE_READ)(
    validate_records
)
server.tool(title="Suggest review-only record fixes", annotations=_PURE_READ)(
    suggest_record_fix
)
server.tool(title="Validate IBAN or BIC", annotations=_PURE_READ)(
    validate_identifier
)
server.tool(title="Generate pain XML from records", annotations=_PURE_READ)(
    generate_message
)
server.tool(title="List supported input formats", annotations=_PURE_READ)(
    list_supported_formats
)
server.tool(
    title="Generate pain XML (async, large batches)", annotations=_PURE_READ
)(generate_message_async)
server.tool(title="Generate pain XML from a CSV file", annotations=_FS_READ)(
    generate_message_from_file
)
server.tool(title="Parse camt.053 statement file", annotations=_FS_READ)(
    parse_camt053
)
server.tool(title="Parse pain.002 status report file", annotations=_FS_READ)(
    parse_pain002
)
server.tool(title="Inspect CSV template columns", annotations=_PURE_READ)(
    inspect_template
)
server.tool(title="Validate against scheme rulebook", annotations=_PURE_READ)(
    validate_payment_scheme
)
server.tool(title="List scheme profiles", annotations=_PURE_READ)(
    list_scheme_profiles
)
server.tool(title="Simulate payment batch", annotations=_PURE_READ)(
    simulate_payment_batch
)
server.tool(title="Migrate records between versions", annotations=_PURE_READ)(
    migrate_records
)
server.tool(title="Validate XML string against XSD", annotations=_PURE_READ)(
    validate_xml_against_schema
)
server.tool(
    title="Sanitise text to ISO 20022 charset", annotations=_PURE_READ
)(sanitize_to_iso20022_charset)
server.tool(title="Convert MT101 to pain.001 records", annotations=_PURE_READ)(
    convert_mt101
)
server.tool(title="List example corpus files", annotations=_PURE_READ)(
    list_corpus_files
)
server.tool(title="Get example corpus file", annotations=_PURE_READ)(
    get_corpus_file
)
server.tool(title="Get example corpus provenance", annotations=_PURE_READ)(
    get_corpus_provenance
)
server.tool(title="Get schema coverage report", annotations=_PURE_READ)(
    get_corpus_coverage
)
server.tool(title="List faces", annotations=_PURE_READ)(list_faces)
server.tool(title="Project pain.001 into a face", annotations=_PURE_READ)(
    project_face
)
server.tool(title="Check an existing payment file", annotations=_PURE_READ)(
    check_payment_file
)
server.tool(
    title="Stage payment batch for simulation and approval",
    annotations=_MUTATING_SAFE,
)(stage_payment_batch)
server.tool(
    title="Simulate clearing network execution",
    annotations=_PURE_READ,
)(simulate_clearing)
server.tool(
    title="Commit staged payment batch",
    annotations=_COMMIT_TOOL,
)(commit_payment_batch)


def main(argv: list[str] | None = None) -> None:
    """Run the pain001 MCP server (the ``pain001-mcp`` entry point).

    stdio by default; ``--transport streamable-http`` or ``--transport sse``
    listens on ``--host``/``--port`` instead. See :mod:`pain001_mcp._cli`.

    Args:
        argv: Command-line arguments; ``None`` reads ``sys.argv[1:]``.
    """
    _cli.serve(server, argv, "pain001-mcp", __version__)


if __name__ == "__main__":
    main()
