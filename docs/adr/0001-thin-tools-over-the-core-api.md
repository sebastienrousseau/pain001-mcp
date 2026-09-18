<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# 0001. Thin tools over the core's public API

- **Status:** Accepted
- **Date:** 2026-09-18 (practised since the first release; written down today)
- **Deciders:** maintainer

## Context

An MCP server could carry its own generation and validation logic,
tuned for agents. The core library already has the generation, the
three validation layers and the parsers, all gated at 100 percent.

## Options considered

1. Re-implement or fork logic here for agent ergonomics; two engines to
   keep in step.
2. Every tool is a small typed adapter over one core call, returning a
   JSON-serialisable result; ergonomics live in the descriptions and
   the argument schemas, not in a second engine.

## Decision

Option 2. A tool that disagrees with the CLI is worse than a tool that
is slightly less convenient; the core is the one place a rule lives.

## Consequences

New capabilities are ported from the core in the same release window.
The server pins the core at its own version (the suite's lockstep
floor). A tool never raises: a `ValueError` becomes an `{"error": ...}`
payload the agent can reason about.
