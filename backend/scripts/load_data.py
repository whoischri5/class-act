"""Phase 1, step 2: load cached JSON files into the database.

    python -m scripts.load_data            # real data from data/raw/
    python -m scripts.load_data --sample   # fake practice data from data/sample/

Safe to run as often as you like: rows are matched on football-data.org's IDs and
updated in place ("upserted"), never duplicated.
"""
import argparse

from sqlalchemy.orm import Session

from app.config import RAW_DATA_DIR, SAMPLE_DATA_DIR
from app.database import engine, init_db, set_meta
from app.ingest import load_directory


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample", action="store_true", help="load the generated sample data instead")
    args = parser.parse_args()

    directory = SAMPLE_DATA_DIR if args.sample else RAW_DATA_DIR
    if not any(directory.glob("*.json")):
        hint = "python -m scripts.make_sample_data" if args.sample else "python -m scripts.fetch_history"
        raise SystemExit(f"No JSON files in {directory}. Run `{hint}` first.")

    init_db()
    with Session(engine) as session:
        stats = load_directory(session, directory)
        set_meta(session, "data_source", "sample" if args.sample else "football-data.org")
        session.commit()
    print(f"Loaded {stats['files']} files: {stats['matches']} matches, {stats['teams']} team records.")
    print("Next: python -m scripts.train")


if __name__ == "__main__":
    main()
