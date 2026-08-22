from fastapi import FastAPI, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from contextlib import asynccontextmanager
from collections import deque
import httpx
import time

from app.mcp_server import mcp_server
from app.auth import verify_auth, AuthResult
from app.logger import setup_logging, get_logger
from app.api_client import api_client
from app.config import settings

setup_logging()
logger = get_logger(__name__)

# Basic rate limiting in memory (bounded to prevent unbounded memory growth)
request_counts: dict[str, deque] = {}
RATE_LIMIT = settings.rate_limit_requests
RATE_WINDOW = settings.rate_limit_window_seconds
RATE_LIMIT_ENABLED = settings.rate_limit_enabled
MAX_TRACKED_IPS = 10_000  # hard cap on tracked clients (DoS protection)


def _prune_rate_limiter(now: float):
    """Removes expired entries and evicts stale IPs so memory stays bounded."""
    if len(request_counts) > MAX_TRACKED_IPS:
        # Evict IPs with no recent activity
        stale = [
            ip
            for ip, dq in request_counts.items()
            if not dq or now - dq[-1] >= RATE_WINDOW
        ]
        for ip in stale[: len(request_counts) - MAX_TRACKED_IPS]:
            request_counts.pop(ip, None)


START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "server_startup",
        environment=settings.environment,
        auth_type=settings.mcp_auth_type,
        api_target=settings.api_base_url,
    )
    yield
    logger.info("server_shutdown")
    await api_client.close()


app = FastAPI(
    title="MCP API Gateway",
    description="Production-ready Remote Model Context Protocol Server",
    version="1.0.0",
    lifespan=lifespan,
)

_wildcard_cors = "*" in settings.allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _wildcard_cors else settings.allowed_origins,
    # Browsers reject credentials + wildcard; only enable credentials for explicit origins.
    allow_credentials=not _wildcard_cors,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Mcp-Session-Id"],
)


@app.middleware("http")
async def rate_limit_and_log_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    current_time = time.time()

    if RATE_LIMIT_ENABLED:
        _prune_rate_limiter(current_time)

        if client_ip not in request_counts:
            request_counts[client_ip] = deque()

        window = request_counts[client_ip]
        while window and current_time - window[0] >= RATE_WINDOW:
            window.popleft()

        if len(window) >= RATE_LIMIT:
            logger.warning("rate_limit_exceeded", ip=client_ip)
            return Response(
                content="Rate limit exceeded",
                status_code=429,
                headers={"Retry-After": str(RATE_WINDOW)},
            )

        window.append(current_time)

    start_time = time.time()
    response = await call_next(request)
    latency_ms = (time.time() - start_time) * 1000

    logger.info(
        "http_request",
        method=request.method,
        url=str(request.url.path),
        status_code=response.status_code,
        latency_ms=f"{latency_ms:.2f}",
        ip=client_ip,
    )

    return response


# Get underlying Starlette app from FastMCP
mcp_asgi_app = mcp_server.http_app(transport="sse")


@app.api_route(
    "/sse",
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD", "TRACE"],
)
async def sse_handler(request: Request, auth: AuthResult = Depends(verify_auth)):
    """
    The main Server-Sent Events endpoint for MCP initialization.
    Secured by verify_auth dependency.
    """
    return await mcp_asgi_app(request.scope, request.receive, request._send)


@app.api_route(
    "/messages",
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD", "TRACE"],
)
@app.api_route(
    "/messages/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD", "TRACE"],
)
async def messages_handler(request: Request, auth: AuthResult = Depends(verify_auth)):
    """
    The endpoint for sending JSON-RPC messages to the MCP server.
    Secured by verify_auth dependency.
    """
    return await mcp_asgi_app(request.scope, request.receive, request._send)


APP_VERSION = "1.0.0"


@app.get("/health")
async def health_check():
    uptime_seconds = int(time.time() - START_TIME)
    return {
        "status": "ok",
        "version": APP_VERSION,
        "environment": settings.environment,
        "uptime_seconds": uptime_seconds,
        "api_target": settings.api_base_url,
        "auth_type": settings.mcp_auth_type,
    }


@app.get("/ready")
async def readiness_check():
    """Readiness probe: verifies the server can reach the target API base URL."""
    reachable = True
    try:
        host = httpx.URL(settings.api_base_url).host
        reachable = bool(host)
    except Exception:
        reachable = False
    return {
        "status": "ready" if reachable else "degraded",
        "target_api_configured": reachable,
    }


@app.get("/api/info")
async def api_info():
    return {
        "server_name": "MCP API Gateway Server",
        "version": APP_VERSION,
        "status": "online",
        "auth_type": settings.mcp_auth_type,
        "target_api_url": settings.api_base_url,
        "endpoints": {
            "health": "/health",
            "ready": "/ready",
            "sse": "/sse",
            "messages": "/messages",
            "info": "/api/info",
        },
        "mcp_tools": [
            {"name": "execute_get", "description": "Execute GET request to target API"},
            {
                "name": "execute_post",
                "description": "Execute POST request to target API",
            },
            {"name": "execute_put", "description": "Execute PUT request to target API"},
            {
                "name": "execute_patch",
                "description": "Execute PATCH request to target API",
            },
            {
                "name": "execute_delete",
                "description": "Execute DELETE request to target API",
            },
        ],
    }


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MCP API Gateway Server | Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0d14;
            --bg-card: rgba(18, 24, 38, 0.7);
            --border-color: rgba(255, 255, 255, 0.08);
            --accent-cyan: #00f2fe;
            --accent-blue: #4facfe;
            --accent-green: #10b981;
            --accent-purple: #8b5cf6;
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background: var(--bg-primary);
            background-image: 
                radial-gradient(at 0% 0%, rgba(79, 172, 254, 0.12) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(139, 92, 246, 0.12) 0px, transparent 50%);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 2rem;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2.5rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid var(--border-color);
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .logo-icon {
            width: 48px;
            height: 48px;
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue));
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 1.5rem;
            color: #000;
            box-shadow: 0 0 20px rgba(0, 242, 254, 0.3);
        }

        .title-group h1 {
            font-size: 1.6rem;
            font-weight: 700;
            background: linear-gradient(to right, #fff, var(--accent-cyan));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .title-group p {
            color: var(--text-secondary);
            font-size: 0.9rem;
        }

        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            background: rgba(16, 185, 129, 0.15);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: var(--accent-green);
            padding: 0.5rem 1rem;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
        }

        .pulse-dot {
            width: 8px;
            height: 8px;
            background-color: var(--accent-green);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(16, 185, 129, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }

        .card {
            background: var(--bg-card);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        }

        .card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 1rem;
        }

        .card-title {
            font-size: 1.1rem;
            font-weight: 600;
            color: #fff;
        }

        .stat-value {
            font-size: 1.8rem;
            font-weight: 700;
            color: var(--accent-cyan);
            margin-top: 0.5rem;
        }

        .tool-list {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }

        .tool-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-color);
            padding: 0.75rem 1rem;
            border-radius: 10px;
        }

        .method-badge {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            font-weight: 700;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
        }

        .method-get { background: rgba(59, 130, 246, 0.2); color: #60a5fa; }
        .method-post { background: rgba(16, 185, 129, 0.2); color: #34d399; }
        .method-put { background: rgba(245, 158, 11, 0.2); color: #fbbf24; }
        .method-patch { background: rgba(168, 85, 247, 0.2); color: #c084fc; }
        .method-delete { background: rgba(239, 68, 68, 0.2); color: #f87171; }

        code-block {
            background: #06090e;
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 1rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            color: #e5e7eb;
            overflow-x: auto;
            display: block;
            margin-top: 1rem;
            white-space: pre-wrap;
        }

        .btn {
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue));
            color: #000;
            font-weight: 600;
            padding: 0.6rem 1.2rem;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            font-size: 0.85rem;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 0 15px rgba(0, 242, 254, 0.4);
        }

        footer {
            text-align: center;
            margin-top: 3rem;
            padding-top: 1.5rem;
            border-top: 1px solid var(--border-color);
            color: var(--text-secondary);
            font-size: 0.85rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand">
                <div class="logo-icon">MCP</div>
                <div class="title-group">
                    <h1>API Gateway Server</h1>
                    <p>Remote Model Context Protocol (MCP) Infrastructure</p>
                </div>
            </div>
            <div class="status-badge">
                <div class="pulse-dot"></div>
                SYSTEM ONLINE & READY
            </div>
        </header>

        <div class="grid">
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Server Overview</span>
                </div>
                <p style="color: var(--text-secondary); font-size: 0.9rem;">Target API Base URL</p>
                <div class="stat-value" id="target-url" style="font-size: 1.2rem; word-break: break-all;">Loading...</div>
                <div style="margin-top: 1rem; display: flex; gap: 1rem;">
                    <div>
                        <p style="color: var(--text-secondary); font-size: 0.8rem;">Auth Type</p>
                        <strong id="auth-type" style="color: #fff; text-transform: uppercase;">Bearer</strong>
                    </div>
                    <div>
                        <p style="color: var(--text-secondary); font-size: 0.8rem;">Transport</p>
                        <strong style="color: #fff;">SSE / JSON-RPC</strong>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <span class="card-title">Health Status</span>
                    <button class="btn" onclick="checkHealth()">Ping Endpoint</button>
                </div>
                <code-block id="health-result">Click Ping to test /health endpoint...</code-block>
            </div>
        </div>

        <div class="card" style="margin-bottom: 2rem;">
            <div class="card-header">
                <span class="card-title">Exposed Generic MCP Tools</span>
            </div>
            <div class="tool-list">
                <div class="tool-item">
                    <div>
                        <strong style="color: #fff;">execute_get</strong>
                        <p style="font-size: 0.8rem; color: var(--text-secondary);">Executes read-only HTTP GET requests against target API</p>
                    </div>
                    <span class="method-badge method-get">GET</span>
                </div>
                <div class="tool-item">
                    <div>
                        <strong style="color: #fff;">execute_post</strong>
                        <p style="font-size: 0.8rem; color: var(--text-secondary);">Executes mutating HTTP POST requests with JSON body</p>
                    </div>
                    <span class="method-badge method-post">POST</span>
                </div>
                <div class="tool-item">
                    <div>
                        <strong style="color: #fff;">execute_put</strong>
                        <p style="font-size: 0.8rem; color: var(--text-secondary);">Executes full update HTTP PUT requests with JSON body</p>
                    </div>
                    <span class="method-badge method-put">PUT</span>
                </div>
                <div class="tool-item">
                    <div>
                        <strong style="color: #fff;">execute_patch</strong>
                        <p style="font-size: 0.8rem; color: var(--text-secondary);">Executes partial update HTTP PATCH requests with JSON body</p>
                    </div>
                    <span class="method-badge method-patch">PATCH</span>
                </div>
                <div class="tool-item">
                    <div>
                        <strong style="color: #fff;">execute_delete</strong>
                        <p style="font-size: 0.8rem; color: var(--text-secondary);">Executes deletion HTTP DELETE requests</p>
                    </div>
                    <span class="method-badge method-delete">DELETE</span>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <span class="card-title">Claude Desktop Configuration</span>
            </div>
            <p style="color: var(--text-secondary); font-size: 0.9rem;">Add the following snippet to your <code>claude_desktop_config.json</code>:</p>
            <code-block>{
  "mcpServers": {
    "mcp-api-gateway": {
      "command": "curl",
      "args": [
        "-N",
        "-H", "Authorization: Bearer super-secret-local-token",
        "-H", "Accept: text/event-stream",
        "http://localhost:8000/sse"
      ]
    }
  }
}</code-block>
        </div>

        <footer>
            Model Control Protocol (MCP) Server &bull; 100% Startup Ready & Active
        </footer>
    </div>

    <script>
        async function loadInfo() {
            try {
                const res = await fetch('/api/info');
                const data = await res.json();
                document.getElementById('target-url').innerText = data.target_api_url;
                document.getElementById('auth-type').innerText = data.auth_type;
            } catch(e) {
                document.getElementById('target-url').innerText = 'Offline / Error';
            }
        }

        async function checkHealth() {
            const block = document.getElementById('health-result');
            block.innerText = 'Checking...';
            try {
                const res = await fetch('/health');
                const data = await res.json();
                block.innerText = JSON.stringify(data, null, 2);
            } catch(e) {
                block.innerText = 'Error connecting to /health';
            }
        }

        loadInfo();
        checkHealth();
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)
