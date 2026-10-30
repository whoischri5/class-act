"""All settings in one place, read from environment variables (or a local .env file).

Why environment variables? Secrets like your API key must never be committed to
GitHub. Locally they live in `backend/.env` (which is git-ignored); in production
you paste them into the Render dashboard instead.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

# --- External API -----------------------------------------------------------
FOOTBALL_DATA_API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY", "")
FOOTBALL_DATA_BASE_URL = "https://api.football-data.org/v4"

# The competition we predict. Other competitions are only used to keep Elo/form
# up to date (see ARCHITECTURE.md, "Why domestic leagues too?").
TARGET_COMPETITION = "CL"
COMPETITIONS = [
    c.strip()
    for c in (os.environ.get("COMPETITIONS") or "CL,PL,PD,BL1,SA,FL1").split(",")
    if c.strip()
]

# --- Database ---------------------------------------------------------------
# SQLite locally (a single file, zero setup). For Supabase, set DATABASE_URL to
# something like: postgresql+psycopg://postgres.xxxx:PASSWORD@aws-0-...pooler.supabase.com:5432/postgres
# (`or` instead of a .get() default, so an empty `DATABASE_URL=` line in .env also works.)
DATABASE_URL = os.environ.get("DATABASE_URL") or f"sqlite:///{BACKEND_DIR / 'data' / 'ucl.db'}"

# --- Folders ------------------------------------------------------------------
# (Overridable so the tests can use a throwaway folder.)
RAW_DATA_DIR = Path(os.environ.get("RAW_DATA_DIR", BACKEND_DIR / "data" / "raw"))
SAMPLE_DATA_DIR = Path(os.environ.get("SAMPLE_DATA_DIR", BACKEND_DIR / "data" / "sample"))
MODELS_DIR = Path(os.environ.get("MODELS_DIR", BACKEND_DIR / "models"))

# --- Web server ---------------------------------------------------------------
# Comma-separated list of frontend URLs allowed to call this API (CORS).
CORS_ORIGINS = [
    o.strip()
    for o in (os.environ.get("CORS_ORIGINS") or "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]

# How old the cached upcoming-fixtures list may get before the API re-fetches it.
FIXTURES_CACHE_HOURS = float(os.environ.get("FIXTURES_CACHE_HOURS") or 6)
