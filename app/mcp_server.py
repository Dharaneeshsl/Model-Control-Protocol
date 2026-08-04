from typing import Any, Dict, Optional
from fastmcp import FastMCP
from pydantic import BaseModel, Field

from app.api_client import api_client
from app.logger import get_logger

logger = get_logger(__name__)

# Initialize the FastMCP server
mcp_server = FastMCP(
    "API Gateway Server"
)

# -----------------------------------------------------------------------------
# Generic API Tools
# Instead of hardcoding 1:1 endpoints, we provide generic tools that allow
# Claude to interact with the API endpoints intelligently.
# -----------------------------------------------------------------------------

@mcp_server.tool()
async def execute_get(
    path: str = Field(..., description="The API endpoint path to request (e.g., 'users', 'projects/123')."),
    query_params: Optional[Dict[str, Any]] = Field(None, description="Optional query parameters to include in the request.")
) -> str:
    """
    Executes a read-only GET request against the API.
    Use this to fetch lists of items or specific details of a resource.
    """
    logger.info("tool_execute_get_called", path=path, query_params=query_params)
    try:
        result = await api_client.get(path, params=query_params)
        return f"Success: {result}"
    except Exception as e:
        logger.error("tool_execute_get_error", path=path, error=str(e))
        return f"Error: {str(e)}"

@mcp_server.tool()
async def execute_post(
    path: str = Field(..., description="The API endpoint path to request (e.g., 'tasks')."),
    payload: Dict[str, Any] = Field(..., description="The JSON payload to send in the request body.")
) -> str:
    """
    Executes a mutating POST request against the API.
    Use this to create new resources.
    Requires write permissions if scopes are enforced.
    """
    logger.info("tool_execute_post_called", path=path, payload=payload)
    try:
        result = await api_client.post(path, json=payload)
        return f"Success: {result}"
    except Exception as e:
        logger.error("tool_execute_post_error", path=path, error=str(e))
        return f"Error: {str(e)}"

@mcp_server.tool()
async def execute_put(
    path: str = Field(..., description="The API endpoint path to request (e.g., 'tasks/123')."),
    payload: Dict[str, Any] = Field(..., description="The JSON payload to send in the request body.")
) -> str:
    """
    Executes a mutating PUT request against the API.
    Use this to update existing resources.
    Requires write permissions if scopes are enforced.
    """
    logger.info("tool_execute_put_called", path=path, payload=payload)
    try:
        result = await api_client.put(path, json=payload)
        return f"Success: {result}"
    except Exception as e:
        logger.error("tool_execute_put_error", path=path, error=str(e))
        return f"Error: {str(e)}"

@mcp_server.tool()
async def execute_delete(
    path: str = Field(..., description="The API endpoint path to request (e.g., 'tasks/123')."),
    query_params: Optional[Dict[str, Any]] = Field(None, description="Optional query parameters.")
) -> str:
    """
    Executes a mutating DELETE request against the API.
    Use this to remove resources.
    Requires write permissions if scopes are enforced.
    """
    logger.info("tool_execute_delete_called", path=path, query_params=query_params)
    try:
        result = await api_client.delete(path, params=query_params)
        return f"Success: {result}"
    except Exception as e:
        logger.error("tool_execute_delete_error", path=path, error=str(e))
        return f"Error: {str(e)}"
