"""Compute minutes played from Impect starting positions and substitutions."""

from __future__ import annotations

from typing import Any

import pandas as pd


def minutes_from_roster(
    positions: pd.DataFrame,
    subs: pd.DataFrame,
    match_length_sec: float = 90 * 60,
) -> dict[int, int]:
    """Return player_id -> minutes played for one match."""
    minutes: dict[int, float] = {}
    if len(positions) == 0:
        return {}

    for row in positions.to_dict(orient="records"):
        pid = int(row["playerId"])
        minutes[pid] = float(match_length_sec) / 60.0

    if len(subs) == 0:
        return {int(k): int(round(v)) for k, v in minutes.items()}

    sub_rows = subs.sort_values("gameTimeInSec")
    for row in sub_rows.to_dict(orient="records"):
        t_sec = float(row.get("gameTimeInSec") or 0)
        t_min = t_sec / 60.0
        on_id = int(row["playerId"])
        off_id = row.get("exchangedPlayerId")
        if on_id not in minutes:
            minutes[on_id] = max(0.0, (match_length_sec - t_sec) / 60.0)
        else:
            minutes[on_id] = max(minutes[on_id], (match_length_sec - t_sec) / 60.0)
        if off_id is not None and not (isinstance(off_id, float) and pd.isna(off_id)):
            off_id = int(off_id)
            if off_id in minutes:
                minutes[off_id] = min(minutes[off_id], t_min)

    return {int(k): int(round(max(0, v))) for k, v in minutes.items()}
