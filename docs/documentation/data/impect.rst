Impect
======

Load event stream data from the `Impect Customer API <https://www.impect.com>`_ or from
local JSON exports (same layout as the `Impect open-data <https://github.com/ImpectAPI/open-data>`_ repository).

Installation
------------

.. code-block:: bash

   pip install socceraction[impect]

Authentication (remote)
-----------------------

Set credentials in a ``.env`` file or environment variables:

- ``IMPECT_USER_1``
- ``IMPECT_PASS_1``
- ``IMPECT_USER_2`` / ``IMPECT_PASS_2`` (optional, for rate-limit rotation)

Loader behaviour
----------------

``ImpectLoader(getter="remote")`` and ``getter="local"`` share the same method signatures
as other socceraction data providers:

- ``competitions()`` — available iterations
- ``games(competition_id, season_id, include_scores=True)`` — schedule; scores from squad
  matchsums when ``include_scores`` is true (remote only)
- ``teams(game_id)``, ``players(game_id)``, ``events(game_id)``

Remote calls refresh the bearer token on HTTP 401 and may rotate credentials on HTTP 429.
``players()`` estimates minutes played from substitution timestamps.

Convert events to SPADL with :mod:`socceraction.spadl.impect` (same schema as StatsBomb /
Wyscout / Opta). VAEP, xT, and other SPADL-based tools work without Impect-specific code.

.. code-block:: python

   from socceraction.data.impect import ImpectLoader
   import socceraction.spadl as spadl

   loader = ImpectLoader(getter="local", root="tests/datasets/impect/raw")
   games = loader.games(competition_id=2, season_id=743)
   game_id = 122838
   events = loader.events(game_id)
   home_team_id = int(games.loc[games.game_id == game_id, "home_team_id"].iloc[0])
   actions = spadl.impect.convert_to_actions(events, home_team_id)
   actions = spadl.add_names(actions)

Production pipeline (local)
---------------------------

To cache a full subscription iteration, build HDF5, and train VAEP on your machine, see
:doc:`impect_pipeline`. That workflow uses ``private/impect-pipeline/`` scripts and
``data/impect/`` outputs, which are **not** part of the public repository.

Open-data demo notebook: ``public-notebooks/1-load-and-convert-impect-data.ipynb``.

Advanced analytics
------------------

- **VAEP** — provider-agnostic once SPADL exists; use the local pipeline or
  ``public-notebooks/2-compute-features-and-labels-impect.ipynb`` through notebook 4.
- **xT** — :mod:`socceraction.xthreat` on Impect SPADL:
  ``public-notebooks/EXTRA-run-xT-impect.ipynb`` (after notebook 1).
- **Atomic-VAEP** — mirror ``public-notebooks/ATOMIC-*`` locally if needed.
- **Kloppy** — can load Impect JSON for reference; prefer ``spadl.impect`` for VAEP.
  ``spadl.kloppy`` does not list Impect as a fully supported provider.

Validation
----------

:mod:`socceraction.data.impect.validate` provides ``convert_and_validate()`` for sanity
checks (schema, action ratio, coordinates). Open-data tests in ``tests/spadl/test_impect*.py``
run in CI without API access.
