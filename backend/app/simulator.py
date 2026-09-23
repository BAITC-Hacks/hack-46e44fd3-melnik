"""Pure deterministic calculation engine. No LLM or database calls belong here."""

from collections import Counter
from collections.abc import Iterable
from copy import deepcopy

from .data import (
    BUDGET,
    DECISIONS_REQUIRED,
    DISTRICT_BY_ID,
    DISTRICTS,
    HORIZON,
    INCOMPATIBILITIES,
    MAX_PER_DIRECTION,
    MEASURE_BY_ID,
    SYNERGIES,
    WEIGHTS,
)
from .schemas import Selection, SimulationResult


def _district_scores(values: dict[str, dict[str, float]]) -> dict[str, float]:
    return {
        district_id: sum(WEIGHTS[key] * indicators[key] for key in WEIGHTS)
        for district_id, indicators in values.items()
    }


def _snapshot(values: dict[str, dict[str, float]]) -> dict:
    district_scores = _district_scores(values)
    city_avg = sum(
        DISTRICT_BY_ID[district_id]["pop_share"] * score
        for district_id, score in district_scores.items()
    )
    min_district = min(district_scores, key=district_scores.get)
    critical_cells = [
        {"district_id": district_id, "indicator": indicator}
        for district_id, indicators in values.items()
        for indicator, value in indicators.items()
        if value < 40
    ]
    score = 0.7 * city_avg + 0.3 * district_scores[min_district] - len(critical_cells)
    return {
        "district_scores": district_scores,
        "city_avg": city_avg,
        "min_district": min_district,
        "critical_cells": critical_cells,
        "n_crit": len(critical_cells),
        "score": score,
    }


def compute_baseline() -> dict:
    values = {
        district["id"]: {key: float(value) for key, value in district["indicators"].items()}
        for district in DISTRICTS
    }
    return {"values": values, **_snapshot(values)}


BASELINE = compute_baseline()


def _invalid(reason: str, selections: Iterable[Selection] = ()) -> SimulationResult:
    return SimulationResult(
        valid=False,
        reason=reason,
        selections=[item.model_dump() for item in selections],
    )


def validate_selections(selections: list[Selection]) -> str | None:
    if len(selections) != DECISIONS_REQUIRED:
        return f"Нужно выбрать ровно {DECISIONS_REQUIRED} решений: выбрано {len(selections)}"

    unknown = [item.measure_id for item in selections if item.measure_id not in MEASURE_BY_ID]
    if unknown:
        return f"Неизвестное мероприятие: {unknown[0]}"

    measure_ids = [item.measure_id for item in selections]
    duplicate = next((item for item, count in Counter(measure_ids).items() if count > 1), None)
    if duplicate:
        return f"Мероприятие {duplicate} выбрано повторно"

    for item in selections:
        measure = MEASURE_BY_ID[item.measure_id]
        if measure["type"] == "district":
            if item.district_id is None:
                return f"Для мероприятия {item.measure_id} необходимо выбрать район"
            if item.district_id not in DISTRICT_BY_ID:
                return f"Неизвестный район для мероприятия {item.measure_id}: {item.district_id}"
        elif item.district_id is not None:
            return f"Для общегородского мероприятия {item.measure_id} район указывать нельзя"

    cost = sum(MEASURE_BY_ID[item.measure_id]["cost"] for item in selections)
    if cost > BUDGET:
        return f"Превышен бюджет: {cost} > {BUDGET}"

    directions = Counter(MEASURE_BY_ID[item.measure_id]["direction"] for item in selections)
    overloaded = next((direction for direction, count in directions.items() if count > MAX_PER_DIRECTION), None)
    if overloaded:
        return f"В направлении «{overloaded}» выбрано больше {MAX_PER_DIRECTION} мероприятий"

    selected = {item.measure_id: item for item in selections}
    for first, second in INCOMPATIBILITIES:
        if first not in selected or second not in selected:
            continue
        if [first, second] == ["M1", "M3"]:
            return f"Мероприятия {first} и {second} несовместимы в любых районах"
        if selected[first].district_id == selected[second].district_id:
            district_name = DISTRICT_BY_ID[selected[first].district_id]["name"]
            return f"Мероприятия {first} и {second} несовместимы в районе «{district_name}»"

    return None


def simulate(selections: list[Selection | dict]) -> SimulationResult:
    parsed = [item if isinstance(item, Selection) else Selection.model_validate(item) for item in selections]
    reason = validate_selections(parsed)
    if reason:
        return _invalid(reason, parsed)

    increments = {
        district["id"]: {key: 0.0 for key in WEIGHTS}
        for district in DISTRICTS
    }
    contributions = []
    selected_by_id = {item.measure_id: item for item in parsed}

    for item in parsed:
        measure = MEASURE_BY_ID[item.measure_id]
        realized_fraction = (HORIZON - measure["lag"]) / HORIZON
        realized_effects = {
            key: value * realized_fraction for key, value in measure["effects"].items()
        }
        affected = [item.district_id] if measure["type"] == "district" else [d["id"] for d in DISTRICTS]
        for district_id in affected:
            for indicator, effect in realized_effects.items():
                increments[district_id][indicator] += effect
        contributions.append({
            "measure_id": item.measure_id,
            "district_id": item.district_id,
            "realized_fraction": realized_fraction,
            "realized_effects": realized_effects,
            "affected_district_ids": affected,
        })

    synergies_applied = []
    for synergy in SYNERGIES:
        if all(measure_id in selected_by_id for measure_id in synergy["pair"]):
            district_id = selected_by_id[synergy["district_source"]].district_id
            for indicator, bonus in synergy["bonus"].items():
                increments[district_id][indicator] += bonus
            synergies_applied.append({
                "pair": synergy["pair"],
                "district_id": district_id,
                "bonus": synergy["bonus"],
            })

    after_values = deepcopy(BASELINE["values"])
    for district_id, indicators in after_values.items():
        for indicator, before in indicators.items():
            indicators[indicator] = max(0.0, min(100.0, before + increments[district_id][indicator]))

    after = _snapshot(after_values)
    district_results = []
    for district in DISTRICTS:
        district_id = district["id"]
        critical_after = [key for key, value in after_values[district_id].items() if value < 40]
        district_results.append({
            "id": district_id,
            "name": district["name"],
            "profile": district["profile"],
            "D_before": BASELINE["district_scores"][district_id],
            "D_after": after["district_scores"][district_id],
            "indicators_before": BASELINE["values"][district_id],
            "indicators_after": after_values[district_id],
            "critical_after": critical_after,
        })

    cost = sum(MEASURE_BY_ID[item.measure_id]["cost"] for item in parsed)
    return SimulationResult(
        valid=True,
        selections=[item.model_dump() for item in parsed],
        cost_total=cost,
        score=after["score"],
        score_base=round(BASELINE["score"], 2),
        delta=after["score"] - BASELINE["score"],
        city_avg_before=BASELINE["city_avg"],
        city_avg_after=after["city_avg"],
        min_district_before=BASELINE["min_district"],
        min_district_after=after["min_district"],
        n_crit_before=BASELINE["n_crit"],
        n_crit_after=after["n_crit"],
        districts=district_results,
        critical_cells_after=after["critical_cells"],
        measure_contributions=contributions,
        synergies_applied=synergies_applied,
    )
