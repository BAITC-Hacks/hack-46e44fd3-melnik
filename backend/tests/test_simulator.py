import pytest

from backend.app.simulator import compute_baseline, simulate

EXAMPLE = [
    {"measure_id": "M7", "district_id": "nura"},
    {"measure_id": "M8", "district_id": "nura"},
    {"measure_id": "M10", "district_id": "nura"},
    {"measure_id": "M12", "district_id": None},
    {"measure_id": "M5", "district_id": "saryarka"},
]


def test_baseline():
    result = compute_baseline()
    assert round(result["city_avg"], 2) == 56.86
    assert result["min_district"] == "nura"
    assert round(result["district_scores"]["nura"], 2) == 49.18
    assert result["n_crit"] == 2
    assert round(result["score"], 2) == 52.56


def test_example_set():
    result = simulate(EXAMPLE)
    assert result.valid
    assert result.cost_total == 95
    assert result.score == pytest.approx(56.54307)
    assert result.delta_vs_base() > 3.5
    assert any(item["pair"] == ["M10", "M12"] for item in result.synergies_applied)


def test_cheapest_valid_set():
    result = simulate([
        {"measure_id": "M9", "district_id": "nura"},
        {"measure_id": "M11", "district_id": "nura"},
        {"measure_id": "M10", "district_id": "nura"},
        {"measure_id": "M12", "district_id": None},
        {"measure_id": "M4", "district_id": "nura"},
    ])
    assert result.valid
    assert result.cost_total == 61


@pytest.mark.parametrize(
    ("selections", "message"),
    [
        (EXAMPLE[:4], "ровно 5"),
        ([EXAMPLE[0], EXAMPLE[0], *EXAMPLE[2:]], "повторно"),
        ([
            {"measure_id": "M1", "district_id": "esil"},
            {"measure_id": "M3", "district_id": "almaty"},
            {"measure_id": "M8", "district_id": "nura"},
            {"measure_id": "M10", "district_id": "nura"},
            {"measure_id": "M12", "district_id": None},
        ], "несовместимы"),
        ([
            {"measure_id": "M3", "district_id": "nura"},
            {"measure_id": "M5", "district_id": "saryarka"},
            {"measure_id": "M7", "district_id": "nura"},
            {"measure_id": "M8", "district_id": "nura"},
            {"measure_id": "M13", "district_id": "almaty"},
        ], "Превышен бюджет"),
        ([
            {"measure_id": "M7", "district_id": "nura"},
            {"measure_id": "M8", "district_id": "nura"},
            {"measure_id": "M9", "district_id": "esil"},
            {"measure_id": "M10", "district_id": "nura"},
            {"measure_id": "M12", "district_id": None},
        ], "больше 2"),
        ([
            {"measure_id": "M7", "district_id": None},
            *EXAMPLE[1:],
        ], "выбрать район"),
        ([
            {"measure_id": "M12", "district_id": "nura"},
            {"measure_id": "M7", "district_id": "nura"},
            {"measure_id": "M8", "district_id": "nura"},
            {"measure_id": "M10", "district_id": "nura"},
            {"measure_id": "M5", "district_id": "saryarka"},
        ], "район указывать нельзя"),
    ],
)
def test_invalid_sets(selections, message):
    result = simulate(selections)
    assert not result.valid
    assert message in result.reason


def test_local_incompatibility_is_allowed_in_different_districts():
    result = simulate([
        {"measure_id": "M4", "district_id": "esil"},
        {"measure_id": "M7", "district_id": "nura"},
        {"measure_id": "M10", "district_id": "nura"},
        {"measure_id": "M12", "district_id": None},
        {"measure_id": "M14", "district_id": None},
    ])
    assert result.valid


def test_effect_fraction_and_fixed_synergy():
    result = simulate(EXAMPLE)
    m7 = next(item for item in result.measure_contributions if item["measure_id"] == "M7")
    assert m7["realized_effects"]["S1"] == 10.0
    synergy = next(item for item in result.synergies_applied if item["pair"] == ["M10", "M12"])
    assert synergy["bonus"] == {"B1": 2}
