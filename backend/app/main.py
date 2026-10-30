"""The FastAPI web server. Run locally with:  uvicorn app.main:app --reload
Then open http://127.0.0.1:8000/docs for interactive, auto-generated API docs.
"""
import logging
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import modeling
from app.config import CORS_ORIGIN_REGEX, CORS_ORIGINS, FIXTURES_CACHE_HOURS, FOOTBALL_DATA_API_KEY, TARGET_COMPETITION
from app.database import Match, Prediction, Team, engine, get_meta, init_db, select, utcnow
from app.features import FeatureTracker, walk
from app.fixtures import refresh_current_season

log = logging.getLogger("ucl")

UPCOMING_STATUSES = ("SCHEDULED", "TIMED")


class AppState:
    """Things we load once and reuse for every request (re-training per request would be far too slow)."""

    model = None
    meta: dict | None = None
    tracker: FeatureTracker = FeatureTracker()
    lock = threading.Lock()


state = AppState()


def rebuild_tracker() -> None:
    """Replay every played match to get each team's *current* Elo and form."""
    with Session(engine) as session:
        state.tracker, _ = walk(modeling.played_matches(session))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    state.model, state.meta = modeling.load_model()
    if state.model is None:
        log.warning("No trained model found — run `python -m scripts.train`. /predict will return 503.")
    rebuild_tracker()
    yield


app = FastAPI(
    title="UCL Match Predictor API",
    description="Champions League win/draw/loss probabilities from an Elo + form model.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_session():
    with Session(engine) as session:
        yield session


# --- Response shapes (these also document the API at /docs) --------------------------


class TeamOut(BaseModel):
    id: int
    name: str
    short_name: str | None
    tla: str | None
    country: str | None
    crest_url: str | None
    elo: float
    form: float


class Probabilities(BaseModel):
    prob_home_win: float
    prob_draw: float
    prob_away_win: float


class PredictionOut(Probabilities):
    model_version: str
    home_team: TeamOut
    away_team: TeamOut
    neutral: bool


class FixtureOut(BaseModel):
    id: int
    match_date: datetime
    stage: str | None
    status: str
    neutral: bool
    home_team: TeamOut
    away_team: TeamOut
    prediction: Probabilities | None = None


# --- Helpers ---------------------------------------------------------------------------


def team_out(team: Team) -> TeamOut:
    ts = state.tracker.team(team.id)
    return TeamOut(
        id=team.id,
        name=team.name,
        short_name=team.short_name,
        tla=team.tla,
        country=team.country,
        crest_url=team.crest_url,
        elo=round(ts.elo, 1),
        form=round(ts.form, 2),
    )


def require_model():
    if state.model is None:
        raise HTTPException(503, "Model not trained yet. Run `python -m scripts.train` and restart the server.")
    return state.model


def predict_for(home_id: int, away_id: int, neutral: bool, season: int | None = None) -> dict:
    snapshot = state.tracker.snapshot(home_id, away_id, season)
    return modeling.predict_probs(require_model(), snapshot, neutral)


def maybe_refresh_fixtures(session: Session) -> None:
    """Re-fetch the current season from football-data.org if our copy is stale.

    This is the 'backend proxy' pattern: the browser never calls football-data.org
    (that would expose the API key) — it calls us, and we call them at most every
    few hours, which also keeps us far below the free tier's rate limit.
    """
    if not FOOTBALL_DATA_API_KEY or get_meta(session, "data_source") == "sample":
        return
    last = get_meta(session, "fixtures_refreshed_at")
    if last and utcnow() - datetime.fromisoformat(last) < timedelta(hours=FIXTURES_CACHE_HOURS):
        return
    if not state.lock.acquire(blocking=False):
        return  # another request is already refreshing
    try:
        refresh_current_season(session)
        rebuild_tracker()
    except Exception as exc:  # serve slightly stale data rather than an error page
        session.rollback()
        log.warning("Fixture refresh failed: %s", exc)
    finally:
        state.lock.release()


def upcoming_matches(session: Session, limit: int) -> list[Match]:
    return list(
        session.scalars(
            select(Match)
            .where(
                Match.competition == TARGET_COMPETITION,
                Match.status.in_(UPCOMING_STATUSES),
                Match.match_date >= utcnow() - timedelta(hours=3),
            )
            .order_by(Match.match_date)
            .limit(limit)
        )
    )


def fixture_out(match: Match, prediction: dict | None = None) -> FixtureOut:
    return FixtureOut(
        id=match.id,
        match_date=match.match_date,
        stage=match.stage,
        status=match.status,
        neutral=match.neutral,
        home_team=team_out(match.home_team),
        away_team=team_out(match.away_team),
        prediction=Probabilities(**prediction) if prediction else None,
    )


# --- Endpoints -------------------------------------------------------------------------


@app.get("/")
def root():
    return {"message": "UCL Match Predictor API. See /docs for the endpoints."}


@app.get("/health")
def health(session: Session = Depends(get_session)):
    return {
        "status": "ok",
        "model_loaded": state.model is not None,
        "model_version": state.meta["model_version"] if state.meta else None,
        "data_source": get_meta(session, "data_source") or "football-data.org",
        "teams": session.scalar(select(func.count(Team.id))),
        "matches": session.scalar(select(func.count(Match.id))),
        "fixtures_refreshed_at": get_meta(session, "fixtures_refreshed_at"),
    }


@app.get("/model")
def model_info():
    """How the current model was trained and how well it scored on the held-out season."""
    if state.meta is None:
        raise HTTPException(503, "Model not trained yet.")
    return state.meta


@app.get("/teams", response_model=list[TeamOut])
def list_teams(session: Session = Depends(get_session)):
    """Teams that have played in the Champions League, strongest (by Elo) first."""
    cl_team_ids = select(Match.home_team_id).where(Match.competition == TARGET_COMPETITION).union(
        select(Match.away_team_id).where(Match.competition == TARGET_COMPETITION)
    )
    teams = session.scalars(select(Team).where(Team.id.in_(cl_team_ids)))
    return sorted((team_out(t) for t in teams), key=lambda t: -t.elo)


@app.get("/fixtures/upcoming", response_model=list[FixtureOut])
def fixtures_upcoming(limit: int = Query(50, ge=1, le=200), session: Session = Depends(get_session)):
    maybe_refresh_fixtures(session)
    return [fixture_out(m) for m in upcoming_matches(session, limit)]


@app.get("/predict", response_model=PredictionOut)
def predict(
    home_id: int,
    away_id: int,
    neutral: bool = False,
    session: Session = Depends(get_session),
):
    """Probabilities for any matchup, using both teams' *current* Elo and form."""
    if home_id == away_id:
        raise HTTPException(400, "Pick two different teams.")
    home, away = session.get(Team, home_id), session.get(Team, away_id)
    if home is None or away is None:
        raise HTTPException(404, "Unknown team id. See /teams for valid ids.")
    probs = predict_for(home_id, away_id, neutral)
    return PredictionOut(
        **probs,
        model_version=state.meta["model_version"],
        home_team=team_out(home),
        away_team=team_out(away),
        neutral=neutral,
    )


@app.get("/predict/fixtures", response_model=list[FixtureOut])
def predict_fixtures(limit: int = Query(50, ge=1, le=200), session: Session = Depends(get_session)):
    """Every upcoming fixture with its prediction attached — one call for the whole page.

    Predictions are also saved to the `predictions` table (once per match and model
    version) so you can later check how the model did once the matches are played.
    """
    require_model()
    maybe_refresh_fixtures(session)
    version = state.meta["model_version"]
    matches = upcoming_matches(session, limit)
    already_saved = set(
        session.scalars(
            select(Prediction.match_id).where(
                Prediction.model_version == version,
                Prediction.match_id.in_([m.id for m in matches]),
            )
        )
    )
    out = []
    for m in matches:
        probs = predict_for(m.home_team_id, m.away_team_id, m.neutral, m.season)
        if m.id not in already_saved:
            session.add(Prediction(match_id=m.id, model_version=version, **probs))
        out.append(fixture_out(m, probs))
    session.commit()
    return out


@app.get("/predictions/track-record")
def track_record(session: Session = Depends(get_session)):
    """How did saved predictions do on matches that have since been played?"""
    rows = session.execute(
        select(Prediction, Match)
        .join(Match, Prediction.match_id == Match.id)
        .where(Match.result.is_not(None))
    ).all()
    correct = 0
    for pred, match in rows:
        probs = {"H": pred.prob_home_win, "D": pred.prob_draw, "A": pred.prob_away_win}
        correct += max(probs, key=probs.get) == match.result
    return {
        "graded_predictions": len(rows),
        "accuracy": round(correct / len(rows), 3) if rows else None,
    }
