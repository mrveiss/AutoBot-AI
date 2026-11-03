# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM owns the first login, so nothing but the two user routers reaches autobot_users (#19406).

``docker-smoke-test.yml`` proves it live on a compose stack. That job runs only for Docker paths,
so this keeps the boundary on every PR: a login or startup path that imports the engine fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

SLM = repo_root() / "autobot-slm-backend"
USERS_DB_ACCESS = re.compile(r"\bget_autobot_(?:db|session|session_maker|engine)\b")
ALLOWED = {"user_management/database.py", "api/autobot_users.py", "api/autobot_teams.py"}


def _is_test(relative: str) -> bool:
    name = relative.rsplit("/", 1)[-1]
    return relative.startswith("tests/") or name.endswith("_test.py") or name.startswith("test_")


def users_db_readers(sources: dict[str, str]) -> set[str]:
    return {path for path, text in sources.items() if USERS_DB_ACCESS.search(text)}


def _source_paths(root: Path) -> list[str]:
    """Non-test SLM python, relative to the repository root as a reach declaration's scope is."""
    base = root / SLM.name
    return sorted(
        path.relative_to(root).as_posix()
        for path in base.rglob("*.py")
        if not _is_test(path.relative_to(base).as_posix())
    )


REACH = declare(
    "slm-users-db-scan",
    discover=_source_paths,
    floor=314,  # mid-window: population 314, window (314, 314)
    what="non-test SLM python source",
    roots=(SLM.name,),
)


def _sources() -> dict[str, str]:
    paths = {path.relative_to(SLM).as_posix(): path for path in SLM.rglob("*.py")}
    return {name: path.read_text(encoding="utf-8") for name, path in paths.items() if not _is_test(name)}


def test_only_the_user_routers_reach_autobot_users() -> None:
    sources = _sources()
    REACH.completed(list(sources))
    assert users_db_readers(sources) == ALLOWED


def test_a_login_path_that_reaches_it_is_caught_and_a_slm_session_is_not() -> None:
    planted = {
        "api/auth.py": "from user_management.database import get_autobot_db\n",
        "api/nodes.py": "from user_management.database import get_slm_db\n",
    }
    assert users_db_readers(planted) == {"api/auth.py"}
