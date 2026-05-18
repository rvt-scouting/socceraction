import os

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
