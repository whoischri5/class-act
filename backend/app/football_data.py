"""A small client for the football-data.org v4 REST API.

Free tier rules worth knowing:
  * 10 requests per minute -> we wait at least 6.5 seconds between calls.
  * Your key goes in the `X-Auth-Token` header.
  * A 403 means "your plan can't see this" (e.g. an old season), not "bad code".
"""
import time

import requests

from app.config import FOOTBALL_DATA_API_KEY, FOOTBALL_DATA_BASE_URL

MIN_SECONDS_BETWEEN_CALLS = 6.5


class FootballDataError(Exception):
    pass


class FootballDataClient:
    def __init__(self, api_key: str = FOOTBALL_DATA_API_KEY):
        if not api_key:
            raise FootballDataError(
                "FOOTBALL_DATA_API_KEY is not set. Copy backend/.env.example to "
                "backend/.env and paste your key from football-data.org."
            )
        self.session = requests.Session()
        self.session.headers["X-Auth-Token"] = api_key
        self._last_call = 0.0

    def _get(self, path: str, params: dict | None = None, max_retries: int = 3) -> dict:
        for attempt in range(max_retries + 1):
            # Rate limiting: never call more often than the free tier allows.
            wait = MIN_SECONDS_BETWEEN_CALLS - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

            resp = self.session.get(f"{FOOTBALL_DATA_BASE_URL}{path}", params=params, timeout=30)
            if resp.status_code == 429 and attempt < max_retries:
                # Too many requests: the API tells us how long until the counter resets.
                reset = int(resp.headers.get("X-RequestCounter-Reset", "60"))
                print(f"  rate limited; sleeping {reset}s")
                time.sleep(reset + 1)
                continue
            if resp.status_code == 403:
                raise FootballDataError(
                    f"403 Forbidden for {path} {params or ''}: your plan can't access this "
                    "resource (common for older seasons on the free tier)."
                )
            if not resp.ok:
                raise FootballDataError(f"{resp.status_code} for {path}: {resp.text[:200]}")
            return resp.json()
        raise FootballDataError(f"Gave up on {path} after {max_retries} retries")

    def competition_matches(
        self, competition: str, season: int | None = None, status: str | None = None
    ) -> dict:
        params = {}
        if season is not None:
            params["season"] = season
        if status:
            params["status"] = status
        return self._get(f"/competitions/{competition}/matches", params)

    def competition_teams(self, competition: str, season: int | None = None) -> dict:
        params = {"season": season} if season is not None else None
        return self._get(f"/competitions/{competition}/teams", params)
