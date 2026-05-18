#!/usr/bin/env python3
"""Run VAEP features, training, and ratings for Impect SPADL HDF5 data."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(x, **kwargs):
        return x

import socceraction.spadl as spadl
import socceraction.vaep.features as fs
import socceraction.vaep.formula as vaepformula
import socceraction.vaep.labels as lab

try:
    import xgboost
except ImportError as exc:
    raise SystemExit("Install xgboost: pip install socceraction[xgboost]") from exc


def _games_with_actions(spadl_h5: Path) -> pd.DataFrame:
    with pd.HDFStore(spadl_h5) as store:
        games = store["games"]
        action_ids = {
            int(key.rsplit("_", 1)[-1])
            for key in store.keys()
            if key.startswith("/actions/game_")
        }
    return games[games.game_id.isin(action_ids)].sort_values("game_date").reset_index(drop=True)


def build_features_labels(spadl_h5: Path, features_h5: Path, labels_h5: Path) -> pd.DataFrame:
    games = _games_with_actions(spadl_h5)
    xfns = [
        fs.actiontype,
        fs.actiontype_onehot,
        fs.bodypart_onehot,
        fs.result,
        fs.result_onehot,
        fs.goalscore,
        fs.startlocation,
        fs.endlocation,
        fs.movement,
        fs.space_delta,
        fs.startpolar,
        fs.endpolar,
        fs.team,
        fs.time_delta,
    ]
    yfns = [lab.scores, lab.concedes, lab.goal_from_shot]

    with pd.HDFStore(spadl_h5) as spadlstore, pd.HDFStore(features_h5, "w") as featstore, pd.HDFStore(
        labels_h5, "w"
    ) as labelstore:
        for game in tqdm(list(games.itertuples()), desc="Features & labels"):
            actions = spadlstore[f"actions/game_{game.game_id}"]
            actions_named = spadl.add_names(actions)
            gamestates = fs.gamestates(actions_named, 3)
            gamestates = fs.play_left_to_right(gamestates, game.home_team_id)
            X = pd.concat([fn(gamestates) for fn in xfns], axis=1)
            Y = pd.concat([fn(actions_named) for fn in yfns], axis=1)
            featstore.put(f"game_{game.game_id}", X, format="table")
            labelstore.put(f"game_{game.game_id}", Y, format="table")
    return games


def train_models(
    games: pd.DataFrame, features_h5: Path, labels_h5: Path, predictions_h5: Path
) -> None:
    xfns = [
        fs.actiontype,
        fs.actiontype_onehot,
        fs.bodypart_onehot,
        fs.result,
        fs.result_onehot,
        fs.goalscore,
        fs.startlocation,
        fs.endlocation,
        fs.movement,
        fs.space_delta,
        fs.startpolar,
        fs.endpolar,
        fs.team,
        fs.time_delta,
    ]
    nb_prev_actions = 1
    Xcols = fs.feature_column_names(xfns, nb_prev_actions)
    Ycols = ["scores", "concedes"]

    split = max(1, int(len(games) * 0.8))
    train_games = games.iloc[:split]
    test_games = games.iloc[split:] if split < len(games) else games.iloc[:1]

    def get_xy(game_frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        X_parts, Y_parts = [], []
        for game_id in game_frame.game_id:
            X_parts.append(pd.read_hdf(features_h5, f"game_{game_id}")[Xcols])
            Y_parts.append(pd.read_hdf(labels_h5, f"game_{game_id}")[Ycols])
        return pd.concat(X_parts).reset_index(drop=True), pd.concat(Y_parts).reset_index(drop=True)

    trainX, trainY = get_xy(train_games)
    testX, testY = get_xy(test_games)

    models = {}
    for col in Ycols:
        model = xgboost.XGBClassifier(
            n_estimators=50, max_depth=3, n_jobs=-1, verbosity=0, enable_categorical=True
        )
        model.fit(trainX, trainY[col])
        models[col] = model

    with pd.HDFStore(predictions_h5, "w") as predstore:
        for game_id in games.game_id:
            Xi = pd.read_hdf(features_h5, f"game_{game_id}")[Xcols]
            Yi_hat = pd.DataFrame(
                {col: models[col].predict_proba(Xi)[:, 1] for col in Ycols}
            )
            predstore.put(f"game_{game_id}", Yi_hat, format="table")


def rate_players(spadl_h5: Path, predictions_h5: Path) -> pd.DataFrame:
    games = _games_with_actions(spadl_h5)
    with pd.HDFStore(spadl_h5) as spadlstore:
        players = spadlstore["players"] if "players" in spadlstore else pd.DataFrame()
        teams = spadlstore["teams"] if "teams" in spadlstore else pd.DataFrame()

    frames = []
    for game in tqdm(list(games.itertuples()), desc="VAEP values"):
        actions = pd.read_hdf(spadl_h5, f"actions/game_{game.game_id}")
        actions = spadl.add_names(actions)
        if len(players):
            actions = actions.merge(players, how="left")
        if len(teams):
            actions = actions.merge(teams, how="left")
        preds = pd.read_hdf(predictions_h5, f"game_{game.game_id}")
        values = vaepformula.value(actions, preds.scores, preds.concedes)
        frames.append(pd.concat([actions, preds, values], axis=1))
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datafolder", type=Path, default=Path("data/impect"))
    parser.add_argument(
        "--spadl-h5",
        type=Path,
        default=None,
        help="SPADL HDF5 file (default: datafolder/spadl-impect.h5)",
    )
    args = parser.parse_args()
    spadl_h5 = args.spadl_h5 or (args.datafolder / "spadl-impect.h5")
    features_h5 = args.datafolder / "features.h5"
    labels_h5 = args.datafolder / "labels.h5"
    predictions_h5 = args.datafolder / "predictions.h5"

    games = build_features_labels(spadl_h5, features_h5, labels_h5)
    print(f"Built features/labels for {len(games)} games")
    train_models(games, features_h5, labels_h5, predictions_h5)
    print("Trained models and saved predictions")
    A = rate_players(spadl_h5, predictions_h5)
    top = (
        A.groupby("player_id")["vaep_value"]
        .agg(["sum", "count"])
        .rename(columns={"sum": "vaep_value", "count": "count"})
        .reset_index()
        .sort_values("vaep_value", ascending=False)
        .head(15)
    )
    print(top)


if __name__ == "__main__":
    main()
