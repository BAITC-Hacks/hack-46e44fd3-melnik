import pytest

from backend.app.simulator import simulate
from backend.app.trajectory import trajectory

EXAMPLE = [
    {"measure_id": "M7", "district_id": "nura"},
    {"measure_id": "M8", "district_id": "nura"},
    {"measure_id": "M10", "district_id": "nura"},
    {"measure_id": "M12", "district_id": None},
    {"measure_id": "M5", "district_id": "saryarka"},
]


def test_empty_trajectory_is_constant_baseline():
    points = trajectory([])

    assert [point["quarter"] for point in points] == list(range(1, 9))
    assert all(round(point["score"], 2) == 52.56 for point in points)
    assert len({point["score"] for point in points}) == 1


def test_reference_scenario_finishes_at_simulation_result():
    points = trajectory(EXAMPLE)
    result = simulate(EXAMPLE)

    assert result.valid
    assert points[-1]["score"] == pytest.approx(result.score)
    assert points[-1]["score"] == pytest.approx(56.54307)
    assert points[-1]["D_avg"] == pytest.approx(result.city_avg_after)


def test_balance_is_district_score_range():
    for point in trajectory(EXAMPLE):
        scores = point["district_scores"]
        assert point["balance"] == pytest.approx(max(scores.values()) - min(scores.values()))
        assert point["min_district"] == min(scores, key=scores.get)
        assert point["max_district"] == max(scores, key=scores.get)


def test_invalid_nonempty_scenario_raises_value_error():
    with pytest.raises(ValueError, match="ровно 5"):
        trajectory(EXAMPLE[:4])
