<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# 0002. Speak stdio only

- **Status:** Accepted
- **Date:** 2026-09-18 (practised since the first release; written down today)
- **Deciders:** maintainer

## Context

MCP servers can be exposed over HTTP as well as stdio. Agents launch a
stdio server as a child process; an HTTP listener on a payments machine
is a network surface to harden.

## Options considered

1. Offer an HTTP transport for remote agents; TLS, authentication and
   a port to document.
2. stdio only through FastMCP; the client owns the process lifetime.

## Decision

Option 2. No listener, no TLS, no token to leak; the same binary works
in Claude Desktop, Claude Code, Cursor and VS Code, which all spawn a
process.

## Consequences

`main()` runs the server over stdio and nothing else. The stdio
end-to-end test spawns the real server and lists its tools. A remote
deployment wraps the process; the server does not open a socket.
