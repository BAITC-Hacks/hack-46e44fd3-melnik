from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_public_search_returns_verified_global_maximum():
    response = client.post(
        "/api/search",
        json={"constraints": {}, "objective": "max_score", "limit": 1},
    )

    assert response.status_code == 200
    candidate = response.json()["candidates"][0]
    assert round(candidate["score"], 2) == 57.24
    replay = client.post(
        "/api/simulate", json={"selections": candidate["selections"]}
    ).json()
    assert replay["valid"] is True
    assert replay["score"] == candidate["score"]
    assert replay["cost_total"] == candidate["cost"]


def test_public_search_rejects_invalid_input_with_human_reason():
    response = client.post(
        "/api/search",
        json={"constraints": {"require_measures": ["M404"]}, "limit": 1},
    )

    assert response.status_code == 400
    assert "Неизвестные мероприятия" in response.json()["detail"]


def test_llms_txt_is_plain_text_and_mentions_simulate():
    response = client.get("/llms.txt")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "/api/simulate" in response.text
    assert "Не вычисляй Score сам" in response.text
