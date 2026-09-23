"""Quarter-by-quarter projection built on the deterministic simulation rules."""

from copy import deepcopy

from .data import DISTRICT_BY_ID, DISTRICTS, HORIZON, MEASURE_BY_ID, SYNERGIES, WEIGHTS
from .schemas import Selection
from .simulator import BASELINE, validate_selections


def _snapshot(values: dict[str, dict[str, float]]) -> dict:
    district_scores = {
        district_id: sum(WEIGHTS[indicator] * indicators[indicator] for indicator in WEIGHTS)
        for district_id, indicators in values.items()
    }
    d_avg = sum(
        DISTRICT_BY_ID[district_id]["pop_share"] * score
        for district_id, score in district_scores.items()
    )
    min_district = min(district_scores, key=district_scores.get)
    max_district = max(district_scores, key=district_scores.get)
    n_crit = sum(
        value < 40
        for indicators in values.values()
        for value in indicators.values()
    )
    score = 0.7 * d_avg + 0.3 * district_scores[min_district] - n_crit
    return {
        "score": score,
        "D_avg": d_avg,
        "min_district": min_district,
        "max_district": max_district,
        "balance": district_scores[max_district] - district_scores[min_district],
        "district_scores": district_scores,
        "n_crit": n_crit,
    }


def trajectory(selections: list[Selection | dict]) -> list[dict]:
    """Return deterministic city metrics for quarters 1 through 8.

    An empty selection represents the unchanged baseline. Non-empty scenarios must
    satisfy the same validation rules as :func:`simulator.simulate`.
    """

    parsed = [
        item if isinstance(item, Selection) else Selection.model_validate(item)
        for item in selections
    ]
    if parsed:
        reason = validate_selections(parsed)
        if reason:
            raise ValueError(reason)

    selected_by_id = {item.measure_id: item for item in parsed}
    points: list[dict] = []

    for quarter in range(1, HORIZON + 1):
        increments = {
            district["id"]: {indicator: 0.0 for indicator in WEIGHTS}
            for district in DISTRICTS
        }

        for item in parsed:
            measure = MEASURE_BY_ID[item.measure_id]
            realized_fraction = (
                0.0 if quarter <= measure["lag"] else (quarter - measure["lag"]) / HORIZON
            )
            affected = (
                [item.district_id]
                if measure["type"] == "district"
                else [district["id"] for district in DISTRICTS]
            )
            for district_id in affected:
                for indicator, effect in measure["effects"].items():
                    increments[district_id][indicator] += effect * realized_fraction

        for synergy in SYNERGIES:
            if not all(measure_id in selected_by_id for measure_id in synergy["pair"]):
                continue
            activation_quarter = max(
                MEASURE_BY_ID[measure_id]["lag"] for measure_id in synergy["pair"]
            )
            if quarter <= activation_quarter:
                continue
            district_id = selected_by_id[synergy["district_source"]].district_id
            for indicator, bonus in synergy["bonus"].items():
                increments[district_id][indicator] += bonus

        values = deepcopy(BASELINE["values"])
        for district_id, indicators in values.items():
            for indicator, before in indicators.items():
                indicators[indicator] = max(
                    0.0,
                    min(100.0, before + increments[district_id][indicator]),
                )

        points.append({"quarter": quarter, **_snapshot(values)})

    return points
