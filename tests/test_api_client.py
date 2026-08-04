import pytest
import httpx
from unittest.mock import patch, MagicMock

from app.api_client import APIClient, APIClientError

@pytest.fixture
def mock_httpx_client():
    with patch("app.api_client.httpx.AsyncClient") as mock_client:
        client_instance = MagicMock()
        mock_client.return_value = client_instance

        # We also need to patch __aenter__ and __aexit__ if using context managers,
        # but here we mock the request method directly.

        async def mock_aclose():
            pass
        client_instance.aclose = mock_aclose

        yield client_instance

@pytest.mark.asyncio
async def test_get_success(mock_httpx_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.json.return_value = {"id": 1, "name": "Test"}

    async def mock_request(*args, **kwargs):
        return mock_response
    mock_httpx_client.request = mock_request

    client = APIClient()
    client.client = mock_httpx_client # inject the mock directly

    result = await client.get("/test")
    assert result == {"id": 1, "name": "Test"}

@pytest.mark.asyncio
async def test_400_error_no_retry(mock_httpx_client):
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"

    # raise_for_status mock
    def mock_raise():
        raise httpx.HTTPStatusError("400 Bad Request", request=MagicMock(), response=mock_response)
    mock_response.raise_for_status = mock_raise

    async def mock_request(*args, **kwargs):
        return mock_response
    mock_httpx_client.request = mock_request

    client = APIClient()
    client.client = mock_httpx_client

    with pytest.raises(APIClientError) as exc_info:
        await client.get("/error")

    assert "Client error (400)" in str(exc_info.value)
