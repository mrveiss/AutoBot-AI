# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Is a database migration in the way of rolling back to a commit? (#20214)

A migration is "in the way" when the database has applied a migration the target commit does not
ship. Deploying that commit would run its code against a schema it has never seen, and the deploy's
own ``alembic upgrade`` cannot even resolve a revision it does not have. The answer is a refusal;
no downgrade is ever run, because a downgrade drops data (#17038).

Two databases carry their own record of what has been applied, and both are checked:

* the SLM database: the ``migrations_applied`` table, against the ``MIGRATIONS`` list of
  ``autobot-slm-backend/migrations/runner.py`` at the target commit;
* the backend database: the ``alembic_version`` table, against the ``revision`` ids declared by
  ``autobot-backend/migrations/versions/*.py`` at the target commit.

The target side is read from the git object store with ``git show`` / ``git grep`` (never by
checking the commit out, never by executing its code). A side that cannot be read is reported as
``unknown`` and treated as a refusal: "could not tell" is not "nothing in the way".
"""

from __future__ import annotations

import ast
import asyncio
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from autobot_shared.logging_manager import get_logger
from services.git_subprocess import run_git_capture
from services.rollback_target import is_full_sha

logger = get_logger(__name__)

SLM_RUNNER_PATH = "autobot-slm-backend/migrations/runner.py"
BACKEND_VERSIONS_DIR = "autobot-backend/migrations/versions/"

CLEAR = "clear"
BLOCKED = "blocked"
UNKNOWN = "unknown"

_CONNECT_TIMEOUT_S = 5
_LIBPQ_DRIVER = "postgresql"  # libpq takes a plain scheme; the deployment URL may carry an asyncpg/psycopg driver
_REVISION_LINE = re.compile(r"""(?:^|:)revision\b[^=\n]*=\s*(['"])([^'"\n]+)\1""")

AppliedReader = Callable[[], Awaitable[list[str]]]


@dataclass(frozen=True)
class MigrationCheck:
    """The verdict for one database."""

    database: str
    status: str
    in_the_way: list[str] = field(default_factory=list)
    message: str = ""


def _assigned_list(tree: ast.AST, name: str) -> list[str] | None:
    """The string items of a module-level ``name = [...]``, or None when it is not a plain literal."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == name for t in targets) and isinstance(node.value, ast.List):
            items = [e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            return items if len(items) == len(node.value.elts) else None
    return None


def parse_slm_migrations(source: str) -> list[str] | None:
    """The ``MIGRATIONS`` names declared by a ``runner.py`` source text."""
    try:
        return _assigned_list(ast.parse(source), "MIGRATIONS")
    except SyntaxError:
        return None


def parse_backend_revisions(grep_output: str) -> list[str]:
    """Alembic revision ids from ``git grep`` lines such as ``revision: str = "abc"`` (path prefix optional)."""
    return [m.group(2) for line in grep_output.splitlines() if (m := _REVISION_LINE.search(line))]


async def _target_slm_migrations(repo: str, commit: str) -> list[str] | None:
    stdout, rc = await run_git_capture(repo, "show", f"{commit}:{SLM_RUNNER_PATH}")
    return parse_slm_migrations(stdout) if rc == 0 else None


async def _target_backend_revisions(repo: str, commit: str) -> list[str] | None:
    stdout, rc = await run_git_capture(repo, "grep", "-h", "-E", r"^revision\b", commit, "--", BACKEND_VERSIONS_DIR)
    revisions = parse_backend_revisions(stdout) if rc == 0 else []
    return revisions or None


async def _applied_or_none(reader: AppliedReader) -> tuple[list[str] | None, str]:
    try:
        return await reader(), ""
    except Exception as exc:  # the reason is the exception type only: a driver message can carry a connection string
        logger.warning("rollback: could not read applied migrations (%s)", type(exc).__name__)
        return None, f"the database could not be read ({type(exc).__name__})"


def judge(database: str, applied: list[str] | None, target: list[str] | None, why_unread: str) -> MigrationCheck:
    """Compare what the database applied with what the target commit ships."""
    if target is None:
        return MigrationCheck(database, UNKNOWN, message=f"The {database} migrations at that commit could not be read.")
    if applied is None:
        return MigrationCheck(database, UNKNOWN, message=f"The {database} migration state is unknown: {why_unread}.")
    missing = sorted(set(applied) - set(target))
    if missing:
        return MigrationCheck(
            database,
            BLOCKED,
            missing,
            f"The {database} database has {len(missing)} migration(s) applied that the chosen commit does not "
            "have. Rolling back would run older code against a newer schema, and the updater never runs a "
            "downgrade because that loses data.",
        )
    return MigrationCheck(database, CLEAR, message=f"No {database} migration is in the way.")


async def read_applied_slm() -> list[str]:
    """Names in the SLM database's ``migrations_applied`` table."""
    from migrations import runner

    def _read() -> list[str]:
        conn = runner.get_connection(timeout=_CONNECT_TIMEOUT_S)
        try:
            return runner.get_applied_migrations(conn)
        finally:
            conn.close()

    return await asyncio.to_thread(_read)


async def read_applied_backend() -> list[str]:
    """Rows of the backend database's ``alembic_version`` table."""
    from pathlib import Path

    import psycopg2
    from sqlalchemy.engine import make_url

    from api.code_sync import _load_env_file, _resolve_pg_db_url
    from services.deployed_dir_resolver import get_live_dir

    env_vars = _load_env_file(Path(get_live_dir("autobot-backend")) / ".env")
    url = make_url(_resolve_pg_db_url(env_vars)).set(drivername=_LIBPQ_DRIVER).render_as_string(hide_password=False)

    def _read() -> list[str]:
        conn = psycopg2.connect(url, connect_timeout=_CONNECT_TIMEOUT_S)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT version_num FROM alembic_version")
                return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

    return await asyncio.to_thread(_read)


async def check_migrations(
    repo: str,
    commit: str,
    read_slm: AppliedReader = read_applied_slm,
    read_backend: AppliedReader = read_applied_backend,
) -> list[MigrationCheck]:
    """One verdict per database for rolling back to ``commit`` (a validated full commit id)."""
    if not is_full_sha(commit):
        raise ValueError("check_migrations needs a validated full commit id")
    slm_target, backend_target = await asyncio.gather(
        _target_slm_migrations(repo, commit), _target_backend_revisions(repo, commit)
    )
    (slm_applied, slm_why), (backend_applied, backend_why) = await asyncio.gather(
        _applied_or_none(read_slm), _applied_or_none(read_backend)
    )
    return [
        judge("SLM", slm_applied, slm_target, slm_why),
        judge("backend", backend_applied, backend_target, backend_why),
    ]
