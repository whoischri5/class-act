"""Keeping the current season up to date: upcoming fixtures and newly finished results."""
import json

from sqlalchemy.orm import Session

from app.config import RAW_DATA_DIR, TARGET_COMPETITION
from app.database import set_meta, utcnow
from app.football_data import FootballDataClient
from app.ingest import Loader, load_matches_payload


def refresh_current_season(
    session: Session, client: FootballDataClient | None = None, competitions: list[str] | None = None
) -> int:
    """Fetch the current season (one request per competition) and upsert it.

    One request returns every match of the season — finished ones get their final
    score, future ones are our upcoming fixtures — so this single call keeps both
    the predictions and the Elo ratings fresh.
    """
    client = client or FootballDataClient()
    competitions = competitions or [TARGET_COMPETITION]
    loader = Loader(session)
    total = 0
    for code in competitions:
        payload = client.competition_matches(code)
        RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        (RAW_DATA_DIR / f"{code}_current_matches.json").write_text(json.dumps(payload))
        total += load_matches_payload(loader, payload)
    set_meta(session, "fixtures_refreshed_at", utcnow().isoformat(timespec="seconds"))
    session.commit()
    return total

