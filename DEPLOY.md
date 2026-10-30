# Deploying the UCL Match Predictor

This guide takes the app from "works on my laptop" to a public website. You'll set up three things:

```
  Supabase (database)  ◀──  Render web service (Python API)  ◀──  Render static site (React)  ◀──  visitors
```

| Piece | What it does | Cost |
|---|---|---|
| **Supabase** | Hosts the Postgres database with all the matches | Free |
| **Render web service** `ucl-predictor-api` | Runs FastAPI and the model | Free; sleeps after 15 min without visitors |
| **Render static site** `ucl-predictor` | Serves the built React app | Free; never sleeps |

Plan on about 30–45 minutes the first time.

**Why not GitHub Pages?** It would work for the React half, but it can't run the Python API, so you'd still need Render for that. Putting both on Render means one account and one config file, and Render deploys both halves together.

**Before you start:** the app should already work locally with real data. `python -m scripts.fetch_history`, `python -m scripts.load_data` and `python -m scripts.train` should all succeed, and you should have pushed the latest code to GitHub (merged into `main`).

---

## Step 1: Create the Supabase database

1. Go to [supabase.com](https://supabase.com), sign up (signing in with GitHub is easiest), and click **New project**.
2. Fill in the form:
   - **Name:** `ucl-predictor`
   - **Database password:** click **Generate a password** and **save it somewhere safe**, such as a password manager. Tip: a password with only letters and numbers avoids the most common connection error (see Troubleshooting).
   - **Region:** pick one in the same part of the world as your Render region. Render's free default is Oregon (US West).
3. Wait a minute or two while the project starts up.

## Step 2: Get the connection string

1. In your Supabase project, click the **Connect** button at the top of the page.
2. Under **Connection String**, find the **Session pooler** option. *Don't* use "Direct connection", because Render can't reach it (it's IPv6-only).
3. Copy the URI. It looks like:
   ```
   postgresql://postgres.abcdefghijkl:[YOUR-PASSWORD]@aws-0-us-west-1.pooler.supabase.com:5432/postgres
   ```
4. Replace `[YOUR-PASSWORD]`, *including the square brackets*, with the password from Step 1.

This string is a secret, just like your API key. Never commit it.

## Step 3: Load your data into Supabase (from your laptop)

Your laptop already has every season cached in `backend/data/raw/`, so this re-uses those files and doesn't call football-data.org again.

1. Open `backend/.env` and set:
   ```
   DATABASE_URL=postgresql://postgres.abcdefghijkl:YOUR-REAL-PASSWORD@aws-0-us-west-1.pooler.supabase.com:5432/postgres
   ```
   (You can paste it exactly as Supabase gives it. The app converts `postgresql://` to the driver format it needs.)
2. In `backend/`, with your venv active, run:
   ```bash
   python -m scripts.load_data
   ```
   ```bash
   python -m scripts.train
   ```
   `load_data` should report thousands of matches. `train` should print the same kind of report you saw locally.
3. Check it in Supabase: open **Table Editor** in the left sidebar. You should see `teams`, `matches`, `predictions` and `app_meta`, with rows in them. They will show as RLS-enabled, which is on purpose: the backend switches on Row Level Security so nobody can read or change your tables through Supabase's public Data API.

**Want to use your local SQLite file again later?** Comment out the `DATABASE_URL` line in `.env` by putting `#` in front of it.

## Step 4: Deploy both services with the Render Blueprint

1. Go to [render.com](https://render.com) and sign up with **GitHub**. When asked, let Render access the `class-act` repo.
2. In the Render dashboard, click **New +** → **Blueprint**.
3. Pick the `whoischri5/class-act` repo and the `main` branch. Render reads `render.yaml` and lists two services: `ucl-predictor-api` and `ucl-predictor`.
4. It asks for the values marked as secret. Fill them in:

   | Variable | Value |
   |---|---|
   | `FOOTBALL_DATA_API_KEY` | your football-data.org key (the same one in your `.env`) |
   | `DATABASE_URL` | the Supabase Session pooler string from Step 2 |
   | `VITE_API_URL` | `https://ucl-predictor-api.onrender.com` |

5. Click **Apply** / **Deploy Blueprint**. The API build takes a few minutes, because it installs packages and then trains the model from your Supabase data. The static site takes about a minute.

## Step 5: Check the API, and fix its URL if needed

1. Open the **ucl-predictor-api** service in Render. Its public URL is at the top of the page.
2. **Is the URL exactly `https://ucl-predictor-api.onrender.com`?**
   - **Yes:** nothing to do.
   - **No** (Render adds a suffix such as `-x7k2` when a name is already taken): copy the real URL, open the **ucl-predictor** static site → **Environment**, change `VITE_API_URL` to the real URL, and save. Then click **Manual Deploy → Deploy latest commit**. The URL is baked into the website when it's built, so it has to be rebuilt after the change.
3. Visit `<your API URL>/health`. You should see something like:
   ```json
   {"status":"ok","model_loaded":true,"model_version":"logreg_v1","data_source":"football-data.org", ...}
   ```
   `<your API URL>/docs` gives you the interactive API docs, live on the internet.

## Step 6: Open your site 🎉

Open the **ucl-predictor** static site in Render and click its URL (something like `https://ucl-predictor.onrender.com`). You should see the upcoming fixtures with predictions.

The first visit after the API has been idle can take **up to about a minute**, because the free API server has to wake up. The page shows a "server may be waking up" message while it waits.

Finally, put that URL in the README's **Live Demo** section.

---

## Keeping it up to date

- **New results and fixtures for the Champions League** come in automatically: the API re-fetches the current CL season when its copy is more than 6 hours old.
- **Domestic-league results**, which keep Elo accurate, come in through the optional GitHub Action. In your GitHub repo, go to **Settings → Secrets and variables → Actions → New repository secret** and add `FOOTBALL_DATA_API_KEY` and `DATABASE_URL`. The **Refresh data** workflow then runs daily, and you can also start it by hand from the **Actions** tab. As a bonus, it keeps your Supabase project from being paused for inactivity.
- **Retraining the model:** every deploy retrains it from the database. Render redeploys automatically whenever you push to `main`. To retrain without a code change, use **Manual Deploy → Deploy latest commit** on `ucl-predictor-api`.

---

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| API build fails with `Need at least 2 seasons of Champions League results` | The Supabase database is empty. Do Step 3 again and make sure `.env` really has the Supabase `DATABASE_URL` when you run `load_data`. |
| `password authentication failed` | Wrong password, or the brackets in `[YOUR-PASSWORD]` were left in. If the password contains `@ # / ? %` or similar, reset it in Supabase (**Project Settings → Database → Reset password**) to one with only letters and numbers. |
| `Network is unreachable` or a connection timeout from Render | You used the *Direct connection* string. Use the **Session pooler** string (Step 2). |
| The site shows "Couldn't reach the API" | 1) Wait a minute; the API may be waking up. Then press **Try again**. 2) Check that `VITE_API_URL` matches the API's real URL exactly, with `https://` and no typos, and that you redeployed the static site after changing it (Step 5). |
| Browser console (F12) mentions **CORS** | The site's URL doesn't start with `https://ucl-predictor`. On `ucl-predictor-api` → **Environment**, add `CORS_ORIGINS` = your site's exact URL, for example `https://my-site.onrender.com`. |
| `/predict` returns 503 "Model not trained yet" | The training step failed during the build. Open the API's **Logs** in Render, scroll to the build output, and look for the error. |
| Supabase says the project is **paused** | Free projects pause after about a week with no activity. Click **Restore** in Supabase. The daily GitHub Action above prevents this. |
