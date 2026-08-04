# MCP API Gateway Server

A production-ready remote Model Context Protocol (MCP) server that exposes a generic REST API to AI agents (like Claude Desktop).

## Architecture
- **Framework:** FastAPI wrapping FastMCP.
- **Transport:** SSE (`streamable-http`).
- **Resilience:** HTTP requests are retried using exponential backoff (via `tenacity`).
- **Observability:** Structured JSON logging (via `structlog`) ready for OpenTelemetry.

## Generic Tools vs 1:1 Mapping
Instead of hardcoding a tool for every endpoint in your API, this server exposes *generic* tools (`execute_get`, `execute_post`, `execute_put`, `execute_delete`). This leverages the LLM's reasoning capabilities.
To customize this for *your specific API tools*, modify `app/mcp_server.py`. You can explicitly define tools that wrap `api_client.get('/your-specific-endpoint')`.

## Running Locally

1. Install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. Create a `.env` file (or just rely on defaults):
   ```ini
   API_BASE_URL=https://your-api.example.com
   API_AUTH_TOKEN=your-target-api-token
   MCP_AUTH_TYPE=bearer
   MCP_BEARER_TOKEN=secret-token-for-claude
   ```
3. Run the server:
   ```bash
   uvicorn app.main:app --reload
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
