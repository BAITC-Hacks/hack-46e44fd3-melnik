from fastapi.testclient import TestClient

from backend.app.main import app
from backend.tests.test_simulator import EXAMPLE

client = TestClient(app)


def test_health_and_catalog():
    assert client.get("/health").json() == {"status": "ok"}
    catalog = client.get("/api/catalog")
    assert catalog.status_code == 200
    assert len(catalog.json()["measures"]) == 14
    baseline = catalog.json()["baseline"]
    assert round(baseline["score"], 2) == 52.56
    assert len(baseline["district_scores"]) == 5
    assert baseline["min_district"] in baseline["district_scores"]
    assert baseline["critical_cells"] == [
        {"district_id": "nura", "indicator": "S1"},
        {"district_id": "nura", "indicator": "S2"},
    ]


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


def test_trajectory_api_matches_simulation_at_quarter_eight():
    baseline = client.get("/api/trajectory")
    assert baseline.status_code == 200
    assert len(baseline.json()) == 8
    assert all(round(point["score"], 2) == 52.56 for point in baseline.json())

    response = client.post("/api/trajectory", json={"selections": EXAMPLE})
    assert response.status_code == 200
    assert round(response.json()[-1]["score"], 5) == 56.54307


def test_indicator_visualization_assets_are_served():
    for path in (
        "/matrix.js",
        "/radar.js",
        "/insights.css",
        "/static/theme.js",
        "/static/vendor/chart.umd.min.js",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response.content


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


def test_resident_proposal_api_uses_verified_catalog_measure(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = client.post(
        "/api/resident/propose",
        json={"district_id": "nura", "message": "Поликлиника в Нуре"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["matched"] is True
    assert data["measure"]["id"] == "M8"
    assert data["district"]["id"] == "nura"
    assert data["evidence"]["measure_effects"][0]["indicator"] == "S2"
    replay = client.post("/api/simulate", json={"selections": data["plan"]["selections"]})
    assert replay.json()["score"] == data["plan"]["score"]
