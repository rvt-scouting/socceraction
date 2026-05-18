"""Tests for Impect minutes played estimation."""

import pandas as pd

from socceraction.data.impect.minutes import minutes_from_roster


def test_starters_play_full_match_without_subs() -> None:
    positions = pd.DataFrame(
        {"playerId": [1, 2], "squadId": [10, 10], "playerName": ["A", "B"], "shirtNumber": [1, 2]}
    )
    subs = pd.DataFrame()
    mins = minutes_from_roster(positions, subs)
    assert mins[1] == 90
    assert mins[2] == 90


def test_sub_off_reduces_starter_minutes() -> None:
    positions = pd.DataFrame(
        {"playerId": [1, 2], "squadId": [10, 10], "playerName": ["A", "B"], "shirtNumber": [1, 2]}
    )
    subs = pd.DataFrame(
        {
            "playerId": [3],
            "exchangedPlayerId": [1],
            "gameTimeInSec": [60 * 60],
        }
    )
    mins = minutes_from_roster(positions, subs)
    assert mins[1] == 60
    assert mins[3] == 30
