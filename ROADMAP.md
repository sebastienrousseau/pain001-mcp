# pain001-mcp Roadmap

This roadmap tracks the next set of capabilities for the MCP companion of
the [pain001](https://github.com/sebastienrousseau/pain001) library. The
versions are **target** windows; releases ship when the gates pass, not
on a calendar.

## v0.0.52 - Initial release (current)

- Nine MCP tools mirroring the pain001 public API (schema discovery,
  identifier validation, XML generation, bank-reply parsing).
- 100% line+branch coverage gate, 100% docstring coverage gate, signed
  conventional commits.
- Three runnable examples and bundled `camt.053` / `pain.002` fixtures.

## v0.0.53 - Streaming and async surface

- `generate_message_async` and `validate_records_async` tools backed by
  `pain001.async_adapter`.
- `generate_message_from_file(path, message_type)` for CSV / SQLite /
  JSON / JSONL inputs (Parquet behind the `pain001[parquet]` extra).
- `pain001.observability` bridge: an opt-in `get_metrics` tool reporting
  the rolling counters / histograms an agent can use to back off when
  the underlying library is under pressure.

## v0.1.0 - Hardened agent surface

- Configurable allow-list for filesystem-reading tools (`parse_camt053`,
  `parse_pain002`, file-driven generation) so deployments can scope what
  an agent may open.
- Structured-output tool variants (each tool returns a typed payload
  schema MCP clients can introspect).
- Streaming responses for large batches.

## Out of scope (handled elsewhere)

- **Editor features** - see [`pain001-lsp`](https://github.com/sebastienrousseau/pain001-lsp).
- **HTTP / file-system bank channels** - see the core
  [`pain001`](https://github.com/sebastienrousseau/pain001) library.
