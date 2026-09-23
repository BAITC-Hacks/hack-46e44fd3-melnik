import re

import pytest
from fastapi.testclient import TestClient

from backend.app.advisor import _fallback_parse, advise
from backend.app.data import MEASURE_BY_ID
from backend.app.main import app
from backend.app.simulator import simulate
from backend.tests.test_simulator import EXAMPLE


def _candidate_ids(candidate: dict) -> set[str]:
    return {item["measure_id"] for item in candidate["scenario"]}


def test_fallback_interprets_constraints_and_uses_verified_numbers(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = advise(EXAMPLE, "Без ЛРТ и обязательно с экологией")

    assert result["source"] == "deterministic_fallback"
    assert result["parsed_constraints"]["exclude"] == ["M3"]
    assert result["parsed_constraints"]["require_directions"] == ["Экология"]
    assert len(result["candidates"]) == 3
    for candidate in result["candidates"]:
        assert "M3" not in _candidate_ids(candidate)
        assert any(
            MEASURE_BY_ID[measure_id]["direction"] == "Экология"
            for measure_id in _candidate_ids(candidate)
        )
        recalculated = simulate(candidate["scenario"])
        assert recalculated.valid
        assert candidate["score"] == pytest.approx(recalculated.score)
        assert candidate["cost"] == recalculated.cost_total

    best = result["candidates"][0]
    allowed_numbers = {
        f"{best['score']:.2f}",
        str(best["cost"]),
        f"{best['diff_vs_current']['score_delta']:+.2f}",
    }
    numbers_in_text = set(re.findall(r"[+-]?\d+(?:\.\d+)?", result["recommendation_text"]))
    assert numbers_in_text
    assert numbers_in_text <= allowed_numbers


def test_advise_api_returns_candidates_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = TestClient(app).post(
        "/api/advise",
        json={
            "current_scenario": EXAMPLE,
            "message": "без ЛРТ, оставь экологию",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "deterministic_fallback"
    assert payload["candidates"]
    assert all("M3" not in _candidate_ids(candidate) for candidate in payload["candidates"])


@pytest.mark.parametrize(
    ("message", "measure_id"),
    [
        ("парк в Есиле", "M4"),
        ("смог в Нуре", "M5"),
        ("озеленение", "M6"),
        ("школа в Алматы", "M7"),
        ("поликлиника в Нуре", "M8"),
        ("спорт во дворе", "M9"),
        ("освещение в Байконуре", "M10"),
        ("переход у школы", "M11"),
        ("обращения жителей", "M12"),
        ("трубы в Алматы", "M13"),
        ("аварийные бригады", "M14"),
        ("автобус в Есиле", "M1"),
        ("светофоры в Есиле", "M2"),
        ("без ЛРТ", "M3"),
    ],
)
def test_fallback_maps_catalog_keywords(message, measure_id):
    parsed = _fallback_parse(message)
    assert parsed["recognized"] is True
    assert measure_id in parsed["require_measures"] or any(
        placement["measure_id"] == measure_id for placement in parsed["require_placements"]
    ) or measure_id in parsed["exclude"]


def test_fallback_places_district_measure_in_named_district():
    parsed = _fallback_parse("Поликлиника в Нуре")

    assert parsed["require_placements"] == [{"measure_id": "M8", "district_id": "nura"}]
    assert "M8" not in parsed["require_measures"]


def test_unrecognized_request_says_unrecognized_and_shows_unconstrained_best(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = advise(EXAMPLE, "Расскажи, что происходит с погодой")

    assert result["candidates"]
    assert "Не удалось распознать условие" in result["recommendation_text"]
