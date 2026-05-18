"""Schemas for Impect event stream data."""

import pandas as pd
import pandera as pa
from pandera.typing import Object, Series
from typing import Optional

from socceraction.data.schema import (
    CompetitionSchema,
    EventSchema,
    GameSchema,
    PlayerSchema,
    TeamSchema,
)


class ImpectCompetitionSchema(CompetitionSchema):
    """Definition of a dataframe containing Impect competition iterations."""

    country_name: Series[str] = pa.Field(nullable=True)
    competition_type: Series[str] = pa.Field(nullable=True)


class ImpectGameSchema(GameSchema):
    """Definition of a dataframe containing Impect matches."""

    match_day_name: Series[str] = pa.Field(nullable=True)
    home_score: Optional[Series[pd.Int64Dtype]] = pa.Field(nullable=True)
    away_score: Optional[Series[pd.Int64Dtype]] = pa.Field(nullable=True)


class ImpectTeamSchema(TeamSchema):
    """Definition of a dataframe containing Impect squads in a match."""


class ImpectPlayerSchema(PlayerSchema):
    """Definition of a dataframe containing Impect players in a match."""

    player_name: Series[str] = pa.Field(nullable=True)


class ImpectEventSchema(EventSchema):
    """Definition of a dataframe containing Impect event stream data."""

    action: Series[str] = pa.Field(nullable=True)
    result: Series[str] = pa.Field(nullable=True)
    body_part: Series[str] = pa.Field(nullable=True)
    game_time_seconds: Series[float]
    start_x: Series[float] = pa.Field(nullable=True)
    start_y: Series[float] = pa.Field(nullable=True)
    end_x: Series[float] = pa.Field(nullable=True)
    end_y: Series[float] = pa.Field(nullable=True)
    phase: Series[str] = pa.Field(nullable=True)
    extra: Series[Object] = pa.Field(nullable=True)
