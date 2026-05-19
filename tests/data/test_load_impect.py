import json
import os
from pathlib import Path

import pytest
from socceraction.data.impect import ImpectLoader
from socceraction.data.impect.schema import (
    ImpectCompetitionSchema,
    ImpectEventSchema,
    ImpectGameSchema,
    ImpectPlayerSchema,
    ImpectTeamSchema,
)


@pytest.fixture(scope="module")
def data_dir() -> str:
    return os.path.join(os.path.dirname(__file__), os.pardir, "datasets", "impect", "raw")


@pytest.fixture(scope="module")
def loader(data_dir: str) -> ImpectLoader:
    return ImpectLoader(getter="local", root=data_dir)


def test_load_local(data_dir: str) -> None:
    """It can load local open-data fixtures."""
    ImpectLoader(getter="local", root=data_dir)


def test_load_invalid_source() -> None:
    """It raises an error if the source is not remote or local."""
    with pytest.raises(ValueError):
        ImpectLoader(getter="foo")


def test_competitions(loader: ImpectLoader) -> None:
    """It loads available competition iterations."""
    df = loader.competitions()
    assert len(df) > 0
    ImpectCompetitionSchema.validate(df)


def test_games(loader: ImpectLoader) -> None:
    """It loads matches for an iteration."""
    df = loader.games(competition_id=2, season_id=743)
    assert len(df) > 0
    ImpectGameSchema.validate(df)
    assert 122838 in df.game_id.values


def test_teams(loader: ImpectLoader) -> None:
    """It loads both squads for a match."""
    df = loader.teams(122838)
    assert len(df) == 2
    ImpectTeamSchema.validate(df)


def test_players(loader: ImpectLoader) -> None:
    """It loads players for a match."""
    df = loader.players(122838)
    assert len(df) > 0
    ImpectPlayerSchema.validate(df)


def test_events(loader: ImpectLoader) -> None:
    """It loads normalized events for a match."""
    df = loader.events(122838)
    assert len(df) > 0
    ImpectEventSchema.validate(df)
    assert df.game_id.nunique() == 1
    assert df.game_id.iloc[0] == 122838


def test_players_api_cached_lineup(tmp_path, data_dir: str) -> None:
    """It loads players from pipeline-cached API lineup JSON (positions/substitutions)."""
    game_id = 122838
    open_lineup = json.loads(
        (Path(data_dir) / "data" / "lineups" / f"lineups_{game_id}.json").read_text(encoding="utf-8")
    )
    # Simulate analytics-pipeline cache format from getStartingPositions / getSubstitutions
    api_lineup = {
        "positions": [
            {
                "playerId": p["id"],
                "squadId": open_lineup["squadHome"]["id"],
                "playerName": str(p["id"]),
                "shirtNumber": p.get("shirtNumber", 0),
            }
            for p in open_lineup["squadHome"]["players"][:11]
        ],
        "substitutions": [],
    }
    lineup_dir = tmp_path / "data" / "lineups"
    lineup_dir.mkdir(parents=True)
    (lineup_dir / f"lineups_{game_id}.json").write_text(json.dumps(api_lineup), encoding="utf-8")
    matches_dir = tmp_path / "data" / "matches"
    matches_dir.mkdir(parents=True)
    (matches_dir / "matches_743.json").write_text(
        json.dumps(
            [
                {
                    "id": game_id,
                    "homeSquadId": open_lineup["squadHome"]["id"],
                    "awaySquadId": open_lineup["squadAway"]["id"],
                }
            ]
        ),
        encoding="utf-8",
    )
    api_loader = ImpectLoader(getter="local", root=str(tmp_path))
    df = api_loader.players(game_id)
    assert len(df) == 11
    ImpectPlayerSchema.validate(df)
    assert df["minutes_played"].sum() > 0
