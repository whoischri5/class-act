"""Phase 4: pull the current season (new results + upcoming fixtures) for every competition.

    python -m scripts.refresh_data

The API also does this automatically for the Champions League every few hours
(see `maybe_refresh_fixtures` in app/main.py). Run this manually — or on a schedule —
to keep the domestic-league results that feed Elo up to date too, then re-run
`python -m scripts.train` now and then so the model learns from new results.
"""
from sqlalchemy.orm import Session

from app.config import COMPETITIONS
from app.database import engine, init_db, set_meta
from app.fixtures import refresh_current_season


def main():
    init_db()
    with Session(engine) as session:
        n = refresh_current_season(session, competitions=COMPETITIONS)
        set_meta(session, "data_source", "football-data.org")
        session.commit()
    print(f"Upserted {n} current-season matches across {', '.join(COMPETITIONS)}.")


if __name__ == "__main__":
    main()
