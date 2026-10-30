"""Train, evaluate, save and load the match-outcome model (ARCHITECTURE.md sections 4.6 and 7)."""
import json
from datetime import datetime, timezone

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy.orm import Session

from app import features
from app.config import MODELS_DIR, TARGET_COMPETITION
from app.database import Match, select

MODEL_VERSION = "logreg_v1"
MODEL_PATH = MODELS_DIR / "model.joblib"
META_PATH = MODELS_DIR / "model_meta.json"
CLASSES = ["H", "D", "A"]  # our fixed order for probabilities everywhere


def played_matches(session: Session) -> list[Match]:
    return list(
        session.scalars(select(Match).where(Match.result.is_not(None)).order_by(Match.match_date))
    )


def compute_and_store_snapshots(session: Session) -> tuple[features.FeatureTracker, list]:
    """Walk all played matches (every competition), write each pre-match snapshot
    into the matches table, and return the final tracker + snapshots."""
    tracker, snapshots = features.walk(played_matches(session))
    for match, snap in snapshots:
        for column, value in snap.items():
            setattr(match, column, value)
    session.commit()
    return tracker, snapshots


def build_dataset(snapshots: list) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Feature matrix X, labels y and season per row — Champions League matches only."""
    rows = [(m, s) for m, s in snapshots if m.competition == TARGET_COMPETITION]
    X = np.array([features.model_inputs(s, m.neutral) for m, s in rows], dtype=float).reshape(-1, len(features.FEATURE_COLUMNS))
    y = np.array([m.result for m, _ in rows])
    seasons = np.array([m.season for m, _ in rows])
    return X, y, seasons


def new_model():
    # Scaling puts elo_diff (hundreds) and form_diff (single digits) on the same footing.
    # Note: LogisticRegression is multinomial by default for 3+ classes — the old
    # `multi_class="multinomial"` argument was removed in recent scikit-learn.
    return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000))


def probs_in_our_order(model, X: np.ndarray) -> np.ndarray:
    """sklearn orders classes alphabetically (A, D, H); reorder to H, D, A."""
    raw = model.predict_proba(X)
    idx = [list(model.classes_).index(c) for c in CLASSES]
    return raw[:, idx]


def log_loss(y: np.ndarray, probs: np.ndarray) -> float:
    """Average of -log(probability we gave to what actually happened).

    Confident AND right -> close to 0. Confident AND wrong -> huge penalty.
    (Written out by hand because sklearn's version expects columns in alphabetical
    order, which silently gives wrong numbers with our H/D/A order.)
    """
    idx = np.array([CLASSES.index(r) for r in y])
    p_actual = np.clip(probs[np.arange(len(y)), idx], 1e-15, 1)
    return float(-np.mean(np.log(p_actual)))


def calibration_table(probs: np.ndarray, y: np.ndarray, bins: int = 5) -> list[dict]:
    """Bucket home-win probabilities and compare to how often home teams actually won."""
    p_home = probs[:, 0]
    actual = (y == "H").astype(float)
    edges = np.linspace(0, 1, bins + 1)
    table = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p_home >= lo) & ((p_home < hi) if hi < 1 else (p_home <= hi))
        if mask.sum() == 0:
            continue
        table.append(
            {
                "bucket": f"{lo:.0%}-{hi:.0%}",
                "matches": int(mask.sum()),
                "avg_predicted": round(float(p_home[mask].mean()), 3),
                "actual_rate": round(float(actual[mask].mean()), 3),
            }
        )
    return table


def evaluate(model, X_test, y_test, y_train) -> dict:
    probs = probs_in_our_order(model, X_test)

    # Baseline 1: always give the training set's base rates (e.g. 45% H / 25% D / 30% A).
    # ("Always predict home win with 100%" can't be scored with log loss — one away win
    # and the loss is infinite — so this is the fair 'dumb' baseline.)
    base_rates = np.array([np.mean(y_train == c) for c in CLASSES])
    baseline_probs = np.tile(base_rates, (len(y_test), 1))

    predicted = np.array(CLASSES)[probs.argmax(axis=1)]
    return {
        "test_matches": int(len(y_test)),
        "log_loss_model": round(log_loss(y_test, probs), 4),
        "log_loss_baseline": round(log_loss(y_test, baseline_probs), 4),
        "accuracy_model": round(float(np.mean(predicted == y_test)), 4),
        "accuracy_always_home": round(float(np.mean(y_test == "H")), 4),
        "predicted_draws": int((predicted == "D").sum()),
        "actual_draws": int((y_test == "D").sum()),
        "calibration_home_win": calibration_table(probs, y_test),
    }


MIN_TEST_MATCHES = 60  # a season with fewer played CL matches is "in progress"


def choose_split(seasons: np.ndarray) -> tuple[list[int], int, list[int]]:
    """Chronological split -> (train_seasons, test_season, extra_seasons).

    * test  = the newest season with enough played matches to judge the model on
    * train = every season before it (minus the very first one when we have enough
              data, because all teams start at Elo 1500 and ratings need to warm up)
    * extra = an in-progress season newer than the test season; not used for
              evaluation, but included when we retrain the final model
    """
    counts = {int(s): int((seasons == s).sum()) for s in set(seasons.tolist())}
    unique = sorted(counts)
    complete = [s for s in unique if counts[s] >= MIN_TEST_MATCHES] or unique
    if len(unique) < 2:
        raise ValueError("Need at least 2 seasons of Champions League results to train and test.")
    test_season = complete[-1] if complete[-1] != unique[0] else unique[-1]
    earlier = [s for s in unique if s < test_season]
    train_seasons = earlier[1:] if len(earlier) >= 3 else earlier
    extra = [s for s in unique if s > test_season]
    return train_seasons, test_season, extra


def train_and_evaluate(session: Session) -> dict:
    _, snapshots = compute_and_store_snapshots(session)
    X, y, seasons = build_dataset(snapshots)
    train_seasons, test_season, extra_seasons = choose_split(seasons)

    train_mask = np.isin(seasons, train_seasons)
    test_mask = seasons == test_season
    model = new_model().fit(X[train_mask], y[train_mask])
    metrics = evaluate(model, X[test_mask], y[test_mask], y[train_mask])

    # Evaluation done -> retrain on ALL usable seasons so production uses the freshest data.
    final_mask = np.isin(seasons, train_seasons + [test_season] + extra_seasons)
    final_model = new_model().fit(X[final_mask], y[final_mask])

    coefficients = final_model[-1].coef_
    meta = {
        "model_version": MODEL_VERSION,
        "feature_columns": features.FEATURE_COLUMNS,
        "classes": CLASSES,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "train_seasons": train_seasons,
        "test_season": test_season,
        "extra_seasons_in_final_model": extra_seasons,
        "metrics": metrics,
        "coefficients": {
            cls: dict(zip(features.FEATURE_COLUMNS, np.round(coefficients[i], 3).tolist()))
            for i, cls in enumerate(final_model.classes_)
        },
        "elo_settings": {
            "base": features.BASE_ELO,
            "k": features.K_FACTOR,
            "home_advantage": features.HOME_ADVANTAGE,
            "season_carryover": features.SEASON_CARRYOVER,
            "form_window": features.FORM_WINDOW,
        },
    }
    MODELS_DIR.mkdir(exist_ok=True)
    joblib.dump(final_model, MODEL_PATH)
    META_PATH.write_text(json.dumps(meta, indent=2))
    return meta


def load_model():
    """Returns (model, meta) or (None, None) if `python -m scripts.train` hasn't been run."""
    if not MODEL_PATH.exists() or not META_PATH.exists():
        return None, None
    meta = json.loads(META_PATH.read_text())
    if meta["feature_columns"] != features.FEATURE_COLUMNS:
        raise RuntimeError(
            "The saved model expects different features than the code provides. "
            "Re-run `python -m scripts.train`."
        )
    return joblib.load(MODEL_PATH), meta


def predict_probs(model, snapshot: dict, neutral: bool) -> dict:
    X = np.array([features.model_inputs(snapshot, neutral)])
    p_home, p_draw, p_away = probs_in_our_order(model, X)[0]
    return {
        "prob_home_win": round(float(p_home), 4),
        "prob_draw": round(float(p_draw), 4),
        "prob_away_win": round(float(p_away), 4),
    }
