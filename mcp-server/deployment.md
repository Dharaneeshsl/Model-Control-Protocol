# Deployment Plan

## 1. Environment Variables
You'll need to set the following secrets in your deployment environment:

- `API_BASE_URL`: The URL of your target product API (e.g., `https://api.myproduct.com/v1`).
- `API_AUTH_TOKEN`: The token your MCP server uses to authenticate against your API.
- `MCP_AUTH_TYPE`: `bearer` or `oauth`.
- `MCP_BEARER_TOKEN`: If using bearer, a secure token for MCP clients (like Claude) to use.

## 2. Deploying to Fly.io
Fly.io is great for this because it automatically provisions TLS certificates and handles edge termination.

1. Install `flyctl`.
2. Run `fly launch` in the `mcp-server` directory.
   - It will detect the `Dockerfile`.
   - Set the internal port to 8000.
3. Set secrets:
   ```bash
   fly secrets set API_BASE_URL="https://api.myproduct.com/v1" API_AUTH_TOKEN="your-api-token" MCP_BEARER_TOKEN="super-secret-mcp-token"
   ```
4. Deploy:
   ```bash
   fly deploy
   ```

## 3. Deploying to a VPS (Caddy)
If deploying to a raw VPS, Caddy is highly recommended for automatic TLS and easy rate-limiting.

1. Install Docker on your VPS.
2. Run the MCP server container:
   ```bash
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
- **Rate Limiting**: A basic memory-based rate limiter is included in `app/main.py`. For production, use an API gateway or Caddy/Nginx rate-limiting modules.
- **Least-privilege**: If migrating to OAuth, `app/auth.py` demonstrates how to check for specific JWT scopes before allowing access.
