# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export shim — the implementation now lives in autobot_shared (#12647).

``models/base.py`` was the file gating the whole ``models/*`` de-fork: the
backend and SLM declarative bases had genuinely different, deliberate
designs (backend: timestamps baked into ``Base``, ``eager_defaults``,
``AsyncAttrs``, generic ``Uuid``; SLM: opt-in ``TimestampMixin``,
``postgresql.UUID``). The owner's 2026-07-31 decision on #12645/#12647 was to
design a *new* canonical base preserving both sides' properties rather than
adopt either fork — see ``autobot_shared/user_management/models/base.py`` for
the property-by-property rationale. Kept as a shim, not deleted, so every
existing ``from user_management.models.base import ...`` importer keeps
working unchanged.

Note: timestamps are now baked into ``Base`` (matching backend's prior
design) rather than opt-in via ``TimestampMixin``. SLM model classes that
still spell out ``(Base, TimestampMixin)`` keep working unchanged —
``TimestampMixin`` is a no-op alias, so combining it with ``Base`` maps the
same columns once, not twice. The two SLM models that never opted into
``TimestampMixin`` (``RolePermission``, ``AuditLog``) now expect
``updated_at`` (and, for ``RolePermission``, ``created_at``) — see the
accompanying migration.
"""

from autobot_shared.user_management.models.base import (  # noqa: F401
    Base,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)

__all__ = ["Base", "TimestampMixin", "TenantMixin", "SoftDeleteMixin"]
