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
