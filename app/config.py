from typing import List, Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    api_auth_token: Optional[str] = None

    # CORS / network hardening
    # Comma-separated list, e.g. "https://app.example.com,https://admin.example.com"
    # Use "*" only for local development (credentials are disabled automatically then).
    cors_allowed_origins: str = "*"

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100  # requests...
    rate_limit_window_seconds: int = 60  # ...per this window, per client IP

    # Runtime environment: "development" or "production"
    environment: Literal["development", "production"] = "development"

    @property
    def allowed_origins(self) -> List[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()

# Fail fast in production if auth is misconfigured (prevents silently-open servers)
if settings.is_production:
    if settings.mcp_auth_type != "bearer" or not settings.mcp_bearer_token:
        raise RuntimeError(
            "PRODUCTION SAFETY: MCP_AUTH_TYPE must be 'bearer' with a strong MCP_BEARER_TOKEN set."
        )
    if settings.mcp_bearer_token == "super-secret-local-token":
        raise RuntimeError(
            "PRODUCTION SAFETY: Refusing to start with the default local bearer token. Set a unique MCP_BEARER_TOKEN."
        )
