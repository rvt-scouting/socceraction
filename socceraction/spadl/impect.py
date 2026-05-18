"""Impect event stream data to SPADL converter."""

from __future__ import annotations

from typing import Optional, cast

import numpy as np
import pandas as pd  # type: ignore
from pandera.typing import DataFrame

from . import config as spadlconfig
from .base import _add_dribbles, _fix_clearances, _fix_direction_of_play
from .schema import SPADLSchema

# Impect uses a pitch-centered coordinate system (-52.5..52.5, -34..34).
_IMPECT_X_OFFSET = spadlconfig.field_length / 2
_IMPECT_Y_OFFSET = spadlconfig.field_width / 2

_NON_ACTION_TYPES = {
    "NO_VIDEO",
    "RECEPTION",
    "OUT",
    "KICK_OFF",
    "FINAL_WHISTLE",
    "REFEREE_INTERCEPTION",
    "GOAL",
    "BLOCK",
    "LOOSE_BALL_REGAIN",
}

_CROSS_ACTIONS = {
    "CROSS",
    "HIGH_CROSS",
    "LOW_CROSS",
    "DIAGONAL_PASS",
    "CHIPPED_PASS",
    "SHORT_AERIAL_PASS",
}


def convert_to_actions(events: pd.DataFrame, home_team_id: int) -> DataFrame[SPADLSchema]:
    """Convert Impect events to SPADL actions.

    Parameters
    ----------
    events : pd.DataFrame
        Normalized Impect events for a single game (see :class:`~socceraction.data.impect.ImpectLoader`).
    home_team_id : int
        ID of the home squad in the corresponding game.

    Returns
    -------
    pd.DataFrame
        SPADL actions.
    """
    events = events.copy()
    actions = pd.DataFrame()
    actions["game_id"] = events.game_id
    actions["original_event_id"] = events.event_id
    actions["period_id"] = events.period_id
    actions["time_seconds"] = events.game_time_seconds
    actions["team_id"] = events.team_id
    actions["player_id"] = events.player_id

    actions["start_x"] = _to_spadl_x(events["start_x"])
    actions["start_y"] = _to_spadl_y(events["start_y"])
    actions["end_x"] = _to_spadl_x(events["end_x"])
    actions["end_y"] = _to_spadl_y(events["end_y"])

    parsed = events.apply(_parse_event_row, axis=1, result_type="expand")
    actions[["type_id", "result_id", "bodypart_id"]] = parsed

    missing_coords = actions.start_x.isna() | actions.start_y.isna()
    actions.loc[missing_coords, "type_id"] = spadlconfig.actiontypes.index("non_action")

    actions[["start_x", "start_y", "end_x", "end_y"]] = actions[
        ["start_x", "start_y", "end_x", "end_y"]
    ].fillna(0.0)

    actions = (
        actions[actions.type_id != spadlconfig.actiontypes.index("non_action")]
        .sort_values(["game_id", "period_id", "time_seconds"], kind="mergesort")
        .reset_index(drop=True)
    )
    actions = _fix_direction_of_play(actions, home_team_id)
    actions = _fix_clearances(actions)
    actions["action_id"] = range(len(actions))
    actions = _add_dribbles(actions)

    return cast(DataFrame[SPADLSchema], actions)


def _to_spadl_x(x: pd.Series) -> pd.Series:
    return x.astype(float).add(_IMPECT_X_OFFSET)


def _to_spadl_y(y: pd.Series) -> pd.Series:
    return y.astype(float).add(_IMPECT_Y_OFFSET)


def _parse_event_row(row: pd.Series) -> pd.Series:
    action_type = str(row["type_name"])
    action = str(row["action"]) if row.get("action") is not None else ""
    result = str(row["result"]) if row.get("result") is not None else ""
    body_part = str(row.get("body_part") or row.get("bodyPart") or "FOOT")

    a, r, b = _map_action(action_type, action, result, body_part)
    return pd.Series(
        {
            "type_id": spadlconfig.actiontypes.index(a),
            "result_id": spadlconfig.results.index(r),
            "bodypart_id": spadlconfig.bodyparts.index(b),
        }
    )


def _map_action(
    action_type: str, action: str, result: str, body_part: str
) -> tuple[str, str, str]:
    b = _map_bodypart(body_part)
    r = _map_result(result, action_type)

    if action_type in _NON_ACTION_TYPES:
        return "non_action", r, b

    if action_type == "PASS":
        if action in _CROSS_ACTIONS:
            return "cross", r, b
        return "pass", r, b
    if action_type == "SHOT":
        if action == "PENALTY":
            return "shot_penalty", r, b
        return "shot", r, b
    if action_type == "DRIBBLE":
        return "take_on", r, b
    if action_type == "INTERCEPTION":
        return "interception", r, b
    if action_type == "CLEARANCE":
        return "clearance", r, b
    if action_type == "FOUL":
        return "foul", r, b
    if action_type in ("YELLOW_CARD", "SECOND_YELLOW_CARD"):
        return "foul", "yellow_card" if action_type == "YELLOW_CARD" else "red_card", b
    if action_type == "RED_CARD":
        return "foul", "red_card", b
    if action_type == "GK_SAVE":
        return "keeper_save", r, b
    if action_type == "GK_CATCH":
        return "keeper_claim", r, b
    if action_type == "GOAL_KICK":
        return "goalkick", r, b
    if action_type == "THROW_IN":
        return "throw_in", r, b
    if action_type == "CORNER":
        if action in _CROSS_ACTIONS:
            return "corner_crossed", r, b
        return "corner_short", r, b
    if action_type == "FREE_KICK":
        if action in _CROSS_ACTIONS:
            return "freekick_crossed", r, b
        return "freekick_short", r, b
    if action_type == "PENALTY_KICK":
        return "shot_penalty", r, b
    if action_type == "GROUND_DUEL":
        return "tackle", r, b
    if action_type == "OFFSIDE":
        return "non_action", r, b
    if action_type == "OWN_GOAL":
        return "bad_touch", "owngoal", b

    return "non_action", r, b


def _map_bodypart(body_part: str) -> str:
    mapping = {
        "FOOT": "foot",
        "FOOT_LEFT": "foot_left",
        "FOOT_RIGHT": "foot_right",
        "HEAD": "head",
        "BODY": "other",
        "HAND": "other",
    }
    return mapping.get(body_part.upper(), "foot")


def _map_result(result: str, action_type: str) -> str:
    if not result or result == "None" or (isinstance(result, float) and np.isnan(result)):
        return "success"
    result = result.upper()
    if result == "FAIL":
        return "fail"
    if result == "OFFSIDE" or action_type == "OFFSIDE":
        return "offside"
    if result == "OWNGOAL" or result == "OWN_GOAL":
        return "owngoal"
    return "success"
