from __future__ import annotations

import json

import pytest

from backend.app import proposals


@pytest.fixture
def board_path(tmp_path, monkeypatch):
    path = tmp_path / "isolated-board.json"
    monkeypatch.setenv("QQ_PROPOSALS_PATH", str(path))
    return path


def test_board_starts_empty_without_creating_seed_data(board_path):
    assert proposals.list_proposals() == {"proposals": []}
    assert not board_path.exists()


def test_empty_people_scenario_has_no_numeric_claims(board_path):
    result = proposals.build_people_scenario()

    assert result["scenario"] is None
    assert result["blind_max"] is None
    assert result["current_scenario"] is None
    assert result["included"] == []
    assert result["excluded"] == []
    assert result["reason"]


def test_recognized_proposal_uses_server_simulation_and_ignores_numbers(board_path):
    proposal = proposals.create_proposal({
        "measure_id": "M8",
        "district_id": "nura",
        "text": "Нужна поликлиника в Нуре",
        "score": 9999,
        "cost": 0,
        "votes": 100,
        "evidence": {"score": 9999},
    })

    assert proposal["status"] == "checked"
    assert proposal["evidence"]["plan_score"] != 9999
    assert proposal["evidence"]["plan_cost"] > 0
    assert proposal["evidence"]["contribution"]["measure_id"] == "M8"
    assert proposal["evidence"]["district"]["id"] == "nura"
    stored = json.loads(board_path.read_text(encoding="utf-8"))[0]
    assert "score" not in stored and "cost" not in stored and "votes" in stored
    assert stored["votes"] == 0


def test_unmatched_proposal_is_saved_submitted_without_numbers(board_path):
    proposal = proposals.create_proposal({
        "measure_id": "NOT-A-MEASURE",
        "district_id": "unknown",
        "text": "Хочу больше возможностей для жителей",
        "score": 100,
        "cost": 1,
    })

    assert proposal["status"] == "submitted"
    assert proposal["measure_id"] is None
    assert proposal["district_id"] is None
    assert "evidence" not in proposal
    assert "score" not in proposal and "cost" not in proposal


def test_votes_are_deduplicated_per_proposal(board_path):
    proposal = proposals.create_proposal(
        {"measure_id": "M6", "text": "Больше зелени в городе"}
    )
    first = proposals.vote_proposal(proposal["id"], "browser-token-1")
    second = proposals.vote_proposal(proposal["id"], "browser-token-1")
    third = proposals.vote_proposal(proposal["id"], "browser-token-2")
    assert first["votes"] == 1
    assert second["votes"] == 1
    assert third["votes"] == 2


def test_people_scenario_requires_votes_and_preserves_zero_vote_status(board_path):
    voted = proposals.create_proposal(
        {"measure_id": "M8", "district_id": "nura", "text": "Поликлиника в Нуре"}
    )
    unvoted = proposals.create_proposal(
        {"measure_id": "M4", "district_id": "saryarka", "text": "Парк в Сарыарке"}
    )

    without_votes = proposals.build_people_scenario()
    assert without_votes["scenario"] is None
    assert without_votes["included"] == []
    assert without_votes["excluded"] == []
    assert without_votes["not_participated_count"] == 2
    assert {row["status"] for row in proposals.list_proposals()["proposals"]} == {"checked"}

    proposals.vote_proposal(voted["id"], "resident-token")
    with_vote = proposals.build_people_scenario()
    assert with_vote["scenario"] is not None
    assert [row["proposal_id"] for row in with_vote["included"]] == [voted["id"]]
    assert with_vote["excluded"] == []
    assert with_vote["not_participated_count"] == 1
    statuses = {row["id"]: row["status"] for row in proposals.list_proposals()["proposals"]}
    assert statuses[voted["id"]] == "in_people_scenario"
    assert statuses[unvoted["id"]] == "checked"


def test_build_people_scenario_rejects_unconditional_m1_m3_conflict(board_path):
    m1 = proposals.create_proposal(
        {
            "measure_id": "M1",
            "district_id": "nura",
            "text": "Автобусная полоса в Нуре",
        }
    )
    m3 = proposals.create_proposal(
        {"measure_id": "M3", "district_id": "nura", "text": "Продлить ЛРТ в Нуре"}
    )
    proposals.vote_proposal(m3["id"], "first")
    proposals.vote_proposal(m1["id"], "second")
    proposals.vote_proposal(m3["id"], "third")

    result = proposals.build_people_scenario()

    assert result["scenario"] is not None
    assert any(item["proposal_id"] == m3["id"] for item in result["included"])
    reason = next(
        item["reason"]
        for item in result["excluded"]
        if item["proposal_id"] == m1["id"]
    )
    assert "Линия ЛРТ / расширение" in reason
    assert "M3" not in reason
    statuses = {
        item["id"]: item["status"]
        for item in proposals.list_proposals()["proposals"]
    }
    assert statuses[m3["id"]] == "in_people_scenario"
    assert statuses[m1["id"]] == "not_fitted"


def test_clear_empties_board(board_path):
    proposals.create_proposal({"text": "Идея без точного сопоставления"})
    assert proposals.clear_proposals() == {"cleared": 1}
    assert proposals.list_proposals() == {"proposals": []}


def test_invalid_inputs_have_human_readable_errors(board_path):
    with pytest.raises(ValueError, match="текст"):
        proposals.create_proposal({"text": "  "})
    proposal = proposals.create_proposal({"text": "Свободное предложение"})
    with pytest.raises(KeyError, match="не найдено"):
        proposals.vote_proposal("missing", "voter")
    with pytest.raises(ValueError, match="идентификатор"):
        proposals.vote_proposal(proposal["id"], "")
