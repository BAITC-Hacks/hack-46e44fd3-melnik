"""Constraint-aware AI advisor built on top of the deterministic simulator.

The model may interpret a user's natural-language policy request, but it is
never trusted to calculate or validate a scenario.  Every candidate and every
number returned by this module is reconstructed from local tool output.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from openai import OpenAI
from pydantic import BaseModel

from .data import MEASURE_BY_ID
from .optimizer import search_scenarios
from .schemas import Selection
from .simulator import simulate, validate_selections

_DIRECTIONS = {measure["direction"] for measure in MEASURE_BY_ID.values()}
_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


class _SelectionOutput(BaseModel):
    measure_id: str
    district_id: str | None


class _ConstraintsOutput(BaseModel):
    exclude: list[str]
    require_measures: list[str]
    require_directions: list[str]
    objective: Literal["max_score", "min_cost"]


class _DiffOutput(BaseModel):
    score_delta: float | None
    added: list[_SelectionOutput]
    removed: list[_SelectionOutput]


class _CandidateOutput(BaseModel):
    scenario: list[_SelectionOutput]
    score: float
    cost: int
    diff_vs_current: _DiffOutput


class _AdvisorOutput(BaseModel):
    parsed_constraints: _ConstraintsOutput
    candidates: list[_CandidateOutput]
    recommendation_text: str


_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "validate_scenario",
            "description": "Проверяет сценарий по бюджету, районам и правилам кейса.",
            "parameters": {
                "type": "object",
                "properties": {
                    "scenario": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "measure_id": {"type": "string"},
                                "district_id": {"type": ["string", "null"]},
                            },
                            "required": ["measure_id", "district_id"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["scenario"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simulate_scenario",
            "description": "Детерминированно рассчитывает проверенный городской сценарий.",
            "parameters": {
                "type": "object",
                "properties": {
                    "scenario": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "measure_id": {"type": "string"},
                                "district_id": {"type": ["string", "null"]},
                            },
                            "required": ["measure_id", "district_id"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["scenario"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_scenarios",
            "description": (
                "Ищет лучшие допустимые сценарии. Сначала извлеки из запроса "
                "exclude, require_measures и require_directions, затем вызови этот инструмент."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "constraints": {
                        "type": "object",
                        "properties": {
                            "exclude": {"type": "array", "items": {"type": "string"}},
                            "require_measures": {"type": "array", "items": {"type": "string"}},
                            "require_directions": {"type": "array", "items": {"type": "string"}},
                        },
                        "additionalProperties": False,
                    },
                    "objective": {"type": "string", "enum": ["max_score", "min_cost"]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5},
                },
                "required": ["constraints", "objective", "limit"],
                "additionalProperties": False,
            },
        },
    },
]


_SYSTEM_PROMPT = (
    "Ты — дружелюбный городской policy-copilot. Строй простой ответ в порядке: "
    "что мешает текущему сценарию, что стоит изменить и какова цена выбора или "
    "компромисс найденного варианта. "
    "Интерпретируй только явно заданные пользователем ограничения и используй "
    "инструменты для проверки, расчёта и поиска. "
    "Обязательно вызови search_scenarios. "
    "Никогда не считай Score, стоимость или дельту самостоятельно. "
    "В финальном тексте не пиши цифры: числовые поля приложение подставит из "
    "проверенного результата инструмента. "
    "Отвечай по-русски, коротко и отмечай содержательный компромисс сценария."
)


def _fallback_parse(message: str) -> dict[str, Any]:
    """Small, predictable parser that keeps the demo useful without an API key."""
    text = message.casefold()
    excluded = {
        match.upper()
        for match in re.findall(r"(?:без|исключ(?:и|ить|ите))\s+(?:мер(?:ы|у)\s+)?(m\d+)", text)
    }
    if re.search(r"(?:без|не\s+использ\w*|исключ\w*)\s+(?:лини\w*\s+)?лрт", text):
        excluded.add("M3")

    required_measures = {
        match.upper()
        for match in re.findall(r"(?:обязательно|оставь|добавь|включи)\s+(?:мер(?:у|ы)\s+)?(m\d+)", text)
    }
    require_directions: set[str] = set()
    direction_patterns = {
        "Экология": r"(?:с|оставь|нужн\w*|обязательн\w*)\s+(?:мер\w*\s+)?эколог",
        "Транспорт": r"(?:с|оставь|нужн\w*|обязательн\w*)\s+(?:мер\w*\s+)?транспорт",
        "Соцсфера": r"(?:с|оставь|нужн\w*|обязательн\w*)\s+(?:мер\w*\s+)?соц",
        "Безопасность": r"(?:с|оставь|нужн\w*|обязательн\w*)\s+(?:мер\w*\s+)?безопас",
        "Сервисы": r"(?:с|оставь|нужн\w*|обязательн\w*)\s+(?:мер\w*\s+)?сервис",
    }
    for direction, pattern in direction_patterns.items():
        if re.search(pattern, text):
            require_directions.add(direction)

    objective = (
        "min_cost"
        if re.search(r"(?:минимальн\w*|наименьш\w*|сам\w*\s+дешев\w*)\s+(?:стоимост\w*|цен\w*|бюджет\w*)", text)
        else "max_score"
    )
    return {
        "exclude": sorted(item for item in excluded if item in MEASURE_BY_ID),
        "require_measures": sorted(item for item in required_measures if item in MEASURE_BY_ID),
        "require_directions": sorted(require_directions),
        "objective": objective,
    }


def _sanitize_constraints(raw: Any, baseline: dict[str, Any]) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}

    def ids(key: str) -> list[str]:
        values = raw.get(key, baseline[key])
        if not isinstance(values, list):
            values = baseline[key]
        return sorted({str(value).upper() for value in values if str(value).upper() in MEASURE_BY_ID})

    directions = raw.get("require_directions", baseline["require_directions"])
    if not isinstance(directions, list):
        directions = baseline["require_directions"]
    result = {
        "exclude": ids("exclude"),
        "require_measures": ids("require_measures"),
        "require_directions": sorted({str(value) for value in directions if str(value) in _DIRECTIONS}),
        "objective": raw.get("objective", baseline["objective"]),
    }
    if result["objective"] not in {"max_score", "min_cost"}:
        result["objective"] = baseline["objective"]

    # Explicit phrases recognized locally must not disappear because of an LLM omission.
    for key in ("exclude", "require_measures", "require_directions"):
        result[key] = sorted(set(result[key]) | set(baseline[key]))
    if baseline["objective"] == "min_cost":
        result["objective"] = "min_cost"
    return result


def _validate_tool(scenario: Any) -> dict[str, Any]:
    try:
        parsed = [Selection.model_validate(item) for item in scenario]
        reason = validate_selections(parsed)
        return {"valid": reason is None, "reason": reason}
    except (TypeError, ValueError, AttributeError) as exc:
        return {"valid": False, "reason": str(exc)}


def _simulate_tool(scenario: Any) -> dict[str, Any]:
    try:
        result = simulate(scenario)
        return {
            "valid": result.valid,
            "reason": result.reason,
            "scenario": result.selections,
            "score": result.score,
            "cost": result.cost_total,
            "delta": result.delta,
        }
    except (TypeError, ValueError, AttributeError) as exc:
        return {"valid": False, "reason": str(exc)}


def _search_tool(constraints: dict[str, Any], objective: str, limit: int) -> list[dict[str, Any]]:
    search_constraints = {
        key: constraints.get(key, [])
        for key in ("exclude", "require_measures", "require_directions")
    }
    return search_scenarios(search_constraints, objective=objective, limit=max(1, min(limit, 5)))


def _normalise_candidates(
    raw_candidates: list[Any], current_scenario: list[dict[str, Any]] | None
) -> tuple[list[dict[str, Any]], Any]:
    current_result = None
    if current_scenario:
        try:
            attempted = simulate(current_scenario)
            if attempted.valid:
                current_result = attempted
        except (TypeError, ValueError, AttributeError):
            pass

    current_pairs = {
        (item["measure_id"], item.get("district_id")) for item in (current_scenario or [])
        if isinstance(item, dict) and "measure_id" in item
    }
    candidates: list[dict[str, Any]] = []
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            continue
        scenario = raw.get("selections", raw.get("scenario"))
        if not isinstance(scenario, list):
            continue
        try:
            verified = simulate(scenario)
        except (TypeError, ValueError, AttributeError):
            continue
        if not verified.valid or verified.score is None or verified.cost_total is None:
            continue
        verified_scenario = verified.selections
        candidate_pairs = {(item["measure_id"], item.get("district_id")) for item in verified_scenario}
        candidates.append({
            "scenario": verified_scenario,
            "score": verified.score,
            "cost": verified.cost_total,
            "diff_vs_current": {
                "score_delta": (
                    verified.score - current_result.score
                    if current_result is not None and current_result.score is not None
                    else None
                ),
                "added": [
                    item for item in verified_scenario
                    if (item["measure_id"], item.get("district_id")) not in current_pairs
                ],
                "removed": [
                    item for item in (current_scenario or [])
                    if isinstance(item, dict)
                    and (item.get("measure_id"), item.get("district_id")) not in candidate_pairs
                ],
            },
        })
    return candidates, current_result


def _safe_recommendation(candidates: list[dict[str, Any]], current_result: Any) -> str:
    if not candidates:
        return (
            "Что мешает: заданные ограничения не оставили допустимых сценариев. "
            "Что изменить: ослабьте одно из условий. Цена выбора: часть исходных "
            "приоритетов придётся пересмотреть."
        )
    best = candidates[0]
    if current_result is None:
        text = "Что мешает: текущий сценарий не передан, поэтому сравнить замену мер нельзя."
    else:
        text = "Что мешает: текущий сценарий уступает найденному варианту по выбранной цели."
    text += f" Что изменить: рассмотреть сценарий со Score {best['score']:.2f}."
    text += f" Цена выбора: {best['cost']} из бюджета."
    score_delta = best["diff_vs_current"].get("score_delta")
    if current_result is not None and score_delta is not None:
        text += f" Изменение относительно текущего сценария: {score_delta:+.2f}."
    text += " Все варианты повторно проверены детерминированным симулятором."
    return text


def _execute_tool(name: str, arguments: dict[str, Any]) -> Any:
    if name == "validate_scenario":
        return _validate_tool(arguments.get("scenario", []))
    if name == "simulate_scenario":
        return _simulate_tool(arguments.get("scenario", []))
    if name == "search_scenarios":
        constraints = arguments.get("constraints", {})
        objective = arguments.get("objective", "max_score")
        limit = arguments.get("limit", 3)
        return _search_tool(constraints, objective, limit)
    return {"error": f"Unknown tool: {name}"}


def _llm_constraints_and_text(
    api_key: str,
    current_scenario: list[dict[str, Any]] | None,
    message: str,
    baseline: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    client = OpenAI(api_key=api_key)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {"current_scenario": current_scenario, "request": message}, ensure_ascii=False
            ),
        },
    ]
    parsed = dict(baseline)
    searched: list[dict[str, Any]] | None = None

    for _ in range(4):
        completion = client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            tools=_TOOLS,
            tool_choice="required" if searched is None else "auto",
            temperature=0,
        )
        assistant_message = completion.choices[0].message
        messages.append(assistant_message.model_dump(exclude_none=True))
        if not assistant_message.tool_calls:
            break
        for call in assistant_message.tool_calls:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            if call.function.name == "search_scenarios":
                combined = dict(arguments.get("constraints", {}))
                combined["objective"] = arguments.get("objective", baseline["objective"])
                parsed = _sanitize_constraints(combined, baseline)
                arguments = {
                    "constraints": {key: parsed[key] for key in ("exclude", "require_measures", "require_directions")},
                    "objective": parsed["objective"],
                    "limit": 3,
                }
            result = _execute_tool(call.function.name, arguments)
            if call.function.name == "search_scenarios" and isinstance(result, list):
                searched = result
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, ensure_ascii=False),
            })
        if searched is not None:
            break

    # Structured Outputs is used for the final response.  Candidate numbers are
    # deliberately discarded later and rebuilt locally from simulator output.
    verified_search = searched or _search_tool(
        {key: parsed[key] for key in ("exclude", "require_measures", "require_directions")},
        parsed["objective"],
        3,
    )
    messages.append({
        "role": "user",
        "content": (
            "Сформируй итог строго по схеме. candidates скопируй из последнего результата поиска. "
            "recommendation_text должен быть по-русски и вообще без цифр. Данные поиска: "
            + json.dumps(verified_search, ensure_ascii=False)
        ),
    })
    final = client.chat.completions.parse(
        model=_MODEL,
        messages=messages,
        response_format=_AdvisorOutput,
        temperature=0,
    )
    final_parsed = final.choices[0].message.parsed
    narrative = final_parsed.recommendation_text if final_parsed else ""
    # A model-written digit is rejected: no unverified number reaches the user.
    if re.search(r"\d", narrative):
        narrative = ""
    return parsed, narrative


def advise(
    current_scenario: list[dict[str, Any]] | None,
    message: str,
) -> dict[str, Any]:
    """Return verified recommendations; external AI failure is always non-fatal."""
    baseline = _fallback_parse(message or "")
    parsed = baseline
    narrative = ""
    source = "deterministic_fallback"
    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if api_key and api_key != "sk-placeholder":
        try:
            parsed, narrative = _llm_constraints_and_text(
                api_key, current_scenario, message or "", baseline
            )
            source = "openai"
        except Exception:  # noqa: BLE001 - an external service must not break the demo
            parsed = baseline
            narrative = ""
            source = "deterministic_fallback"

    constraints = {
        key: parsed[key] for key in ("exclude", "require_measures", "require_directions")
    }
    try:
        raw_candidates = search_scenarios(
            constraints, objective=parsed["objective"], limit=3
        )
    except (TypeError, ValueError, KeyError):
        raw_candidates = []
    candidates, current_result = _normalise_candidates(raw_candidates, current_scenario)

    # The safe sentence is the only place where numeric claims are made.  The
    # optional model prose contains no digits and can only add interpretation.
    safe_text = _safe_recommendation(candidates, current_result)
    recommendation = f"{safe_text} {narrative}".strip() if narrative else safe_text
    return {
        "parsed_constraints": parsed,
        "candidates": candidates,
        "recommendation_text": recommendation,
        "source": source,
    }
