"""Utilities to validate Impect → SPADL conversion quality."""

from __future__ import annotations

from typing import Any

import pandas as pd  # type: ignore

from socceraction.spadl import SPADLSchema, add_names, config as spadlconfig
from socceraction.spadl import impect as spadl_impect


def validate_actions(
    events: pd.DataFrame, actions: pd.DataFrame, home_team_id: int
) -> dict[str, Any]:
    """Run sanity checks on converted SPADL actions for one match."""
    named = add_names(actions)
    SPADLSchema.validate(named)

    type_names = set(named.type_name.dropna())
    ratio = len(named) / len(events) if len(events) else 0.0

    return {
        "n_events": len(events),
        "n_actions": len(named),
        "action_ratio": ratio,
        "type_counts": named.type_name.value_counts().to_dict(),
        "has_pass": "pass" in type_names,
        "has_shot": "shot" in type_names or "shot_penalty" in type_names,
        "has_take_on_or_dribble": "take_on" in type_names or "dribble" in type_names,
        "start_x_min": float(named.start_x.min()),
        "start_x_max": float(named.start_x.max()),
        "start_y_min": float(named.start_y.min()),
        "start_y_max": float(named.start_y.max()),
        "coords_in_bounds": (
            named.start_x.min() >= 0
            and named.start_x.max() <= spadlconfig.field_length
            and named.start_y.min() >= 0
            and named.start_y.max() <= spadlconfig.field_width
        ),
    }


def convert_and_validate(events: pd.DataFrame, home_team_id: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Convert events to SPADL and return actions plus validation report."""
    actions = spadl_impect.convert_to_actions(events, home_team_id)
    report = validate_actions(events, actions, home_team_id)
    return actions, report
