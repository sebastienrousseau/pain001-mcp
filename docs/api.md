<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# Python API reference

The standalone server's importable Python surface (used by the runnable
examples and any agent that wraps the FastMCP instance directly).

```{eval-rst}
.. automodule:: pain001_mcp
   :members:
   :exclude-members: Field
   :undoc-members:
```

## Tool, resource and prompt modules

Each tool family has its own module; `pain001_mcp.server` builds the
server, registers every tool and re-exports them.

### Server and registrations

```{eval-rst}
.. automodule:: pain001_mcp.server
   :members: main
```

### Discovery tools, resource and prompt

```{eval-rst}
.. automodule:: pain001_mcp._catalogue
   :members:
   :exclude-members: Field
   :undoc-members:
   :show-inheritance:
```

### Record tools

```{eval-rst}
.. automodule:: pain001_mcp._records
   :members:
   :exclude-members: Field
   :undoc-members:
   :show-inheritance:
```

### Generation tools

```{eval-rst}
.. automodule:: pain001_mcp._generate
   :members:
   :exclude-members: Field
   :undoc-members:
   :show-inheritance:
```

### Payment file check tool

```{eval-rst}
.. automodule:: pain001_mcp._check
   :members:
   :exclude-members: Field
   :undoc-members:
   :show-inheritance:
```

### Bank-reply tools

```{eval-rst}
.. automodule:: pain001_mcp._replies
   :members:
   :exclude-members: Field
   :undoc-members:
   :show-inheritance:
```

### Scheme tools

```{eval-rst}
.. automodule:: pain001_mcp._schemes
   :members:
   :exclude-members: Field
   :undoc-members:
   :show-inheritance:
```

### Example corpus tools

```{eval-rst}
.. automodule:: pain001_mcp._corpus
   :members:
   :exclude-members: Field
   :undoc-members:
   :show-inheritance:
```

### Faces tools

```{eval-rst}
.. automodule:: pain001_mcp._faces
   :members:
   :exclude-members: Field
   :undoc-members:
   :show-inheritance:
```

### Staging tools

```{eval-rst}
.. automodule:: pain001_mcp._staging
   :members:
   :exclude-members: Field
   :undoc-members:
   :show-inheritance:
```

### Clearing simulation

```{eval-rst}
.. automodule:: pain001_mcp._clearing
   :members:
   :exclude-members: Field
   :undoc-members:
   :show-inheritance:
```

### Result shapes

```{eval-rst}
.. automodule:: pain001_mcp._shapes
   :members:
   :exclude-members: Field
   :undoc-members:
   :show-inheritance:
```

### Transports and command line

The transport dispatch and its flags, shared verbatim by every server in
the suite.

```{eval-rst}
.. automodule:: pain001_mcp._transports
   :members:

.. automodule:: pain001_mcp._cli
   :members:
```
