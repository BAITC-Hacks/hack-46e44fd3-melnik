from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measure_id: str
    district_id: str | None = None


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selections: list[Selection]


class Explanation(BaseModel):
    summary: str
    strengths: list[str]
    risks: list[str]
    tradeoffs: list[str]
    source: str = "openai"


class SimulationResult(BaseModel):
    valid: bool
    reason: str | None = None
    selections: list[dict[str, Any]] = Field(default_factory=list)
    cost_total: int | None = None
    score: float | None = None
    score_base: float | None = None
    delta: float | None = None
    city_avg_before: float | None = None
    city_avg_after: float | None = None
    min_district_before: str | None = None
    min_district_after: str | None = None
    n_crit_before: int | None = None
    n_crit_after: int | None = None
    districts: list[dict[str, Any]] = Field(default_factory=list)
    critical_cells_after: list[dict[str, str]] = Field(default_factory=list)
    measure_contributions: list[dict[str, Any]] = Field(default_factory=list)
    synergies_applied: list[dict[str, Any]] = Field(default_factory=list)

    def delta_vs_base(self) -> float:
        return float(self.delta or 0.0)

