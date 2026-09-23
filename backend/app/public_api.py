"""Validated public search API built on the deterministic optimizer."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .data import DISTRICTS, MEASURE_BY_ID, MEASURES
from .optimizer import search_scenarios
from .schemas import Selection
from .simulator import simulate


class RequiredPlacement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measure_id: str
    district_id: str | None = None


class SearchConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exclude: list[str] = Field(default_factory=list)
    require_measures: list[str] = Field(default_factory=list)
    require_directions: list[str] = Field(default_factory=list)
    require_placements: list[RequiredPlacement] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> SearchConstraints:
        known_measures = set(MEASURE_BY_ID)
        known_districts = {district["id"] for district in DISTRICTS}
        known_directions = {measure["direction"] for measure in MEASURES}

        referenced = set(self.exclude) | set(self.require_measures)
        referenced.update(item.measure_id for item in self.require_placements)
        unknown_measures = sorted(referenced - known_measures)
        if unknown_measures:
            raise ValueError(
                "Неизвестные мероприятия: " + ", ".join(unknown_measures)
            )

        unknown_directions = sorted(set(self.require_directions) - known_directions)
        if unknown_directions:
            raise ValueError(
                "Неизвестные направления: " + ", ".join(unknown_directions)
            )

        placements: dict[str, str | None] = {}
        for placement in self.require_placements:
            measure = MEASURE_BY_ID[placement.measure_id]
            if measure["type"] == "district":
                if placement.district_id not in known_districts:
                    raise ValueError(
                        f"Для районной меры {placement.measure_id} нужен существующий район"
                    )
            elif placement.district_id is not None:
                raise ValueError(
                    f"Для общегородской меры {placement.measure_id} район должен быть null"
                )
            previous = placements.get(placement.measure_id)
            if placement.measure_id in placements and previous != placement.district_id:
                raise ValueError(
                    f"Для меры {placement.measure_id} указаны разные обязательные районы"
                )
            placements[placement.measure_id] = placement.district_id

        if set(self.exclude) & set(self.require_measures):
            raise ValueError("Мера не может быть одновременно исключена и обязательна")
        if set(self.exclude) & set(placements):
            raise ValueError("Исключённая мера не может иметь обязательное размещение")
        required = set(self.require_measures) | set(placements)
        if len(required) > 5:
            raise ValueError("Нельзя потребовать больше пяти разных мероприятий")
        return self


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    constraints: SearchConstraints = Field(default_factory=SearchConstraints)
    objective: Literal["max_score", "min_cost"] = "max_score"
    limit: int = Field(default=3, ge=1, le=5)


def public_search(request: SearchRequest) -> dict[str, list[dict[str, object]]]:
    """Search and independently re-simulate every candidate before returning it."""
    raw = search_scenarios(
        request.constraints.model_dump(),
        objective=request.objective,
        limit=request.limit,
    )
    candidates: list[dict[str, object]] = []
    for item in raw:
        selections = [Selection.model_validate(value) for value in item["selections"]]
        verified = simulate(selections)
        if not verified.valid:
            continue
        candidates.append(
            {
                "selections": verified.selections,
                "score": verified.score,
                "cost": verified.cost_total,
                "delta": verified.delta,
            }
        )
    return {"candidates": candidates}
