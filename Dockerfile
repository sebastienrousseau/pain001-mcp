# syntax=docker/dockerfile:1.6
# Multi-stage build for a minimal pain001-mcp image.
#
# The container runs the FastMCP server over stdio so an MCP client can
# launch it directly with ``docker run -i --rm pain001-mcp``.

FROM python:3.12-slim AS builder

WORKDIR /build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --upgrade pip poetry

COPY pyproject.toml ./
COPY pain001_mcp ./pain001_mcp

# Install pain001 from source (it is not yet published to PyPI), then
# layer this package on top inside a self-contained virtualenv.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install \
        "git+https://github.com/sebastienrousseau/pain001.git@feat/v0.0.52" \
    && /opt/venv/bin/pip install .


FROM python:3.12-slim

LABEL org.opencontainers.image.title="pain001-mcp" \
      org.opencontainers.image.description="Model Context Protocol server for the pain001 ISO 20022 library." \
      org.opencontainers.image.source="https://github.com/sebastienrousseau/pain001-mcp" \
      org.opencontainers.image.licenses="Apache-2.0"

# Non-root user (MCP clients launch the container with stdio; no extra
# privileges needed).
RUN groupadd --system mcp && useradd --system --gid mcp --home /home/mcp mcp \
    && mkdir -p /home/mcp \
    && chown -R mcp:mcp /home/mcp

COPY --from=builder /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER mcp
WORKDIR /home/mcp

# A non-zero exit here means an import / dependency mismatch; the MCP
# client will see it before the first tool call.
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import pain001_mcp.server" || exit 1

ENTRYPOINT ["pain001-mcp"]
