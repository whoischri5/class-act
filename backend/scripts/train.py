"""Phase 1, step 3: compute features, train the model, and print how well it does.

    python -m scripts.train

Success criterion (ARCHITECTURE.md Phase 1): the model's log loss must beat the
baseline's. Lower log loss = better probabilities.
"""
from sqlalchemy.orm import Session

from app.database import engine, init_db
from app.modeling import META_PATH, MODEL_PATH, train_and_evaluate


def main():
    init_db()
    with Session(engine) as session:
        meta = train_and_evaluate(session)

    m = meta["metrics"]
    print(f"Model {meta['model_version']}: trained on seasons {meta['train_seasons']}, "
          f"tested on {meta['test_season']} ({m['test_matches']} matches)\n")
    print(f"  {'':<26}{'model':>10}{'baseline':>10}")
    print(f"  {'log loss (lower = better)':<26}{m['log_loss_model']:>10}{m['log_loss_baseline']:>10}")
    print(f"  {'accuracy':<26}{m['accuracy_model']:>10}{m['accuracy_always_home']:>10}  (baseline = always pick home)")
    print(f"  draws predicted / actual: {m['predicted_draws']} / {m['actual_draws']}\n")

    print("  Calibration — when we say X% home win, how often does home actually win?")
    for row in m["calibration_home_win"]:
        print(f"    {row['bucket']:>9}: predicted {row['avg_predicted']:.0%}, actual {row['actual_rate']:.0%}  ({row['matches']} matches)")

    verdict = "BEATS" if m["log_loss_model"] < m["log_loss_baseline"] else "does NOT beat"
    print(f"\n  The model {verdict} the baseline on log loss.")
    print(f"\nSaved {MODEL_PATH.name} and {META_PATH.name} to {MODEL_PATH.parent}")
    print("Next: uvicorn app.main:app --reload   (then open http://127.0.0.1:8000/docs)")


if __name__ == "__main__":
    main()
