# Destructive Migrations

A migration that drops a column, table or constraint is the one change this repository cannot undo.
Migrations run during a **rolling** update, while the previous release is still serving requests — so
a column dropped in release N that release N-1 still writes loses data, with nothing to roll back to.

**80 of 90 migrations here are destructive** (`drop_table` 50, `drop_column` 33, `drop_constraint` 7).
This page is the procedure; `tools/lint/check_destructive_migration_marker.py` is the gate.

## The rule

Every migration whose `revision` is at or above **`20260822_082`** and which drops anything must carry
a `NO DATA LOSS:` statement in its module docstring, saying what it touches and why nothing is lost.

The floor is a single revision rather than an allowlist of the 75 migrations that predate the
convention. That is deliberate:

- no entry can outlive its own fix, because there are no entries
- nothing strands when a file is renamed or removed
- it ratchets one way: retrofitting `081` moves the floor to `081` and the guard gets strictly
  stronger, with no list to edit
- a reviewer reads "at or above `082`" and has the whole policy

The 75 below the line are not exempted-and-forgotten; they are *below a stated line*, which is a
weaker and more honest claim.

## Expand / migrate / contract

| Phase | Release | What happens |
|---|---|---|
| **Expand** | N | Add the new column or table. Write **both** old and new. Nothing is dropped. |
| **Migrate** | N | Backfill in bounded chunks (below). Reads may prefer the new value once it is populated. |
| **Contract** | N+1 | Drop the old column, once no deployed release still writes it. |

Contract in the same release as expand and you have not done expand-contract — you have done a drop
with extra steps, and the rolling window is exactly where it breaks.

## Chunked backfill

An unbounded `UPDATE` over a large table holds locks for the length of the update and can exceed the
database's parameter limits; a migration that cannot finish stops a rolling update mid-flight.
Copy `autobot-backend/migrations/templates/chunked_backfill.py`: it walks the table in batches sized
by an env-var-backed module constant, never a literal.

## What the guard checks, and what it deliberately does not

It reads the **`revision` string**, not the filename — alembic treats `revision` as authoritative and
the filename is convention. Two live migrations use letter-suffixed revisions (`036b`, `043b`) that a
filename parser drops silently.

Three conditions, three distinct messages:

1. **No readable `revision`** → fail. An input that cannot be read and reports clean is
   indistinguishable from a clean input.
2. **A `revision` outside `YYYYMMDD_NNN[x]`** → fail, naming the *convention*. Lexical comparison is
   only correct for the dated shape: measured against the floor, a bare `9` sorts **above** it
   (`'9' > '2'`), and alembic's own default hex id sorts either side depending on its first
   character — so a stock `alembic revision` migration would be silently exempted roughly one time in
   eight. A revision the floor cannot order is a different defect from a missing marker.
3. **Destructive at or above the floor without the marker** → fail, naming the marker.

Its reach floor counts migrations **parsed**, not violations found: a scanner whose discovery breaks
finds zero violations and prints the same clean line as a clean tree.

### The cross-source column check

A fourth condition, with its own message: for every `op.drop_column("table", "column")` in
**`upgrade()`**, the guard looks for a model class declaring `__tablename__ = "table"` and a
`Column(...)`/`mapped_column(...)` assignment named `column`. If one exists, the *current* tree still
writes the column being dropped, and the migration is a contract without an expand.

Table and column are tied together through the class rather than by both names appearing in one file
— a bare grep for a column called `name` or `status` matches everywhere, and a guard that cries wolf
is a guard someone silences.

**Two scope limits, stated because an unstated limit reads as coverage:**

- **Literal pairs only.** `op.drop_column(table, column)` is read from the AST, so a call whose table
  or column comes from a variable is invisible to *this* check. The marker still applies to it.
- **`MODEL_ROOTS` only.** The scan covers the four ORM packages, not the whole tree. A model defined
  outside them would not be found — which is why a missing or under-populated root is a **failure**
  rather than an empty result: `MIN_MODEL_FILES` and an explicit existence check mean a renamed
  package cannot turn the check off silently while it keeps reporting success.

The marker itself is required in the **module docstring**, not merely somewhere in the file. `MARKER
in source` was satisfied by the words appearing in a code comment or in a column name — the statement
is meant to be the first thing a reader of the migration sees.

A drop written as raw SQL (`op.execute("ALTER TABLE t DROP COLUMN c")`) counts as destructive too: it
contains none of the `op.drop_*` names, so a name-only scan would wave it through.

**Only `upgrade()` is inspected.** A `downgrade()` dropping a column is reversing an `upgrade()` that
added one, and the model *should* still declare it. Scanning the whole module reported
`20260824_084_device_capability_scoping.py` as a violation for exactly this — all three of its drops
are in `downgrade()`, and `MobileDevice` correctly still declares all three columns.

**Still not checked, and worth knowing:** whether release N-1 writes the column. The check proves the
*current* tree does not; the previous release is a fact about deployed code, not about this
repository, and it is what the `NO DATA LOSS:` sentence exists to make a human state explicitly.
