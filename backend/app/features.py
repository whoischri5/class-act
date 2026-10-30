"""Elo ratings + recent form, computed in a leakage-safe way.

The one rule of this file: walk through matches in date order, and for each match
  1. take a SNAPSHOT of both teams' features   (only uses the past)
  2. THEN update the teams with the result      (now the match is "in the past")

Training and the live /predict endpoint both use this same code, so the features the
model sees in production are computed exactly like the ones it was trained on
(mismatches here are called "train/serve skew" and are a classic silent bug).
"""
from collections import deque
from dataclasses import dataclass, field

# --- Tunable constants ---------------------------------------------------------
BASE_ELO = 1500.0
K_FACTOR = 20.0  # how fast ratings move after each match
HOME_ADVANTAGE = 60.0  # Elo points added to the home side when computing expectations
SEASON_CARRYOVER = 0.8  # between seasons, keep 80% of a team's distance from 1500
FORM_WINDOW = 5  # "last N matches" for form features
DEFAULT_FORM_POINTS = 1.4  # ~average points per game; used before a team has played

# The model's inputs, in a fixed order. Saved next to the model so we never mix them up.
FEATURE_COLUMNS = ["elo_diff", "form_diff", "gd_diff", "neutral"]

POINTS = {"W": 3, "D": 1, "L": 0}


def expected_score(rating_a: float, rating_b: float) -> float:
    """Probability-like expected score for team A vs team B (0..1). 0.5 = even match."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


@dataclass
class TeamState:
    elo: float = BASE_ELO
    last_season: int | None = None
    # Each entry is (points, goal_difference) from one match; old ones fall off automatically.
    recent: deque = field(default_factory=lambda: deque(maxlen=FORM_WINDOW))

    @property
    def form(self) -> float:
        """Average points per game over the last few matches (0..3)."""
        if not self.recent:
            return DEFAULT_FORM_POINTS
        return sum(p for p, _ in self.recent) / len(self.recent)

    @property
    def goal_diff(self) -> float:
        """Average goal difference per game over the last few matches."""
        if not self.recent:
            return 0.0
        return sum(gd for _, gd in self.recent) / len(self.recent)


class FeatureTracker:
    """Keeps the running Elo + form for every team as we walk forward through time."""

    def __init__(self):
        self.teams: dict[int, TeamState] = {}

    def team(self, team_id: int) -> TeamState:
        if team_id not in self.teams:
            self.teams[team_id] = TeamState()
        return self.teams[team_id]

    def _start_season_if_new(self, state: TeamState, season: int | None) -> None:
        # Squads change over the summer, so pull ratings a bit back toward average.
        if season is not None and state.last_season is not None and season > state.last_season:
            state.elo = BASE_ELO + SEASON_CARRYOVER * (state.elo - BASE_ELO)
        if season is not None:
            state.last_season = season

    def snapshot(self, home_id: int, away_id: int, season: int | None = None) -> dict:
        """Pre-match features for both teams. Reads the current state; changes nothing
        except applying the between-seasons rating adjustment."""
        home, away = self.team(home_id), self.team(away_id)
        self._start_season_if_new(home, season)
        self._start_season_if_new(away, season)
        return {
            "home_elo_pre": home.elo,
            "away_elo_pre": away.elo,
            "home_form_pre": home.form,
            "away_form_pre": away.form,
            "home_gd_pre": home.goal_diff,
            "away_gd_pre": away.goal_diff,
        }

    def update(
        self,
        home_id: int,
        away_id: int,
        result: str,
        home_goals: int | None,
        away_goals: int | None,
        neutral: bool = False,
    ) -> None:
        """Apply a finished match's result to both teams."""
        home, away = self.team(home_id), self.team(away_id)

        # Elo update (ARCHITECTURE.md 4.3)
        bonus = 0.0 if neutral else HOME_ADVANTAGE
        e_home = expected_score(home.elo + bonus, away.elo)
        s_home = {"H": 1.0, "D": 0.5, "A": 0.0}[result]
        delta = K_FACTOR * (s_home - e_home)
        home.elo += delta
        away.elo -= delta  # zero-sum: whatever home gains, away loses

        # Form update
        gd = (home_goals - away_goals) if home_goals is not None and away_goals is not None else 0
        home_outcome = {"H": "W", "D": "D", "A": "L"}[result]
        away_outcome = {"H": "L", "D": "D", "A": "W"}[result]
        home.recent.append((POINTS[home_outcome], gd))
        away.recent.append((POINTS[away_outcome], -gd))


def model_inputs(snapshot: dict, neutral: bool) -> list[float]:
    """Turn a snapshot into the model's feature vector (order = FEATURE_COLUMNS).

    We feed *differences* between the teams rather than raw values, so the model
    learns "how much better is home than away" instead of memorising what a
    rating of 1700 means.
    """
    return [
        snapshot["home_elo_pre"] - snapshot["away_elo_pre"],
        snapshot["home_form_pre"] - snapshot["away_form_pre"],
        snapshot["home_gd_pre"] - snapshot["away_gd_pre"],
        1.0 if neutral else 0.0,
    ]


def walk(matches) -> tuple[FeatureTracker, list[tuple[object, dict]]]:
    """Process *played* matches in chronological order.

    `matches` can be any objects with: match_date, season, home_team_id, away_team_id,
    home_goals, away_goals, result, neutral. Returns the final tracker (= everyone's
    current form, used for live predictions) and a (match, snapshot) pair per match.
    """
    tracker = FeatureTracker()
    snapshots = []
    for m in sorted(matches, key=lambda m: m.match_date):
        if m.result is None:
            continue
        snap = tracker.snapshot(m.home_team_id, m.away_team_id, m.season)  # 1. look first...
        snapshots.append((m, snap))
        tracker.update(m.home_team_id, m.away_team_id, m.result, m.home_goals, m.away_goals, m.neutral)  # 2. ...then learn
    return tracker, snapshots
