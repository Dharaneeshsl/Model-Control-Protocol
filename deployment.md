# Deployment Plan

## 1. Environment Variables
You'll need to set the following secrets in your deployment environment (see `.env.example` for the full list):

- `API_BASE_URL`: The URL of your target product API (e.g., `https://api.myproduct.com/v1`).
- `API_AUTH_TOKEN`: The token your MCP server uses to authenticate against your API.
- `MCP_AUTH_TYPE`: `bearer` or `oauth`.
- `MCP_BEARER_TOKEN`: If using bearer, a secure token for MCP clients (like Claude). Generate one: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
- `ENVIRONMENT=production`: **Required in production.** Enables fail-fast safety checks at boot.
- `CORS_ALLOWED_ORIGINS`: Comma-separated explicit origins (avoid `*` in production).

> **Production fail-fast:** with `ENVIRONMENT=production`, the server refuses to start if auth is misconfigured or the default local bearer token is still in use.

## 2. Pre-Flight Check
Before/after deploying, verify everything works with the one-shot boot check:

```bash
python verify_boot.py
```

It boots the server, probes `/health`, `/ready`, `/api/info`, the dashboard, auth rejection (401s), and a live SSE MCP handshake — then shuts down cleanly.

## 3. Deploying to Fly.io
Fly.io is great for this because it automatically provisions TLS certificates and handles edge termination.

1. Install `flyctl`.
2. Run `fly launch` in the project directory.
   - It will detect the `Dockerfile` (which includes a built-in `HEALTHCHECK`).
   - Set the internal port to 8000.
3. Set secrets:
   ```bash
   fly secrets set API_BASE_URL="https://api.myproduct.com/v1" API_AUTH_TOKEN="your-api-token" MCP_BEARER_TOKEN="super-secret-mcp-token" ENVIRONMENT=production
   ```
4. Deploy:
   ```bash
   fly deploy
   ```

## 4. Deploying to a VPS (Caddy)
If deploying to a raw VPS, Caddy is highly recommended for automatic TLS and easy rate-limiting.

1. Install Docker on your VPS.
2. Build and run the MCP server container:
   ```bash
   docker build -t mcp-server-image .
   docker run -d -p 8000:8000 --env-file .env --name mcp-server mcp-server-image
   ```
3. Install Caddy.
4. Configure `/etc/caddy/Caddyfile`:

```caddyfile
mcp.yourdomain.com {
    # Simple rate limiting plugin (if installed) or rely on the Python app's basic limit
    reverse_proxy localhost:8000 {
        header_up Host {host}
        header_up X-Real-IP {remote}
    }
}
```

## Security Best Practices Enforced
- **TLS**: Required at the edge (handled by Fly.io or Caddy). The server accepts `X-Forwarded-*` headers correctly via uvicorn.
- **Fail-fast config validation**: Production mode refuses insecure startup configurations.
- **Hardened CORS**: Explicit origin allowlist; wildcard mode auto-disables credentials; methods/headers restricted to what MCP needs.
- **Bounded Rate Limiting**: Per-IP sliding window with hard caps on tracked clients (memory-safe), plus `Retry-After` headers on 429 responses.
- **Non-root container**: Docker runs as an unprivileged user with a built-in healthcheck.
- **Least-privilege**: If migrating to OAuth, `app/auth.py` demonstrates how to check for specific JWT scopes before allowing access.
