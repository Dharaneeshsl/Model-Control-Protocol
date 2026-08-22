import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings


class TestServer(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_check(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("uptime_seconds", data)
        self.assertIn("version", data)
        self.assertIn("environment", data)

    def test_readiness_check(self):
        response = self.client.get("/ready")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("status", data)
        self.assertTrue(data["target_api_configured"])

    def test_dashboard_endpoint(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("MCP API Gateway Server", response.text)

    def test_api_info_endpoint(self):
        response = self.client.get("/api/info")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["server_name"], "MCP API Gateway Server")
        self.assertEqual(data["status"], "online")
        self.assertIn("mcp_tools", data)

    def test_sse_endpoint_unauthorized(self):
        response = self.client.get("/sse")
        self.assertEqual(response.status_code, 401)
