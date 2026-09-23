from fastapi.testclient import TestClient

from backend.app.main import app
from backend.tests.test_simulator import EXAMPLE

client = TestClient(app)


def test_health_and_catalog():
    assert client.get("/health").json() == {"status": "ok"}
    catalog = client.get("/api/catalog")
    assert catalog.status_code == 200
    assert len(catalog.json()["measures"]) == 14
    assert round(catalog.json()["baseline"]["score"], 2) == 52.56


def test_simulate_api_reference_scenario():
    response = client.post("/api/simulate", json={"selections": EXAMPLE})
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert round(data["score"], 2) == 56.54
    assert data["cost_total"] == 95


def test_simulate_api_returns_human_reason():
    response = client.post("/api/simulate", json={"selections": EXAMPLE[:4]})
    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert "ровно 5" in response.json()["reason"]


def test_explain_recomputes_and_uses_fallback(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    simulation = client.post("/api/simulate", json={"selections": EXAMPLE}).json()
    simulation["score"] = 999  # tampering must not leak into the explanation
    response = client.post("/api/explain", json=simulation)
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "deterministic_fallback"
    assert "56.54" in data["summary"]
    assert "999" not in data["summary"]

