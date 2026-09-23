from __future__ import annotations

from backend.app import digest


def _rows():
    return [
        {
            "id": "transport-a",
            "text": "Нужна автобусная полоса",
            "measure_id": "M1",
            "district_id": "nura",
            "votes": 4,
            "status": "in_people_scenario",
        },
        {
            "id": "transport-b",
            "text": "Настройте светофоры",
            "measure_id": "M2",
            "district_id": None,
            "votes": 3,
            "status": "checked",
        },
        {
            "id": "ecology-a",
            "text": "Нужен парк",
            "measure_id": "M4",
            "district_id": "saryarka",
            "votes": 2,
            "status": "checked",
        },
        {
            "id": "free-text",
            "text": "Свободная идея",
            "measure_id": None,
            "district_id": None,
            "votes": 1,
            "status": "submitted",
        },
    ]


def test_empty_board_returns_clear_empty_digest(monkeypatch) -> None:
    monkeypatch.setattr(digest, "list_proposals", lambda: {"proposals": []})

    result = digest.generate_digest()

    assert result["source"] == "deterministic_fallback"
    assert result["themes"] == []
    assert result["generated_at"]


def test_fallback_groups_by_catalog_direction(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(digest, "list_proposals", lambda: {"proposals": _rows()})

    result = digest.generate_digest()

    assert result["source"] == "deterministic_fallback"
    by_title = {theme["title"]: theme for theme in result["themes"]}
    assert set(by_title) == {"Транспорт", "Экология", "Прочее"}
    assert by_title["Транспорт"]["proposal_count"] == 2
    assert by_title["Транспорт"]["votes"] == 7
    assert by_title["Транспорт"]["districts"] == ["Нура"]
    assert len(by_title["Транспорт"]["measures"]) == 2
    assert by_title["Транспорт"]["in_people_scenario"] == 1


def test_numeric_llm_summary_forces_fallback_and_unknown_id_is_not_counted(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(digest, "list_proposals", lambda: {"proposals": _rows()})
    monkeypatch.setattr(
        digest,
        "_request_llm",
        lambda rows: [
            {
                "title": "Выдуманная тема",
                "summary": "Здесь 99 предложений",
                "proposal_ids": ["missing-id", rows[0]["id"]],
            }
        ],
    )

    result = digest.generate_digest()

    assert result["source"] == "deterministic_fallback"
    assert {theme["title"] for theme in result["themes"]} == {
        "Транспорт",
        "Экология",
        "Прочее",
    }
    assert sum(theme["proposal_count"] for theme in result["themes"]) == len(_rows())


def test_llm_ids_are_validated_and_missing_proposals_go_to_misc(monkeypatch) -> None:
    rows = _rows()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(digest, "list_proposals", lambda: {"proposals": rows})
    monkeypatch.setattr(
        digest,
        "_request_llm",
        lambda _rows_arg: [
            {
                "title": "Передвижение",
                "summary": "Жители предлагают изменить передвижение по городу.",
                "proposal_ids": ["transport-a", "transport-a", "missing-id"],
            }
        ],
    )

    result = digest.generate_digest()

    assert result["source"] == "openai"
    by_title = {theme["title"]: theme for theme in result["themes"]}
    assert by_title["Передвижение"]["proposal_count"] == 1
    assert by_title["Передвижение"]["votes"] == 4
    assert by_title["Прочее"]["proposal_count"] == 3
    assert sum(theme["proposal_count"] for theme in result["themes"]) == len(rows)
