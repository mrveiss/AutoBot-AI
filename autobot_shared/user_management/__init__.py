# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Canonical user_management core shared by both backends (#12647).

`user_management` is forked across `autobot-backend` and `autobot-slm-backend`,
with 19 shared-but-divergent `.py` source files. This package is the
consolidation target: files land here once their drift is either non-existent
or reconciled, so each move carries no semantic loss.

Movers so far:
- `base_service` (#12972) — byte-identical, no backend-specific imports.
- `schemas.user` (#12647) — identical apart from Pydantic v1/v2 config style;
  no SQLAlchemy dependency, so it does not need the declarative-base decision
  gating the model files.
- `models.base` (#12647) — the declarative base itself, resolving the
  backend/SLM design fork per the owner's 2026-07-31 decision: a new
  canonical base preserving both sides' properties (AsyncAttrs +
  eager_defaults from backend; postgresql.UUID typing from SLM), not an
  adoption of either fork.
- `models.team` / `models.mfa` (#12647) — byte-identical between backends,
  no reconciliation needed.
- `models.role` / `models.sso` / `models.api_key` / `models.audit` (#12647)
  — only cosmetic diffs (unused `Optional` import, `Mapped[Optional[...]]`
  vs `Mapped["... | None"]` style, comment wording, and one redundant
  `from __future__ import annotations`); no schema or behavior changed. See
  each module's docstring for the specific diff it resolved.

- `models.user` / `models.organization` (#12647) — the two files that could
  not move wholesale: backend genuinely carries more than SLM (activity
  relationships #871; LLC/PM-sync columns #8211/#8257/#8241/#4451). Per the
  owner's decision these landed as **abstract cores** (`UserCore`,
  `OrganizationCore`) holding everything both backends share, with each
  backend keeping a thin concrete subclass for its own extras. No column
  changed on either side — see `models/core_test.py`, which pins both
  concrete schemas against their pre-move shape.

Each fork keeps a re-export shim (or, for `user`/`organization`, a concrete
subclass) so existing importers are untouched — the fork is removed, not the
callers.

#12647 (follow-up): the re-exports below are lazy (PEP 562 module
``__getattr__``, mirroring ``autobot_shared/__init__.py``'s own pattern) —
NOT for style, but because eager imports here previously coupled every
submodule of this package together. Merely importing
``autobot_shared.user_management.models.base`` (SQLAlchemy + time_utils only)
forced Python to first execute this package's ``__init__.py`` in full,
which eagerly imported ``schemas.user`` — whose ``EmailStr`` fields need
``email_validator`` at class-definition time. That pulled ``email_validator``
into `import models`'s chain (via the models/base.py shim) for the first
time, breaking ``migration-gate``'s deliberately thin dependency set (the
same defect class as the ``jsonschema`` coupling PR #13053 fixed). Lazy
attribute resolution keeps each submodule's dependency footprint scoped to
callers that actually touch it.
"""

_LAZY_IMPORTS = {
    "BaseService": (".base_service", "BaseService"),
    "TenantContext": (".base_service", "TenantContext"),
    "Base": (".models.base", "Base"),
    "TimestampMixin": (".models.base", "TimestampMixin"),
    "TenantMixin": (".models.base", "TenantMixin"),
    "SoftDeleteMixin": (".models.base", "SoftDeleteMixin"),
    "RoleResponse": (".schemas.user", "RoleResponse"),
    "UserCreate": (".schemas.user", "UserCreate"),
    "UserUpdate": (".schemas.user", "UserUpdate"),
    "UserResponse": (".schemas.user", "UserResponse"),
    "UserListResponse": (".schemas.user", "UserListResponse"),
    "UserLogin": (".schemas.user", "UserLogin"),
    "PasswordChange": (".schemas.user", "PasswordChange"),
}

__all__ = list(_LAZY_IMPORTS)


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        import importlib

        module_path, attr_name = _LAZY_IMPORTS[name]
        mod = importlib.import_module(module_path, __name__)
        val = getattr(mod, attr_name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(_LAZY_IMPORTS))
