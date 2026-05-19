# ML-DA legacy archive

After a successful Impect pipeline test run **and** PostgreSQL push, move superseded
Data Analytics scripts here (or delete on the server).

## Replace with

| Old (ML-DA) | New |
|-------------|-----|
| Ad-hoc Impect → VAEP notebooks/scripts | `private/impect-pipeline/run_iteration.sh` |
| Manual CSV exports | `export_ratings.py` + `push_vaep_to_postgres.py` |
| One-off HDF5 builds | `build_spadl_h5.py` with `--config` |

## Server cleanup (DA group)

On the server, remove or archive directories that fail to run (broken imports, old provider paths).
Keep:

- `socceraction` git clone (library + `public-notebooks/`)
- `private/impect-pipeline/`
- `data/impect/`
- `.env` (credentials + `DATABASE_URL`)

Document removed paths in `SERVER_CLEANUP.log` before deleting.
