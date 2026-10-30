"""Generate FAKE Champions League seasons in football-data.org's exact JSON format.

    python -m scripts.make_sample_data

Why? So you can build and test the whole pipeline (loading, Elo, training, API,
frontend) before you have an API key, offline, without touching the rate limit.
The club names are real but every result is simulated — the app shows a
"sample data" banner whenever this data is loaded.

Each club gets a hidden "true strength" that drifts a little every season, and
goals are drawn from a Poisson distribution. A model that works should learn to
recover those strengths from results alone — a nice sanity check of the pipeline.
"""
import json
import math
import random
from datetime import datetime, timedelta, timezone

from app.config import SAMPLE_DATA_DIR
from scripts.fetch_history import current_season_start

CLUBS = [
    # (name, short name, TLA, country, starting strength)
    ("Manchester City FC", "Man City", "MCI", "England", 1800),
    ("Real Madrid CF", "Real Madrid", "RMA", "Spain", 1800),
    ("FC Bayern München", "Bayern", "FCB", "Germany", 1780),
    ("Liverpool FC", "Liverpool", "LIV", "England", 1750),
    ("FC Barcelona", "Barça", "BAR", "Spain", 1740),
    ("Paris Saint-Germain FC", "PSG", "PSG", "France", 1730),
    ("Arsenal FC", "Arsenal", "ARS", "England", 1720),
    ("FC Internazionale Milano", "Inter", "INT", "Italy", 1720),
    ("Club Atlético de Madrid", "Atleti", "ATM", "Spain", 1690),
    ("Bayer 04 Leverkusen", "Leverkusen", "B04", "Germany", 1680),
    ("Borussia Dortmund", "Dortmund", "BVB", "Germany", 1670),
    ("Chelsea FC", "Chelsea", "CHE", "England", 1670),
    ("Juventus FC", "Juventus", "JUV", "Italy", 1660),
    ("AC Milan", "Milan", "MIL", "Italy", 1650),
    ("SSC Napoli", "Napoli", "NAP", "Italy", 1650),
    ("Atalanta BC", "Atalanta", "ATA", "Italy", 1640),
    ("Tottenham Hotspur FC", "Tottenham", "TOT", "England", 1630),
    ("RB Leipzig", "Leipzig", "RBL", "Germany", 1630),
    ("Sport Lisboa e Benfica", "Benfica", "SLB", "Portugal", 1620),
    ("FC Porto", "Porto", "FCP", "Portugal", 1610),
    ("Sporting Clube de Portugal", "Sporting CP", "SCP", "Portugal", 1600),
    ("Aston Villa FC", "Aston Villa", "AVL", "England", 1610),
    ("PSV", "PSV", "PSV", "Netherlands", 1590),
    ("AFC Ajax", "Ajax", "AJA", "Netherlands", 1580),
    ("Feyenoord Rotterdam", "Feyenoord", "FEY", "Netherlands", 1570),
    ("Club Brugge KV", "Club Brugge", "CLU", "Belgium", 1560),
    ("Celtic FC", "Celtic", "CEL", "Scotland", 1530),
    ("FC Red Bull Salzburg", "Salzburg", "RBS", "Austria", 1540),
    ("Galatasaray SK", "Galatasaray", "GAL", "Turkey", 1550),
    ("FC Shakhtar Donetsk", "Shakhtar", "SHA", "Ukraine", 1530),
    ("GNK Dinamo Zagreb", "Dinamo Zagreb", "DIN", "Croatia", 1510),
    ("BSC Young Boys", "Young Boys", "YB", "Switzerland", 1500),
    ("FK Crvena Zvezda", "Crvena Zvezda", "CZV", "Serbia", 1500),
    ("FC København", "København", "COP", "Denmark", 1500),
    ("Olympique de Marseille", "Marseille", "MAR", "France", 1600),
    ("AS Monaco FC", "Monaco", "ASM", "France", 1590),
    ("Girona FC", "Girona", "GIR", "Spain", 1570),
    ("Real Sociedad de Fútbol", "Real Sociedad", "RSO", "Spain", 1590),
    ("VfB Stuttgart", "Stuttgart", "VFB", "Germany", 1580),
    ("Newcastle United FC", "Newcastle", "NEW", "England", 1630),
]

HOME_ADV = 60
SEASONS_BACK = 7


def make_team(i, club):
    name, short, tla, _country, _ = club
    return {"id": 9000 + i, "name": name, "shortName": short, "tla": tla, "crest": None}


def poisson(rng, lam):
    # Knuth's algorithm — fine for small lambdas like football scores.
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


def play(rng, strength, home, away, neutral=False):
    diff = (strength[home] + (0 if neutral else HOME_ADV) - strength[away]) / 400
    return poisson(rng, 1.45 * math.exp(0.9 * diff)), poisson(rng, 1.15 * math.exp(-0.9 * diff))


class SeasonWriter:
    def __init__(self, season, teams):
        self.season, self.teams, self.matches = season, teams, []
        self.next_id = 500000 + season * 1000

    def add(self, when, stage, home, away, score=None, group=None):
        self.next_id += 1
        self.matches.append(
            {
                "id": self.next_id,
                "utcDate": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "FINISHED" if score else "TIMED",
                "stage": stage,
                "group": group,
                "season": {"startDate": f"{self.season}-08-01", "endDate": f"{self.season + 1}-06-01"},
                "competition": {"code": "CL", "name": "UEFA Champions League"},
                "homeTeam": self.teams[home],
                "awayTeam": self.teams[away],
                "score": score
                or {"winner": None, "duration": "REGULAR", "fullTime": {"home": None, "away": None}},
            }
        )


def regular_score(h, a):
    winner = "HOME_TEAM" if h > a else "AWAY_TEAM" if a > h else "DRAW"
    return {"winner": winner, "duration": "REGULAR", "fullTime": {"home": h, "away": a}}


def decided_score(rng, h, a, needs_winner):
    """A knockout game that may need extra time and penalties. Mirrors the API's shape:
    fullTime includes extra time AND shoot-out goals; regularTime is the 90-minute score."""
    if not needs_winner:
        return regular_score(h, a), (h, a)
    eh, ea = poisson(rng, 0.35), poisson(rng, 0.3)
    if eh != ea:
        score = {"winner": "HOME_TEAM" if eh > ea else "AWAY_TEAM", "duration": "EXTRA_TIME",
                 "regularTime": {"home": h, "away": a}, "extraTime": {"home": eh, "away": ea},
                 "fullTime": {"home": h + eh, "away": a + ea}}
        return score, (h + eh, a + ea)
    ph = rng.choice([3, 4, 5]); pa = ph - 1 if rng.random() < 0.5 else ph + 1
    score = {"winner": "HOME_TEAM" if ph > pa else "AWAY_TEAM", "duration": "PENALTY_SHOOTOUT",
             "regularTime": {"home": h, "away": a}, "extraTime": {"home": eh, "away": ea},
             "penalties": {"home": ph, "away": pa},
             "fullTime": {"home": h + eh + ph, "away": a + ea + pa}}
    return score, (h + eh + (1 if ph > pa else 0), a + ea + (1 if pa > ph else 0))


def two_legged(rng, strength, w, t1, t2, stage, d1, played):
    """Returns the winner of a two-legged tie (t1 hosts leg 1)."""
    if not played(d1):
        w.add(d1, stage, t1, t2)
        w.add(d1 + timedelta(days=7), stage, t2, t1)
        return None
    h1, a1 = play(rng, strength, t1, t2)
    w.add(d1, stage, t1, t2, regular_score(h1, a1))
    h2, a2 = play(rng, strength, t2, t1)
    tied = (a1 + h2) == (h1 + a2)
    score, (fh, fa) = decided_score(rng, h2, a2, tied)
    w.add(d1 + timedelta(days=7), stage, t2, t1, score)
    return t1 if (h1 + fa) > (a1 + fh) else t2


def simulate_season(rng, season, strength, all_teams, now):
    is_current = season == current_season_start(now.date())
    w = SeasonWriter(season, all_teams)
    # Top 24 by strength always qualify; 8 more from the rest at random.
    ranked = sorted(strength, key=lambda t: -strength[t])
    entrants = ranked[:24] + rng.sample(ranked[24:], 8)
    pots = [sorted(entrants, key=lambda t: -strength[t])[i * 8:(i + 1) * 8] for i in range(4)]
    for pot in pots:
        rng.shuffle(pot)
    groups = [[pots[p][g] for p in range(4)] for g in range(8)]

    if is_current:
        # Spread matchdays around today so some are played and some are upcoming.
        start = now - timedelta(days=42)
        md_dates = [start + timedelta(days=14 * k) for k in range(6)]
    else:
        md_dates = [datetime(season, 9, 17) + timedelta(days=21 * k) for k in range(6)]

    def played(d):
        return d < now

    schedule = [((0, 1), (2, 3)), ((3, 0), (1, 2)), ((0, 2), (3, 1)), ((2, 0), (1, 3)), ((1, 0), (3, 2)), ((0, 3), (2, 1))]
    standings = {t: [0, 0, 0] for t in entrants}  # points, goal diff, goals for
    for md, pairs in enumerate(schedule):
        for g, group in enumerate(groups):
            when = md_dates[md].replace(hour=20, minute=0, second=0, microsecond=0) + timedelta(days=g // 4)
            for hi, ai in pairs:
                home, away = group[hi], group[ai]
                if played(when):
                    h, a = play(rng, strength, home, away)
                    w.add(when, "GROUP_STAGE", home, away, regular_score(h, a), group=f"GROUP_{'ABCDEFGH'[g]}")
                    for t, gf, ga in ((home, h, a), (away, a, h)):
                        standings[t][0] += 3 if gf > ga else 1 if gf == ga else 0
                        standings[t][1] += gf - ga
                        standings[t][2] += gf
                else:
                    w.add(when, "GROUP_STAGE", home, away, group=f"GROUP_{'ABCDEFGH'[g]}")

    if not played(md_dates[-1] + timedelta(days=2)):
        return w.matches  # current season: knockouts not drawn yet

    ranked_groups = [sorted(g, key=lambda t: standings[t], reverse=True) for g in groups]
    winners = [g[0] for g in ranked_groups]
    runners = [g[1] for g in ranked_groups]
    rng.shuffle(runners)
    ko_start = datetime(season + 1, 2, 18, 20)
    alive = []
    for i in range(8):  # runner-up hosts the first leg
        alive.append(two_legged(rng, strength, w, runners[i], winners[i], "LAST_16", ko_start + timedelta(days=i % 2), played))
    for stage, offset in (("QUARTER_FINALS", 49), ("SEMI_FINALS", 70)):
        rng.shuffle(alive)
        alive = [two_legged(rng, strength, w, alive[i], alive[i + 1], stage, ko_start + timedelta(days=offset), played)
                 for i in range(0, len(alive), 2)]
    final_day = datetime(season + 1, 6, 1, 19)
    h, a = play(rng, strength, alive[0], alive[1], neutral=True)
    score, _ = decided_score(rng, h, a, h == a)
    w.add(final_day, "FINAL", alive[0], alive[1], score)
    return w.matches


def main():
    rng = random.Random(42)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    current = current_season_start(now.date())
    teams = {i: make_team(i, c) for i, c in enumerate(CLUBS)}
    strength = {i: float(c[4]) for i, c in enumerate(CLUBS)}

    SAMPLE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for old in SAMPLE_DATA_DIR.glob("*.json"):
        old.unlink()
    for season in range(current - SEASONS_BACK, current + 1):
        for t in strength:  # clubs get better/worse between seasons
            strength[t] += rng.gauss(0, 35)
        matches = simulate_season(rng, season, strength, teams, now)
        payload = {"competition": {"code": "CL", "name": "UEFA Champions League"},
                   "filters": {"season": str(season)}, "matches": matches}
        (SAMPLE_DATA_DIR / f"CL_{season}_matches.json").write_text(json.dumps(payload, indent=1))
        played = sum(m["status"] == "FINISHED" for m in matches)
        print(f"CL {season}/{str(season + 1)[2:]}: {len(matches)} matches ({played} played)")

    team_payload = {"teams": [dict(teams[i], area={"name": c[3]}) for i, c in enumerate(CLUBS)]}
    (SAMPLE_DATA_DIR / "CL_sample_teams.json").write_text(json.dumps(team_payload, indent=1))
    print(f"\nWrote FAKE sample data to {SAMPLE_DATA_DIR}")
    print("Next: python -m scripts.load_data --sample")


if __name__ == "__main__":
    main()
