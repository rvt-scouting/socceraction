"""Impect event stream data loader."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional, cast

import pandas as pd  # type: ignore
from pandera.typing import DataFrame

from socceraction.data.base import EventDataLoader, MissingDataError, ParseError

from .minutes import minutes_from_roster
from .normalize import load_events_json, normalize_api_events
from .schema import (
    ImpectCompetitionSchema,
    ImpectEventSchema,
    ImpectGameSchema,
    ImpectPlayerSchema,
    ImpectTeamSchema,
)

try:
    import impectPy as ip
except ImportError:
    ip = None

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore


def _load_dotenv(root: Optional[str]) -> None:
    if load_dotenv is None:
        return
    if root:
        env_path = Path(root) / ".env"
        if env_path.is_file():
            load_dotenv(env_path)
            return
    load_dotenv(Path.cwd() / ".env")


def _credential_pairs(creds: Optional[dict[str, str]]) -> list[dict[str, str]]:
    if creds is not None:
        return [{"user": creds.get("user", ""), "passwd": creds.get("passwd", "")}]
    pairs = []
    for idx in (1, 2):
        user = os.environ.get(f"IMPECT_USER_{idx}", "")
        passwd = os.environ.get(f"IMPECT_PASS_{idx}", "")
        if user and passwd:
            pairs.append({"user": user, "passwd": passwd})
    return pairs


def _resolve_creds(creds: Optional[dict[str, str]], cred_index: int = 0) -> dict[str, str]:
    pairs = _credential_pairs(creds)
    if not pairs:
        raise ValueError(
            "Impect credentials missing. Pass creds={'user': ..., 'passwd': ...} "
            "or set IMPECT_USER_1 and IMPECT_PASS_1 in the environment / .env file."
        )
    if cred_index >= len(pairs):
        cred_index = 0
    return pairs[cred_index]


class ImpectLoader(EventDataLoader):
    """Load Impect event stream data from the Customer API or local JSON files.

    Local data should follow the layout of the Impect open-data repository:
    ``data/events/events_{game_id}.json``, ``data/matches/matches_{iteration_id}.json``,
    ``data/lineups/lineups_{game_id}.json``, and ``iterations.json``.

    Parameters
    ----------
    getter : str
        ``"remote"`` or ``"local"``.
    root : str, optional
        Root directory for local data or directory containing a ``.env`` file.
    creds : dict, optional
        Login credentials as ``{"user": "<username>", "passwd": "<password>"}``.
    """

    def __init__(
        self,
        getter: str = "local",
        root: Optional[str] = None,
        creds: Optional[dict[str, str]] = None,
    ) -> None:
        self._getter = getter
        self._root = Path(root) if root else Path.cwd()
        self._creds = creds
        self._token: Optional[str] = None
        self._cred_index = 0
        self._cred_pairs: list[dict[str, str]] = []

        if getter == "remote":
            if ip is None:
                raise ImportError(
                    "The 'impectPy' package is required. Install with "
                    "'pip install socceraction[impect]'."
                )
            _load_dotenv(str(self._root))
            self._cred_pairs = _credential_pairs(creds)
            if not self._cred_pairs:
                raise ValueError(
                    "Impect credentials missing. Set IMPECT_USER_1 and IMPECT_PASS_1 in .env "
                    f"(checked {self._root / '.env'} and environment)."
                )
            self._creds = self._cred_pairs[self._cred_index]
        elif getter == "local":
            if not self._root.is_dir():
                raise ValueError(f"Local data directory does not exist: {self._root}")
        else:
            raise ValueError("Invalid getter specified. Use 'remote' or 'local'.")

    def _invalidate_token(self) -> None:
        self._token = None

    def _rotate_credentials(self) -> bool:
        if len(self._cred_pairs) <= 1:
            return False
        self._cred_index = (self._cred_index + 1) % len(self._cred_pairs)
        self._creds = self._cred_pairs[self._cred_index]
        self._invalidate_token()
        return True

    def _get_token(self, force_refresh: bool = False) -> str:
        if force_refresh:
            self._invalidate_token()
        if self._token is None:
            assert self._creds is not None
            self._token = ip.getAccessToken(  # type: ignore[union-attr]
                username=self._creds["user"],
                password=self._creds["passwd"],
            )
        return self._token

    def _call_with_token_retry(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Call impectPy API function; refresh token on 401 and rotate creds on 429."""
        last_exc: Optional[Exception] = None
        for attempt in range(4):
            try:
                return fn(*args, token=self._get_token(), **kwargs)
            except Exception as exc:
                last_exc = exc
                msg = str(exc).lower()
                if "401" in msg or "unauthorized" in msg:
                    self._get_token(force_refresh=True)
                    continue
                if "429" in msg or "rate" in msg:
                    if self._rotate_credentials():
                        time.sleep(2.0 * (attempt + 1))
                        continue
                    time.sleep(5.0 * (attempt + 1))
                    continue
                raise
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("API call failed without exception")

    def _attach_match_scores(self, games: pd.DataFrame) -> pd.DataFrame:
        """Merge home/away goals from squad matchsums when available."""
        game_ids = [int(g) for g in games["game_id"]]
        if not game_ids:
            games["home_score"] = pd.Series(dtype="Int64")
            games["away_score"] = pd.Series(dtype="Int64")
            return games

        chunks: list[pd.DataFrame] = []
        try:
            for i in range(0, len(game_ids), 40):
                batch = game_ids[i : i + 40]
                sums = self._call_with_token_retry(ip.getSquadMatchsums, matches=batch)  # type: ignore[union-attr]
                if len(sums):
                    chunks.append(sums[["matchId", "squadId", "GOALS"]])
                time.sleep(0.5)
        except Exception:
            games["home_score"] = pd.NA
            games["away_score"] = pd.NA
            return games

        if not chunks:
            games["home_score"] = pd.NA
            games["away_score"] = pd.NA
            return games

        all_sums = pd.concat(chunks, ignore_index=True)
        score_rows = []
        for game_id in game_ids:
            row = games.loc[games["game_id"] == game_id].iloc[0]
            home_id = int(row["home_team_id"])
            away_id = int(row["away_team_id"])
            match_sums = all_sums.loc[all_sums["matchId"] == game_id]
            home_goals = match_sums.loc[match_sums["squadId"] == home_id, "GOALS"]
            away_goals = match_sums.loc[match_sums["squadId"] == away_id, "GOALS"]
            score_rows.append(
                {
                    "game_id": game_id,
                    "home_score": int(home_goals.iloc[0]) if len(home_goals) else pd.NA,
                    "away_score": int(away_goals.iloc[0]) if len(away_goals) else pd.NA,
                }
            )
        scores = pd.DataFrame(score_rows)
        return games.merge(scores, on="game_id", how="left")

    def _data_dir(self) -> Path:
        data = self._root / "data"
        return data if data.is_dir() else self._root

    def competitions(self) -> DataFrame[ImpectCompetitionSchema]:
        """Return available competition iterations."""
        if self._getter == "remote":
            df = self._call_with_token_retry(ip.getIterations)  # type: ignore[union-attr]
            competitions = pd.DataFrame(
                {
                    "competition_id": df["competitionId"],
                    "season_id": df["id"],
                    "competition_name": df["competitionName"],
                    "season_name": df["season"].astype(str),
                    "country_name": df.get("competitionCountryName"),
                    "competition_type": df.get("competitionType"),
                }
            )
        else:
            path = self._root / "iterations.json"
            if not path.is_file():
                path = self._data_dir().parent / "iterations.json"
            if not path.is_file():
                raise MissingDataError(f"iterations.json not found under {self._root}")
            with path.open(encoding="utf-8") as fh:
                iterations = json.load(fh)
            if iterations and "competitionId" in iterations[0]:
                competitions = pd.DataFrame(
                    {
                        "competition_id": [it["competitionId"] for it in iterations],
                        "season_id": [it["id"] for it in iterations],
                        "competition_name": [it["competitionName"] for it in iterations],
                        "season_name": [it["season"] for it in iterations],
                        "country_name": [it.get("competitionCountryName") for it in iterations],
                        "competition_type": [it.get("competitionType") for it in iterations],
                    }
                )
            else:
                competitions = pd.DataFrame(
                    {
                        "competition_id": [it["competition"]["id"] for it in iterations],
                        "season_id": [it["id"] for it in iterations],
                        "competition_name": [it["competition"]["name"] for it in iterations],
                        "season_name": [it["season"] for it in iterations],
                        "country_name": None,
                        "competition_type": [it["competition"].get("type") for it in iterations],
                    }
                )
        return cast(DataFrame[ImpectCompetitionSchema], competitions)

    def games(
        self, competition_id: int, season_id: int, include_scores: bool = True
    ) -> DataFrame[ImpectGameSchema]:
        """Return matches for a competition iteration (season_id = iterationId)."""
        if self._getter == "remote":
            df = self._call_with_token_retry(ip.getMatches, season_id)  # type: ignore[union-attr]
            comp_col = df["competitionId"] if "competitionId" in df.columns else competition_id
            games = pd.DataFrame(
                {
                    "game_id": df["id"],
                    "season_id": season_id,
                    "competition_id": comp_col,
                    "game_day": df.get("matchDayIndex"),
                    "game_date": pd.to_datetime(df["scheduledDate"]),
                    "home_team_id": df["homeSquadId"],
                    "away_team_id": df["awaySquadId"],
                    "match_day_name": df.get("matchDayName"),
                }
            )
            if include_scores:
                games = self._attach_match_scores(games)
            else:
                games["home_score"] = pd.NA
                games["away_score"] = pd.NA
        else:
            path = self._data_dir() / "matches" / f"matches_{season_id}.json"
            if not path.is_file():
                raise MissingDataError(f"Match file not found: {path}")
            with path.open(encoding="utf-8") as fh:
                matches = json.load(fh)
            game_days = []
            match_day_names = []
            for m in matches:
                md = m.get("matchDay") or {}
                game_days.append(m.get("matchDayIndex", md.get("index")))
                match_day_names.append(m.get("matchDayName", md.get("name")))
            games = pd.DataFrame(
                {
                    "game_id": [m["id"] for m in matches],
                    "season_id": season_id,
                    "competition_id": competition_id,
                    "game_day": game_days,
                    "game_date": pd.to_datetime([m["scheduledDate"] for m in matches]),
                    "home_team_id": [m["homeSquadId"] for m in matches],
                    "away_team_id": [m["awaySquadId"] for m in matches],
                    "match_day_name": match_day_names,
                }
            )
            games["home_score"] = pd.NA
            games["away_score"] = pd.NA
        return cast(DataFrame[ImpectGameSchema], games)

    def teams(self, game_id: int) -> DataFrame[ImpectTeamSchema]:
        """Return the home and away squads for a match."""
        if self._getter == "remote":
            match = self._get_match_row(game_id)
            teams = pd.DataFrame(
                {
                    "team_id": [match["homeSquadId"], match["awaySquadId"]],
                    "team_name": [match.get("homeSquadName"), match.get("awaySquadName")],
                }
            )
            return cast(DataFrame[ImpectTeamSchema], teams)

        lineup = self._load_lineup(game_id)
        teams = pd.DataFrame(
            {
                "team_id": [lineup["home"]["id"], lineup["away"]["id"]],
                "team_name": [
                    str(lineup["home"]["id"]),
                    str(lineup["away"]["id"]),
                ],
            }
        )
        return cast(DataFrame[ImpectTeamSchema], teams)

    def players(self, game_id: int) -> DataFrame[ImpectPlayerSchema]:
        """Return players that participated in a match."""
        if self._getter == "remote":
            positions = self._call_with_token_retry(  # type: ignore[union-attr]
                ip.getStartingPositions, matches=[game_id]
            )
            subs = self._call_with_token_retry(  # type: ignore[union-attr]
                ip.getSubstitutions, matches=[game_id]
            )
            starter_ids = set(positions["playerId"].astype(int))
            played_minutes = minutes_from_roster(positions, subs)
            records = []
            for row in positions.to_dict(orient="records"):
                pid = int(row["playerId"])
                records.append(
                    {
                        "game_id": game_id,
                        "team_id": int(row["squadId"]),
                        "player_id": pid,
                        "player_name": row.get("playerName", str(pid)),
                        "is_starter": True,
                        "minutes_played": played_minutes.get(pid, 90),
                        "jersey_number": int(row.get("shirtNumber", 0)),
                    }
                )
            if len(subs) > 0:
                for row in subs.to_dict(orient="records"):
                    pid = int(row["playerId"])
                    if pid in starter_ids:
                        continue
                    records.append(
                        {
                            "game_id": game_id,
                            "team_id": int(row["squadId"]),
                            "player_id": pid,
                            "player_name": row.get("playerName", str(pid)),
                            "is_starter": False,
                            "minutes_played": played_minutes.get(pid, 0),
                            "jersey_number": int(row.get("shirtNumber", 0)),
                        }
                    )
            return cast(DataFrame[ImpectPlayerSchema], pd.DataFrame(records))

        lineup = self._load_lineup(game_id)
        records: list[dict[str, Any]] = []
        for side in ("home", "away"):
            squad = lineup[side]
            starter_ids = {
                int(p["playerId"])
                for p in squad.get("startingPositions", [])
                if p.get("playerId") is not None
            }
            for player in squad.get("players", []):
                pid = int(player["id"])
                records.append(
                    {
                        "game_id": game_id,
                        "team_id": squad["id"],
                        "player_id": pid,
                        "player_name": str(pid),
                        "is_starter": pid in starter_ids,
                        "minutes_played": 90 if pid in starter_ids else 0,
                        "jersey_number": int(player.get("shirtNumber", 0)),
                    }
                )
        return cast(DataFrame[ImpectPlayerSchema], pd.DataFrame(records))

    def events(self, game_id: int) -> DataFrame[ImpectEventSchema]:
        """Return the event stream for a match."""
        if self._getter == "remote":
            raw = self._call_with_token_retry(  # type: ignore[union-attr]
                ip.getEvents,
                matches=[game_id],
                include_kpis=False,
                include_set_pieces=False,
            )
            if len(raw) == 0:
                raise ParseError(f"No events returned for match {game_id}")
            events = normalize_api_events(raw, game_id=game_id)
        else:
            path = self._data_dir() / "events" / f"events_{game_id}.json"
            if not path.is_file():
                raise MissingDataError(f"Event file not found: {path}")
            events = load_events_json(path, game_id)
        return cast(DataFrame[ImpectEventSchema], events)

    def _get_match_row(self, game_id: int) -> pd.Series:
        iteration_id = int(
            self._call_with_token_retry(ip.getStartingPositions, matches=[game_id])  # type: ignore[union-attr]
            .iloc[0]["iterationId"]
        )
        matches = self._call_with_token_retry(ip.getMatches, iteration_id)  # type: ignore[union-attr]
        match = matches.loc[matches["id"] == game_id]
        if len(match) == 0:
            raise MissingDataError(f"Match {game_id} not found in iteration {iteration_id}")
        return match.iloc[0]

    def _load_lineup(self, game_id: int) -> dict[str, Any]:
        path = self._data_dir() / "lineups" / f"lineups_{game_id}.json"
        if not path.is_file():
            raise MissingDataError(f"Lineup file not found: {path}")
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return {
            "home": {
                "id": data["squadHome"]["id"],
                "players": data["squadHome"].get("players", []),
                "startingPositions": data["squadHome"].get("startingPositions", []),
            },
            "away": {
                "id": data["squadAway"]["id"],
                "players": data["squadAway"].get("players", []),
                "startingPositions": data["squadAway"].get("startingPositions", []),
            },
        }
