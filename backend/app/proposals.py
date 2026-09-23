"""Small file-backed API layer for resident proposals and voting.

The board starts empty. Values that affect calculations are always resolved
from the server-side catalog and simulator; request-supplied numeric fields are
never copied into stored records or evidence.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from collections import Counter
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from .data import (
    BUDGET,
    DISTRICT_BY_ID,
    INCOMPATIBILITIES,
    MAX_PER_DIRECTION,
    MEASURE_BY_ID,
)
from .optimizer import search_scenarios
from .simulator import simulate

_LOCK = threading.Lock()
def _storage_path() -> Path:
    configured = os.getenv("QQ_PROPOSALS_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "var" / "proposals.json"


def _read_unlocked() -> list[dict[str, Any]]:
    path = _storage_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Не удалось прочитать доску предложений") from exc
    if not isinstance(payload, list) or any(
        not isinstance(row, dict) for row in payload
    ):
        raise RuntimeError("Файл доски предложений имеет неверный формат")
    return payload


def _write_unlocked(proposals: list[dict[str, Any]]) -> None:
    path = _storage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix="proposals-", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(proposals, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _resolve_evidence(
    measure_id: str, district_id: str | None
) -> dict[str, Any] | None:
    """Find a valid five-measure plan containing this proposal and resimulate it."""
    scenarios = search_scenarios(
        {
            "require_placements": [
                {"measure_id": measure_id, "district_id": district_id}
            ]
        },
        limit=1,
    )
    if not scenarios:
        return None
    result = simulate(scenarios[0]["selections"])
    if not result.valid:
        return None
    return {
        "plan_score": result.score,
        "plan_cost": result.cost_total,
        "plan_selections": result.selections,
        "contribution": next(
            (
                item
                for item in result.measure_contributions
                if item["measure_id"] == measure_id
            ),
            None,
        ),
        "district": next(
            (item for item in result.districts if item["id"] == district_id), None
        ) if district_id else None,
    }


def list_proposals() -> dict[str, Any]:
    """Return a vote-ranked board without creating seeded or placeholder records."""
    with _LOCK:
        rows = _read_unlocked()
    rows.sort(key=lambda row: (-int(row.get("votes", 0)), row.get("created_at", "")))
    return {
        "proposals": [
            {key: value for key, value in row.items() if key != "voter_ids"}
            for row in rows
        ]
    }


def create_proposal(payload: dict[str, Any]) -> dict[str, Any]:
    """Store only text and catalog placement fields; ignore all client numbers."""
    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Добавьте текст предложения")
    text = text.strip()
    if len(text) > 2000:
        raise ValueError("Текст предложения должен быть короче 2000 символов")

    requested_measure = payload.get("measure_id")
    measure_id = (
        requested_measure
        if isinstance(requested_measure, str) and requested_measure in MEASURE_BY_ID
        else None
    )
    requested_district = payload.get("district_id")
    district_id = (
        requested_district
        if isinstance(requested_district, str) and requested_district in DISTRICT_BY_ID
        else None
    )
    evidence = None
    status = "submitted"
    reason = None
    measure = MEASURE_BY_ID.get(measure_id) if measure_id else None
    if measure:
        if measure["type"] == "district" and district_id:
            evidence = _resolve_evidence(measure_id, district_id)
            if evidence:
                status = "checked"
            else:
                reason = (
                    "Меру нельзя включить в допустимый сценарий с таким размещением"
                )
        elif measure["type"] == "city":
            district_id = None
            evidence = _resolve_evidence(measure_id, None)
            if evidence:
                status = "checked"
            else:
                reason = "Меру нельзя включить в допустимый сценарий"
        else:
            # Missing placements remain resident-submitted for later clarification.
            district_id = None

    record: dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "measure_id": measure_id,
        "district_id": district_id,
        "text": text,
        "status": status,
        "status_reason": reason,
        "votes": 0,
        "voter_ids": [],
        "created_at": _now(),
    }
    if evidence is not None:
        record["evidence"] = evidence
    with _LOCK:
        rows = _read_unlocked()
        rows.append(record)
        _write_unlocked(rows)
    return record


def vote_proposal(proposal_id: str, voter_id: str) -> dict[str, Any]:
    """Count at most one vote per client-generated voter token and proposal."""
    voter_id = voter_id.strip() if isinstance(voter_id, str) else ""
    if not voter_id or len(voter_id) > 128:
        raise ValueError("Нужен идентификатор голосующего")
    with _LOCK:
        rows = _read_unlocked()
        record = next((row for row in rows if row.get("id") == proposal_id), None)
        if record is None:
            raise KeyError("Предложение не найдено")
        voter_ids = record.setdefault("voter_ids", [])
        if voter_id not in voter_ids:
            voter_ids.append(voter_id)
            record["votes"] = len(voter_ids)
            _write_unlocked(rows)
        return {key: value for key, value in record.items() if key != "voter_ids"}


def clear_proposals() -> dict[str, int]:
    """Clear the board (intended for an explicit admin/reset endpoint)."""
    with _LOCK:
        count = len(_read_unlocked())
        _write_unlocked([])
    return {"cleared": count}


def _proposal_order(row: dict[str, Any]) -> tuple[int, str]:
    return (-int(row.get("votes", 0)), str(row.get("created_at", "")))


@lru_cache(maxsize=1)
def _blind_maximum() -> dict[str, Any] | None:
    candidates = search_scenarios({}, objective="max_score", limit=1)
    if not candidates:
        return None
    result = simulate(candidates[0]["selections"])
    if not result.valid:
        return None
    return {
        "selections": result.selections,
        "score": result.score,
        "cost": result.cost_total,
        "districts": result.districts,
    }


def _scenario_payload(result: Any) -> dict[str, Any]:
    return {
        "selections": result.selections,
        "score": result.score,
        "cost": result.cost_total,
        "districts": result.districts,
    }


def _placement_conflict_reason(
    candidate: dict[str, Any], accepted: list[dict[str, Any]],
) -> str:
    measure_id = candidate.get("measure_id")
    measure = MEASURE_BY_ID.get(measure_id)
    if measure is None:
        return "Предложение не сопоставлено с мерой каталога"
    if len(accepted) >= 5:
        return "В сценарии уже выбрано пять мер"
    if any(row.get("measure_id") == measure_id for row in accepted):
        return "Мера уже представлена в сценарии"
    proposed = [*accepted, candidate]
    cost = sum(MEASURE_BY_ID[row["measure_id"]]["cost"] for row in proposed)
    if cost > BUDGET:
        return "Превышен общий бюджет"
    directions = Counter(
        MEASURE_BY_ID[row["measure_id"]]["direction"] for row in proposed
    )
    if any(count > MAX_PER_DIRECTION for count in directions.values()):
        return "Превышен лимит мер по одному направлению"
    placements = {row["measure_id"]: row.get("district_id") for row in proposed}
    for first, second in INCOMPATIBILITIES:
        if first in placements and second in placements:
            if first == "M1" and second == "M3":
                return "Меры M1 и M3 несовместимы"
            if placements[first] == placements[second]:
                return f"Меры {first} и {second} несовместимы в этом районе"
    return "Не удалось дополнить предложения до допустимого набора из пяти мер"


def build_people_scenario(
    current_scenario: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Greedily accept vote-ranked placements while the optimizer can complete them."""
    with _LOCK:
        rows = _read_unlocked()
    ranked = sorted(rows, key=_proposal_order)
    accepted: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for row in ranked:
        if row.get("measure_id") not in MEASURE_BY_ID:
            excluded.append(
                {
                    "proposal_id": row["id"],
                    "reason": "Предложение не сопоставлено с мерой каталога",
                }
            )
            continue
        measure = MEASURE_BY_ID[row["measure_id"]]
        district_id = row.get("district_id")
        if (measure["type"] == "district" and district_id not in DISTRICT_BY_ID) or (
            measure["type"] == "city" and district_id is not None
        ):
            excluded.append(
                {
                    "proposal_id": row["id"],
                    "reason": "Для меры не задано корректное размещение",
                }
            )
            continue
        candidate = {
            "proposal_id": row["id"],
            "measure_id": row["measure_id"],
            "district_id": district_id,
            "votes": int(row.get("votes", 0)),
        }
        if len(accepted) >= 5:
            excluded.append(
                {"proposal_id": row["id"], "reason": "В сценарии уже выбрано пять мер"}
            )
            continue
        placements = [
            {"measure_id": item["measure_id"], "district_id": item["district_id"]}
            for item in [*accepted, candidate]
        ]
        if not search_scenarios({"require_placements": placements}, limit=1):
            excluded.append(
                {
                    "proposal_id": row["id"],
                    "reason": _placement_conflict_reason(candidate, accepted),
                }
            )
            continue
        accepted.append(candidate)

    best = search_scenarios(
        {"require_placements": [
            {"measure_id": item["measure_id"], "district_id": item["district_id"]}
            for item in accepted
        ]},
        limit=1,
    ) if accepted else []
    scenario = None
    if best:
        simulation = simulate(best[0]["selections"])
        if simulation.valid:
            scenario = _scenario_payload(simulation)

    current_result = (
        simulate(current_scenario)
        if scenario and current_scenario
        else None
    )
    current_payload = (
        _scenario_payload(current_result)
        if current_result is not None and current_result.valid
        else None
    )

    included_ids = {item["proposal_id"] for item in accepted}
    excluded_by_id = {item["proposal_id"]: item["reason"] for item in excluded}
    with _LOCK:
        latest = _read_unlocked()
        for row in latest:
            if row.get("id") in included_ids:
                row["status"] = "in_people_scenario"
                row["status_reason"] = None
            elif row.get("id") in excluded_by_id:
                row["status"] = "not_fitted"
                row["status_reason"] = excluded_by_id[row["id"]]
        _write_unlocked(latest)

    return {
        "scenario": scenario,
        "included": accepted,
        "excluded": excluded,
        "blind_max": _blind_maximum() if scenario else None,
        "current_scenario": current_payload,
        "reason": None if scenario else "Пока нет подходящих предложений для сценария",
    }
