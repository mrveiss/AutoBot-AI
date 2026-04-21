# Datetime `utcnow()` Non-Isoformat Audit — Field Assignments + Delta Measurements

> **Status**: Part A of [#5211](https://github.com/mrveiss/AutoBot-AI/issues/5211). Audit only — Part B (migration) and Part C (broader DTZ003 enforcement) follow.
> **Companion audits**:
>   - [datetime parsing audit](datetime-parsing-audit.md) (#5169 part B) — consumer landscape
>   - [datetime producer audit](datetime-producer-audit.md) (#5178 part A) — string-producing sites
> **This audit**: the **complement** — `datetime.utcnow()` calls that are NOT immediately `.isoformat()`-stringified.

## TL;DR

| Pattern | Sites | Files | Migration target | Severity |
|---|---|---|---|---|
| **A — Delta / timing** | ~55 | ~15 | `time.monotonic()` | 🟡 Py 3.12 deprecation; correctness fine today |
| **B — Field assignment** | ~67 | ~30 | `datetime.now(timezone.utc)` | 🔴 Latent bug — naive vs aware mismatch on read |
| **C — Constructor / kwarg** | ~50 | ~15 | `datetime.now(timezone.utc)` | 🔴 Same as B (subtype of B) |
| **D — Predicate / arithmetic** | ~20 | ~12 | `datetime.now(timezone.utc)` | 🟡 Mixed — see breakdown |
| **E — `default_factory=`** | ~56 | ~25 | `lambda: datetime.now(timezone.utc)` or callable | 🔴 Persisted naive into new records |
| **Total** | **248** | **84** | | |

(Counts overlap because some files have multiple patterns. Per-pattern numbers are approximate based on grep heuristics; precise counts come from per-file inspection during migration.)

## Method

```bash
grep -rn "datetime\.utcnow\b\|datetime\.datetime\.utcnow" autobot-backend autobot_shared --include="*.py" \
  | grep -v "_test.py\|__pycache__\|time_utils.py\|workflow_versioning.py" \
  | grep -v "utcnow().isoformat"   # exclude #5178 sites (already migrated)
```

Counts on commit `cf465d027` (Dev_new_gui head at audit time):
- **84 files**, **248 sites** total

## Distribution by subsystem

```
services/             18 files
knowledge/            16
api/                  11
integrations/          8
user_management/       7  ← models — heavy on Pattern B/E (audit-relevant fields)
security/              7
models/                5
utils/                 2
planner/               2
training/              1
skills/                1
routers/               1
rlm/                   1
events/                1
agent_loop/            1
tests/                 2  ← excluded by audit, but listed for completeness
```

## Pattern breakdown

### Pattern A — Delta / timing measurement

Used to measure elapsed time between two points:

```python
start_time = datetime.utcnow()
# ... do work ...
latency = (datetime.utcnow() - start_time).total_seconds() * 1000
```

**~55 sites**, concentrated in:

- `integrations/cloud_integration.py` (~6)
- `integrations/project_management_integration.py` (~6)
- `integrations/github_integration.py` (~3)
- `integrations/communication_integration.py` (~2)
- `integrations/database_integration.py` (~2)
- `services/scheduler/cron_scheduler.py`
- `services/scheduling/cron_scheduler.py`
- `services/captcha_human_loop.py`
- `services/incremental_trainer.py`
- `services/feedback_tracker.py`
- ... others scattered

**Bug profile**: ✅ functionally correct today (naive minus naive is a valid `timedelta`). Py 3.12 deprecates `utcnow()` so this needs migration before that upgrade.

**Migration target**: `time.monotonic()` is the right primitive for elapsed-time measurement — it's immune to wall-clock jumps (NTP corrections, daylight savings) which `datetime.utcnow()` is not. `time.monotonic()` returns a float of seconds; the `.total_seconds()` step disappears:

```python
# before
start_time = datetime.utcnow()
# ...
latency = (datetime.utcnow() - start_time).total_seconds() * 1000
# after
start_time = time.monotonic()
# ...
latency = (time.monotonic() - start_time) * 1000
```

If the start time is also stored / logged as an absolute timestamp (not just used for delta), keep a parallel `datetime.now(timezone.utc)` for that purpose — or use `time.monotonic_ns()` paired with a one-shot wall-clock snapshot at process start.

### Pattern B — Field assignment

Assigning UTC time to an instance attribute:

```python
self.last_used_at = datetime.utcnow()
self.deleted_at = datetime.utcnow()
self.revoked_at = datetime.utcnow()
model.deployed_at = datetime.utcnow()
```

**~67 sites**, concentrated in:

- `user_management/models/{api_key,base,mfa,organization,sso,team,user}.py`
- `routers/model_management.py`
- `services/agent_analytics.py`
- `services/feedback_tracker.py`
- `services/captcha_human_loop.py`
- `services/llm_cost_tracker.py`
- `services/saved_reports_service.py`
- `services/scheduler/cron_scheduler.py`
- ... others

**Bug profile**: 🔴 **latent bug class**. Each stored value is tz-naive. The moment any consumer reads it back and compares with a tz-aware datetime (which the canonicalization in #5178 + #5169 makes increasingly common), `TypeError: can't compare offset-naive and offset-aware datetimes` fires.

**Migration target**: `datetime.now(timezone.utc)` — returns tz-aware. Stored values then round-trip correctly through both `fromisoformat` paths and any `>` / `<` comparisons.

```python
# before
self.last_used_at = datetime.utcnow()
# after
from datetime import datetime, timezone
self.last_used_at = datetime.now(timezone.utc)
```

**SQLAlchemy caveat**: if the attribute is a `Column(DateTime)` (not `DateTime(timezone=True)`), SQLAlchemy will silently strip the tzinfo on insert. In that case the migration is more invasive — either add `timezone=True` to the column AND backfill existing rows, OR keep storing naive but document the constraint clearly. **The Migration B follow-up MUST audit each ORM model's column type before deciding.**

### Pattern C — Constructor / kwarg

Same intent as Pattern B but happens at construction time:

```python
HealthRecord(last_checked=datetime.utcnow())
WorkerHealthInfo(
    worker_id=worker_id,
    timestamp=datetime.utcnow(),
)
```

**~50 sites**. Same bug profile + migration as Pattern B.

### Pattern D — Predicate / arithmetic

Comparison without storing:

```python
if datetime.utcnow() > self.expires_at: ...
cutoff = datetime.utcnow() - timedelta(days=30)
since = datetime.utcnow() - timedelta(hours=time_window_hours)
```

**~20 sites**. **The bug**: the LHS is tz-naive (`datetime.utcnow()`) but `self.expires_at` may have been stored as tz-aware (if migrated to Pattern B's target) or naive (legacy). Mismatch → `TypeError`.

**Migration**: same as Pattern B — replace `datetime.utcnow()` with `datetime.now(timezone.utc)`. The compared field's tz-awareness must match. **Migrate Pattern B first** in a given subsystem to converge tz-aware on stored fields, THEN migrate the predicates that compare against them.

### Pattern E — `default_factory=` (subtype of Pattern B)

Pydantic / dataclasses field default:

```python
@dataclass
class WorkerStatus:
    timestamp: datetime = field(default_factory=datetime.utcnow)
    started_at: datetime = field(default_factory=datetime.utcnow)
```

**~56 sites**, concentrated in:

- `agent_loop/types.py` (~4)
- `events/types.py`
- `planner/types.py`
- `rlm/types.py`
- `gateway/types.py`
- `models/{activities,completion_context,document_version,npu_models,secret}.py`
- `integrations/base.py`
- ... others

**Bug profile**: 🔴 worst — these defaults are persisted to the **first record created from this dataclass**, and every subsequent unread/migrated stored value carries the naive form forever.

**Migration**: `default_factory=lambda: datetime.now(timezone.utc)` (lambda needed — `datetime.now(timezone.utc)` is a CALL with arg; can't pass directly as a factory). Or extract to a module-level helper:

```python
# new helper in autobot_shared/time_utils.py (companion to utc_timestamp())
def now_utc() -> datetime:
    """Return current UTC time as a tz-aware datetime."""
    return datetime.now(timezone.utc)

# usage
@dataclass
class WorkerStatus:
    timestamp: datetime = field(default_factory=now_utc)
```

**Recommendation**: extract `now_utc()` to `autobot_shared.time_utils` so dataclasses can pass it directly without lambda noise. Keeps the migration mechanical (alias-import pattern proven in #5178).

## Recommended Part B sequencing

| Phase | Scope | Pattern | Risk | Why this order |
|---|---|---|---|---|
| **B1** — extract helper | Add `now_utc()` to `autobot_shared/time_utils.py` | foundation | trivial | unblocks dataclass migrations |
| **B2** — Pattern E dataclasses | `agent_loop/types.py`, `events/types.py`, `planner/types.py`, `rlm/types.py`, `gateway/types.py`, `integrations/base.py`, `models/*.py` (~7 files, ~30 sites) | E | low — `field(default_factory=...)` swap, no behavior change inside lifetime of dataclass instance | mechanical, isolates the most leaky producers |
| **B3** — Pattern A timing | `integrations/*.py`, `services/scheduler/*.py`, `services/captcha_*.py`, `services/incremental_trainer.py` (~10 files, ~55 sites) | A | low — `time.monotonic()` swap, semantically equivalent for deltas | unblocks Py 3.12 |
| **B4** — Pattern B/C field+kwarg | `user_management/models/*.py`, `routers/model_management.py`, services (~30 files, ~117 sites) | B + C | **medium** — SQLAlchemy column-type audit needed first (`DateTime` vs `DateTime(timezone=True)`) | most fragile; tz-aware change touches stored data |
| **B5** — Pattern D predicates | scattered (~20 sites) | D | low — must follow B4 in the same subsystem | type-mismatch resolution |
| **B6** — Lint enforcement | enable Ruff `DTZ003` | — | — | now safe to enable globally |

## SQLAlchemy column-type concern (gates B4)

Several Pattern B sites are SQLAlchemy ORM model attributes:

```python
# autobot-backend/user_management/models/team.py:178
deleted_at = Column(DateTime, default=datetime.utcnow, nullable=True)
```

If the column type is plain `DateTime` (not `DateTime(timezone=True)`), assigning a tz-aware datetime → SQLAlchemy strips the tzinfo on insert. Behavior becomes: write produces aware → DB stores naive → read returns naive. The aware-ness gain is lost at the DB boundary.

**Required pre-Phase-B4 work**:
1. Audit every Column / mapped_column with `default=datetime.utcnow` or assigned `datetime.utcnow()` results
2. For each: check if column type is `DateTime(timezone=True)` (PostgreSQL `TIMESTAMP WITH TIME ZONE`)
3. If not, decide: (a) migrate column type + backfill existing rows, OR (b) keep naive at the DB boundary, document the constraint

This is a DATABASE MIGRATION concern, not just a code change. **Do not bulk-migrate Pattern B/C until this is done.**

## Cross-references

- [#5169](https://github.com/mrveiss/AutoBot-AI/issues/5169) — canonicalization decision (`+00:00` for ISO strings)
- [#5178](https://github.com/mrveiss/AutoBot-AI/issues/5178) — `utcnow().isoformat()` migration (parent of this discovery; 49 files / 124 sites already migrated)
- [#5238](https://github.com/mrveiss/AutoBot-AI/issues/5238) — `+ "Z"` mixed-format sites (closed)
- [#5263](https://github.com/mrveiss/AutoBot-AI/issues/5263) — 59 pre-existing `utcnow().isoformat()` sites in slm/infra (separate from this audit's scope)
- [`datetime-parsing-audit.md`](datetime-parsing-audit.md) — consumer landscape (55 unguarded `fromisoformat` parsers — these are the consumers that mis-compare against Pattern B/C/D's naive output)
- [`datetime-producer-audit.md`](datetime-producer-audit.md) — string producers (already migrated by #5178)

## Acceptance criteria covered

- [x] **Part A — Audit doc with full breakdown** ← this document
- [x] Per-pattern classification (A=delta, B/C=field/kwarg, D=predicate, E=default_factory)
- [x] Per-pattern migration target (`time.monotonic` vs `datetime.now(timezone.utc)`)
- [x] Sequencing recommendation with risk per phase
- [x] SQLAlchemy column-type concern surfaced (gates Phase B4)
- [ ] **Part B — Migration** (sub-PRs per phase B1-B5)
- [ ] **Part C — Lint enforcement** (Ruff DTZ003 enabled globally)

## Next steps

- This PR ships Part A only — issue #5211 stays OPEN
- Part B starts with **Phase B1** (extract `now_utc()` helper to `autobot_shared.time_utils`) — trivial unblocker
- **Do NOT start Phase B4** before completing the SQLAlchemy column-type audit
- Part C waits on B6
