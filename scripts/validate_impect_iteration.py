#!/usr/bin/env python3
"""Run SPADL validation across all cached/loaded games in an iteration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from socceraction.data.impect import ImpectLoader
from socceraction.data.impect.validate import convert_and_validate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids-json", type=Path, help="JSON with competition_id and season_id")
    parser.add_argument("--getter", choices=["local", "remote"], default="local")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--competition-id", type=int)
    parser.add_argument("--season-id", type=int)
    parser.add_argument("--max-games", type=int, default=0, help="0 = all")
    args = parser.parse_args()

    load_dotenv(args.root / ".env")
    if args.ids_json and args.ids_json.is_file():
        meta = json.loads(args.ids_json.read_text())
        competition_id = int(meta["competition_id"])
        season_id = int(meta["season_id"])
    else:
        if args.competition_id is None or args.season_id is None:
            raise SystemExit("Provide --ids-json or both --competition-id and --season-id")
        competition_id = args.competition_id
        season_id = args.season_id

    loader = ImpectLoader(getter=args.getter, root=str(args.root))
    games = loader.games(competition_id, season_id).sort_values("game_date")
    if args.max_games > 0:
        games = games.head(args.max_games)

    reports = []
    for game in games.itertuples():
        game_id = int(game.game_id)
        home_team_id = int(game.home_team_id)
        try:
            events = loader.events(game_id)
            _, report = convert_and_validate(events, home_team_id)
            report["game_id"] = game_id
            reports.append(report)
        except Exception as exc:
            print(f"FAIL {game_id}: {exc}", file=sys.stderr)

    if not reports:
        raise SystemExit("No games validated")

    df = pd.DataFrame(reports)
    print(f"Validated {len(df)} games")
    print(
        "action_ratio: min={:.2f} max={:.2f} mean={:.2f}".format(
            df["action_ratio"].min(), df["action_ratio"].max(), df["action_ratio"].mean()
        )
    )
    print(f"coords_in_bounds: {df['coords_in_bounds'].all()}")
    print(f"has_pass: {df['has_pass'].mean():.1%}  has_shot: {df['has_shot'].mean():.1%}")


if __name__ == "__main__":
    main()
