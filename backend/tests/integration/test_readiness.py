from unittest.mock import patch

from fastapi.testclient import TestClient


def test_readiness_healthy(client: TestClient):
    with patch(
        "app.api.v1.endpoints.readiness.check_database_connectivity",
        return_value=(True, 1.25, None),
    ):
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"]["status"] == "connected"
        assert data["database"]["latency_ms"] == 1.25
        assert data["database"]["error"] is None


def test_readiness_unhealthy(client: TestClient):
    with patch(
        "app.api.v1.endpoints.readiness.check_database_connectivity",
        return_value=(False, 25.4, "FATAL: connection to server on socket failed"),
    ):
        response = client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"]["status"] == "disconnected"
        assert data["database"]["latency_ms"] == 25.4
        assert "connection to server" in data["database"]["error"]


def test_api_v1_readiness_route(client: TestClient):
    with patch(
        "app.api.v1.endpoints.readiness.check_database_connectivity",
        return_value=(True, 0.85, None),
    ):
        response = client.get("/api/v1/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
