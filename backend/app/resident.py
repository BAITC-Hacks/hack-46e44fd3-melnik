"""Turn a resident's request into a catalog-backed, verified city proposal."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any

from openai import OpenAI, OpenAIError
from pydantic import BaseModel

from .data import (
    BUDGET,
    DISTRICT_BY_ID,
    DISTRICTS,
    HORIZON,
    INDICATOR_NAMES,
    MEASURE_BY_ID,
    MEASURES,
)
from .optimizer import search_scenarios
from .simulator import simulate


class _ResidentMatch(BaseModel):
    matched: bool
    measure_id: str | None
    explanation: str


_KEYWORDS = {
    "M1": ("автобус", "выделенн", "полос"),
    "M2": ("светофор", "перекрест", "перекрёст"),
    "M3": ("лрт", "рельс", "трамва"),
    "M4": ("парк", "сквер", "зелени", "дерев"),
    "M5": ("угол", "топлив", "смог", "воздух", "частн"),
    "M6": ("озеленен", "озеленён", "ветрозащит"),
    "M7": ("школ", "детсад", "детск"),
    "M8": ("поликлиник", "врач", "здоров", "медпомощ"),
    "M9": ("спорт", "площадк", "дворов"),
    "M10": ("освещ", "камер", "темно", "safe city"),
    "M11": ("переход", "зебр", "безопасн", "школьн зон", "дтп"),
    "M12": ("обращен", "обращён", "цифров", "жалоб"),
    "M13": ("теплосет", "водосет", "труб", "отоплен", "водоснаб"),
    "M14": ("аварийн", "жкх", "оповещ", "бригада"),
}

_SYSTEM_PROMPT = (
    "Сопоставь запрос жителя ровно с одной существующей мерой каталога. "
    "Не придумывай новые меры и эффекты. Если уверенного соответствия нет, верни "
    "matched=false и measure_id=null. explanation напиши по-русски без цифр."
)


def _normalise_text(value: str) -> str:
    return " ".join(re.findall(r"[a-zа-яё]+", value.casefold()))


def _keyword_scores(message: str) -> dict[str, int]:
    text = _normalise_text(message)
    return {
        measure_id: sum(keyword in text for keyword in keywords)
        for measure_id, keywords in _KEYWORDS.items()
    }


def _fallback_match(message: str) -> str | None:
    scores = _keyword_scores(message)
    best = max(scores, key=lambda measure_id: (scores[measure_id], -int(measure_id[1:])))
    return best if scores[best] else None


def _nearest_measures(message: str, limit: int = 3) -> list[str]:
    scores = _keyword_scores(message)
    ranked = sorted(
        MEASURES,
        key=lambda measure: (-scores[measure["id"]], measure["id"]),
    )
    return [measure["name"] for measure in ranked[:limit]]


def _infer_district(district_id: str | None, message: str) -> str | None:
    if district_id is not None:
        return district_id if district_id in DISTRICT_BY_ID else None
    text = _normalise_text(message)
    for district in DISTRICTS:
        if district["name"].casefold() in text:
            return district["id"]
    return None


def _llm_match(message: str) -> tuple[str | None, str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or api_key == "sk-placeholder":
        return None, ""
    catalog = [{"id": item["id"], "name": item["name"]} for item in MEASURES]
    try:
        client = OpenAI(api_key=api_key)
        completion = client.chat.completions.parse(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"catalog": catalog, "resident_message": message},
                        ensure_ascii=False,
                    ),
                },
            ],
            response_format=_ResidentMatch,
            temperature=0,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None or not parsed.matched or parsed.measure_id not in MEASURE_BY_ID:
            return None, ""
        prose = parsed.explanation.strip()
        return parsed.measure_id, prose if not re.search(r"\d", prose) else ""
    except (OpenAIError, ValueError, AttributeError, TypeError):
        return None, ""


@lru_cache(maxsize=1)
def _blind_maximum() -> dict[str, Any] | None:
    results = search_scenarios({}, objective="max_score", limit=1)
    return results[0] if results else None


def _unmatched(message: str, reason: str | None = None) -> dict[str, Any]:
    alternatives = _nearest_measures(message)
    body = reason or (
        "Такой меры нет в каталоге симулятора. Уточните запрос или выберите один "
        "из ближайших вариантов."
    )
    return {
        "matched": False,
        "measure": None,
        "district": None,
        "evidence": None,
        "plan": None,
        "max_score": None,
        "appeal": {
            "title": "Подходящая мера пока не найдена",
            "body": body,
        },
        "alternatives": alternatives,
        "source": "deterministic_fallback",
    }


def _measure_payload(measure: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": measure["id"],
        "name": measure["name"],
        "direction": measure["direction"],
        "type": measure["type"],
        "cost": measure["cost"],
        "lag": measure["lag"],
    }


def _build_appeal(
    measure: dict[str, Any],
    district: dict[str, Any] | None,
    evidence: dict[str, Any],
    max_score: float,
    llm_prose: str,
) -> dict[str, str]:
    place = f"района {district['name']}" if district else "всего города"
    title = f"Предложение для {place}: {measure['name']}"
    body = (
        f"Прошу рассмотреть меру «{measure['name']}» для {place}. "
        f"Её стоимость в модели — {evidence['measure_cost']} из {evidence['budget']}. "
    )
    for effect in evidence["measure_effects"]:
        if effect["before"] is None:
            body += (
                f"Проверенный эффект для показателя «{effect['name']}» — "
                f"{effect['delta']:+.2f}. "
            )
        else:
            body += (
                f"Показатель «{effect['name']}» меняется с {effect['before']:.2f} "
                f"до {effect['after']:.2f}. "
            )
    if district is not None:
        body += (
            f"Оценка района меняется с {evidence['district_score_before']:.2f} "
            f"до {evidence['district_score_after']:.2f}. "
        )
    body += (
        f"Итоговый Score проверенного плана — {evidence['plan_score']:.2f}; "
        f"максимум без этого условия — {max_score:.2f}. "
    )
    if llm_prose:
        body += f"{llm_prose} "
    body += "Это черновик: в демо обращение никуда не отправляется."
    return {"title": title, "body": body}


def propose_resident(district_id: str | None, message: str) -> dict[str, Any]:
    """Match one catalog measure and produce a fully verified resident proposal."""
    fallback_measure_id = _fallback_match(message or "")
    llm_measure_id, llm_prose = (
        (None, "") if fallback_measure_id else _llm_match(message or "")
    )
    measure_id = fallback_measure_id or llm_measure_id
    source = "deterministic_fallback" if fallback_measure_id or not llm_measure_id else "openai"
    if measure_id is None:
        return _unmatched(message or "")

    measure = MEASURE_BY_ID[measure_id]
    inferred_district = _infer_district(district_id, message or "")
    if measure["type"] == "district" and inferred_district is None:
        return _unmatched(
            message or "",
            "Для этой районной меры сначала выберите район.",
        )
    placement_district = inferred_district if measure["type"] == "district" else None
    placement = {"measure_id": measure_id, "district_id": placement_district}
    candidates = search_scenarios(
        {"require_placements": [placement]},
        objective="max_score",
        limit=1,
    )
    if not candidates:
        return _unmatched(
            message or "",
            "Для выбранной меры не удалось собрать допустимый план. Измените район или запрос.",
        )

    verified = simulate(candidates[0]["selections"])
    if not verified.valid or verified.score is None:
        return _unmatched(message or "")
    contribution = next(
        item for item in verified.measure_contributions if item["measure_id"] == measure_id
    )
    district_result = next(
        (item for item in verified.districts if item["id"] == placement_district),
        None,
    )
    effects = []
    for indicator, delta in contribution["realized_effects"].items():
        before = (
            district_result["indicators_before"][indicator]
            if district_result is not None
            else None
        )
        effects.append(
            {
                "indicator": indicator,
                "name": INDICATOR_NAMES[indicator],
                "delta": delta,
                "before": before,
                "after": before + delta if before is not None else None,
            }
        )

    evidence = {
        "measure_cost": measure["cost"],
        "budget": BUDGET,
        "horizon_years": HORIZON / 4,
        "realized_fraction": contribution["realized_fraction"],
        "measure_effects": effects,
        "district_indicator_before": {
            item["indicator"]: item["before"] for item in effects if item["before"] is not None
        },
        "district_indicator_after": {
            item["indicator"]: item["after"] for item in effects if item["after"] is not None
        },
        "district_score_before": (
            district_result["D_before"] if district_result is not None else None
        ),
        "district_score_after": (
            district_result["D_after"] if district_result is not None else None
        ),
        "plan_score": verified.score,
    }
    maximum = _blind_maximum()
    max_score = float(maximum["score"]) if maximum is not None else float(verified.score)
    district_payload = (
        {"id": DISTRICT_BY_ID[placement_district]["id"], "name": DISTRICT_BY_ID[placement_district]["name"]}
        if placement_district is not None
        else None
    )
    return {
        "matched": True,
        "measure": _measure_payload(measure),
        "district": district_payload,
        "evidence": evidence,
        "plan": {
            "selections": verified.selections,
            "score": verified.score,
            "cost": verified.cost_total,
        },
        "max_score": max_score,
        "appeal": _build_appeal(
            measure,
            district_payload,
            evidence,
            max_score,
            llm_prose,
        ),
        "alternatives": [],
        "source": source,
    }
