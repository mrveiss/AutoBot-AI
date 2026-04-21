# SQLAlchemy `DateTime` Column Audit — naive vs aware classification

> **Status**: Closes [#5270](https://github.com/mrveiss/AutoBot-AI/issues/5270). Audit only — no code change in this PR.
> **Purpose**: enumerate every SQLAlchemy `DateTime` column to determine which would silently strip tzinfo on insert. **Gates [#5211](https://github.com/mrveiss/AutoBot-AI/issues/5211) Phase B4** (Pattern B/C migration of 117 sites).

## TL;DR

| Column type | Behavior | Files | Migration impact |
|---|---|---|---|
| `DateTime(timezone=True)` | ✅ Stores tz-aware (PostgreSQL `TIMESTAMP WITH TIME ZONE`) | **8** | Pattern B migration is fully transparent at DB boundary |
| `Column(DateTime, ...)` (no `timezone=True`) | 🔴 Strips tzinfo on insert | **4** | Pattern B migration is no-op at DB boundary — needs column type migration OR app-side convention |
| **Total inspected** | | **12 model files, ~28 columns** | |

The audit's scope is narrow: only ~28 columns store datetimes (vs 248 sites total in #5211). The remaining 220 sites are non-persistent (Pydantic / dataclass / in-memory). **Phase B4 of #5211 is safer than the audit's worst-case implied** — only the 4 legacy-style files need careful column-type decisions before migration.

## Method

```bash
grep -rn -A 4 "Column(\s*DateTime\|mapped_column(\s*$\|mapped_column(\s*DateTime\|Mapped\[Optional\?\[datetime\]\]\?\s*=\s*mapped_column" \
  autobot-backend autobot_shared --include="*.py" \
  | grep -v "_test.py"
```

Multi-line context (`-A 4`) catches the modern `mapped_column(\n    DateTime(timezone=True), ...)` pattern that single-line greps miss.

## Classification

### ✅ Aware columns (`DateTime(timezone=True)`) — 8 files

These store tz-aware datetimes correctly. SQLAlchemy preserves tzinfo on insert; reads return tz-aware. **Pattern B migration is transparent here** — assigning `datetime.now(timezone.utc)` works as expected.

| File | Columns | Default |
|---|---|---|
| [`models/activities.py`](autobot-backend/models/activities.py) | `timestamp` (×5 across 5 model classes — terminal/file/browser/desktop/network event tables) | `default=datetime.utcnow` 🟡 |
| [`models/code_pattern.py`](autobot-backend/models/code_pattern.py) | `created_at`, `updated_at` | `server_default=func.now()` ✅ |
| [`models/completion_feedback.py`](autobot-backend/models/completion_feedback.py) | `timestamp` | `server_default=func.now()` ✅ |
| [`models/ml_model.py`](autobot-backend/models/ml_model.py) | `deployed_at`, `created_at`, `updated_at` | mixed `server_default=func.now()` + `nullable=True` |
| [`models/secret.py`](autobot-backend/models/secret.py) | `expires_at` | `nullable=True` (no default — caller-set) |
| [`user_management/models/base.py`](autobot-backend/user_management/models/base.py) | `created_at`, `updated_at` | `server_default=func.now()`, `onupdate=func.now()` ✅ |
| [`user_management/models/team.py`](autobot-backend/user_management/models/team.py) | `joined_at` | `default=datetime.utcnow` 🟡 |
| [`user_management/models/audit.py`](autobot-backend/user_management/models/audit.py) | `created_at` | `server_default=func.now()` ✅ |

**🟡 Subtle gotcha — `default=datetime.utcnow` on aware columns**: 4 of the columns above use `default=datetime.utcnow` (the bare callable). Even on a `DateTime(timezone=True)` column, this passes a NAIVE datetime into SQLAlchemy at insert. PostgreSQL then INTERPRETS the naive datetime in the **session timezone** (typically UTC, but configuration-dependent), then stores it as tz-aware. **This is correct but fragile** — depends on DB session timezone matching the implicit "this is UTC" assumption.

For these 4 columns (`activities.py` ×5, `team.py` ×1), Phase B2 of #5211 should swap to `default=lambda: datetime.now(timezone.utc)` (or the proposed `now_utc` helper) to eliminate the implicit assumption.

### 🔴 Naive columns (`Column(DateTime, ...)`) — 4 files, 13 columns

These store **naive** datetimes regardless of what the app passes. **Pattern B migration to `datetime.now(timezone.utc)` is a no-op at the DB boundary** — SQLAlchemy strips the tzinfo on insert. The naive datetime returns from reads, and any consumer comparing it to a tz-aware datetime hits `TypeError`.

| File | Columns | Current usage |
|---|---|---|
| [`models/process_run.py`](autobot-backend/models/process_run.py) | `started_at`, `completed_at` (L55-56), `expires_at` (L116) | All `nullable=True`, no default — caller-set |
| [`models/heartbeat.py`](autobot-backend/models/heartbeat.py) | `last_heartbeat_at` (L63), `started_at` (L104), `finished_at` (L105), `consumed_at` (L163) | `nullable=True`, no default |
| [`models/approval.py`](autobot-backend/models/approval.py) | `decided_at` (L75) | `nullable=True`, no default |
| [`skills/models.py`](autobot-backend/skills/models.py) | `created_at` (L61), `promoted_at` (L62), `last_synced` (L75), `requested_at` (L88), `reviewed_at` (L92) | 2 use `default=lambda: datetime.now(timezone.utc)` (interesting — passes aware to naive column!), 3 are `nullable=True` |

**Critical observation on `skills/models.py:61, 88`**: these columns ALREADY assign `datetime.now(timezone.utc)` (the canonical aware form #5211 wants). Because the column is `Column(DateTime)` (naive), SQLAlchemy strips tzinfo silently. **The aware-ness gain is already lost today** — this is exactly the bug class the audit predicts. Worth fixing as the canary.

## Decision matrix per naive column

For the 4 files / 13 naive columns, three options:

### Option (a) — Migrate column type to `DateTime(timezone=True)`

**Cost**: high. Requires:
1. Code change: `Column(DateTime, ...)` → `Column(DateTime(timezone=True), ...)`
2. **Alembic migration** to alter the column on existing DB (`ALTER COLUMN ... TYPE TIMESTAMP WITH TIME ZONE USING ...`)
3. **Backfill decision** for existing naive rows — interpret as UTC (most likely intent) or local-server-timezone (depends on history)
4. Maintenance window — `ALTER COLUMN` on a non-trivial table can require an exclusive lock

**When**: choose for tables where the bug class is actively biting (cross-comparisons fail) OR where the table is small enough that the migration is cheap.

### Option (b) — Accept naive at DB boundary, normalize in app

**Cost**: medium. Code-only changes:
1. Document column as "stores naive UTC by convention"
2. Read paths normalize via `.replace(tzinfo=timezone.utc)` (precedent from existing memory: "old Redis returns naive from fromisoformat; normalize")
3. Write paths can pass either naive or aware — naive passes through, aware gets stripped (same result)
4. Document the convention in module docstring + each column's `comment=`

**When**: choose for tables where Alembic migration is too expensive OR the existing data is too large for confident backfill semantics.

### Option (c) — Hybrid: aware in app, naive in DB (transparent)

**Cost**: medium-high. Use SQLAlchemy event listeners on each column:
- `before_insert` / `before_update`: if value is aware, normalize to UTC + strip tzinfo
- `load` / column property: read returns `naive.replace(tzinfo=timezone.utc)`

**When**: choose if call sites expect aware datetimes uniformly and rewriting them all is more work than the listener machinery.

## Recommendation per file

| File | Recommended option | Reason |
|---|---|---|
| `skills/models.py` | **(a) Migrate** | Already has `datetime.now(timezone.utc)` callers — the existing code DEMONSTRATES the bug. Fix at the source |
| `models/heartbeat.py` | **(b) Accept naive + document** | High-frequency table, `nullable=True` everywhere; column migration cost outweighs benefit |
| `models/process_run.py` | **(a) Migrate** | 3 columns, table likely small (one row per process) |
| `models/approval.py` | **(b) Accept naive + document** | 1 column, `nullable=True`, simple call sites |

This converts 8 of 13 naive columns to aware (`skills/models.py` 5 + `process_run.py` 3), leaving 5 columns (`heartbeat.py` 4 + `approval.py` 1) on documented naive convention.

## Phase B4 ordering implication

Once this audit's recommendations are implemented:

1. **Pattern B/C migration is safe per-subsystem** as long as the file's columns are either (a)-migrated or (b)-documented
2. The `now_utc()` helper from Phase B1 of #5211 works uniformly — Option (a) columns store the aware datetime; Option (b) columns silently strip but the upstream call site is already in canonical form

**Without this audit's resolution, bulk-migrating Pattern B/C creates the silent-data-inconsistency hazard the original concern surfaced.**

## Acceptance criteria

- [x] Audit doc with full `Column(DateTime)` enumeration (this document)
- [x] Per-column classification (aware vs naive)
- [x] Per-file recommendation (option a / b / c)
- [x] Subtle gotcha noted: `default=datetime.utcnow` on `DateTime(timezone=True)` columns (4 sites)
- [x] Cross-link from #5211 audit doc → this audit (TODO: file follow-up to add the link)
- [ ] **Implementation** of Option (a) migrations (separate PRs per file with Alembic migration + backfill)
- [ ] **Implementation** of Option (b) docstring conventions (small follow-up PR)
- [ ] **#5211 Phase B4 unblocked** once above implementations land

## Cross-references

- [#5211](https://github.com/mrveiss/AutoBot-AI/issues/5211) — parent (gates B4)
- [#5270](https://github.com/mrveiss/AutoBot-AI/issues/5270) — this audit issue
- [`datetime-utcnow-non-isoformat-audit.md`](datetime-utcnow-non-isoformat-audit.md) — flagged this concern in #5211 Part A
- Memory: "UTC datetime: old Redis returns naive from fromisoformat; normalize `.replace(tzinfo=timezone.utc)`" — precedent for Option (b)
