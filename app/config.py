from typing import Literal, Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    Configuration settings for the MCP Server.
    Can be configured via environment variables.
    """
    # Target API configuration
    api_base_url: str = "https://api.example.com/v1"

    # MCP Server authentication (How clients authenticate to this server)
    mcp_auth_type: Literal["bearer", "oauth", "none"] = "bearer"
    mcp_bearer_token: Optional[str] = "super-secret-local-token"

    # For OAuth (if mcp_auth_type == "oauth")
    oauth_jwks_url: Optional[str] = None
    oauth_audience: Optional[str] = None
    oauth_issuer: Optional[str] = None

    # Target API Authentication (How this server authenticates to the target API)
    # E.g., placing this in the Authorization header.
    api_auth_token: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
