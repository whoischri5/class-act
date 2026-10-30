from sqlalchemy.orm import Session

from app.database import Match, Team, engine, init_db, select
from app.ingest import Loader, load_matches_payload, ninety_minute_score, result_letter


def test_regular_time_score_is_full_time():
    assert ninety_minute_score({"duration": "REGULAR", "fullTime": {"home": 2, "away": 1}}) == (2, 1)


def test_extra_time_uses_regular_time_field():
    score = {"duration": "EXTRA_TIME", "regularTime": {"home": 1, "away": 1},
             "extraTime": {"home": 1, "away": 0}, "fullTime": {"home": 2, "away": 1}}
    assert ninety_minute_score(score) == (1, 1)


def test_penalties_without_regular_time_field_subtracts_extras():
    score = {"duration": "PENALTY_SHOOTOUT", "extraTime": {"home": 0, "away": 0},
             "penalties": {"home": 4, "away": 3}, "fullTime": {"home": 6, "away": 5}}
    assert ninety_minute_score(score) == (2, 2)


def test_result_letter():
    assert result_letter(2, 1) == "H"
    assert result_letter(1, 1) == "D"
    assert result_letter(0, 3) == "A"
    assert result_letter(None, None) is None


def _payload(match_id, status="FINISHED", score=None, stage="GROUP_STAGE"):
    return {
        "competition": {"code": "CL"},
        "matches": [{
            "id": match_id, "utcDate": "2024-06-01T19:00:00Z", "status": status, "stage": stage,
            "season": {"startDate": "2023-08-01"},
            "homeTeam": {"id": 1, "name": "Home FC", "tla": "HOM"},
            "awayTeam": {"id": 2, "name": "Away FC", "tla": "AWY"},
            "score": score or {"duration": "REGULAR", "fullTime": {"home": 2, "away": 0}},
        }],
    }


def test_loading_is_idempotent_and_marks_finals_neutral():
    init_db()
    with Session(engine) as session:
        for _ in range(2):  # load twice: must not duplicate anything
            load_matches_payload(Loader(session), _payload(777001, stage="FINAL"))
            session.commit()
        rows = session.scalars(select(Match).where(Match.fd_api_id == 777001)).all()
        assert len(rows) == 1
        m = rows[0]
        assert (m.season, m.result, m.neutral) == (2023, "H", True)
        assert session.scalar(select(Team).where(Team.fd_api_id == 1)).tla == "HOM"


def test_scheduled_match_has_no_result():
    init_db()
    with Session(engine) as session:
        load_matches_payload(Loader(session), _payload(777002, status="TIMED", score={"fullTime": {"home": None, "away": None}}))
        session.commit()
        m = session.scalar(select(Match).where(Match.fd_api_id == 777002))
        assert m.result is None and m.home_goals is None
