#!/usr/bin/env python3
"""Build an HDF5 file with SPADL actions for a full Impect iteration."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, **kwargs):  # type: ignore
        return iterable

from socceraction.data.impect import ImpectLoader
from socceraction.spadl import add_names
from socceraction.spadl import impect as spadl_impect


def _cache_root(project_root: Path, season_id: int) -> Path:
    return project_root / "data" / "impect" / str(season_id)


def cache_iteration(
    loader: ImpectLoader, competition_id: int, season_id: int, project_root: Path
) -> Path:
    """Download iteration data into local open-data layout."""
    import impectPy as ip

    root = _cache_root(project_root, season_id)
    data_dir = root / "data"
    (data_dir / "events").mkdir(parents=True, exist_ok=True)
    (data_dir / "matches").mkdir(parents=True, exist_ok=True)
    (data_dir / "lineups").mkdir(parents=True, exist_ok=True)

    iterations = loader._call_with_token_retry(ip.getIterations)
    sel = iterations[iterations["id"] == season_id]
    records = []
    for row in sel.to_dict(orient="records"):
        records.append(
            {
                "id": row["id"],
                "season": row["season"],
                "competition": {
                    "id": row["competitionId"],
                    "name": row["competitionName"],
                    "type": row.get("competitionType"),
                },
            }
        )
    (root / "iterations.json").write_text(json.dumps(records, indent=2))

    matches = loader._call_with_token_retry(ip.getMatches, season_id)
    matches.to_json(data_dir / "matches" / f"matches_{season_id}.json", orient="records", indent=2)

    for game_id in tqdm(matches["id"], desc="Caching events"):
        game_id = int(game_id)
        event_path = data_dir / "events" / f"events_{game_id}.json"
        lineup_path = data_dir / "lineups" / f"lineups_{game_id}.json"
        if event_path.is_file():
            continue
        try:
            raw = loader._call_with_token_retry(
                ip.getEvents,
                matches=[game_id],
                include_kpis=False,
                include_set_pieces=False,
            )
            event_path.write_text(json.dumps(raw.to_dict(orient="records"), indent=2))
            if not lineup_path.is_file():
                try:
                    positions = loader._call_with_token_retry(
                        ip.getStartingPositions, matches=[game_id]
                    )
                    subs = loader._call_with_token_retry(ip.getSubstitutions, matches=[game_id])
                    lineup_path.write_text(
                        json.dumps(
                            {
                                "positions": positions.to_dict(orient="records"),
                                "substitutions": subs.to_dict(orient="records"),
                            },
                            indent=2,
                        )
                    )
                except Exception as exc:
                    print(f"Skip lineup {game_id}: {exc}", file=sys.stderr)
        except Exception as exc:
            print(f"Skip events {game_id}: {exc}", file=sys.stderr)
            time.sleep(3)
        else:
            time.sleep(1.5)

    return root


def build_h5(
    loader: ImpectLoader,
    competition_id: int,
    season_id: int,
    output: Path,
) -> None:
    """Convert all games in an iteration and store SPADL in HDF5."""
    games = loader.games(competition_id, season_id, include_scores=False)
    competitions = loader.competitions()
    selected = competitions[
        (competitions.competition_id == competition_id)
        & (competitions.season_id == season_id)
    ]

    teams_list = []
    players_list = []
    actions: dict[int, pd.DataFrame] = {}

    for game in tqdm(list(games.itertuples()), desc="Converting to SPADL"):
        game_id = int(game.game_id)
        home_team_id = int(game.home_team_id)
        try:
            events = loader.events(game_id)
        except Exception as exc:
            print(f"Skip game {game_id}: {exc}", file=sys.stderr)
            continue
        if len(events) == 0:
            continue
        act = add_names(spadl_impect.convert_to_actions(events, home_team_id))
        actions[game_id] = act
        try:
            teams_list.append(loader.teams(game_id))
            players_list.append(loader.players(game_id))
        except Exception as exc:
            print(f"Skip roster {game_id}: {exc}", file=sys.stderr)

    teams = pd.concat(teams_list).drop_duplicates(subset="team_id") if teams_list else pd.DataFrame()
    players = pd.concat(players_list) if players_list else pd.DataFrame()

    output.parent.mkdir(parents=True, exist_ok=True)
    with pd.HDFStore(output) as store:
        store["competitions"] = selected
        store["games"] = games
        if len(teams):
            store["teams"] = teams
        if len(players):
            store["players"] = players[["player_id", "player_name"]].drop_duplicates(
                subset="player_id"
            )
            store["player_games"] = players[
                [
                    "player_id",
                    "game_id",
                    "team_id",
                    "is_starter",
                    "minutes_played",
                    "jersey_number",
                ]
            ]
        for game_id, df in actions.items():
            store[f"actions/game_{game_id}"] = df

    print(f"Wrote {len(actions)} games to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--getter", choices=["local", "remote"], default="local")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--competition-id", type=int, required=True)
    parser.add_argument("--season-id", type=int, required=True, help="Impect iterationId")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/impect/spadl-impect.h5"),
    )
    parser.add_argument("--cache", action="store_true", help="Cache remote API data first")
    args = parser.parse_args()

    if args.cache:
        if args.getter != "remote":
            raise SystemExit("--cache requires --getter remote")
        remote = ImpectLoader(getter="remote", root=str(args.root))
        cache_root = cache_iteration(remote, args.competition_id, args.season_id, args.root)
        loader = ImpectLoader(getter="local", root=str(cache_root))
    else:
        loader = ImpectLoader(getter=args.getter, root=str(args.root))

    build_h5(loader, args.competition_id, args.season_id, args.output)


if __name__ == "__main__":
    main()
