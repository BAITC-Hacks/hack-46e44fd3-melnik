"""Generate a verified thematic digest of resident proposal texts."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from openai import OpenAI
from pydantic import BaseModel

from .data import DISTRICT_BY_ID, MEASURE_BY_ID
from .proposals import list_proposals


class _ThemeDraft(BaseModel):
    title: str
    summary: str
    proposal_ids: list[str]


class _DigestDraft(BaseModel):
    themes: list[_ThemeDraft]


_SYSTEM_PROMPT = (
    "Сгруппируй тексты предложений жителей по смысловым темам. Используй только "
    "переданные идентификаторы и тексты. Не придумывай предложения и не делай "
    "выводов о голосах, районах, стоимости или эффектах. Каждое предложение "
    "помести ровно в одну тему. Дай теме короткий заголовок и краткое резюме на "
    "русском языке. В summary не пиши цифры."
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _request_llm(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Send only proposal ids and texts to the model."""
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    payload = [
        {"id": str(row.get("id", "")), "text": str(row.get("text", ""))}
        for row in rows
    ]
    completion = client.chat.completions.parse(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format=_DigestDraft,
        temperature=0,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise ValueError("OpenAI returned no structured digest")
    return [theme.model_dump() for theme in parsed.themes]


def _fallback_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        measure = MEASURE_BY_ID.get(row.get("measure_id"))
        title = measure["direction"] if measure else "Прочее"
        grouped[title].append(str(row.get("id", "")))

    themes = []
    for title, proposal_ids in grouped.items():
        summary = (
            "Предложения, которые пока не сопоставлены с направлением каталога."
            if title == "Прочее"
            else f"Предложения жителей о мерах направления «{title}»."
        )
        themes.append(
            {"title": title, "summary": summary, "proposal_ids": proposal_ids}
        )
    return themes


def _validate_groups(
    drafts: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Drop unknown/duplicate ids and put every omitted proposal into Misc."""
    known_ids = {str(row.get("id", "")) for row in rows}
    assigned: set[str] = set()
    validated: list[dict[str, Any]] = []
    for draft in drafts:
        title = draft.get("title") if isinstance(draft, dict) else None
        summary = draft.get("summary") if isinstance(draft, dict) else None
        proposal_ids = draft.get("proposal_ids") if isinstance(draft, dict) else None
        if not isinstance(title, str) or not title.strip():
            continue
        if not isinstance(summary, str) or re.search(r"\d", summary):
            raise ValueError("Theme summaries must not contain digits")
        if not isinstance(proposal_ids, list):
            continue
        accepted = []
        for proposal_id in proposal_ids:
            proposal_id = str(proposal_id)
            if proposal_id in known_ids and proposal_id not in assigned:
                accepted.append(proposal_id)
                assigned.add(proposal_id)
        if accepted:
            validated.append(
                {
                    "title": title.strip(),
                    "summary": summary.strip(),
                    "proposal_ids": accepted,
                }
            )

    missing = [
        str(row.get("id", ""))
        for row in rows
        if str(row.get("id", "")) not in assigned
    ]
    if missing:
        validated.append(
            {
                "title": "Прочее",
                "summary": "Другие предложения жителей, не вошедшие в основные темы.",
                "proposal_ids": missing,
            }
        )
    return validated


def _safe_votes(row: dict[str, Any]) -> int:
    try:
        return max(0, int(row.get("votes", 0)))
    except (TypeError, ValueError):
        return 0


def _aggregate(
    groups: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_id = {str(row.get("id", "")): row for row in rows}
    themes = []
    for group in groups:
        proposals = [by_id[item] for item in group["proposal_ids"] if item in by_id]
        districts = sorted(
            {
                DISTRICT_BY_ID[row["district_id"]]["name"]
                for row in proposals
                if row.get("district_id") in DISTRICT_BY_ID
            }
        )
        measures = sorted(
            {
                MEASURE_BY_ID[row["measure_id"]]["name"]
                for row in proposals
                if row.get("measure_id") in MEASURE_BY_ID
            }
        )
        themes.append(
            {
                "title": group["title"],
                "summary": group["summary"],
                "proposal_count": len(proposals),
                "votes": sum(_safe_votes(row) for row in proposals),
                "districts": districts,
                "measures": measures,
                "in_people_scenario": sum(
                    row.get("status") == "in_people_scenario" for row in proposals
                ),
            }
        )
    themes.sort(key=lambda theme: (-theme["votes"], theme["title"]))
    return themes


def generate_digest() -> dict[str, Any]:
    """Return themes plus code-computed board statistics."""
    rows = list_proposals().get("proposals", [])
    if not rows:
        return {
            "source": "deterministic_fallback",
            "themes": [],
            "generated_at": _now(),
        }

    source = "deterministic_fallback"
    groups = _fallback_groups(rows)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if api_key and api_key != "sk-placeholder":
        try:
            groups = _validate_groups(_request_llm(rows), rows)
            source = "openai"
        except Exception:  # noqa: BLE001 - digest must remain available offline
            groups = _fallback_groups(rows)
            source = "deterministic_fallback"

    return {
        "source": source,
        "themes": _aggregate(groups, rows),
        "generated_at": _now(),
    }
