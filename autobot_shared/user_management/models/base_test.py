# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The shared declarative base is the single implementation (#12647).

``models/base.py`` was the file gating the whole ``user_management``
``models/*`` de-fork: backend and SLM had genuinely different declarative
bases. The owner's 2026-07-31 decision was a *new* canonical base, not an
adoption of either fork — see ``base.py`` for the property-by-property
rationale.

These pin the property that matters — both backends resolve to the SAME
class objects, not merely equivalent ones. Two same-named classes are not
interchangeable (the trap #12913 fixed for CircuitState), so identity is the
assertion, not behaviour.
"""

import importlib.util
import pathlib
import sys

import pytest

from autobot_shared.user_management.models.base import (
    Base,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)

# parents: [0] models, [1] user_management, [2] autobot_shared, [3] repo root.
# This said parents[2] until #12647's core extraction ran the file — every
# shim assertion below silently resolved to a path under autobot_shared/ that
# does not exist, so they failed on sight rather than testing anything.
_ROOT = pathlib.Path(__file__).resolve().parents[3]
_SHIMS = {
    "backend": _ROOT / "autobot-backend/user_management/models/base.py",
    "slm": _ROOT / "autobot-slm-backend/user_management/models/base.py",
}


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("backend", sorted(_SHIMS))
def test_shim_exists(backend):
    assert _SHIMS[backend].is_file(), f"{backend} shim missing"


@pytest.mark.parametrize("backend", sorted(_SHIMS))
def test_shim_resolves_to_the_shared_classes(backend):
    """Same objects, not same-named twins — see #12913."""
    module = _load(_SHIMS[backend], f"shim_{backend}")

    assert module.Base is Base
    assert module.TimestampMixin is TimestampMixin
    assert module.TenantMixin is TenantMixin
    assert module.SoftDeleteMixin is SoftDeleteMixin


def test_both_backends_share_one_implementation():
    a = _load(_SHIMS["backend"], "shim_a")
    b = _load(_SHIMS["slm"], "shim_b")

    assert a.Base is b.Base
    assert a.TimestampMixin is b.TimestampMixin
    assert a.TenantMixin is b.TenantMixin


def test_package_reexports_the_public_surface():
    import autobot_shared.user_management as pkg

    assert pkg.Base is Base
    assert pkg.TimestampMixin is TimestampMixin
    assert pkg.TenantMixin is TenantMixin
    assert pkg.SoftDeleteMixin is SoftDeleteMixin


def test_base_preserves_asyncattrs_and_eager_defaults():
    """#4300 / #11684 rationale must survive the new canonical base."""
    from sqlalchemy.ext.asyncio import AsyncAttrs

    assert issubclass(Base, AsyncAttrs)
    assert Base.__mapper_args__ == {"eager_defaults": True}


def test_base_preserves_slm_uuid_typing():
    """SLM's postgresql.UUID typing must not silently change (#12647)."""
    import uuid

    from sqlalchemy.dialects.postgresql import UUID as PgUUID

    mapped_type = Base.type_annotation_map[uuid.UUID]
    assert isinstance(mapped_type, PgUUID)


def test_base_provides_timestamps_unconditionally():
    """Matches backend's existing (#10636-hardened) design: every subclass
    gets created_at/updated_at without re-declaring them."""
    assert "created_at" in Base.__dict__
    assert "updated_at" in Base.__dict__


def test_timestamp_mixin_is_a_noop():
    """Combining (Base, TimestampMixin) must not double-map columns (#4300)."""
    assert not hasattr(TimestampMixin, "created_at")
    assert not hasattr(TimestampMixin, "updated_at")
