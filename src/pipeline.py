"""Run the MarketThemeAI pipeline end to end.

    python -m src.pipeline                  # every step
    python -m src.pipeline --skip query     # reuse the existing BigQuery CSV
    python -m src.pipeline --from themes    # rerun clustering onward

Run from the repo root; every step reads and writes paths under data/.
With DATA_BUCKET set (as in AWS), state is pulled from S3 before the run and
the results are pushed back afterwards.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import time

from src import storage

STEPS = [
    ("query", "src.gkg.run_query", "Query GDELT in BigQuery for candidate article URLs"),
    ("ingest", "src.ingest.fetch_news", "Download articles and extract text"),
    ("filter", "src.preprocess.filter_articles", "Filter for relevance and tag companies"),
    ("themes", "src.themes.build_weekly_themes", "Embed and cluster each week into themes"),
    ("link", "src.track.link_themes_over_time", "Link themes across weeks"),
    ("index", "src.themes.build_weekly_index", "Index available weeks"),
    ("export", "src.frontend_export.build_dashboard_data", "Score themes and export dashboard data"),
]
STEP_NAMES = [name for name, _, _ in STEPS]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="start", choices=STEP_NAMES, default=STEP_NAMES[0], help="First step to run.")
    parser.add_argument("--skip", nargs="*", choices=STEP_NAMES, default=[], help="Steps to skip.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    to_run = STEPS[STEP_NAMES.index(args.start):]
    to_run = [step for step in to_run if step[0] not in args.skip]

    bucket = os.environ.get("DATA_BUCKET")
    if bucket:
        storage.pull_state(bucket)

    total_start = time.monotonic()
    for name, module_path, description in to_run:
        print(f"\n=== [{name}] {description}", flush=True)
        step_start = time.monotonic()
        # Each step parses its own CLI flags; run it with its defaults.
        sys.argv = [module_path]
        importlib.import_module(module_path).main()
        print(f"=== [{name}] done in {time.monotonic() - step_start:.1f}s", flush=True)

    print(f"\nPipeline finished in {time.monotonic() - total_start:.1f}s")

    if bucket:
        storage.push_state(bucket)


if __name__ == "__main__":
    main()
