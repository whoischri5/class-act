"""Phase 1, step 1: download historical seasons from football-data.org and cache them to disk.

    python -m scripts.fetch_history                        # default seasons + competitions
    python -m scripts.fetch_history --seasons 2021-2025 --competitions CL

Every response is saved to data/raw/<COMP>_<season>_matches.json. Finished seasons
never change, so they're never downloaded twice (that saves your rate limit and lets
you work on the parsing code offline). Run this first with --competitions CL and a
wide season range to see which seasons your plan can access.
"""
import argparse
import json
from datetime import date

from app.config import COMPETITIONS, RAW_DATA_DIR, TARGET_COMPETITION
from app.football_data import FootballDataClient, FootballDataError


def current_season_start(today: date | None = None) -> int:
    today = today or date.today()
    return today.year if today.month >= 7 else today.year - 1


def parse_seasons(text: str) -> list[int]:
    if "-" in text:
        start, end = text.split("-")
        return list(range(int(start), int(end) + 1))
    return [int(s) for s in text.split(",")]


def main():
    current = current_season_start()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seasons", default=f"{current - 7}-{current}", help="e.g. 2019-2026 or 2022,2023")
    parser.add_argument("--competitions", default=",".join(COMPETITIONS), help="e.g. CL,PL,PD")
    parser.add_argument("--force", action="store_true", help="re-download even if cached")
    args = parser.parse_args()

    client = FootballDataClient()
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    summary = []

    for code in args.competitions.split(","):
        for season in parse_seasons(args.seasons):
            path = RAW_DATA_DIR / f"{code}_{season}_matches.json"
            # Past seasons never change, so a cached copy is good forever.
            if path.exists() and season < current and not args.force:
                summary.append((code, season, "cached"))
                continue
            try:
                payload = client.competition_matches(code, season=season)
                path.write_text(json.dumps(payload))
                n = len(payload.get("matches", []))
                if code == TARGET_COMPETITION:
                    # The /teams endpoint also tells us each club's country.
                    teams = client.competition_teams(code, season=season)
                    (RAW_DATA_DIR / f"{code}_{season}_teams.json").write_text(json.dumps(teams))
                summary.append((code, season, f"ok ({n} matches)"))
            except FootballDataError as exc:
                summary.append((code, season, f"FAILED: {exc}"))
            print(f"{code} {season}: {summary[-1][2]}")

    print("\nSummary")
    for code, season, status in summary:
        print(f"  {code:<4} {season}/{str(season + 1)[2:]}  {status}")
    print("\nNext: python -m scripts.load_data")


if __name__ == "__main__":
    main()
