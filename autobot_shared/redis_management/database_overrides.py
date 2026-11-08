# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``AUTOBOT_REDIS_DB_<NAME>`` overrides, applied to the ONE database table (#19232).

``redis-databases.yaml`` declares every database name and its default number. These
environment variables are the documented operator interface for moving one of them
(``.env.example``: "override individual DB numbers here only if your deployment
differs"), so they feed that table instead of a parallel one. Before #19232 they fed
``ssot_config.RedisConfig.db_*`` only: ``AUTOBOT_REDIS_DB_KNOWLEDGE=9`` moved the
backend config readers and left the canonical client on DB 1.

The variable name is derived from the database name, so a database added to the YAML
is overridable without touching this module. ``AUTOBOT_REDIS_DB_TASKS`` is the one
legacy spelling: ``RedisConfig.db_tasks`` read it for the ``workflows`` database.

An override that lands two declared databases on one number, or is not a number, is
refused: that database keeps its YAML number and the refusal is logged at WARNING. Two
features in one keyspace would look exactly like success. ``validate-env-files.py``
reports the same refusals before deployment (``override_problems``).
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Mapping

logger = logging.getLogger(__name__)

ENV_PREFIX = "AUTOBOT_REDIS_DB_"
#: Legacy variable -> the database it has always meant.
LEGACY_ENV_NAMES: Dict[str, str] = {"AUTOBOT_REDIS_DB_TASKS": "workflows"}

__all__ = [
    "ENV_PREFIX",
    "LEGACY_ENV_NAMES",
    "apply_overrides",
    "env_var_name",
    "override_problems",
    "override_source",
]


def env_var_name(database: str) -> str:
    """The override variable for *database*: ``knowledge`` -> ``AUTOBOT_REDIS_DB_KNOWLEDGE``."""
    return f"{ENV_PREFIX}{database.upper()}"


def _env_file_values() -> Dict[str, str]:
    """The project-root ``.env`` (the file ``ssot_config`` reads), via the stdlib-only reader.

    Not python-dotenv: the SLM agent imports this module and its venv does not ship it (#14278).
    """
    from autobot_shared.env_file import parse_env_file
    from autobot_shared.paths import ProjectRootUndeterminable, project_root

    try:
        env_file = project_root() / ".env"
    except ProjectRootUndeterminable:
        return {}
    return parse_env_file(env_file) if env_file.is_file() else {}


def override_source() -> Dict[str, str]:
    """``.env`` values overlaid by the process environment (the process wins, as in pydantic-settings)."""
    return {**_env_file_values(), **os.environ}


def _set(source: Mapping[str, str], var: str) -> bool:
    """Whether *source* sets *var* to a non-blank value; a blank one (``VAR=``) is no request."""
    return bool((source.get(var) or "").strip())


def _requested(base: Mapping[str, int], source: Mapping[str, str]) -> Dict[str, str]:
    """``{database: raw value}`` for every non-blank override *source* sets on a database *base* declares."""
    requested = {name: source[env_var_name(name)] for name in base if _set(source, env_var_name(name))}
    for legacy, name in LEGACY_ENV_NAMES.items():
        if _set(source, legacy) and name in base and name not in requested:
            requested[name] = source[legacy]
    return requested


#: Highest index a Redis server has by default (``databases 16``), the range the env
#: registry documents for AUTOBOT_REDIS_DB_* (0-15). Shell (ssot-config.sh) and the
#: standalone Ansible inventory apply the same bound -- one contract, pinned by a test.
MAX_DATABASE_INDEX = 15


def _parse(raw: str) -> int | None:
    """A database number from an override value: ASCII digits after trimming, 0..MAX_DATABASE_INDEX.

    ``int()`` alone would also take ``+5``, ``1_0`` and non-ASCII digits, which the shell
    reader cannot; the contract is the intersection, spelled out.
    """
    text = raw.strip()
    if not text.isascii() or not text.isdigit():
        return None
    number = int(text)
    return number if number <= MAX_DATABASE_INDEX else None


def _parsed(base: Mapping[str, int], source: Mapping[str, str]) -> tuple[Dict[str, int], list[str]]:
    """``{database: number}`` for every valid override, and a line for each invalid one."""
    accepted: Dict[str, int] = {}
    problems: list[str] = []
    for name, raw in _requested(base, source).items():
        number = _parse(raw)
        if number is None:
            problems.append(f"{env_var_name(name)}={raw!r} is not a Redis database number (0-{MAX_DATABASE_INDEX})")
        else:
            accepted[name] = number
    return accepted, problems


def _colliding(mapping: Mapping[str, int]) -> Dict[int, list[str]]:
    """``{number: [names]}`` for every number more than one database resolves to."""
    by_number: Dict[int, list[str]] = {}
    for name, number in mapping.items():
        by_number.setdefault(number, []).append(name)
    return {number: sorted(names) for number, names in by_number.items() if len(names) > 1}


def _without_collisions(base: Mapping[str, int], accepted: Dict[str, int]) -> list[str]:
    """Drop (in place) every override that shares a number with another database; one line each."""
    problems: list[str] = []
    while True:
        clashes = _colliding({**base, **accepted})
        rejected = sorted({name for names in clashes.values() for name in names if name in accepted})
        if not rejected:
            return problems
        for name in rejected:
            others = [n for n in clashes[accepted[name]] if n != name]
            problems.append(f"{env_var_name(name)}={accepted.pop(name)} collides with {', '.join(others)}")


def _resolve(base: Mapping[str, int], source: Mapping[str, str]) -> tuple[Dict[str, int], list[str]]:
    """*base* with every acceptable override applied, and why each other one was refused."""
    accepted, problems = _parsed(base, source)
    problems += _without_collisions(base, accepted)
    return {**base, **accepted}, problems


def override_problems(base: Mapping[str, int], source: Mapping[str, str]) -> list[str]:
    """Every ``AUTOBOT_REDIS_DB_*`` override in *source* the runtime refuses, one line each."""
    return _resolve(base, source)[1]


def apply_overrides(base: Mapping[str, int], source: Mapping[str, str]) -> Dict[str, int]:
    """*base* with the ``AUTOBOT_REDIS_DB_*`` overrides in *source* applied.

    A refused override keeps its database on the YAML number and is logged once, at
    WARNING -- refused rather than raised, because a stale ``AUTOBOT_REDIS_DB_LOGS=5`` from
    an old installer was harmless while nothing read it, and must not take a host down now
    or flood its log at ERROR. This runs once per process, when the table is built.
    """
    merged, problems = _resolve(base, source)
    for problem in problems:
        logger.warning("Refused Redis database override (keeping redis-databases.yaml): %s", problem)
    for name, number in merged.items():
        if number != base[name]:
            logger.info("Redis database %r moved to DB %d by %s", name, number, env_var_name(name))
    return merged
