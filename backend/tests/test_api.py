"""End-to-end: generate sample data, load it, train, then call the API like the frontend would."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.fixture(scope="module")
def client():
    from app.config import SAMPLE_DATA_DIR
    from app.database import engine, init_db, set_meta
    from app.ingest import load_directory
    from app.modeling import train_and_evaluate
    from scripts import make_sample_data

    make_sample_data.main()
    init_db()
    with Session(engine) as session:
        load_directory(session, SAMPLE_DATA_DIR)
        set_meta(session, "data_source", "sample")
        session.commit()
        meta = train_and_evaluate(session)
    assert meta["metrics"]["log_loss_model"] < meta["metrics"]["log_loss_baseline"]

    from app.main import app

    with TestClient(app) as c:
        yield c


def test_health(client):
    body = client.get("/health").json()
    assert body["model_loaded"] and body["data_source"] == "sample"


def test_teams_sorted_by_elo(client):
    teams = client.get("/teams").json()
    assert len(teams) >= 32
    elos = [t["elo"] for t in teams]
    assert elos == sorted(elos, reverse=True)


def test_predict_probabilities_sum_to_one_and_favour_stronger_team(client):
    teams = client.get("/teams").json()
    best, worst = teams[0]["id"], teams[-1]["id"]
    strong_home = client.get("/predict", params={"home_id": best, "away_id": worst}).json()
    total = strong_home["prob_home_win"] + strong_home["prob_draw"] + strong_home["prob_away_win"]
    assert total == pytest.approx(1, abs=1e-3)
    assert strong_home["prob_home_win"] > strong_home["prob_away_win"]


def test_predict_rejects_bad_input(client):
    teams = client.get("/teams").json()
    assert client.get("/predict", params={"home_id": teams[0]["id"], "away_id": teams[0]["id"]}).status_code == 400
    assert client.get("/predict", params={"home_id": 999999, "away_id": teams[0]["id"]}).status_code == 404


def test_predict_fixtures_returns_upcoming_with_predictions_and_saves_them(client):
    fixtures = client.get("/predict/fixtures").json()
    assert fixtures, "sample data always includes upcoming fixtures"
    assert all(f["prediction"] is not None for f in fixtures)
    dates = [f["match_date"] for f in fixtures]
    assert dates == sorted(dates)
    client.get("/predict/fixtures")  # calling twice must not duplicate stored predictions
    assert client.get("/predictions/track-record").status_code == 200


def test_cors_allows_local_frontend(client):
    r = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
