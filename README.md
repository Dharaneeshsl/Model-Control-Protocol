# MCP API Gateway Server

A production-ready remote Model Context Protocol (MCP) server that exposes a generic REST API to AI agents (like Claude Desktop).

## Architecture
- **Framework:** FastAPI wrapping FastMCP.
- **Transport:** SSE (`streamable-http`).
- **Resilience:** HTTP requests are retried using exponential backoff (via `tenacity`).
- **Observability:** Structured JSON logging (via `structlog`) ready for OpenTelemetry.
- **Security:** Bearer/OAuth auth, hardened CORS, bounded in-memory rate limiting, production boot-time safety checks.

## Generic Tools vs 1:1 Mapping
Instead of hardcoding a tool for every endpoint in your API, this server exposes *generic* tools (`execute_get`, `execute_post`, `execute_put`, `execute_patch`, `execute_delete`). This leverages the LLM's reasoning capabilities.
To customize this for *your specific API tools*, modify `app/mcp_server.py`. You can explicitly define tools that wrap `api_client.get('/your-specific-endpoint')`.

## Running Locally

1. Install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in your values.
3. Run the server:
   ```bash
   uvicorn app.main:app --reload
   ```

## Endpoints

| Endpoint   | Purpose                                            | Auth     |
|------------|----------------------------------------------------|----------|
| `/`        | Live status dashboard (HTML)                       | Public   |
| `/health`  | Liveness probe (status, version, uptime)           | Public   |
| `/ready`   | Readiness probe (target API configuration check)   | Public   |
| `/api/info`| Server metadata + tool registry                    | Public   |
| `/sse`     | MCP SSE transport (Claude/agents connect here)     | Required |
| `/messages`| MCP JSON-RPC message channel                       | Required |

## Production Safety Features
- **Fail-fast boot:** with `ENVIRONMENT=production`, the server refuses to start unless `MCP_AUTH_TYPE=bearer` and a unique `MCP_BEARER_TOKEN` is set (no default-token accidents).
- **Hardened CORS:** explicit origins via `CORS_ALLOWED_ORIGINS` (comma-separated). Wildcard mode automatically disables credentials.
- **Bounded rate limiting:** per-IP sliding window with hard caps on tracked clients (no memory-leak DoS vector), configurable via `RATE_LIMIT_*` vars.
- **Container healthcheck:** built into the `Dockerfile` (`HEALTHCHECK` hitting `/health`).

## Verify a Deployment (Boot Check)

Run the one-shot live verification — it boots the real server, probes every endpoint (health, readiness, info, dashboard, auth rejection, SSE MCP handshake), then shuts down cleanly:

```bash
python verify_boot.py
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## Local Testing with MCP Inspector

You can test the SSE transport locally using the MCP Inspector.

```bash
npx @modelcontextprotocol/inspector
```
Connect to `http://localhost:8000/sse` using the SSE transport type.

## Connecting Claude Desktop

Once deployed (e.g., to `https://mcp.yourdomain.com`), configure your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "my-product-api": {
      "command": "curl",
      "args": [
        "-N",
        "-H", "Authorization: Bearer secret-token-for-claude",
        "-H", "Accept: text/event-stream",
        "https://mcp.yourdomain.com/sse"
      ]
    }
  }
}
```

## Deployment
See `deployment.md` for instructions on deploying to Fly.io or a VPS.
