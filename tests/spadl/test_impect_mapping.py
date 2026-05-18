"""Parametrized tests for Impect → SPADL action mapping."""

import pandas as pd
import pytest

from socceraction.spadl import config as spadlconfig
from socceraction.spadl import impect as spadl_impect


def _event_row(**kwargs: object) -> pd.Series:
    base = {
        "game_id": 1,
        "event_id": 1,
        "period_id": 1,
        "team_id": 10,
        "player_id": 99,
        "type_id": 0,
        "type_name": "PASS",
        "action": "LOW_PASS",
        "result": "SUCCESS",
        "body_part": "FOOT",
        "game_time_seconds": 10.0,
        "start_x": 0.0,
        "start_y": 0.0,
        "end_x": 5.0,
        "end_y": 1.0,
        "phase": "OPEN_PLAY",
        "extra": None,
    }
    base.update(kwargs)
    return pd.Series(base)


@pytest.mark.parametrize(
    "row_kwargs,expected_type,expected_result",
    [
        ({"type_name": "PASS", "action": "HIGH_CROSS"}, "cross", "success"),
        ({"type_name": "SHOT", "action": "SHOT"}, "shot", "success"),
        ({"type_name": "SHOT", "result": "FAIL"}, "shot", "fail"),
        ({"type_name": "DRIBBLE", "action": "DRIBBLE"}, "take_on", "success"),
        ({"type_name": "INTERCEPTION"}, "interception", "success"),
        ({"type_name": "CLEARANCE"}, "clearance", "success"),
        ({"type_name": "FOUL", "result": "FAIL"}, "foul", "fail"),
        ({"type_name": "YELLOW_CARD"}, "foul", "yellow_card"),
        ({"type_name": "GK_SAVE"}, "keeper_save", "success"),
        ({"type_name": "THROW_IN"}, "throw_in", "success"),
        ({"type_name": "CORNER", "action": "HIGH_CROSS"}, "corner_crossed", "success"),
        ({"type_name": "RECEPTION"}, "non_action", "success"),
        ({"type_name": "GROUND_DUEL", "result": "SUCCESS"}, "tackle", "success"),
    ],
)
def test_map_action_types(
    row_kwargs: dict, expected_type: str, expected_result: str
) -> None:
    """It maps Impect event fields to the expected SPADL type and result."""
    events = pd.DataFrame([_event_row(**row_kwargs)])
    actions = spadl_impect.convert_to_actions(events, home_team_id=10)
    if expected_type == "non_action":
        assert len(actions) == 0
        return
    assert len(actions) == 1
    assert actions.type_id.iloc[0] == spadlconfig.actiontypes.index(expected_type)
    assert actions.result_id.iloc[0] == spadlconfig.results.index(expected_result)


@pytest.mark.parametrize(
    "body_part,expected",
    [
        ("HEAD", "head"),
        ("FOOT_LEFT", "foot_left"),
        ("FOOT_RIGHT", "foot_right"),
    ],
)
def test_map_bodyparts(body_part: str, expected: str) -> None:
    """It maps Impect body parts to SPADL bodyparts."""
    events = pd.DataFrame([_event_row(body_part=body_part)])
    actions = spadl_impect.convert_to_actions(events, home_team_id=10)
    assert actions.bodypart_id.iloc[0] == spadlconfig.bodyparts.index(expected)
