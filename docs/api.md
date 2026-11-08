# Python API reference

The standalone server's importable Python surface (used by the runnable
examples and any agent that wraps the FastMCP instance directly).

```{eval-rst}
.. automodule:: pain001_mcp
   :members:
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
   :undoc-members:
   :show-inheritance:
```

### Record tools

```{eval-rst}
.. automodule:: pain001_mcp._records
   :members:
   :undoc-members:
   :show-inheritance:
```

### Generation tools

```{eval-rst}
.. automodule:: pain001_mcp._generate
   :members:
   :undoc-members:
   :show-inheritance:
```

### Bank-reply tools

```{eval-rst}
.. automodule:: pain001_mcp._replies
   :members:
   :undoc-members:
   :show-inheritance:
```

### Scheme tools

```{eval-rst}
.. automodule:: pain001_mcp._schemes
   :members:
   :undoc-members:
   :show-inheritance:
```

### Example corpus tools

```{eval-rst}
.. automodule:: pain001_mcp._corpus
   :members:
   :undoc-members:
   :show-inheritance:
```

### Faces tools

```{eval-rst}
.. automodule:: pain001_mcp._faces
   :members:
   :undoc-members:
   :show-inheritance:
```

### Staging tools

```{eval-rst}
.. automodule:: pain001_mcp._staging
   :members:
   :undoc-members:
   :show-inheritance:
```

### Clearing simulation

```{eval-rst}
.. automodule:: pain001_mcp._clearing
   :members:
   :undoc-members:
   :show-inheritance:
```

### Result shapes

```{eval-rst}
.. automodule:: pain001_mcp._shapes
   :members:
   :undoc-members:
   :show-inheritance:
```
