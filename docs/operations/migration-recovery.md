# Migration Recovery — Baseline Adoption & Manual Re-stamp

> **Audience:** operators whose deploy aborted in the database migration
> step, or whose backend logs point here.
> **Related:** #10001 (silent migration failure), #10026 (legacy upgrade
> paths), #9759 (chain repair), `autobot-backend/migrations/baseline.py`.

## Background

Until #10001 was fixed, the Ansible migration step invoked Alembic without
its config file and swallowed the failure, so native Postgres-backed
deployments often have a schema built by the application (historical
`metadata.create_all`) with **no `alembic_version` stamp**. The deploy
pipeline now runs, in order:

1. `python -m migrations.baseline` — classifies the database, stamps an
   adoption revision when that is provably safe, refuses otherwise;
2. `pg_dumpall` backup (when Postgres is local to the node);
3. `python -m alembic -c migrations/alembic.ini upgrade head` — **strict**:
   failure aborts the deploy.

A refused adoption (exit 3/4) is **recoverable** — nothing was written.
A wrong stamp would silently corrupt every future migration. That is why
the tool never guesses.

## Reading your current revision

All commands run as the backend user from `/opt/autobot/autobot-backend`
(or wherever the backend code lives):

```bash
# What does the database think?
venv/bin/python -m alembic -c migrations/alembic.ini current

# What would the baseline tool decide? (writes nothing)
venv/bin/python -m migrations.baseline --dry-run

# What is head?
venv/bin/python -m alembic -c migrations/alembic.ini heads
```

The database URL comes from `AUTOBOT_DATABASE_URL` or the deployment
config; in a shell, source the backend `.env` first:
`set -a; . ./.env; set +a`.

## How the adoption logic decides

`migrations.baseline` inspects `information_schema` once and classifies:

| State | Observation | Action | Exit |
|---|---|---|---|
| 1 EMPTY | no chain-known tables | nothing — upgrade runs the full chain | 0 |
| 2 STAMPED | `alembic_version` holds known revision(s) | nothing — upgrade continues from the stamp | 0 |
| 3 SCHEMA, NO STAMP | known tables, no `alembic_version` | adoption (below) | 0 / 3 |
| 4 FOREIGN STAMP | `alembic_version` revision not in the chain | map via compatibility table, else refuse | 0 / 4 |

Adoption (state 3):

- **3a.** If an autogenerate comparison against the head models shows no
  drift, the schema IS head: stamp head.
- **3b.** Otherwise the **probe ladder** brackets the schema. For every
  revision the tool knows the structural artifacts its `upgrade()`
  introduces (created tables, added columns, TIMESTAMPTZ conversions —
  extracted from the migration files themselves). A revision R is the
  bracket when everything at or below R looks applied and everything above
  R looks absent. R gets stamped; `upgrade head` applies the rest.
- **3c.** If the artifacts are non-monotonic (e.g. a later table exists
  while an earlier one is missing, or a revision is *partially* applied),
  the schema matches no point in the chain → **exit 3, refused**.

## Manual recovery for the refused (ambiguous) case

1. **Do not stamp anything yet.** Take a backup:
   `su - postgres -c "pg_dumpall --clean --if-exists" | gzip > /opt/autobot/backups/manual-$(date +%s).sql.gz`
2. Run `venv/bin/python -m migrations.baseline --dry-run` and read the
   refusal report: it lists *partially-applied*, *applied-looking* and
   *absent-looking* revisions.
3. Decide what the database actually is:
   - **Disposable / re-provisionable** (test box, fresh install gone
     wrong): drop and recreate the database, rerun the deploy. The full
     chain applies cleanly. This is the safest path.
   - **Has data you need:** reconcile by hand. For each *partially-applied*
     revision, apply the missing artifacts manually (compare the migration
     file against `\d <table>` in psql) until the schema matches one
     revision boundary exactly. Re-run `--dry-run` until it brackets.
4. Only when the schema provably matches revision X:
   `venv/bin/python -m alembic -c migrations/alembic.ini stamp <X>`
   then `... upgrade head`.
5. If the stamp was wrong, restore from the backup taken in step 1 —
   **never** try to walk back a half-applied chain in place.

## Foreign stamp (exit 4)

`alembic_version` references a revision that does not exist in the current
chain — usually a database last touched by a fork or a pre-repair chain.
The repairs to date (#9759/PR #9988, #8225) changed **zero** revision IDs,
so AutoBot's own history cannot produce this state. If you know which
revision the foreign ID corresponds to, either add the mapping to
`KNOWN_FOREIGN_REVISIONS` in `migrations/baseline.py` (preferred — it is
then tested and shared) or follow the manual re-stamp procedure above.

## Verifying after recovery

```bash
venv/bin/python -m alembic -c migrations/alembic.ini current   # == heads
venv/bin/python -m migrations.baseline --dry-run               # state 2, exit 0
```

The CI **Migration Gate** (`.github/workflows/migration-gate.yml`) runs the
empty / stamped-intermediate / unstamped-adoption / downgrade-roundtrip
matrix on every change to migrations, models or the deploy playbooks.
