from fastapi import FastAPI, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import time

from app.mcp_server import mcp_server
from app.auth import verify_auth, AuthResult
from app.logger import setup_logging, get_logger
from app.api_client import api_client

setup_logging()
logger = get_logger(__name__)

# Basic rate limiting in memory (for simplicity and per instructions "rate-limit at the edge").
# If deployed on a VPS/Platform, the edge (e.g. Caddy/nginx/Fly.io) should do the real rate limiting.
# We include a basic token bucket or request counter here just in case.
request_counts = {}
RATE_LIMIT = 100 # requests per minute

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("server_startup")
    yield
    logger.info("server_shutdown")
    await api_client.close()

app = FastAPI(title="MCP API Gateway", lifespan=lifespan)

# Add CORS if needed (MCP clients typically run locally or specific origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def rate_limit_and_log_middleware(request: Request, call_next):
    # Basic rate limit check (very naive, strictly for demonstration)
    client_ip = request.client.host if request.client else "unknown"
    current_time = time.time()

    if client_ip not in request_counts:
        request_counts[client_ip] = []

    # Clean up old requests
    request_counts[client_ip] = [t for t in request_counts[client_ip] if current_time - t < 60]

    if len(request_counts[client_ip]) >= RATE_LIMIT:
        logger.warning("rate_limit_exceeded", ip=client_ip)
        return Response(content="Rate limit exceeded", status_code=429)

    request_counts[client_ip].append(current_time)

    # Proceed and log latency
    start_time = time.time()
    response = await call_next(request)
    latency_ms = (time.time() - start_time) * 1000

    logger.info(
        "http_request",
        method=request.method,
        url=str(request.url.path),
        status_code=response.status_code,
        latency_ms=f"{latency_ms:.2f}",
        ip=client_ip
    )

    return response

# Get the underlying Starlette app from FastMCP
mcp_asgi_app = mcp_server.http_app(transport="sse")

# We want to secure the MCP routes. We can do this by wrapping the ASGI app
# in a dependency or mounting it. FastAPI's mount doesn't easily apply Depends
# to the mounted app. Instead, we can intercept requests at the FastAPI level.

@app.api_route("/sse", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD", "TRACE"])
async def sse_handler(request: Request, auth: AuthResult = Depends(verify_auth)):
    """
    The main Server-Sent Events endpoint for MCP initialization.
    Secured by the verify_auth dependency.
    """
    # FastMCP uses the path directly in its Starlette app, we forward it.
    return await mcp_asgi_app(request.scope, request.receive, request._send)

@app.api_route("/messages", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD", "TRACE"])
async def messages_handler(request: Request, auth: AuthResult = Depends(verify_auth)):
    """
    The endpoint for sending JSON-RPC messages to the MCP server.
    Secured by the verify_auth dependency.
    """
    return await mcp_asgi_app(request.scope, request.receive, request._send)

@app.get("/health")
async def health_check():
    return {"status": "ok"}
