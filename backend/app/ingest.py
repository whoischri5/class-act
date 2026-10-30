"""Turn raw football-data.org JSON into rows in our database ("upsert" = insert or update).

Football-specific gotcha handled here: knockout games can go to extra time and
penalties. We predict the **90-minute result** (home win / draw / away win), so a
tie decided on penalties counts as a draw — that's also how bookmakers price it.
"""
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.database import Match, Team, select

PLAYED_STATUSES = {"FINISHED", "AWARDED"}


def parse_utc(s: str) -> datetime:
    """'2024-06-01T19:00:00Z' -> naive UTC datetime."""
    return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)


def _pair(d: dict | None) -> tuple[int | None, int | None]:
    d = d or {}
    return d.get("home"), d.get("away")


def ninety_minute_score(score: dict) -> tuple[int | None, int | None]:
    """Return the score after 90 minutes (+ stoppage time), excluding extra time and penalties."""
    full = _pair(score.get("fullTime"))
    if score.get("duration", "REGULAR") == "REGULAR":
        return full

    regular = _pair(score.get("regularTime"))
    if regular[0] is not None:
        return regular

    # Older payloads may lack `regularTime`: subtract extra-time and shoot-out goals.
    if full[0] is None:
        return None, None
    home, away = full
    for part in ("extraTime", "penalties"):
        h, a = _pair(score.get(part))
        home -= h or 0
        away -= a or 0
    return home, away


def result_letter(home_goals: int | None, away_goals: int | None) -> str | None:
    if home_goals is None or away_goals is None:
        return None
    if home_goals > away_goals:
        return "H"
    if home_goals < away_goals:
        return "A"
    return "D"


class Loader:
    """Caches existing rows by football-data ID so repeated loads are fast and idempotent."""

    def __init__(self, session: Session):
        self.session = session
        self.teams = {t.fd_api_id: t for t in session.scalars(select(Team))}
        self.matches = {m.fd_api_id: m for m in session.scalars(select(Match))}

    def upsert_team(self, data: dict) -> Team:
        team = self.teams.get(data["id"])
        if team is None:
            team = Team(fd_api_id=data["id"], name=data.get("name") or f"Team {data['id']}")
            self.session.add(team)
            self.teams[data["id"]] = team
        # Only overwrite fields when the new payload actually has them.
        for attr, key in (("name", "name"), ("short_name", "shortName"), ("tla", "tla"), ("crest_url", "crest")):
            if data.get(key):
                setattr(team, attr, data[key])
        area = (data.get("area") or {}).get("name")  # only present in /teams responses
        if area:
            team.country = area
        return team

    def upsert_match(self, data: dict, competition: str) -> Match | None:
        home, away = data.get("homeTeam") or {}, data.get("awayTeam") or {}
        if not home.get("id") or not away.get("id"):
            return None  # e.g. a final whose teams aren't decided yet

        home_team = self.upsert_team(home)
        away_team = self.upsert_team(away)
        self.session.flush()  # assigns database IDs to any new teams

        status = data["status"]
        home_goals = away_goals = None
        if status in PLAYED_STATUSES:
            home_goals, away_goals = ninety_minute_score(data.get("score") or {})
        result = result_letter(home_goals, away_goals)
        if status in PLAYED_STATUSES and result is None and (data.get("score") or {}).get("duration") != "REGULAR":
            result = "D"  # went to extra time, so it was level after 90 minutes

        season_start = (data.get("season") or {}).get("startDate") or data["utcDate"]
        stage = data.get("stage")

        match = self.matches.get(data["id"])
        if match is None:
            match = Match(fd_api_id=data["id"])
            self.session.add(match)
            self.matches[data["id"]] = match
        match.competition = competition
        match.season = int(season_start[:4])
        match.stage = stage
        match.status = status
        match.match_date = parse_utc(data["utcDate"])
        match.neutral = stage == "FINAL"
        match.home_team_id = home_team.id
        match.away_team_id = away_team.id
        match.home_goals = home_goals
        match.away_goals = away_goals
        match.result = result
        return match


def load_teams_payload(loader: Loader, payload: dict) -> int:
    for team in payload.get("teams", []):
        loader.upsert_team(team)
    return len(payload.get("teams", []))


def load_matches_payload(loader: Loader, payload: dict) -> int:
    competition = (payload.get("competition") or {}).get("code") or "CL"
    count = 0
    for m in payload.get("matches", []):
        if loader.upsert_match(m, (m.get("competition") or {}).get("code") or competition):
            count += 1
    return count


def load_directory(session: Session, directory: Path) -> dict:
    """Load every cached JSON file in a folder. Team files first (they carry the country)."""
    loader = Loader(session)
    files = sorted(directory.glob("*.json"))
    stats = {"teams": 0, "matches": 0, "files": 0}
    for path in [f for f in files if f.stem.endswith("_teams")] + [f for f in files if not f.stem.endswith("_teams")]:
        payload = json.loads(path.read_text())
        if "teams" in payload and "matches" not in payload:
            stats["teams"] += load_teams_payload(loader, payload)
        else:
            stats["matches"] += load_matches_payload(loader, payload)
        stats["files"] += 1
    session.commit()
    return stats
