<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# 0003. Register tools explicitly, not with decorators

- **Status:** Accepted
- **Date:** 2026-09-18 (practised since the first release; written down today)
- **Deciders:** maintainer

## Context

FastMCP tools are conventionally declared with `@server.tool(...)`.
mutmut 3 never mutates a decorated function, so the 21 tools were
outside mutation testing: a first run produced 29 mutants for a
1,300-line module.

## Options considered

1. Keep the decorators and accept that the handlers are untested by
   mutation; the score describes the helpers only.
2. Register the same functions by explicit `server.tool(...)(fn)` calls
   after the definitions; the registered object, docstring, signature
   and listing order are identical.

## Decision

Option 2. The handlers are what an agent calls; a mutation score that
excludes them measures the wrong thing. The first honest run exposed
that no test asserted the shape of a tool result; fifteen tests now do,
and the score is gated.

## Consequences

A new tool is a plain function plus one registration line in the block
before `main()`; `EXPECTED_TOOLS` in the tests and `docs/tools.md` (via
`scripts/tool_catalogue.py --check` in CI) must both follow. The stdio
end-to-end test proves the registrations still list every tool.
