"""Database tables (the schema from ARCHITECTURE.md section 5) and connection setup.

We use SQLAlchemy, an ORM ("object-relational mapper"): each class below is a
table, each attribute is a column. The same code works on SQLite (local) and
Postgres (Supabase) — switching is just a different DATABASE_URL.

Note: all datetimes are stored as *naive UTC* (no timezone attached), because
SQLite has no real timezone support. Always compare against `utcnow()` below.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from app.config import BACKEND_DIR, DATABASE_URL


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fd_api_id: Mapped[int] = mapped_column(Integer, unique=True)  # football-data.org's ID
    name: Mapped[str] = mapped_column(String, nullable=False)
    short_name: Mapped[str | None] = mapped_column(String)
    tla: Mapped[str | None] = mapped_column(String)  # three-letter abbreviation, e.g. "MCI"
    country: Mapped[str | None] = mapped_column(String)
    crest_url: Mapped[str | None] = mapped_column(String)


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fd_api_id: Mapped[int] = mapped_column(Integer, unique=True)
    competition: Mapped[str] = mapped_column(String, nullable=False, index=True)  # 'CL', 'PL', ...
    season: Mapped[int] = mapped_column(Integer, nullable=False)  # 2023 = the 2023/24 season
    stage: Mapped[str | None] = mapped_column(String)  # 'GROUP_STAGE', 'LEAGUE_STAGE', 'FINAL', ...
    status: Mapped[str] = mapped_column(String, nullable=False)  # 'FINISHED', 'SCHEDULED', 'TIMED', ...
    match_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    neutral: Mapped[bool] = mapped_column(Boolean, default=False)  # True for the final

    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    home_goals: Mapped[int | None] = mapped_column(Integer)  # 90-minute score; NULL until played
    away_goals: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[str | None] = mapped_column(String(1))  # 'H', 'D', 'A'

    # Pre-match feature SNAPSHOTS — what we knew *before* kickoff (leakage safety).
    home_elo_pre: Mapped[float | None] = mapped_column(Float)
    away_elo_pre: Mapped[float | None] = mapped_column(Float)
    home_form_pre: Mapped[float | None] = mapped_column(Float)  # avg points, last 5 matches
    away_form_pre: Mapped[float | None] = mapped_column(Float)
    home_gd_pre: Mapped[float | None] = mapped_column(Float)  # avg goal difference, last 5
    away_gd_pre: Mapped[float | None] = mapped_column(Float)

    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])


class Prediction(Base):
    __tablename__ = "predictions"
    # One stored prediction per (match, model version), so models can be compared later.
    __table_args__ = (UniqueConstraint("match_id", "model_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), nullable=False)
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    prob_home_win: Mapped[float] = mapped_column(Float)
    prob_draw: Mapped[float] = mapped_column(Float)
    prob_away_win: Mapped[float] = mapped_column(Float)
    predicted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AppMeta(Base):
    """A tiny key/value table, e.g. 'fixtures_refreshed_at' or 'data_source'."""

    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


# `pool_pre_ping` re-checks connections before use — helpful with hosted Postgres,
# which closes idle connections.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def init_db() -> None:
    """Create any tables that don't exist yet (safe to call repeatedly)."""
    if DATABASE_URL.startswith("sqlite"):
        (BACKEND_DIR / "data").mkdir(exist_ok=True)
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        # Supabase also exposes every table through a public "Data API". Turning on
        # Row Level Security with no policies switches that off; our backend still has
        # full access because it connects as the tables' owner.
        with engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                conn.execute(text(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY'))


def get_meta(session: Session, key: str) -> str | None:
    row = session.get(AppMeta, key)
    return row.value if row else None


def set_meta(session: Session, key: str, value: str) -> None:
    row = session.get(AppMeta, key)
    if row:
        row.value = value
    else:
        session.add(AppMeta(key=key, value=value))


__all__ = [
    "AppMeta",
    "Base",
    "Match",
    "Prediction",
    "Session",
    "Team",
    "engine",
    "get_meta",
    "init_db",
    "select",
    "set_meta",
    "utcnow",
]
