# UEFA Champions League Match Predictor — Architecture & Learning Guide

A full-stack project plan for a beginner Python programmer who wants to learn new languages/frameworks while building something real for the API Challenge.

> **v2: revised while building.** Phases 0–4 are implemented in this repo. The changes from the original plan are listed first, with the reason for each, and the rest of the guide has been updated to match.

---

## 0. What Changed From v1 (and why)

| # | Change | Why it matters |
|---|---|---|
| 1 | **Domestic leagues (PL, La Liga, Bundesliga, Serie A, Ligue 1) now feed Elo and form.** The model still trains and predicts *only* Champions League matches. | A club plays only 6–17 CL matches a season, too few for Elo to settle. With league matches included it updates ~50 times a season instead. All five leagues are on football-data.org's free tier, and team IDs are shared across competitions, so this costs about one request per league per season. |
| 2 | **We predict the 90-minute result.** A knockout tie decided in extra time or on penalties counts as a *draw*. | The API's `fullTime` score *includes* extra-time and shoot-out goals. Using it naively would turn draws into wins and corrupt both the labels and the Elo updates. `ingest.py` reads `regularTime` instead. |
| 3 | **The final is a neutral venue**: no Elo home bonus, plus a `neutral` model feature. | Neither "home" team is at home in the final. |
| 4 | **Ratings regress 20% toward 1500 between seasons.** | Squads change every summer, so last May's rating is over-confident by August. |
| 5 | **Baseline = historical base rates**, not "always predict home win". | A 100% home-win prediction gets an *infinite* log loss the first time an away team wins, so it can't be compared on log loss. "Always home" is still reported for **accuracy**. |
| 6 | **No `multi_class="multinomial"` argument.** | That argument was removed in recent scikit-learn, where multinomial is already the default. Passing it now raises an error. |
| 7 | **Hand-written `log_loss`.** | scikit-learn's `log_loss(..., labels=["H","D","A"])` silently assumes the columns are in *alphabetical* order (A, D, H). It printed a warning and gave wrong numbers that made the model look worse than the baseline. |
| 8 | **Training and `/predict` share one feature function** (`features.walk`). | If live features are computed even slightly differently from training features ("train/serve skew"), predictions go quietly wrong. Sharing one function rules that out. |
| 9 | **Chronological split now skips a warm-up season and handles an in-progress season.** | Every club starts at 1500, so the first season's features are noise. The current season usually has too few played matches to test on. It still goes into the final model. |
| 10 | **A sample-data mode** (`scripts.make_sample_data`) writes fake seasons in football-data.org's exact JSON format. | You can build and test everything offline, before you have a key, without spending rate limit. A banner in the UI makes it obvious when you're looking at fake data. |
| 11 | **Free-tier history might be limited.** `fetch_history` prints which seasons your key could access, and skips any that return 403. | Older seasons may be restricted on the free plan. Check this on day one, because how much CL history you can get decides how much there is to train on. |
| 12 | **Supabase: use the *Session pooler* connection string.** | Supabase's direct connection is IPv6-only, and Render's free tier can't reach it. |
| 13 | **Added `/health`, `/model` and `/predictions/track-record` endpoints, a "How good is the model?" tab, CI, and an optional daily data-refresh GitHub Action.** | These make the README's "technical rationale" easy to show, and keep the deployed app current without manual runs. |
| 14 | **Two small schema additions:** `matches.competition`, `status`, `neutral` and goal-difference snapshot columns, plus an `app_meta` key/value table. Probabilities use `FLOAT` instead of `NUMERIC`. | `NUMERIC` comes back from Postgres as Python `Decimal`, which doesn't mix with numpy. |

---

## 1. How This Satisfies the Challenge

| Requirement | How the project meets it |
|---|---|
| 2–3 APIs/platforms | **football-data.org** (match and fixture data) + **Supabase** (hosted Postgres). **The Odds API** is an optional third, as a stretch feature |
| At least 1 never used before | Both of the above are new to you. React and FastAPI are new too |
| JS recommended | The **frontend is React**. The ML core stays in Python (your strength). This is a normal real-world split, not a workaround |
| Public GitHub repo + README | `README.md` follows the submission skeleton (section 11) |
| Deploy if possible | Render (API + static frontend) + Supabase (DB), all on free tiers. One `render.yaml` Blueprint deploys both; [DEPLOY.md](DEPLOY.md) walks through it |

About the data source: football-data.org's free tier covers 12 competitions, **including the Champions League and the top 5 leagues**, at 10 requests/minute, with slightly delayed (not live) scores. That suits this project. You don't need live data. You need *historical* results for training and fixture lists that are accurate by the next day. Older seasons may be restricted on the free tier (change #11). If you later want richer stats, such as player-level data, API-Football's free tier (100 req/day) is the usual next step.

---

## 2. High-Level Architecture

```
                    ┌──────────────────────┐
                    │  football-data.org    │  CL + 5 domestic leagues
                    └──────────┬────────────┘
                               │ fetched only by the backend, never the browser
                               ▼
   ┌────────────────────────────────────────────────────────┐
   │                    BACKEND (Python)                     │
   │                                                         │
   │  scripts/fetch_history ──▶ data/raw/*.json (cache)      │
   │  scripts/load_data     ──▶ Database (SQLite → Supabase)  │
   │                            teams / matches / predictions│
   │                                   │ reads               │
   │  scripts/train ──▶ features.walk ─┤──▶ models/model.joblib
   │                    (Elo + form)   │     + model_meta.json
   │                                   ▼                     │
   │                       FastAPI (app/main.py)             │
   │       /teams  /fixtures/upcoming  /predict  /model      │
   │       (same features.walk → current Elo for /predict)   │
   └───────────────────────────────┬────────────────────────┘
                                   │ JSON over HTTPS
                                   ▼
                    ┌──────────────────────────────┐
                    │  FRONTEND (React + Vite)      │
                    │  fixtures · any matchup ·     │
                    │  model report card            │
                    └──────────────────────────────┘
```

**Key architectural decision:** the browser never talks to football-data.org directly. It only talks to *your* backend, and the backend talks to football-data.org. This is called the **backend proxy pattern**. It is the standard way to keep an API key secret, because a key embedded in frontend JavaScript is visible to anyone who opens dev tools. The backend also caches what it fetches and refreshes at most every 6 hours, which keeps you well under the rate limit however many people use the site.

---

## 3. Tech Stack & Why

| Layer | Choice | Why |
|---|---|---|
| ML / feature engineering | **Python** (numpy, scikit-learn) | Your existing strength. This is the intellectual core of the project, so there's no reason to fight your tools here. Add pandas for exploring data in a notebook if you like |
| Backend API | **FastAPI** (Python) | A new framework for you, but still Python syntax, so the learning curve is gentle. It generates interactive API docs at `/docs` automatically, which is useful for testing and makes a good README screenshot |
| Database access | **SQLAlchemy 2** (ORM) | The same code runs on SQLite and on Postgres, so the Supabase switch is a one-line config change. This is tested: the test suite passes on both |
| Database | **Postgres via Supabase** | A new platform. Free tier, a real relational database (not a toy), and a web dashboard for browsing your tables while you learn SQL |
| Frontend | **React 19** (via Vite) + React-Bootstrap | A new language for you (JS/JSX). Vite is faster and simpler to set up than older tooling. React-Bootstrap gives you a decent-looking UI without deep CSS knowledge |
| HTTP client | **axios** | Cleaner syntax than raw `fetch` for a beginner |
| Deployment | Render (Python web service + static site) | A generous free tier, and one Blueprint file (`render.yaml`) deploys both halves of the app |
| Local dev DB | **SQLite** first, then Postgres | See section 10. Build against something with no setup before adding a network dependency |

---

## 4. Concepts You Need — Taught in Full

### 4.1 What an API actually is
An API (Application Programming Interface) is a contract: "send a request shaped like *this*, and I'll send back data shaped like *that*." A **REST API** (which both football-data.org and your own backend are) uses HTTP, the same protocol your browser uses to load web pages. URLs are the "nouns" (`/matches`, `/teams`) and HTTP methods are the "verbs" (`GET` to read, `POST` to create). Calling `GET https://api.football-data.org/v4/competitions/CL/matches` asks for the noun "matches" in the competition "CL" (Champions League). The server responds with JSON, a text format that maps directly onto Python dicts and lists.

**API keys** are how a service knows who's calling and enforces rate limits. You get one free from football-data.org and send it in the `X-Auth-Token` request header. Never commit it to GitHub (see 4.7).

### 4.2 Relational databases and schema design
A relational database stores data in **tables** (rows and columns). Tables relate to each other through **keys**:
- A **primary key** uniquely identifies a row. For example, each team has a unique `id`.
- A **foreign key** is a column in one table that points to a primary key in another. For example, `matches.home_team_id` points to `teams.id`.

Why not dump everything into one giant spreadsheet? Because data would be duplicated everywhere. Every match row would repeat the full team name, country and so on, and renaming a team would mean updating hundreds of rows. Splitting data into linked tables so that each fact lives in exactly one place is called **normalization**. Section 5 gives the concrete schema.

### 4.3 Elo ratings — the single most important feature you'll build
Elo (originally from chess) gives every team a single number for "how good are they right now", updated after every match. It's simple to implement and a genuinely strong predictive feature. It was the backbone of FiveThirtyEight's old soccer model.

The core idea (`app/features.py`):
1. Every team starts at a baseline rating of 1500.
2. Before a match, calculate the **expected result** for the home team from the rating gap:
   `E_home = 1 / (1 + 10^((R_away - (R_home + home_bonus)) / 400))`
   This gives a number between 0 and 1. For example, 0.5 means an evenly matched game.
3. After the match, update both ratings based on the *actual* result compared with the *expected* one:
   `R_home_new = R_home + K * (S_home - E_home)` (and the away team loses exactly what home gains)
   `S_home` is 1 for a win, 0.5 for a draw and 0 for a loss. `K` controls how fast ratings move. We use K=20.
4. **Home-field bonus:** +60 rating points for the home team when calculating `E_home`, because home advantage is real and measurable in football. The bonus is **0 at a neutral venue** (the final).
5. **Between seasons**, every rating moves 20% of the way back toward 1500, because squads change.

The elegant part is that this is *sequential*. You process matches in chronological order, and each match's Elo calculation only uses information available *before* that match. That leads directly to the most important warning in this guide:

### 4.4 Data leakage — the #1 mistake in sports prediction models
**Leakage** is when your model accidentally has access to information it wouldn't have had at prediction time. It looks great in testing and fails in reality. Three leakage traps apply to this project:

1. **Random train/test splits.** If you randomly shuffle matches and split 80/20, the model can end up training on a 2024 match and being "tested" on a 2022 match, which means it indirectly learned about the future. **Always split chronologically**: train on older seasons, test on the most recent one.
2. **Using end-of-match data as a "pre-match" feature.** Goals scored *in* the match you're predicting obviously can't be an input. That sounds obvious, but it's an easy mistake when features come from a careless SQL query, such as a "team's goals this season" feature that accidentally includes the match itself.
3. **Using today's ratings for old matches.** Labelling a 2021 match with a team's *current* Elo leaks four years of future results into it.

The safeguard is to snapshot every feature (Elo, form and so on) *as it stood right before kickoff* for every match, and store that snapshot instead of recomputing it later. In code, `features.walk()` always takes the snapshot first and applies the result second. `tests/test_features.py::test_no_leakage_...` checks this: changing a match's result must not change that match's features.

### 4.5 Feature engineering for match prediction
Useful predictive signals:
- **Elo** (implemented).
- **Recent form**: average points per game over the last 5 matches in *any* competition (win=3, draw=1, loss=0). Implemented.
- **Goal difference trend**: average goals scored minus conceded over the last 5 matches. Implemented.
- **Neutral venue** flag. Implemented.
- *Ideas for later:* home/away split performance, head-to-head history, rest days since the last match, and the second leg's first-leg score (a team 3–0 up plays differently).

Each feature is computed for both teams, and the model gets the **difference** (`elo_diff = home_elo - away_elo`) rather than the raw values. That generalizes much better than making the model memorize what "Elo 1700" means on its own.

### 4.6 Training and evaluating the model
This is a **multi-class classification** problem: the outcome is one of `{Home Win, Draw, Away Win}`.
- **Baseline model:** multinomial logistic regression (`LogisticRegression()`, which is multinomial by default; don't pass `multi_class`), with `StandardScaler` in front so that Elo gaps (hundreds) and form gaps (single digits) are on the same scale. It's fast, easy to reason about, and a strong baseline in sports prediction. Don't skip it to jump straight to something fancier.
- **Upgrade later:** gradient-boosted trees (`XGBoost` or `LightGBM`) usually squeeze out more accuracy once you're comfortable with the pipeline. Save the result as `model_version="xgb_v1"` so the `predictions` table keeps both versions.

**Evaluation matters more than people think here.** Plain accuracy is misleading because draws are rare and hard to predict. A model that never predicts "draw" can still score decent accuracy, and it does: expect `predicted_draws` to be near 0. Use:
- **Log loss** (cross-entropy): the average of `-log(probability you gave to what actually happened)`. It punishes confident wrong predictions heavily and rewards well-calibrated probabilities, which is exactly what a "probability of each outcome" product needs. Compare it against the **base-rate baseline** (always predicting the historical H/D/A frequencies).
- **Calibration check:** of all the matches where you predicted "70% home win", did home teams actually win about 70% of the time? `scripts.train` prints this table, and the "How good is the model?" tab shows it.

### 4.7 Serving a model behind a web API
Once trained, the model is saved with `joblib.dump`, together with `model_meta.json`, which holds the exact feature list, the metrics and the coefficients. FastAPI loads both once at startup and reuses them for every request. You are **not** retraining on every prediction, which would be far too slow. At startup the API also replays every played match through `features.walk()` to get each team's *current* Elo and form.

Two things every beginner backend needs:
- **CORS (Cross-Origin Resource Sharing):** by default, browsers block a page on `ucl-predictor.onrender.com` from calling an API on `ucl-predictor-api.onrender.com`, because they are different "origins". FastAPI's `CORSMiddleware` explicitly allows your frontend's domain, set with the `CORS_ORIGINS` (exact URLs) or `CORS_ORIGIN_REGEX` (a pattern) environment variable. Without it you get a confusing browser error that has nothing to do with your code being wrong.
- **Environment variables for secrets:** your football-data.org key and database connection string live in `backend/.env`, which is listed in `.gitignore` and never pushed to GitHub. The code reads them in `app/config.py`. In production you set them in the Render dashboard.

### 4.8 React basics you actually need (nothing more)
React apps are built from **components**: functions that return HTML-like syntax called JSX. Two hooks cover 90% of what you need at the start:
- `useState`: a variable that makes the component re-render when it changes (for example, the list of fixtures you fetched).
- `useEffect`: runs code when the component first loads (for example, "fetch fixtures from my API as soon as this page opens").

`frontend/src/components/FixtureList.jsx` is exactly this pattern, plus loading and error states:
```jsx
function FixtureList() {
  const [fixtures, setFixtures] = useState([]);

  useEffect(() => {
    getFixturePredictions().then(setFixtures); // axios call, defined in src/api.js
  }, []); // empty array = run once on load

  return (
    <div>
      {fixtures.map(f => <FixtureCard key={f.id} fixture={f} />)}
    </div>
  );
}
```
That's most of the mental model. Everything else (routing, forms, state libraries) is optional polish you can add later if the project grows.

### 4.9 Deployment concepts
"Deploying" means running your code on a server other people can reach, instead of only on your laptop. For this stack:
- **Backend (Render):** `render.yaml` tells Render "this is a Python web service in `backend/`: install, train, run uvicorn". You set the secrets in its dashboard. The free plan **sleeps after 15 minutes idle**, so the first request takes about 50 seconds; the frontend shows a "waking up" message. Render's disk is also wiped on every deploy, which is why production needs Supabase rather than SQLite.
- **Frontend (Render static site):** `npm run build` turns the React app into static HTML/CSS/JS files, and Render serves them directly. The frontend itself needs no server, so it never sleeps. `VITE_API_URL` is baked in *at build time*, so changing it needs a rebuild.
- **Database (Supabase):** already hosted for you. You get a connection string to put in your backend's environment variables (use the Session pooler string, change #12).

---

## 5. Database Schema (as implemented in `app/database.py`)

```sql
teams (
  id            SERIAL PRIMARY KEY,
  fd_api_id     INTEGER UNIQUE,      -- football-data.org's ID (shared across competitions)
  name          TEXT NOT NULL,
  short_name    TEXT,
  tla           TEXT,                -- 'MCI', 'RMA', ...
  country       TEXT,
  crest_url     TEXT
)

matches (
  id              SERIAL PRIMARY KEY,
  fd_api_id       INTEGER UNIQUE,
  competition     TEXT NOT NULL,     -- 'CL', 'PL', 'PD', ...
  season          INTEGER NOT NULL,  -- 2023 = the 2023/24 season
  stage           TEXT,              -- 'GROUP_STAGE', 'LEAGUE_STAGE' (2024+ format), 'FINAL', ...
  status          TEXT NOT NULL,     -- 'FINISHED', 'SCHEDULED', 'TIMED', ...
  match_date      TIMESTAMP NOT NULL,-- UTC
  neutral         BOOLEAN,           -- true for the final
  home_team_id    INTEGER REFERENCES teams(id),
  away_team_id    INTEGER REFERENCES teams(id),
  home_goals      INTEGER,           -- 90-MINUTE score; NULL until played
  away_goals      INTEGER,
  result          TEXT,              -- 'H', 'D', 'A' (90 minutes); NULL if not yet played

  -- pre-match feature SNAPSHOTS (the leakage-safety mechanism from 4.4)
  home_elo_pre    FLOAT,  away_elo_pre   FLOAT,
  home_form_pre   FLOAT,  away_form_pre  FLOAT,   -- avg points/game, last 5
  home_gd_pre     FLOAT,  away_gd_pre    FLOAT    -- avg goal difference, last 5
)

predictions (
  id              SERIAL PRIMARY KEY,
  match_id        INTEGER REFERENCES matches(id),
  model_version   TEXT,              -- 'logreg_v1', later 'xgb_v1', ...
  prob_home_win   FLOAT,
  prob_draw       FLOAT,
  prob_away_win   FLOAT,
  predicted_at    TIMESTAMP,
  UNIQUE (match_id, model_version)
)

app_meta (key TEXT PRIMARY KEY, value TEXT)  -- 'data_source', 'fixtures_refreshed_at'
```

`predictions` is a *separate* table from `matches`, not extra columns on `matches`. That lets you store predictions from several model versions for the same match and compare them later. `/predictions/track-record` grades them once the matches have been played, which is useful material for your "technical rationale" README section.

---

## 6. Data Collection Plan

1. Register for a free football-data.org API key and put it in `backend/.env`.
2. **Check access first:** `python -m scripts.fetch_history --competitions CL`. The summary at the end shows which seasons your key can see.
3. Fetch everything with `python -m scripts.fetch_history`. It downloads CL plus the top 5 leagues for the last ~8 seasons, waits 6.5 seconds between calls, and backs off automatically on a 429 ("too many requests").
4. **Raw JSON is cached to disk** (`data/raw/CL_2022_matches.json`). Finished seasons never change, so they are never downloaded twice. You can also work on the parsing code offline without using your rate limit.
5. `python -m scripts.load_data` reads the cache and upserts teams and matches into the database.
6. **Current season:** the API refreshes the CL season on its own when its copy is more than 6 hours old. `python -m scripts.refresh_data` (or the daily GitHub Action) refreshes every competition, including the leagues that feed Elo.

---

## 7. Modeling Approach — Step by Step (`app/modeling.py`)

1. Load all played matches from **every** competition, sorted by `match_date`.
2. Walk through them in order with `features.walk()`, keeping running Elo and form per team and writing each match's pre-match snapshot into the `*_pre` columns.
3. Keep only **Champions League** rows and build the feature matrix `[elo_diff, form_diff, gd_diff, neutral]`.
4. Split chronologically. The test set is the newest season with at least 60 played CL matches. The training set is every earlier season except the first (Elo warm-up). A newer, in-progress season is held back from evaluation.
5. Train `StandardScaler → LogisticRegression` on the training seasons.
6. Evaluate on the test season: log loss against the base-rate baseline, accuracy against "always home", and the calibration table.
7. **Retrain on all seasons**, including the test season and the in-progress one, so production uses the freshest data. Save `model.joblib` and `model_meta.json`, which records the feature list, metrics and coefficients. The API refuses to load a model whose feature list doesn't match the code.

---

## 8. Serving Predictions — API Design

| Endpoint | Method | Returns |
|---|---|---|
| `/health` | GET | Status, whether the model is loaded, the data source, and row counts |
| `/teams` | GET | CL teams with current Elo and form, strongest first (for dropdowns) |
| `/fixtures/upcoming` | GET | Upcoming CL fixtures, cached and refreshed from football-data.org at most every 6 hours |
| `/predict?home_id=X&away_id=Y&neutral=false` | GET | `{prob_home_win, prob_draw, prob_away_win, model_version, home_team, away_team}`, computed from current Elo and form |
| `/predict/fixtures` | GET | Every upcoming fixture with its prediction attached, so the frontend makes one call instead of N. Also saves predictions for later grading |
| `/model` | GET | Training seasons, test metrics, calibration and coefficients |
| `/predictions/track-record` | GET | Accuracy of saved predictions on matches that have since been played |

---

## 9. Frontend Plan

- **Upcoming fixtures** tab: a card per fixture with crests (or a TLA badge), kickoff in your local time, stage, and a Home / Draw / Away probability bar. *(done)*
- **Any matchup** tab: two dropdowns and a neutral-venue switch that call `/predict`. *(done)*
- **How good is the model?** tab: log loss and accuracy against the baselines, plus the calibration table. *(done)*
- Stretch: click a team to see an Elo-over-time line chart (`recharts`). The data is already stored in the `home_elo_pre`/`away_elo_pre` columns, so this needs one new endpoint and one component.

---

## 10. Build Order — Roadmap

The guiding principle: **prove the riskiest, most uncertain part first** (does this data plus this modeling approach produce sane predictions?) before spending time on web plumbing you already understand conceptually.

**Phase 0 — Setup** ✅
Repo, README, Python venv, `.env.example`, `.gitignore`. SQLite locally, through SQLAlchemy so the Postgres switch is a single config change.

**Phase 1 — Data + baseline model** ✅ *(code done; run it with your key)*
Fetch and cache historical seasons, load them, compute Elo and form, train, print metrics.
Success criterion: the model's log loss clearly beats the base-rate baseline. On sample data it does (0.86 vs 1.03). **Your first real task is to check this on real data.** Real football is noisier than the simulation, so expect a smaller gap. If the model doesn't win, tune `K_FACTOR` / `HOME_ADVANTAGE` in `features.py` before building anything else.

**Phase 2 — Wrap the model in an API** ✅
FastAPI with `/teams`, `/predict` and more. Test it in Bruno, with `curl`, or in the auto-generated docs at `/docs`.

**Phase 3 — Minimal React frontend** ✅
The full chain (React → your API → DB/model → back to React) works.

**Phase 4 — Wire in live fixtures** ✅
The backend caches the current season with a 6-hour TTL, and the frontend renders `/predict/fixtures`.

**Phase 5 — Migrate DB to Supabase, deploy everything** ⏳ *(needs your accounts; steps are in the README)*
Point `DATABASE_URL` at Supabase (Session pooler), run `load_data`, then deploy both services with the `render.yaml` Blueprint. Step-by-step: [DEPLOY.md](DEPLOY.md).

**Phase 6 — Polish + README** ⏳
Loading, error and "server waking up" states are done. Still to do: screenshots or a GIF, and your own Learning Journey, Technical Rationale and AI Usage sections.

**Phase 7 — Stretch goals (pick what interests you)**
- Elo-over-time chart per team.
- XGBoost as `xgb_v1`; compare its log loss with `logreg_v1`.
- **The Odds API** (the third API): show bookmaker-implied probabilities next to yours. Bookmakers are the toughest baseline there is.
- More features: head-to-head, rest days, first-leg score for second legs.
- Grade live predictions over a full season with `/predictions/track-record`.

---

## 11. README Skeleton (matches the submission requirements)

The real `README.md` follows this structure. The sections only you can write are marked in italics there.

```markdown
# UCL Match Predictor
## Description
## Live Demo
## Screenshots / Demo
## Setup Instructions  (Backend / Frontend)
## Learning Journey     (inspiration, audience, new tech + why)
## Technical Rationale  (Python+JS split, tradeoffs, hardest bug)
## AI Usage             (tools, a prompt example, what you changed)
```

---

## 12. Where to Spend Your Learning Effort

If you only have time to learn two new things deeply from this project, make them:
1. **Elo / feature engineering with leakage awareness** (sections 4.3–4.5; read `app/features.py` and `tests/test_features.py`). This is ML skill that carries over to other projects, not project-specific trivia.
2. **React's component + fetch pattern** (section 4.8; read `FixtureList.jsx` and `api.js`). This pattern alone covers a large share of the frontend work you'll run into again.

Everything else (FastAPI syntax, the Supabase dashboard, deployment configs) is comparatively shallow to pick up once those two ideas click.
