from __future__ import annotations

import json
from pathlib import Path

WEEKLY_DIR = Path("data/themes/weekly")
OUT_PATH = Path("data/themes/weekly_index.json")


def main() -> None:
    weeks = sorted(p.stem for p in WEEKLY_DIR.glob("*.json"))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"weeks": weeks}, f, indent=2)


if __name__ == "__main__":
    main()