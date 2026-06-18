# pain001-mcp examples

Runnable, self-contained examples for the pain001 MCP server. Run any of
them from the repository root:

```sh
python examples/<name>.py
```

| Example | Demonstrates |
|---------|--------------|
| [`01_mcp_tools.py`](01_mcp_tools.py) | Calling the MCP tools in-process — `list_message_types`, `validate_identifier`, and `generate_message` |
| [`02_validate_pipeline.py`](02_validate_pipeline.py) | Chaining `get_required_fields`, `validate_records`, and `validate_identifier` to surface every problem before generating XML |
| [`03_parse_bank_replies.py`](03_parse_bank_replies.py) | Parsing a `camt.053` statement and a `pain.002` status report via the MCP tools (uses the bundled fixtures by default) |

The examples import directly from `pain001_mcp.server`, so install this
package (and the core `pain001` library it depends on) first:

```sh
pip install pain001-mcp   # Python 3.10+
```
