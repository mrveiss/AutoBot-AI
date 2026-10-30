# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""PostgreSQL AUTOBOT_* environment variable registrations (#19320).

Moved out of ``env_registry.py`` (at its size ceiling, #14236) when the defaults
stopped being literals: every default here is read from
``autobot_shared.postgres_identity``, the one home for Postgres database, role
and host values, so the registry cannot disagree with ``ssot_config`` again.

Registration contract (import side effect, ordering): see ``env_registry`` (#16415).
"""

from __future__ import annotations

from autobot_shared import postgres_identity
from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_POSTGRES_DB",
        type=str,
        default=postgres_identity.USERS_DB_NAME,
        description="User-management database name (see postgres_identity).",
        component="postgres",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_POSTGRES_HOST",
        type=str,
        default=postgres_identity.USERS_DB_HOST,
        description="PostgreSQL server hostname or IP.",
        component="postgres",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_POSTGRES_PASSWORD",
        type=str,
        default="",
        description="PostgreSQL user password.",
        component="postgres",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_POSTGRES_PORT",
        type=str,
        default=str(postgres_identity.DB_PORT),
        description="PostgreSQL server port.",
        component="postgres",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_POSTGRES_USER",
        type=str,
        default=postgres_identity.USERS_DB_ROLE,
        description="Login role the AutoBot backend uses on the user-management database.",
        component="postgres",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_USERS_DATABASE_URL",
        type=str,
        default=None,
        description=(
            "Full SQLAlchemy connection URL for the users database. "
            "Overrides AUTOBOT_POSTGRES_* individual vars when set."
        ),
        component="postgres",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_COMPOSE_LEGACY_DB_VARS",
        type=str,
        default="",
        description=(
            "Set by docker-compose.yml only: the deprecated database variable names the operator still sets, "
            "so the SLM can warn about them (#19408). Holds names, never values."
        ),
        component="postgres",
    )
)

register_env_var(
    EnvVarSpec(
        name="SLM_DB_NAME",
        type=str,
        default=postgres_identity.SLM_DB_NAME,
        description="SLM control-plane database name; compose has its own default (see postgres_identity).",
        component="postgres",
    )
)

register_env_var(
    EnvVarSpec(
        name="SLM_POSTGRES_USER",
        type=str,
        default=postgres_identity.SLM_DB_ROLE,
        description="The SLM's login role; on compose a non-default role must already exist (#19408).",
        component="postgres",
    )
)
