"""Normalize Impect API and open-data JSON into a flat event dataframe."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np
import pandas as pd  # type: ignore

JSONType = Union[dict[str, Any], list[Any]]


def _coord(component: Any, axis: str) -> Optional[float]:
    if component is None or (isinstance(component, float) and np.isnan(component)):
        return None
    if isinstance(component, (int, float)):
        return float(component)
    if isinstance(component, dict):
        coords = component.get("coordinates") or component
        if isinstance(coords, dict) and axis in coords:
            val = coords[axis]
            return float(val) if val is not None else None
    return None


def _game_time_seconds(row: dict[str, Any]) -> float:
    if "gameTimeInSec" in row and row["gameTimeInSec"] is not None:
        return float(row["gameTimeInSec"])
    game_time = row.get("gameTime")
    if isinstance(game_time, dict) and game_time.get("gameTimeInSec") is not None:
        return float(game_time["gameTimeInSec"])
    return 0.0


def _optional_int(value: Any) -> Optional[int]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return int(value)


def _player_id(row: dict[str, Any]) -> Optional[int]:
    return _optional_int(row.get("playerId")) or (
        _optional_int(row.get("player", {}).get("id"))
        if isinstance(row.get("player"), dict)
        else None
    )


def flatten_raw_event(row: dict[str, Any], game_id: int) -> dict[str, Any]:
    """Flatten one Impect event record (API or open-data JSON)."""
    event_id = row.get("eventId", row.get("id"))
    start = row.get("start")
    end = row.get("end")
    period_id = row.get("periodId")
    return {
        "game_id": int(row.get("matchId", game_id)),
        "event_id": event_id,
        "period_id": int(period_id) if period_id is not None and not pd.isna(period_id) else None,
        "team_id": _optional_int(row.get("squadId")),
        "player_id": _player_id(row),
        "type_id": 0,
        "type_name": str(row["actionType"]),
        "action": row.get("action"),
        "result": row.get("result"),
        "body_part": row.get("bodyPart") or row.get("body_part"),
        "game_time_seconds": _game_time_seconds(row),
        "start_x": row.get("startCoordinatesX", _coord(start, "x")),
        "start_y": row.get("startCoordinatesY", _coord(start, "y")),
        "end_x": row.get("endCoordinatesX", _coord(end, "x")),
        "end_y": row.get("endCoordinatesY", _coord(end, "y")),
        "phase": row.get("phase"),
        "extra": None,
    }


def events_from_json(data: JSONType, game_id: int) -> pd.DataFrame:
    """Build a normalized events dataframe from Impect JSON."""
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict) and "events" in data:
        rows = data["events"]
    else:
        rows = []
    records = [flatten_raw_event(row, game_id) for row in rows]
    df = pd.DataFrame(records)
    if len(df) == 0:
        return df
    df["type_id"] = pd.factorize(df["type_name"])[0]
    return df


def load_events_json(path: Path, game_id: Optional[int] = None) -> pd.DataFrame:
    """Load events from a local JSON file (open-data nested or cached API flat)."""
    if game_id is None:
        stem = path.stem
        if stem.startswith("events_"):
            game_id = int(stem.split("_", 1)[1])
        else:
            raise ValueError("game_id must be provided if it cannot be inferred from the filename.")
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, list) and data:
        first = data[0]
        if "start" in first or "gameTime" in first:
            return events_from_json(data, game_id)
        if "matchId" in first:
            return normalize_api_events(pd.DataFrame(data))
    return events_from_json(data, game_id)


def normalize_api_events(events: pd.DataFrame, game_id: Optional[int] = None) -> pd.DataFrame:
    """Normalize a dataframe returned by impectPy.getEvents."""
    records = []
    for row in events.to_dict(orient="records"):
        match_id = row.get("matchId", game_id)
        if match_id is None or (isinstance(match_id, float) and np.isnan(match_id)):
            match_id = game_id
        records.append(flatten_raw_event(row, int(match_id)))
    df = pd.DataFrame(records)
    if len(df) == 0:
        return df
    df["type_id"] = pd.factorize(df["type_name"])[0]
    return df
