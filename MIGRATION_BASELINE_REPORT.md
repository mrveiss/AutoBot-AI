# Migration Baseline Report — #10001 → #10026

> Session: `issue-10001` branch · 2026-06-12
> Mission: fix the silently-failing Ansible migration invocation (#10001)
> and make it strict (#10026) — **in that order**. The ordering IS the
> mission: making the invocation strict before baseline adoption exists
> strands every schema-without-stamp database at the first unguarded
> `op.create_table`.

## Ordering statement (the point of this whole exercise)

**#10026's strictness landed only after #10001's adoption logic.**
Concretely, by commit order on this branch:

| Phase | Commit | What |
|---|---|---|
| A | `test(migrations): reproduce unstamped-DB stranding` | RED acceptance test + permanent stranding reproduction |
| B | `feat(migrations): baseline adoption` | `python -m migrations.baseline` — flips Phase A green |
| C | `feat(migrations): close the create_all faucet` | runtime create_all guard + static schema-authority sweep |
| D | `fix(ansible): strict backend migration invocation` | `failed_when: false` removed — **only possible because B exists** |
| E | `ci(migrations): migration-gate matrix + recovery runbook` | permanent CI gates + operator doc |

## The defect being fixed (verified, not assumed)

Both Ansible tasks ran `python -m alembic upgrade head` with `chdir` at the
backend root, where **no `alembic.ini` exists** (config lives at
`migrations/alembic.ini`) — a guaranteed *"No config file"* failure — and
both swallowed it with `failed_when: false`
(`setup-user-backend.yml:79`, `update-all-nodes.yml:540`). Native
Postgres-backed deployments therefore never migrated; their schemas came
from historical application `create_all` and carry **no `alembic_version`
stamp**. 32 of 37 table-creating migrations use unguarded
`op.create_table`, so a strict `upgrade head` aborts at migration 001
(`relation "users" already exists`) — reproduced and pinned by
`test_raw_upgrade_on_unstamped_schema_fails`, which stays green forever as
documentation of the mechanism.

## State machine (migrations/baseline.py)

```
                       ┌────────────────────────────┐
        inspect DB ───▶│ alembic_version present?   │
                       └──────┬──────────────┬──────┘
                          yes │              │ no
              ┌───────────────▼───┐      ┌───▼────────────────┐
              │ revisions known?  │      │ any chain-known    │
              └───┬───────────┬───┘      │ tables present?    │
              yes │        no │          └───┬────────────┬───┘
                  ▼           ▼           no │        yes  │
        ┌──────────────┐ ┌─────────────┐     ▼            ▼
        │ 2 STAMPED    │ │ 4 FOREIGN   │ ┌────────┐ ┌──────────────────┐
        │ exit 0, noop │ │ map via     │ │1 EMPTY │ │3 ADOPTION        │
        └──────────────┘ │ compat tbl  │ │exit 0  │ │ a. autogen diff  │
                         │ else exit 4 │ └────────┘ │    empty→stamp   │
                         │ REFUSE      │            │    head          │
                         └─────────────┘            │ b. probe ladder  │
                                                    │    brackets→stamp│
                                                    │ c. ambiguous →   │
                                                    │    exit 3 REFUSE │
                                                    └──────────────────┘
```

Exit codes: `0` proceed to `upgrade head` · `2` operational error ·
`3` adoption refused (ambiguous) · `4` foreign stamp. Refusals write
nothing — the database stays recoverable
(`docs/operations/migration-recovery.md`).

## Probe ladder contents

The ladder is **self-maintaining**: per-revision artifacts are AST-extracted
from the migration files themselves at runtime (`extract_artifacts`), so new
migrations join the ladder automatically. Extraction soundness is enforced
by `test_probe_ladder_selfcheck.py` (literal-only `create_table`, full chain
coverage, observability allowlist).

- **59 revisions** in the chain (`001` → `20260611_054`, branches merged at
  `20260608_052`).
- **Table probes** (37 revisions create tables): e.g. `001` → `users`,
  `organizations`, …(13); `20260315_010` → `process_runs`,
  `task_decompositions`, `agent_sessions`; `20260516_019` → `canvas*`;
  `20260523_022` → `llc_work_items`…
- **Column probes** (add_column revisions): e.g. `20260522_021` →
  `agent_wakeup_requests.merged_count`; `20260523_037` →
  `agent_org_nodes.company_id`; `20260611_054` →
  `llc_work_items.checkout_intent`.
- **Type probes** (curated `TIMESTAMPTZ_MARKERS`): `20260422_018` →
  `process_runs.started_at` / `agent_sessions.expires_at` are
  `timestamp with time zone` (checked only when the table exists).
- **Unobservable (allowlisted, re-run on adoption — all idempotent):**
  `20260525_043` (guarded enum-value add), `20260526_045` (data migration),
  `20260608_052` (merge no-op).

Bracketing: candidate R must have every ancestor applied-looking (or
unobservable) and every non-ancestor absent-looking (or unobservable);
among candidates the **minimal** is stamped, so unobservable revisions
re-run rather than being skipped. Any *partially*-applied revision or
non-monotonic artifact pattern → refusal. A bug class this design caught
during development: helper-function `create_table` calls (migration 010)
were invisible to an upgrade()-scoped scan and bracketed one rung low —
fixed by module-scoped extraction (downgrade() excluded) and pinned by the
self-check.

## Fleet states tested (all against disposable Postgres 16)

| # | State | Expectation | Test |
|---|---|---|---|
| 1 | Empty DB | exit 0; full chain to head | `test_empty_db_proceeds` (matrix a) |
| 2 | Stamped at head | no-op | `test_stamped_at_head_noop` |
| 3 | Stamped at `20260522_021` | no-op; upgrade continues (matrix b, #10026 case 1) | `test_stamped_intermediate_noop` |
| 4 | Head schema, stamp dropped | stamp head | `test_head_schema_unstamped_stamps_head` |
| 5 | `20260315_010`-era schema, no stamp | ladder stamps exactly `20260315_010`; upgrade reaches head | `test_old_schema_bracketed_by_probe_ladder` |
| 6 | `20260522_021`-era schema, no stamp (realistic stranded fleet shape) | adopt → head (matrix c, #10026 case 3) | `test_bootstrap_adopts_unstamped_schema_and_reaches_head` |
| 7 | 021-era schema + one later table | **refuse** exit 3, nothing written | `test_mixed_schema_refuses_loudly` |
| 8 | Current-code UM-only `create_all` (interleaved with LLC revisions) | **refuse** exit 3 | `test_interleaved_create_all_refuses` |
| 9 | Foreign stamp `deadbeef0001` | **refuse** exit 4, stamp untouched | `test_unknown_revision_refuses` |
| 10 | Raw `upgrade head` on unstamped schema | fails `relation already exists` (the stranding) | `test_raw_upgrade_on_unstamped_schema_fails` |
| 11 | head → downgrade −1 → head | round-trips (matrix d) | `test_downgrade_one_and_back_to_head` |
| 12 | `--dry-run` on adoptable schema | decision reported, nothing written | `test_dry_run_writes_nothing` |

27 tests total (12 DB states above + guard unit tests + static sweeps +
Ansible contract). Full suite: **27 passed** locally; the
**Migration Gate** workflow runs the same suite in CI on every
migrations/models/playbook change.

### Red-first evidence per phase

- **A**: acceptance test failed (`No module named migrations.baseline`),
  stranding repro passed — committed in that state.
- **B**: flipped A green; suite additionally caught two real bugs red-first
  (helper-function extraction; cross-metadata FK in autogenerate).
- **C**: 4 guard tests failed before `schema_bootstrap.py` existed; static
  sweep red-proven by scratch-offender injection (trips on offender).
- **D**: all 5 Ansible contract tests failed against the old playbooks,
  green after the rewrite.
- **E**: matrix case (d) (downgrade round-trip) was green on first run —
  the current chain's downgrade is healthy; it is a regression gate, not a
  bug reproduction. Reported honestly rather than staged.

## Ambiguity assessment (the Phase B go/no-go gate)

The mission required stopping after Phase B if the ambiguous case could not
be made rare. Assessment: **the ladder is strong.** 56/59 revisions are
directly observable; bracketing is exact at three tested schema shapes
(010-era, 021-era, head). The refusal cases that remain are *correctly*
ambiguous — schemas that genuinely match no chain point (mixed/interleaved
shapes, e.g. a hypothetical UM-only `create_all` from current code, which no
shipped code path can produce). Real stranded fleet shapes are pre-LLC
(≤ 021) and bracket cleanly. Proceeding to Phase D was justified.

## What was deliberately NOT done (with reasons)

- **`LLCBase.metadata.create_all` on Postgres is broken at head** — enum
  member NAMES vs lowercase value `server_default`s. This is exactly the
  already-filed **#9980**; confirmed empirically while building fixtures.
  Not fixed here (separate issue; adjacent, not blocking — it also means no
  real fleet DB can be LLC-create_all-shaped).
- **`migrations/env.py` does not import `models/process_run.py`**, so
  autogenerate treats `process_runs`/`agent_sessions`/`task_decompositions`
  as stray tables. `baseline.py` imports it for its own comparison; changing
  env.py's autogenerate view would alter revision generation and belongs in
  a dedicated change.
- **SLM backend (`autobot-slm-backend`) `create_all` paths** (`main.py:124`,
  `services/database.py:58`) target the SLM's own databases (`slm`,
  `slm_users`) with its own migration runner — a different system by
  design. Mission scope was the backend ("backend canonical").
- **App-owned SQLite initializers** (skills via guarded lifespan call,
  conversation files, memory manager, knowledge loader) keep `create_all` —
  those are local data files Alembic does not manage. The Phase C guard
  ensures they can never touch a migration-managed dialect.
- **Remote-Postgres backup gap**: the pre-migration backup follows the
  `backup-node-data.yml` pattern (`su - postgres pg_dumpall`), which only
  works when Postgres is local to the backend node. When remote, the deploy
  warns loudly and proceeds. A URL-driven `pg_dump` would close this; left
  as a conscious follow-up.
- **LICENSE/SPDX**: untouched (read-only per mission); new files carry the
  repo's standard headers.

## Files changed

- `autobot-backend/migrations/baseline.py` — adoption entrypoint (new)
- `autobot-backend/migrations/db_url.py` — URL resolution shared with env.py (new)
- `autobot-backend/migrations/schema_bootstrap.py` — create_all guard (new)
- `autobot-backend/migrations/__init__.py`, `env.py` — package marker; env.py now imports from db_url
- `autobot-backend/initialization/lifespan.py` — skills create_all goes through the guard
- `autobot-slm-backend/ansible/setup-user-backend.yml`, `playbooks/update-all-nodes.yml` — strict sequence
- `autobot-backend/tests/migrations/` — 7 test modules, 27 tests
- `.github/workflows/migration-gate.yml` — CI matrix
- `docs/operations/migration-recovery.md` — operator runbook
- `pytest.ini` — `migration_gate` marker
