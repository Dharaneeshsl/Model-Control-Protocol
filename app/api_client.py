import httpx
from tenacity import AsyncRetrying, wait_exponential, stop_after_attempt, retry_if_exception_type
from typing import Any, Dict, Optional
import time

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

class APIClientError(Exception):
    """Base exception for API client errors."""
    pass

class APIClient:
    """
    A generic async HTTP client for communicating with the target product API.
    Handles retries, timeouts, and logging.
    """
    def __init__(self):
        self.base_url = settings.api_base_url.rstrip("/")
        headers = {"Content-Type": "application/json"}
        if settings.api_auth_token:
            headers["Authorization"] = f"Bearer {settings.api_auth_token}"

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(10.0, connect=5.0) # 10s general timeout, 5s connect timeout
        )

    async def close(self):
        await self.client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """
        Executes an HTTP request with exponential backoff retries.
        """
        url_path = f"/{path.lstrip('/')}"

        # Retry logic: up to 3 attempts, waiting 1, 2, 4 seconds between attempts
        # Only retry on specific network/server errors
        retryer = AsyncRetrying(
            wait=wait_exponential(multiplier=1, min=1, max=10),
            stop=stop_after_attempt(3),
            retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
            reraise=True
        )

        try:
            async for attempt in retryer:
                with attempt:
                    start_time = time.time()
                    try:
                        response = await self.client.request(method, url_path, **kwargs)
                        response.raise_for_status() # Raise exception for 4xx/5xx status codes

                        latency = (time.time() - start_time) * 1000
                        logger.info("api_request_success",
                                    method=method,
                                    path=url_path,
                                    status=response.status_code,
                                    latency_ms=f"{latency:.2f}")

                        # Return JSON if possible, otherwise text
                        if response.headers.get("Content-Type", "").startswith("application/json"):
                            return response.json()
                        return {"text_response": response.text}
                    except httpx.HTTPStatusError as e:
                        # Log error details before potentially retrying (if 5xx) or raising (if 4xx)
                        logger.warning("api_request_status_error",
                                    method=method,
                                    path=url_path,
                                    status=e.response.status_code,
                                    error=str(e),
                                    response_body=e.response.text)

                        # Do not retry on 4xx client errors (except perhaps 429)
                        if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                            raise APIClientError(f"Client error ({e.response.status_code}): {e.response.text}") from e

                        raise # Will be caught by tenacity to potentially retry

                    except httpx.RequestError as e:
                        logger.warning("api_request_network_error",
                                    method=method,
                                    path=url_path,
                                    error=str(e))
                        raise
        except APIClientError:
            raise
        except Exception as e:
            logger.error("api_request_failed", method=method, path=url_path, error=str(e))
            raise APIClientError(f"Request failed: {str(e)}") from e

    # Helper methods for generic HTTP actions
    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return await self._request("POST", path, json=json)

    async def put(self, path: str, json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return await self._request("PUT", path, json=json)

    async def delete(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return await self._request("DELETE", path, params=params)

# Singleton instance
api_client = APIClient()
