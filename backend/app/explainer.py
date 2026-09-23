"""LLM explanation layer. It only receives results produced by simulator.py."""

import json
import os

from openai import OpenAI, OpenAIError
from pydantic import BaseModel

from .data import DISTRICT_BY_ID, INDICATOR_NAMES, MEASURE_BY_ID
from .schemas import Explanation, SimulationResult

SYSTEM_PROMPT = """Ты — аналитик городских сценариев. Ты получаешь готовые,
уже посчитанные кодом цифры. Не пересчитывай и не придумывай числа, не меняй
Score. Объясняй только то, что явно есть в JSON: какие районы выиграли или не
изменились, какие показатели остались критическими, какие направления и районы
получили инвестиции и какой компромисс сделала команда. Не утверждай причинно-
следственные связи сверх данных. Пиши кратко и понятно по-русски."""


class _LLMExplanation(BaseModel):
    summary: str
    strengths: list[str]
    risks: list[str]
    tradeoffs: list[str]


def _compact_payload(result: SimulationResult) -> dict:
    """Only evidence required for explanation; no prompts or raw user text."""
    selected = []
    for item in result.selections:
        measure = MEASURE_BY_ID[item["measure_id"]]
        selected.append({
            "id": measure["id"],
            "name": measure["name"],
            "direction": measure["direction"],
            "district": DISTRICT_BY_ID[item["district_id"]]["name"] if item["district_id"] else "Весь город",
            "cost": measure["cost"],
        })
    return {
        "score": result.score,
        "score_base": result.score_base,
        "delta": result.delta,
        "cost_total": result.cost_total,
        "city_avg_before": result.city_avg_before,
        "city_avg_after": result.city_avg_after,
        "min_district_before": result.min_district_before,
        "min_district_after": result.min_district_after,
        "n_crit_before": result.n_crit_before,
        "n_crit_after": result.n_crit_after,
        "selected_measures": selected,
        "districts": [
            {
                "name": item["name"],
                "profile": item["profile"],
                "score_before": item["D_before"],
                "score_after": item["D_after"],
                "critical_after": [
                    {"code": code, "name": INDICATOR_NAMES[code], "value": item["indicators_after"][code]}
                    for code in item["critical_after"]
                ],
            }
            for item in result.districts
        ],
        "synergies_applied": result.synergies_applied,
    }


def _fallback(result: SimulationResult) -> Explanation:
    """Deterministic demo-safe explanation when an API key is unavailable."""
    improved = sorted(
        result.districts,
        key=lambda item: item["D_after"] - item["D_before"],
        reverse=True,
    )
    leaders = [item for item in improved if item["D_after"] > item["D_before"]][:2]
    strengths = [
        f"{item['name']}: районная оценка выросла с {item['D_before']:.2f} до {item['D_after']:.2f}."
        for item in leaders
    ] or ["Сценарий не улучшил оценки районов."]

    if result.critical_cells_after:
        risks = [
            f"{DISTRICT_BY_ID[cell['district_id']]['name']}: показатель {cell['indicator']} "
            f"«{INDICATOR_NAMES[cell['indicator']]}» остался ниже 40."
            for cell in result.critical_cells_after
        ]
    else:
        risks = ["После реализации сценария критических показателей ниже 40 не осталось."]

    district_spend = [item for item in result.selections if item["district_id"]]
    covered = sorted({DISTRICT_BY_ID[item["district_id"]]["name"] for item in district_spend})
    directions = sorted({MEASURE_BY_ID[item["measure_id"]]["direction"] for item in result.selections})
    tradeoffs = [
        f"Районные меры сосредоточены в: {', '.join(covered) if covered else 'нет районных мер'}.",
        f"Сценарий охватывает {len(directions)} из 5 направлений: {', '.join(directions)}.",
    ]
    return Explanation(
        summary=(
            f"Astana Quality of Life Score изменился с {result.score_base:.2f} "
            f"до {result.score:.2f}; бюджет сценария — {result.cost_total} из 100."
        ),
        strengths=strengths,
        risks=risks,
        tradeoffs=tradeoffs,
        source="deterministic_fallback",
    )


def explain_result(result: SimulationResult) -> Explanation:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or api_key == "sk-placeholder":
        return _fallback(result)

    try:
        client = OpenAI(api_key=api_key)
        completion = client.chat.completions.parse(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(_compact_payload(result), ensure_ascii=False)},
            ],
            response_format=_LLMExplanation,
            temperature=0.2,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            return _fallback(result)
        return Explanation(**parsed.model_dump(), source="openai")
    except (OpenAIError, ValueError, AttributeError, TypeError):
        # A failed external service must not break the deterministic simulator demo.
        return _fallback(result)
