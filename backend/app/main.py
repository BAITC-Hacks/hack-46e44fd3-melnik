from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .advisor import advise
from .data import (
    BUDGET,
    DECISIONS_REQUIRED,
    DISTRICTS,
    HORIZON,
    INCOMPATIBILITIES,
    INDICATOR_NAMES,
    MAX_PER_DIRECTION,
    MEASURES,
    SYNERGIES,
    WEIGHTS,
)
from .explainer import explain_result
from .schemas import SimulationRequest
from .simulator import BASELINE, simulate
from .trajectory import trajectory

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"


class AdvisorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_scenario: list[dict[str, Any]] | None = None
    message: str = Field(min_length=1, max_length=500)

app = FastAPI(
    title="Аким на 5 часов",
    description="Детерминированный AI-симулятор управления Астаной",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/style.css", include_in_schema=False)
def stylesheet() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "style.css", media_type="text/css")


@app.get("/app.js", include_in_schema=False)
def javascript() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "app.js", media_type="text/javascript")


@app.get("/advisor.css", include_in_schema=False)
def advisor_stylesheet() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "advisor.css", media_type="text/css")


@app.get("/advisor.js", include_in_schema=False)
def advisor_javascript() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "advisor.js", media_type="text/javascript")


@app.get("/trajectory.css", include_in_schema=False)
def trajectory_stylesheet() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "trajectory.css", media_type="text/css")


@app.get("/trajectory.js", include_in_schema=False)
def trajectory_javascript() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "trajectory.js", media_type="text/javascript")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/catalog")
def catalog() -> dict[str, Any]:
    return {
        "budget": BUDGET,
        "decisions_required": DECISIONS_REQUIRED,
        "max_per_direction": MAX_PER_DIRECTION,
        "horizon": HORIZON,
        "districts": DISTRICTS,
        "measures": MEASURES,
        "weights": WEIGHTS,
        "indicator_names": INDICATOR_NAMES,
        "synergies": SYNERGIES,
        "incompatibilities": INCOMPATIBILITIES,
        "baseline": {
            "score": BASELINE["score"],
            "city_avg": BASELINE["city_avg"],
            "min_district": BASELINE["min_district"],
            "n_crit": BASELINE["n_crit"],
        },
    }


@app.post("/api/simulate")
def simulate_endpoint(request: SimulationRequest):
    return simulate(request.selections)


@app.get("/api/trajectory")
def baseline_trajectory_endpoint():
    return trajectory([])


@app.post("/api/trajectory")
def trajectory_endpoint(request: SimulationRequest):
    try:
        return trajectory(request.selections)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/explain")
def explain_endpoint(payload: dict[str, Any]):
    # Never trust or explain client-provided numbers: reconstruct them from selections.
    selections = payload.get("selections")
    if not isinstance(selections, list):
        raise HTTPException(status_code=400, detail="В результате отсутствует список selections")
    result = simulate(selections)
    if not result.valid:
        raise HTTPException(status_code=400, detail=result.reason)
    return explain_result(result)


@app.post("/api/advise")
def advise_endpoint(request: AdvisorRequest):
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Запрос советнику не может быть пустым")
    return advise(request.current_scenario, message)
