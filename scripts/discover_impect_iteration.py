#!/usr/bin/env python3
"""List Impect iterations and optionally save IDs for a target competition."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from socceraction.data.impect import ImpectLoader


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--competition-name", type=str, default="Challenger Pro League")
    parser.add_argument("--season-contains", type=str, default="25")
    parser.add_argument("--country-contains", type=str, default="Belg")
    parser.add_argument("--output", type=Path, help="Write selected row as JSON")
    args = parser.parse_args()

    load_dotenv(args.root / ".env")
    loader = ImpectLoader(getter="remote", root=str(args.root))
    comps = loader.competitions()

    mask = comps["competition_name"].str.contains(args.competition_name, case=False, na=False)
    mask &= comps["season_name"].str.contains(args.season_contains, na=False)
    if comps["country_name"].notna().any():
        mask &= comps["country_name"].str.contains(args.country_contains, case=False, na=False)

    sel = comps.loc[mask]
    if len(sel) == 0:
        print("No match. Available competitions:")
        print(comps.sort_values(["country_name", "competition_name", "season_name"]).to_string())
        raise SystemExit(1)

    print(sel.to_string())
    row = sel.iloc[-1]
    record = {
        "competition_id": int(row["competition_id"]),
        "season_id": int(row["season_id"]),
        "competition_name": row["competition_name"],
        "season_name": row["season_name"],
        "country_name": row.get("country_name"),
        "competition_type": row.get("competition_type"),
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(record, indent=2))
        print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
