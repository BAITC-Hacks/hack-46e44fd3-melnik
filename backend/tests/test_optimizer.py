from time import perf_counter

import pytest

from backend.app.data import MEASURE_BY_ID
from backend.app.optimizer import search_scenarios
from backend.app.schemas import Selection
from backend.app.simulator import simulate, validate_selections


def _ids(result: dict) -> set[str]:
    return {item["measure_id"] for item in result["selections"]}


def test_unconstrained_search_finds_reference_maximum() -> None:
    result = search_scenarios(limit=1)[0]

    assert round(result["score"], 2) == 57.24
    assert result["cost"] == 98
    assert _ids(result) == {"M2", "M3", "M8", "M9", "M14"}
    districts = {
        item["measure_id"]: item["district_id"] for item in result["selections"]
    }
    assert districts["M3"] == districts["M8"] == districts["M9"] == "nura"


def test_excluded_measure_never_appears() -> None:
    results = search_scenarios({"exclude": ["M3"]}, limit=5)

    assert results
    assert all("M3" not in _ids(result) for result in results)


def test_required_direction_is_present() -> None:
    results = search_scenarios({"require_directions": ["Экология"]}, limit=5)

    assert results
    assert all(
        any(
            MEASURE_BY_ID[item_id]["direction"] == "Экология"
            for item_id in _ids(result)
        )
        for result in results
    )


def test_required_placement_is_exact_and_valid() -> None:
    results = search_scenarios(
        {"require_placements": [{"measure_id": "M8", "district_id": "nura"}]},
        limit=3,
    )

    assert results
    for result in results:
        assert {"measure_id": "M8", "district_id": "nura"} in result["selections"]
        assert simulate(result["selections"]).valid


def test_results_are_revalidated_by_simulator() -> None:
    results = search_scenarios({"require_measures": ["M4"], "exclude": ["M3"]}, limit=3)

    assert len(results) == 3
    for result in results:
        selections = [Selection.model_validate(item) for item in result["selections"]]
        assert validate_selections(selections) is None
        recalculated = simulate(selections)
        assert recalculated.valid
        assert result["score"] == pytest.approx(recalculated.score)
        assert result["delta"] == pytest.approx(recalculated.delta)
        assert result["cost"] == recalculated.cost_total


def test_min_cost_can_be_selected_via_constraints() -> None:
    results = search_scenarios({"objective": "min_cost"}, limit=3)

    assert results
    assert [result["cost"] for result in results] == sorted(
        result["cost"] for result in results
    )


def test_full_search_finishes_in_reasonable_time() -> None:
    started = perf_counter()
    search_scenarios(limit=1)
    elapsed = perf_counter() - started

    assert elapsed < 5.0
