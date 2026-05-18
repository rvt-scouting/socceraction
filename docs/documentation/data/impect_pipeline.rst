Impect production pipeline (local)
====================================

This guide describes a **local-only** workflow for building SPADL from your Impect
subscription and training VAEP on a full iteration. It is not part of the installable
library API.

The operational scripts live in ``private/impect-pipeline/`` at the project root. That
folder is listed in ``.gitignore`` and should **not** be pushed to GitHub. Only the
:socceraction: package, tests, and documentation belong in the public repository.

Prerequisites
-------------

.. code-block:: bash

   pip install socceraction[impect,xgboost,hdf]

Create a ``.env`` file in the project root (also gitignored):

.. code-block:: text

   IMPECT_USER_1=your_username
   IMPECT_PASS_1=your_password
   IMPECT_USER_2=optional_second_user
   IMPECT_PASS_2=optional_second_password

Folder layout
-------------

After setup, your machine typically looks like:

.. code-block:: text

   socceraction/
   ├── socceraction/          # library (committed)
   ├── tests/                 # open-data fixtures (committed)
   ├── docs/                  # documentation (committed)
   ├── private/               # local only — gitignored
   │   └── impect-pipeline/
   │       ├── build_spadl_h5.py
   │       ├── discover_iteration.py
   │       ├── validate_iteration.py
   │       ├── run_vaep.py
   │       ├── export_ratings.py
   │       └── config/
   │           └── my_iteration.json
   ├── public-notebooks/      # Impect VAEP notebooks 1–4 (committed)
   └── data/impect/           # cache + HDF5 + outputs — gitignored
       ├── 1476/              # raw JSON cache (iterationId)
       └── challenger-2526/   # or basename from config
           ├── spadl-impect.h5
           ├── features.h5
           ├── labels.h5
           ├── predictions.h5
           └── player_vaep.csv

Copy the example config:

.. code-block:: bash

   mkdir -p private/impect-pipeline/config
   cp docs/documentation/data/impect_iteration.example.json \
      private/impect-pipeline/config/my_iteration.json
   # Edit competition_id, season_id, output_basename

Step 1 — Discover iteration
---------------------------

Find ``competition_id`` and ``season_id`` (Impect **iterationId**) for your target league:

.. code-block:: bash

   python private/impect-pipeline/discover_iteration.py \
     --competition-name "Challenger Pro League" \
     --season-contains "25" \
     --country-contains "Belg" \
     --output private/impect-pipeline/config/my_iteration.json

If nothing matches, omit filters and inspect the printed table.

Step 2 — Cache and build SPADL HDF5
-----------------------------------

Download event JSON once, then convert to SPADL. Use ``--dry-run`` to print paths without
calling the API.

.. code-block:: bash

   python private/impect-pipeline/build_spadl_h5.py \
     --config private/impect-pipeline/config/my_iteration.json \
     --getter remote --cache

Options:

- ``--getter local`` — rebuild HDF5 from ``data/impect/{season_id}/`` cache (default)
- ``--data-root PATH`` — local JSON root for open-data or custom exports (see
  ``impect_open_data.example.json``)
- ``--only-new`` — skip games already present in the HDF5 file
- ``--dry-run`` — show resolved paths and game count only

Expect **~5 seconds per match** when caching from the API. Some matches may be unavailable;
the script logs skips and continues. Re-running is safe: existing event files are skipped.

Match scores are written to the HDF5 ``games`` table when building from the API, or when
building from cache via a one-off remote ``games(include_scores=True)`` merge (no extra
per-match API calls).

Step 3 — Validate SPADL
-----------------------

.. code-block:: bash

   python private/impect-pipeline/validate_iteration.py \
     --config private/impect-pipeline/config/my_iteration.json

Pass criteria (rule of thumb):

- ``coords_in_bounds`` is true for all matches
- ``action_ratio`` roughly 0.5–0.75 (receptions filtered)
- ``has_pass`` and ``has_shot`` true for most matches

Step 4 — Train VAEP
-------------------

Chronological train/test split (first 80% of matchdays train). Outputs go to
``data/impect/{output_basename}/``.

.. code-block:: bash

   python private/impect-pipeline/run_vaep.py \
     --config private/impect-pipeline/config/my_iteration.json

Use ``--dry-run`` to verify paths. Use ``--skip-train`` if features/labels already exist
and you only want to re-rate players.

Step 5 — Export player ratings
------------------------------

Per-90 VAEP with minutes from ``player_games``:

.. code-block:: bash

   python private/impect-pipeline/export_ratings.py \
     --config private/impect-pipeline/config/my_iteration.json

Optional step-by-step analysis: ``public-notebooks/2-compute-features-and-labels-impect.ipynb``
through notebook 4 (same config JSON as the pipeline scripts). For xT on the same SPADL file,
see ``public-notebooks/EXTRA-run-xT-impect.ipynb``.

What not to commit
------------------

- ``private/`` — pipeline scripts and your configs
- ``data/impect/`` — API cache, HDF5, CSV, logs (notebooks read paths from config)
- ``.env`` — credentials
- ``*.h5`` — large model/data artifacts

Troubleshooting
---------------

**HTTP 401** — Token expired; the loader refreshes automatically on the next call.

**HTTP 429** — Rate limit. Wait and retry, or set ``IMPECT_USER_2`` / ``IMPECT_PASS_2``.
The build script sleeps between event downloads.

**Missing matches** — Some iteration slots have no events in the API. They are skipped;
VAEP uses all games with SPADL in the HDF5.

**Empty HDF5 after build** — Check stderr for systematic conversion errors; run
``validate_iteration.py`` on one ``game_id``.

Example: Belgium Challenger Pro League 25/26
----------------------------------------------

Local config only (do not commit real IDs if your policy forbids it):

.. code-block:: json

   {
     "competition_id": 239,
     "season_id": 1476,
     "competition_name": "Challenger Pro League",
     "season_name": "25/26",
     "output_basename": "challenger-2526"
   }
