FROM python:3.11-slim AS base

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

ARG PIP_EXTRA_INDEX_URL=""
ENV PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL}

RUN pip install --no-cache-dir .

ENV MCP_TRANSPORT=http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

EXPOSE 8080

ENTRYPOINT ["mcp-artifacts"]
