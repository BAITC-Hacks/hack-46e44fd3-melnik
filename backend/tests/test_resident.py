import re
from typing import Any

import pytest

from backend.app.resident import _fallback_match, propose_resident
from backend.app.simulator import simulate


def _text_values(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _text_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _text_values(item)


def test_polyclinic_in_nura_is_catalog_backed_and_verified(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = propose_resident("nura", "Поликлиника в Нуре")

    assert result["matched"] is True
    assert result["measure"]["id"] == "M8"
    assert result["district"]["id"] == "nura"
    assert {"measure_id": "M8", "district_id": "nura"} in result["plan"]["selections"]
    recalculated = simulate(result["plan"]["selections"])
    assert recalculated.valid
    assert result["plan"]["score"] == pytest.approx(recalculated.score)

    effects = result["evidence"]["measure_effects"]
    s2 = next(item for item in effects if item["indicator"] == "S2")
    contribution = next(
        item for item in recalculated.measure_contributions if item["measure_id"] == "M8"
    )
    assert s2["delta"] == pytest.approx(contribution["realized_effects"]["S2"])
    assert s2["before"] == 35
    assert s2["after"] == pytest.approx(43.75)


def test_unmatched_response_has_no_digits_in_text(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = propose_resident(None, "Хочу пляж и кинотеатр рядом")

    assert result["matched"] is False
    assert result["alternatives"]
    assert all(re.search(r"\d", text) is None for text in _text_values(result))


@pytest.mark.parametrize(
    ("message", "expected_measure"),
    [
        ("Темно на улицах", "M10"),
        ("Плохой воздух", "M5"),
    ],
)
def test_demo_chip_keyword_fallback(message: str, expected_measure: str) -> None:
    assert _fallback_match(message) == expected_measure


@pytest.mark.parametrize(
    ("message", "measure_id", "district_id"),
    [
        ("В Нуре не хватает поликлиник", "M8", "nura"),
        ("Больше зелени в Сарыарке", "M4", "saryarka"),
    ],
)
def test_district_in_text_produces_verified_plan(
    monkeypatch, message: str, measure_id: str, district_id: str
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = propose_resident(None, message)

    assert result["matched"] is True
    assert result["measure"]["id"] == measure_id
    assert result["district"]["id"] == district_id
    assert result["district_hint"] is None
    assert {"measure_id": measure_id, "district_id": district_id} in result["plan"]["selections"]
    assert result["plan"]["score"] == pytest.approx(
        simulate(result["plan"]["selections"]).score
    )


def test_explicit_district_overrides_text(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = propose_resident("esil", "В Нуре не хватает поликлиник")

    assert result["matched"] is True
    assert result["district"]["id"] == "esil"
    assert result["district_hint"] == {"id": "nura", "name": "Нура"}


@pytest.mark.parametrize("district_id", [None, "nura", "esil", "saryarka", "baikonur", "almaty"])
def test_aquapark_is_not_catalog_park(monkeypatch, district_id: str | None) -> None:
    monkeypatch.setattr(
        "backend.app.resident._llm_match",
        lambda message: ("M4", "Сомнительное совпадение"),
    )

    result = propose_resident(district_id, "Хочу аквапарк на Луне")

    assert result["matched"] is False
    assert result["measure"] is None
    assert result["evidence"] is None
    assert result["plan"] is None
    assert "Такой меры нет в каталоге симулятора" in result["appeal"]["body"]
    assert all(re.search(r"\d", text) is None for text in _text_values(result))


def test_found_measure_without_district_requests_selection(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = propose_resident(None, "Не хватает поликлиник")

    assert result["matched"] is False
    assert result["needs_district"] is True
    assert result["measure"]["id"] == "M8"
    assert result["plan"] is None
    assert result["evidence"] is None
    assert "Нашли меру" in result["appeal"]["title"]
    assert "Выберите район" in result["appeal"]["body"]
