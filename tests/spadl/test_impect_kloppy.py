"""Compare native Impect SPADL conversion with kloppy loading (open-data only)."""

import os

import pytest

pytest.importorskip("kloppy")

from kloppy import impect as kloppy_impect
from socceraction.data.impect import ImpectLoader
from socceraction.data.impect.validate import convert_and_validate
from socceraction.spadl import config as spadlconfig


@pytest.fixture(scope="module")
def data_dir() -> str:
    return os.path.join(os.path.dirname(__file__), os.pardir, "datasets", "impect", "raw")


def test_kloppy_loads_open_data_match(data_dir: str) -> None:
    """Kloppy can deserialize the open-data event and lineup files."""
    game_id = 122838
    dataset = kloppy_impect.load(
        event_data=os.path.join(data_dir, "data/events", f"events_{game_id}.json"),
        lineup_data=os.path.join(data_dir, "data/lineups", f"lineups_{game_id}.json"),
    )
    assert len(dataset.events) > 1000


def test_native_validation_report(data_dir: str) -> None:
    """Native conversion passes schema and sanity checks on open-data."""
    game_id = 122838
    loader = ImpectLoader(getter="local", root=data_dir)
    games = loader.games(competition_id=2, season_id=743)
    home_team_id = int(games.loc[games.game_id == game_id, "home_team_id"].iloc[0])
    events = loader.events(game_id)
    _, report = convert_and_validate(events, home_team_id)
    assert report["has_pass"]
    assert report["has_shot"]
    assert report["coords_in_bounds"]
    assert 0.4 <= report["action_ratio"] <= 0.85
    assert "shot" in spadlconfig.actiontypes
