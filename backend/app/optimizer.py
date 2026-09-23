"""Exhaustive search over valid five-measure city scenarios.

The search deliberately separates measure-set filtering from district placement:
there are only ``C(14, 5)`` measure sets, while district assignments are expanded
only for sets that already satisfy the cheap constraints.
"""

from __future__ import annotations

from collections import Counter
from heapq import heappush, heapreplace
from itertools import combinations, product
from typing import Any

from .data import (
    BUDGET,
    DISTRICTS,
    HORIZON,
    INCOMPATIBILITIES,
    MAX_PER_DIRECTION,
    MEASURE_BY_ID,
    MEASURES,
    SYNERGIES,
    WEIGHTS,
)
from .schemas import Selection
from .simulator import BASELINE, simulate, validate_selections

_DISTRICT_IDS = tuple(item["id"] for item in DISTRICTS)
_POP_SHARES = tuple(item["pop_share"] for item in DISTRICTS)
_BASE_DISTRICT_SCORES = tuple(
    BASELINE["district_scores"][item] for item in _DISTRICT_IDS
)

# Only these cells can be critical in any valid scenario.  All effects are
# non-negative except M11/T1, so cells initially above 40 cannot cross the
# threshold (apart from T1 in districts that start at exactly 40).
_SENSITIVE_CELLS = tuple(
    (district_id, indicator)
    for district_id in _DISTRICT_IDS
    for indicator, value in BASELINE["values"][district_id].items()
    if value <= 40
)
_SENSITIVE_INDEX = {cell: index for index, cell in enumerate(_SENSITIVE_CELLS)}
_BASE_SENSITIVE_VALUES = tuple(
    BASELINE["values"][district_id][indicator]
    for district_id, indicator in _SENSITIVE_CELLS
)


def _realized_effects(measure: dict[str, Any]) -> dict[str, float]:
    fraction = (HORIZON - measure["lag"]) / HORIZON
    return {
        indicator: effect * fraction for indicator, effect in measure["effects"].items()
    }


_REALIZED = {measure["id"]: _realized_effects(measure) for measure in MEASURES}
_WEIGHTED_GAIN = {
    measure_id: sum(
        WEIGHTS[indicator] * effect for indicator, effect in effects.items()
    )
    for measure_id, effects in _REALIZED.items()
}


def _normalise_ids(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    return {str(item) for item in value}


def _measure_set_is_possible(
    measures: tuple[dict[str, Any], ...],
    *,
    excluded: set[str],
    required: set[str],
    required_directions: set[str],
) -> bool:
    ids = {measure["id"] for measure in measures}
    if ids & excluded or not required <= ids:
        return False
    if sum(measure["cost"] for measure in measures) > BUDGET:
        return False

    directions = Counter(measure["direction"] for measure in measures)
    if any(count > MAX_PER_DIRECTION for count in directions.values()):
        return False
    if not required_directions <= set(directions):
        return False

    # M1 + M3 is unconditionally incompatible.  The other incompatibilities
    # are district-local and must be checked after placement expansion.
    return not ({"M1", "M3"} <= ids)


def _district_options(measure: dict[str, Any]) -> tuple[int, ...]:
    return tuple(range(len(_DISTRICT_IDS))) if measure["type"] == "district" else (-1,)


def _normalise_placements(value: Any) -> dict[str, str | None] | None:
    """Validate and normalise exact measure placements requested by a caller."""
    if value is None:
        return {}
    if not isinstance(value, list):
        return None

    placements: dict[str, str | None] = {}
    for item in value:
        if not isinstance(item, dict):
            return None
        measure_id = item.get("measure_id")
        district_id = item.get("district_id")
        if not isinstance(measure_id, str) or measure_id not in MEASURE_BY_ID:
            return None
        measure = MEASURE_BY_ID[measure_id]
        if measure["type"] == "district":
            if district_id not in _DISTRICT_IDS:
                return None
        elif district_id is not None:
            return None
        if measure_id in placements and placements[measure_id] != district_id:
            return None
        placements[measure_id] = district_id
    return placements


def search_scenarios(
    constraints: dict[str, Any] | None = None,
    objective: str = "max_score",
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return the best valid scenarios matching deterministic constraints.

    Supported constraints are ``exclude``, ``require_measures``,
    ``require_directions``, ``require_placements`` and ``objective``.  An
    objective inside constraints is honoured when the explicit argument is
    left at its default.
    """

    constraints = constraints or {}
    if objective == "max_score" and constraints.get("objective"):
        objective = str(constraints["objective"])
    if objective not in {"max_score", "min_cost"}:
        raise ValueError("objective must be 'max_score' or 'min_cost'")
    if limit <= 0:
        return []

    excluded = _normalise_ids(constraints.get("exclude"))
    required = _normalise_ids(constraints.get("require_measures"))
    required_directions = _normalise_ids(constraints.get("require_directions"))
    required_placements = _normalise_placements(constraints.get("require_placements"))
    if required_placements is None:
        return []
    required |= set(required_placements)
    known_ids = set(MEASURE_BY_ID)
    known_directions = {measure["direction"] for measure in MEASURES}
    if not required <= known_ids or not required_directions <= known_directions:
        return []
    if required & excluded or len(required) > 5:
        return []

    heap: list[tuple[tuple[float, float], int, list[dict[str, str | None]]]] = []
    serial = 0

    for measures in combinations(MEASURES, 5):
        if not _measure_set_is_possible(
            measures,
            excluded=excluded,
            required=required,
            required_directions=required_directions,
        ):
            continue

        cost = sum(measure["cost"] for measure in measures)
        measure_ids = tuple(measure["id"] for measure in measures)
        positions = {measure_id: index for index, measure_id in enumerate(measure_ids)}
        district_positions = tuple(
            index
            for index, measure in enumerate(measures)
            if measure["type"] == "district"
        )
        city_gain = sum(
            _WEIGHTED_GAIN[measure["id"]]
            for measure in measures
            if measure["type"] == "city"
        )
        city_sensitive = [0.0] * len(_SENSITIVE_CELLS)
        for measure in measures:
            if measure["type"] != "city":
                continue
            for district_index, district_id in enumerate(_DISTRICT_IDS):
                for indicator, effect in _REALIZED[measure["id"]].items():
                    sensitive_index = _SENSITIVE_INDEX.get((district_id, indicator))
                    if sensitive_index is not None:
                        city_sensitive[sensitive_index] += effect

        local_conflicts = tuple(
            (positions[first], positions[second])
            for first, second in INCOMPATIBILITIES
            if first in positions
            and second in positions
            and (first, second) != ("M1", "M3")
        )
        active_synergies = tuple(
            (
                positions[synergy["district_source"]],
                sum(
                    WEIGHTS[indicator] * bonus
                    for indicator, bonus in synergy["bonus"].items()
                ),
                synergy["bonus"],
            )
            for synergy in SYNERGIES
            if all(measure_id in positions for measure_id in synergy["pair"])
        )

        district_options = tuple(
            (
                (_DISTRICT_IDS.index(required_placements[measure["id"]]),)
                if measure["id"] in required_placements
                and required_placements[measure["id"]] is not None
                else (-1,)
                if measure["id"] in required_placements
                else _district_options(measure)
            )
            for measure in measures
        )
        for districts in product(*district_options):
            if any(
                districts[first] == districts[second]
                for first, second in local_conflicts
            ):
                continue

            district_gains = [city_gain] * len(_DISTRICT_IDS)
            sensitive_gains = city_sensitive.copy()
            for position in district_positions:
                district_index = districts[position]
                measure_id = measure_ids[position]
                district_gains[district_index] += _WEIGHTED_GAIN[measure_id]
                district_id = _DISTRICT_IDS[district_index]
                for indicator, effect in _REALIZED[measure_id].items():
                    sensitive_index = _SENSITIVE_INDEX.get((district_id, indicator))
                    if sensitive_index is not None:
                        sensitive_gains[sensitive_index] += effect

            for source_position, weighted_bonus, bonuses in active_synergies:
                district_index = districts[source_position]
                district_gains[district_index] += weighted_bonus
                district_id = _DISTRICT_IDS[district_index]
                for indicator, bonus in bonuses.items():
                    sensitive_index = _SENSITIVE_INDEX.get((district_id, indicator))
                    if sensitive_index is not None:
                        sensitive_gains[sensitive_index] += bonus

            district_scores = tuple(
                base + gain for base, gain in zip(_BASE_DISTRICT_SCORES, district_gains)
            )
            city_average = sum(
                population * district_score
                for population, district_score in zip(_POP_SHARES, district_scores)
            )
            critical_count = sum(
                base + gain < 40
                for base, gain in zip(_BASE_SENSITIVE_VALUES, sensitive_gains)
            )
            score = 0.7 * city_average + 0.3 * min(district_scores) - critical_count
            rank = (
                (score, -float(cost))
                if objective == "max_score"
                else (-float(cost), score)
            )
            if len(heap) < limit or rank > heap[0][0]:
                selections = [
                    {
                        "measure_id": measure["id"],
                        "district_id": None
                        if district == -1
                        else _DISTRICT_IDS[district],
                    }
                    for measure, district in zip(measures, districts)
                ]
                item = (rank, serial, selections)
                serial += 1
                if len(heap) < limit:
                    heappush(heap, item)
                else:
                    heapreplace(heap, item)

    ranked = sorted(heap, reverse=True)
    results: list[dict[str, Any]] = []
    for _rank, _serial, selection_dicts in ranked:
        parsed = [Selection.model_validate(item) for item in selection_dicts]
        if validate_selections(parsed) is not None:
            continue
        simulation = simulate(parsed)
        if not simulation.valid:
            continue
        results.append(
            {
                "selections": simulation.selections,
                "score": float(simulation.score),
                "cost": int(simulation.cost_total),
                "delta": float(simulation.delta),
            }
        )

    if objective == "max_score":
        results.sort(key=lambda item: (-item["score"], item["cost"]))
    else:
        results.sort(key=lambda item: (item["cost"], -item["score"]))
    return results[:limit]
