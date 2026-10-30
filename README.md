# UCL Match Predictor

## Description

A web app that predicts **home win / draw / away win** probabilities for upcoming UEFA Champions League matches.

Every club gets an **Elo rating**, a single number for how strong it is right now, which updates after every match. The app also tracks each club's **recent form** and **goal difference** over its last five games. A logistic-regression model trained on past seasons turns the gap between two teams into probabilities. A React frontend shows each upcoming fixture as a probability bar, and you can also pick any two clubs and ask for a prediction.

**APIs and platforms used**

| | Role |
|---|---|
| [football-data.org](https://www.football-data.org/) | Historical results and upcoming fixtures (REST API, free tier) |
| [Supabase](https://supabase.com/) | Hosted Postgres database in production |
| [FastAPI](https://fastapi.tiangolo.com/) | Python web API that serves the model |
| [React](https://react.dev/) + [Vite](https://vitejs.dev/) | Frontend |
| Render + Netlify | Hosting |

The full design, with the concepts explained, is in [ARCHITECTURE.md](ARCHITECTURE.md).

## Live Demo

_Coming in Phase 5: add the Netlify link here._

## Screenshots / Demo

_Add screenshots or a GIF of the fixture list and the matchup predictor (Phase 6)._

## Project layout

```
backend/
  app/
    config.py          settings from environment variables / .env
    database.py        tables: teams, matches, predictions, app_meta
    football_data.py   API client (rate limited, 10 req/min)
    ingest.py          raw JSON -> database rows (90-minute results)
    features.py        Elo + form, computed leakage-safe
    modeling.py        train / evaluate / save / load the model
    fixtures.py        refresh the current season
    main.py            FastAPI endpoints
  scripts/             command-line steps of the pipeline (see below)
  tests/               pytest suite (includes a data-leakage test)
frontend/
  src/api.js           every call to the backend lives here
  src/components/      FixtureList, FixtureCard, ProbabilityBar, MatchupPredictor, ModelInfo
render.yaml            backend deploy config for Render
.github/workflows/     CI tests + optional daily data refresh
```

## Setup Instructions

You need Python 3.11 or newer and Node.js 20 or newer.

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env              # then paste your football-data.org key into .env
```

**Option A: try it right away with sample data (no API key needed).** These results are simulated, and the app shows a banner while you use them.

```bash
python -m scripts.make_sample_data
python -m scripts.load_data --sample
python -m scripts.train
```

**Option B: use real data.** You need a [free API key](https://www.football-data.org/client/register) in `.env`.

```bash
rm -f data/ucl.db                 # only if you loaded sample data before
python -m scripts.fetch_history   # downloads ~8 seasons x 6 competitions; takes several minutes
python -m scripts.load_data
python -m scripts.train           # prints log loss vs. baseline + a calibration table
```

`fetch_history` ends with a summary of which seasons your plan could access. Free-tier keys may be refused (403) on older seasons. Missing seasons are skipped, and the rest of the pipeline still runs.

Then start the API:

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs to try every endpoint from the browser.

Run the tests:

```bash
python -m pytest
```

### Frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

### API endpoints

| Endpoint | Returns |
|---|---|
| `GET /health` | Status, whether the model is loaded, and the data source |
| `GET /teams` | Champions League clubs with their current Elo and form |
| `GET /fixtures/upcoming` | Upcoming CL fixtures, refreshed from football-data.org at most every 6 hours |
| `GET /predict?home_id=&away_id=&neutral=` | Probabilities for any matchup |
| `GET /predict/fixtures` | Every upcoming fixture with its prediction, in one call |
| `GET /model` | Training seasons, test metrics, calibration and coefficients |
| `GET /predictions/track-record` | How saved predictions did once the matches were played |

### Deployment (Phase 5)

1. **Supabase.** Create a project. Under *Connect*, copy the **Session pooler** connection string; Render can't reach the "direct" one because it is IPv6-only. Change its start to `postgresql+psycopg://` and put it in `backend/.env` as `DATABASE_URL`. Then run `python -m scripts.load_data` again. The tables are created automatically.
2. **Render.** Choose *New → Blueprint* and pick this repo. It reads `render.yaml`. Fill in `FOOTBALL_DATA_API_KEY`, `DATABASE_URL`, and `CORS_ORIGINS` (your Netlify URL). The model is trained during each deploy.
3. **Netlify.** Import the repo, set **Base directory** to `frontend`, and add the environment variable `VITE_API_URL` set to your Render URL.
4. **Optional:** add `FOOTBALL_DATA_API_KEY` and `DATABASE_URL` as GitHub Actions secrets. The *Refresh data* workflow will then pull new results for every competition each day.

The free Render plan sleeps after 15 minutes without traffic, so the first request after that can take about 50 seconds. The frontend shows a "waking up" message while it waits.

## Learning Journey

- _What inspired this project_
- _Intended impact / audience_
- _New tech learned (React, FastAPI, Supabase) and why you chose it_

## Technical Rationale

- _Why Python for the ML core and JS for the frontend_
- _Biggest tradeoffs (e.g., SQLite→Postgres migration timing, logistic regression vs gradient boosting)_
- _Hardest bug and how you debugged it_ (a real one from this build: scikit-learn's `log_loss` assumes the probability columns are in alphabetical order (A, D, H), but ours are H, D, A. The first evaluation scored the wrong columns and showed the model losing to the baseline. A warning in the output gave it away, and the fix was a five-line `log_loss` written by hand in `modeling.py`.)

## AI Usage

- _Which tools, a specific prompt example, and exactly what you changed in the output_
