# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Baseline adoption for never-migrated databases (#10001, #10026 case 3).

Run BEFORE ``alembic upgrade head``::

    python -m migrations.baseline [--dry-run]

Historical deployments built their schema via ``metadata.create_all`` while
the Ansible alembic invocation silently failed, leaving tables with no
``alembic_version`` stamp. Running the (now strict) migration chain against
such a database aborts at the first unguarded ``op.create_table``. This
entrypoint classifies the database into four states and, for adoptable
schemas, stamps the revision the schema already corresponds to:

1. EMPTY            — no known tables: exit 0, upgrade runs the full chain.
2. STAMPED          — alembic_version holds known revision(s): exit 0, no-op.
3. SCHEMA_NO_STAMP  — tables exist, no stamp (adoption):
                      a. autogenerate diff vs head models empty → stamp head;
                      b. else probe-ladder bracketing over per-revision
                         structural artifacts (created tables, added columns,
                         TIMESTAMPTZ conversions) → stamp the bracketed
                         revision; the subsequent ``upgrade head`` applies
                         the remainder;
                      c. bracketing ambiguous → exit 3 and REFUSE. A refused
                         adoption is recoverable; a wrong stamp silently
                         corrupts every future migration.
4. STAMPED_UNKNOWN  — alembic_version holds a revision not in the chain:
                      mapped via KNOWN_FOREIGN_REVISIONS when possible,
                      otherwise exit 4 and refuse.

Exit codes: 0 proceed with upgrade · 2 operational error · 3 adoption
refused (ambiguous bracketing) · 4 unknown foreign revision. On 3/4 see
docs/operations/migration-recovery.md.
"""

import ast
import asyncio
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from migrations.db_url import as_async_url, get_url

logger = logging.getLogger("migrations.baseline")

EXIT_OK = 0
EXIT_ERROR = 2
EXIT_AMBIGUOUS = 3
EXIT_FOREIGN = 4

RECOVERY_DOC = "docs/operations/migration-recovery.md"

MIGRATIONS_DIR = Path(__file__).resolve().parent

# Revisions from superseded chains mapped to their equivalent in the current
# chain. The #9759 chain repair (PR #9988) changed ZERO revision IDs and the
# #8225 rename kept its ID, so this is empty today; it exists so any future
# chain repair has a designated place to record stamp translations.
KNOWN_FOREIGN_REVISIONS: dict[str, str] = {}

# Structural markers for revisions whose only effect is a column TYPE change
# and which are therefore invisible to the created-tables/added-columns
# probes. Checked only when the table exists: True ⇔ TIMESTAMPTZ.
TIMESTAMPTZ_MARKERS: dict[str, tuple[tuple[str, str], ...]] = {
    "20260422_018": (
        ("process_runs", "started_at"),
        ("agent_sessions", "expires_at"),
    ),
}

# applied_status() result for a revision whose artifacts are partially
# present — schema stopped mid-revision; bracketing must refuse.
PARTIAL = "partial"


@dataclass(frozen=True)
class Artifacts:
    """Observable schema artifacts a revision's upgrade() introduces."""

    tables: tuple[str, ...] = ()
    columns: tuple[tuple[str, str], ...] = ()


@dataclass
class DbFacts:
    """Schema facts gathered from one inspection pass."""

    tables: set[str] = field(default_factory=set)
    columns: set[tuple[str, str]] = field(default_factory=set)
    column_types: dict[tuple[str, str], str] = field(default_factory=dict)
    version_rows: list[str] = field(default_factory=list)


def _script_directory():
    """Load the Alembic ScriptDirectory for this migrations package."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(MIGRATIONS_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("version_locations", str(MIGRATIONS_DIR / "versions"))
    return ScriptDirectory.from_config(cfg)


def iter_upgrade_nodes(tree: ast.Module):
    """Yield every AST node of a migration module except downgrade() bodies.

    Migrations frequently split their upgrade into helper functions (e.g.
    20260315_010), so scanning only ``upgrade()`` misses artifacts; scanning
    ``downgrade()`` would poison the ladder with revert operations.
    """
    for top in tree.body:
        if isinstance(top, ast.FunctionDef) and top.name == "downgrade":
            continue
        yield from ast.walk(top)


def extract_artifacts(script) -> dict[str, Artifacts]:
    """AST-extract created tables / added columns per revision.

    Every ``op.create_table``/``op.add_column`` in this chain passes the
    table name as a string literal (enforced by the ladder self-check test),
    so static extraction is exact and self-maintaining — new migrations are
    picked up automatically.
    """
    result: dict[str, Artifacts] = {}
    for sc in script.walk_revisions():
        tree = ast.parse(Path(sc.path).read_text(encoding="utf-8"))
        tables: list[str] = []
        columns: list[tuple[str, str]] = []
        for node in iter_upgrade_nodes(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr == "create_table" and node.args and isinstance(node.args[0], ast.Constant):
                tables.append(node.args[0].value)
            elif node.func.attr == "add_column" and node.args and isinstance(node.args[0], ast.Constant):
                col = node.args[1] if len(node.args) > 1 else None
                if isinstance(col, ast.Call) and col.args and isinstance(col.args[0], ast.Constant):
                    columns.append((node.args[0].value, col.args[0].value))
        result[sc.revision] = Artifacts(tables=tuple(tables), columns=tuple(columns))
    return result


async def inspect_database(url: str) -> DbFacts:
    """Collect tables, columns, column types and stamp rows in one pass."""
    facts = DbFacts()
    engine = create_async_engine(as_async_url(url))
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT table_name, column_name, data_type "
                    "FROM information_schema.columns WHERE table_schema = 'public'"
                )
            )
            for table, column, data_type in rows:
                facts.tables.add(table)
                facts.columns.add((table, column))
                facts.column_types[(table, column)] = data_type
            if "alembic_version" in facts.tables:
                stamped = await conn.execute(text("SELECT version_num FROM alembic_version"))
                facts.version_rows = [r[0] for r in stamped]
    finally:
        await engine.dispose()
    return facts


def applied_status(rev: str, artifacts: dict[str, Artifacts], facts: DbFacts):
    """Judge one revision against the live schema.

    Returns True (all artifacts present), False (none present), None
    (unobservable — no artifacts), or PARTIAL (mixed — refuse adoption).
    """
    art = artifacts.get(rev, Artifacts())
    checks: list[bool] = []
    checks.extend(t in facts.tables for t in art.tables)
    checks.extend(c in facts.columns for c in art.columns)
    for table, column in TIMESTAMPTZ_MARKERS.get(rev, ()):
        if table in facts.tables:
            checks.append(facts.column_types.get((table, column)) == "timestamp with time zone")
    if not checks:
        return None
    if all(checks):
        return True
    if not any(checks):
        return False
    return PARTIAL


def _ancestors(script, rev: str) -> set[str]:
    """All revisions in rev's lineage, rev inclusive."""
    return {sc.revision for sc in script.iterate_revisions(rev, "base")}


def find_candidate(script, statuses: dict[str, object]) -> str | None:
    """Bracket the schema between applied-looking and absent revisions.

    A candidate R must have every ancestor looking applied (or unobservable)
    and every non-ancestor looking absent (or unobservable). Among multiple
    candidates the MINIMAL one is chosen — unobservable revisions between the
    bracket bounds re-run rather than being skipped. Any partial revision or
    incomparable candidate set means the schema matches no point in the
    chain: refuse (#10001 rule 3d).
    """
    if any(s == PARTIAL for s in statuses.values()):
        return None
    all_revs = set(statuses)
    ancestors = {rev: _ancestors(script, rev) for rev in all_revs}
    candidates = [
        rev
        for rev in all_revs
        if all(statuses[a] is not False for a in ancestors[rev])
        and all(statuses[n] is not True for n in all_revs - ancestors[rev])
    ]
    if not candidates:
        return None
    minimal = [c for c in candidates if all(c in ancestors[o] for o in candidates)]
    if len(minimal) != 1:
        return None
    return minimal[0]


def autogenerate_diff_empty(url: str) -> bool:
    """Fast path 3a: does the schema already match the head models exactly?

    Foreign tables (operator extensions) are ignored; any other drift falls
    through to the probe ladder. Import or comparison failures are treated
    as drift, never as a match.
    """
    try:
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext
        from sqlalchemy import MetaData

        import canvas.models  # noqa: F401 — registers canvas tables on Base
        import models.process_run  # noqa: F401 — registers process_runs et al.
        import user_management.models  # noqa: F401 — registers all UM models
        from llc.models.activity import LLCBase
        from models.push_subscription import PushSubscription  # noqa: F401
        from user_management.models.base import Base

        # Merge both declarative metadatas into one so cross-metadata foreign
        # keys (LLC tables referencing organizations) resolve during compare.
        combined = MetaData()
        for md in (Base.metadata, LLCBase.metadata):
            for table in md.tables.values():
                table.to_metadata(combined)
        known_tables = set(combined.tables)

        async def _diff() -> list:
            engine = create_async_engine(as_async_url(url))
            try:
                async with engine.connect() as conn:

                    def _compare(sync_conn):
                        ctx = MigrationContext.configure(sync_conn)
                        return compare_metadata(ctx, combined)

                    return await conn.run_sync(_compare)
            finally:
                await engine.dispose()

        diffs = asyncio.run(_diff())

        def _is_foreign_removal(diff) -> bool:
            if diff[0] == "remove_table":
                return diff[1].name not in known_tables
            if diff[0] in ("remove_index", "remove_table_comment"):
                table = getattr(diff[1], "table", None)
                return table is not None and table.name not in known_tables
            return False

        relevant = [d for d in diffs if not _is_foreign_removal(d)]
        if relevant:
            logger.info("Schema differs from head models (%d diffs) — using probe ladder", len(relevant))
        return not relevant
    except Exception as exc:  # any failure here must fall back to the ladder
        logger.warning("Autogenerate comparison unavailable (%s) — using probe ladder", exc)
        return False


async def stamp_revision(url: str, revision: str) -> None:
    """Write the adoption stamp exactly the way ``alembic stamp`` would."""
    engine = create_async_engine(as_async_url(url))
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version ("
                    "version_num VARCHAR(32) NOT NULL, "
                    "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
                )
            )
            await conn.execute(text("DELETE FROM alembic_version"))
            await conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:rev)"),
                {"rev": revision},
            )
    finally:
        await engine.dispose()


def _refuse(code: int, message: str) -> int:
    logger.error("REFUSING to guess: %s", message)
    logger.error("Manual recovery procedure: %s", RECOVERY_DOC)
    logger.error("No stamp was written; the database is unchanged and recoverable.")
    return code


def _handle_stamped(script, facts: DbFacts, url: str, dry_run: bool) -> int:
    """States 2 and 4: alembic_version exists."""
    known = {sc.revision for sc in script.walk_revisions()}
    unknown = [r for r in facts.version_rows if r not in known]
    if not unknown:
        logger.info("STAMPED at %s — normal upgrade applies.", facts.version_rows)
        return EXIT_OK
    if len(facts.version_rows) == 1 and unknown[0] in KNOWN_FOREIGN_REVISIONS:
        new = KNOWN_FOREIGN_REVISIONS[unknown[0]]
        logger.info("Mapping foreign stamp %s -> %s (compatibility table)", unknown[0], new)
        if not dry_run:
            asyncio.run(stamp_revision(url, new))
        return EXIT_OK
    return _refuse(
        EXIT_FOREIGN,
        f"alembic_version contains revision(s) {unknown} not present in the "
        "current migration chain and not in the compatibility table "
        "(KNOWN_FOREIGN_REVISIONS).",
    )


def _adopt(script, facts: DbFacts, url: str, dry_run: bool) -> int:
    """State 3: tables without a stamp — adopt or refuse."""
    artifacts = extract_artifacts(script)
    known_artifact_tables = {t for a in artifacts.values() for t in a.tables}
    if not facts.tables & known_artifact_tables:
        logger.info("EMPTY (no chain-known tables) — upgrade runs the full chain.")
        return EXIT_OK

    logger.info("SCHEMA WITHOUT STAMP detected — attempting baseline adoption (#10001).")
    head = script.get_heads()
    if len(head) != 1:
        return _refuse(EXIT_ERROR, f"migration chain has {len(head)} heads: {head}")

    if autogenerate_diff_empty(url):
        logger.info("Schema matches head models exactly — stamping head %s.", head[0])
        if not dry_run:
            asyncio.run(stamp_revision(url, head[0]))
        return EXIT_OK

    statuses = {rev: applied_status(rev, artifacts, facts) for rev in artifacts}
    candidate = find_candidate(script, statuses)
    if candidate is None:
        partial = sorted(r for r, s in statuses.items() if s == PARTIAL)
        present = sorted(r for r, s in statuses.items() if s is True)
        absent = sorted(r for r, s in statuses.items() if s is False)
        return _refuse(
            EXIT_AMBIGUOUS,
            "probe ladder cannot bracket this schema to a single revision.\n"
            f"  partially-applied revisions: {partial or 'none'}\n"
            f"  applied-looking revisions:   {present}\n"
            f"  absent-looking revisions:    {absent}",
        )

    logger.info("Probe ladder bracketed schema at revision %s — stamping.", candidate)
    if not dry_run:
        asyncio.run(stamp_revision(url, candidate))
    logger.info("Stamped %s; 'alembic upgrade head' will apply the remainder.", candidate)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Classify the database and stamp an adoption baseline when safe."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)-5.5s [%(name)s] %(message)s")
    args = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in args
    try:
        url = get_url()
        script = _script_directory()
        facts = asyncio.run(inspect_database(url))
    except Exception as exc:
        logger.error("Baseline inspection failed: %s", exc)
        return EXIT_ERROR

    if facts.version_rows:
        return _handle_stamped(script, facts, url, dry_run)
    if not facts.tables:
        logger.info("EMPTY database — upgrade runs the full chain.")
        return EXIT_OK
    return _adopt(script, facts, url, dry_run)


if __name__ == "__main__":
    sys.exit(main())
