import os

import pytest
from socceraction.data.impect import ImpectLoader
from socceraction.spadl import SPADLSchema, add_names, config as spadlconfig
from socceraction.spadl import impect as spadl_impect


@pytest.fixture(scope="module")
def loader() -> ImpectLoader:
    data_dir = os.path.join(os.path.dirname(__file__), os.pardir, "datasets", "impect", "raw")
    return ImpectLoader(getter="local", root=data_dir)


@pytest.fixture(scope="module")
def actions(loader: ImpectLoader) -> pytest.fixture:
    events = loader.events(122838)
    games = loader.games(competition_id=2, season_id=743)
    home_team_id = int(games.loc[games.game_id == 122838, "home_team_id"].iloc[0])
    actions = spadl_impect.convert_to_actions(events, home_team_id)
    return add_names(actions)


def test_convert_to_actions(actions) -> None:
    """It converts Impect events to valid SPADL actions."""
    assert len(actions) > 0
    SPADLSchema.validate(actions)
    assert (actions.game_id == 122838).all()


def test_action_types_present(actions) -> None:
    """It produces common on-ball SPADL action types."""
    type_names = set(actions.type_name)
    assert "pass" in type_names
    assert "take_on" in type_names or "dribble" in type_names
    assert spadlconfig.actiontypes.index("shot") in actions.type_id.values
