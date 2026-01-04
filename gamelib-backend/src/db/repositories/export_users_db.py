"""
Export users table playtime data to a flat CSV for offline model training.

Each row is a (steam_id, game_id, playtime_forever, playtime_2weeks, rtime_last_played, name, playtime_score).
The playtime_score applies log1p scaling to dampen extremes, matching the RF target logic.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List

import pandas as pd

# Ensure project root is on sys.path when running as a script
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.supabase_client import supabase

# Output alongside games_db.csv for convenience
THIS_DIR = Path(__file__).resolve().parent
USERS_CSV_PATH = THIS_DIR / "users_db.csv"
BATCH_SIZE = 1000


def _fetch_users_batch(start: int, end: int):
    return supabase.table("users").select("steam_id,games").range(start, end).execute()


def _flatten_user_games(user: Dict) -> List[Dict]:
    steam_id = user.get("steam_id")
    games = user.get("games") or {}
    rows: List[Dict] = []
    for game_id_str, payload in games.items():
        try:
            game_id = int(game_id_str)
        except (TypeError, ValueError):
            continue
        playtime = float(payload.get("playtime_forever", 0) or 0)
        playtime_recent = float(payload.get("playtime_2weeks", 0) or 0)
        last_played = payload.get("rtime_last_played")
        name = payload.get("name") or ""
        if playtime <= 0:
            continue
        rows.append(
            {
                "steam_id": steam_id,
                "game_id": game_id,
                "playtime_forever": playtime,
                "playtime_2weeks": playtime_recent,
                "rtime_last_played": last_played,
                "name": name,
                "playtime_score": math.log1p(playtime) * 100.0,
            }
        )
    return rows


def export_users_csv(output_path: Path = USERS_CSV_PATH) -> Path:
    all_rows: List[Dict] = []
    start = 0
    while True:
        end = start + BATCH_SIZE - 1
        resp = _fetch_users_batch(start, end)
        batch = resp.data or []
        if not batch:
            break
        for user in batch:
            all_rows.extend(_flatten_user_games(user))
        if len(batch) < BATCH_SIZE:
            break
        start += BATCH_SIZE

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_rows).to_csv(output_path, index=False)
    print(f"Wrote {len(all_rows)} rows to {output_path}")
    return output_path


if __name__ == "__main__":
    export_users_csv(Path(os.getenv("USERS_CSV_PATH", USERS_CSV_PATH)))
