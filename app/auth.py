from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)
security = HTTPBearer(auto_error=False)

class AuthResult(BaseModel):
    user_id: str
    scopes: list[str] = []

async def verify_auth(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> AuthResult:
    """
    Verifies the incoming token based on the configured auth type.
    """
    auth_type = settings.mcp_auth_type

    if auth_type == "none":
        return AuthResult(user_id="anonymous", scopes=["*"])

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    if auth_type == "bearer":
        if not settings.mcp_bearer_token:
            logger.error("bearer_auth_configured_but_token_missing")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server configuration error"
            )
        if token != settings.mcp_bearer_token:
            logger.warning("invalid_bearer_token_provided")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return AuthResult(user_id="admin", scopes=["*"])

    if auth_type == "oauth":
        if not settings.oauth_jwks_url:
            logger.error("oauth_auth_configured_but_jwks_missing")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server configuration error"
            )

        try:
            # Setup JWKS client
            jwks_client = jwt.PyJWKClient(settings.oauth_jwks_url)
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            # Verify token
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=settings.oauth_audience,
                issuer=settings.oauth_issuer
            )

            # Extract basic info
            user_id = payload.get("sub", "unknown")
            scopes_str = payload.get("scope", "")
            scopes = scopes_str.split(" ") if scopes_str else []

            return AuthResult(user_id=user_id, scopes=scopes)

        except jwt.PyJWKClientError as e:
            logger.warning("oauth_jwks_fetch_error", error=str(e))
            raise HTTPException(status_code=500, detail="Unable to verify token")
        except jwt.InvalidTokenError as e:
            logger.warning("invalid_oauth_token", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unknown auth configuration"
    )

def require_scope(required_scope: str):
    """
    Dependency to enforce least-privilege scopes (useful for OAuth setups serving many users).
    """
    async def scope_checker(auth: AuthResult = Depends(verify_auth)):
        if "*" in auth.scopes:
            return auth

        if required_scope not in auth.scopes:
            logger.warning("scope_denied", required_scope=required_scope, provided_scopes=auth.scopes)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope: {required_scope}"
            )
        return auth
    return scope_checker
