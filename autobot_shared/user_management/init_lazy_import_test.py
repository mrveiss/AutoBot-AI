# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for #13129: user_management package __init__ must not eagerly couple
submodule dependencies together.

Package-level "convenience" re-exports (``from .base_service import ...``,
``from .models.base import ...``, ``from .schemas.user import ...`` all at
``__init__.py`` body level, pre-fix) coupled three independently-scoped
modules' dependency footprints. Since Python always runs a package's
``__init__.py`` before any of its submodules import, importing ANY ONE
submodule forced ALL THREE to import -- including ``schemas.user``'s
``EmailStr`` fields, which need ``email_validator`` at class-definition time.

These tests block ``email_validator`` (sentinel ``None`` in ``sys.modules`` --
not uninstalled) and confirm that importing ``models.base`` (SQLAlchemy +
time_utils only) still succeeds, while touching the one mover that genuinely
needs ``email_validator`` (``schemas.user``, via ``RoleResponse``) still fails
-- the dependency footprint is scoped, not coupled.
"""

import importlib
import sys

import pytest


def _user_management_module_names():
    return [
        name
        for name in sys.modules
        if name == "autobot_shared.user_management" or name.startswith("autobot_shared.user_management.")
    ]


def _rebind_parent_attrs(names):
    """Re-point each dotted name's parent attribute at the sys.modules entry.

    Python's import machinery does ``setattr(parent, leaf, child_module)`` as
    a side effect of every ``import a.b.c`` -- restoring ``sys.modules``
    alone leaves the parent's attribute pointing at whatever module the
    *test* imported in between, which is exactly the identity break this
    fixture exists to avoid.
    """
    for name in sorted(names, key=lambda n: n.count(".")):  # shallow paths first
        parent_name, _, leaf = name.rpartition(".")
        parent = sys.modules.get(parent_name)
        if parent is not None and name in sys.modules:
            setattr(parent, leaf, sys.modules[name])


@pytest.fixture
def email_validator_blocked(monkeypatch):
    """Simulate a thin dependency set (e.g. migration-gate CI) where
    email_validator is absent, without uninstalling it.

    Other suites (base_test.py, user_test.py, team_service_test.py, ...)
    assert module *identity* against copies imported at collection time.
    Deleting-and-leaving-deleted would force those into re-importing a
    different module object the next time they touch this package, so the
    pre-existing entries are snapshotted and restored, not merely dropped --
    including the parent-package attribute bindings the import machinery
    rewrites while this fixture's own imports run.
    """
    snapshot = {name: sys.modules[name] for name in _user_management_module_names()}
    monkeypatch.setitem(sys.modules, "email_validator", None)
    try:
        for name in snapshot:
            del sys.modules[name]
        yield
    finally:
        for name in _user_management_module_names():
            if name not in snapshot:
                del sys.modules[name]
        sys.modules.update(snapshot)
        _rebind_parent_attrs(snapshot)


class TestScopedSubmoduleImports:
    def test_models_base_imports_without_email_validator(self, email_validator_blocked):
        """The regression itself: models/base.py's shim (SQLAlchemy +
        time_utils only) must not pay for schemas.user's pydantic EmailStr
        dependency just because it shares a package with it."""
        mod = importlib.import_module("autobot_shared.user_management.models.base")
        assert mod.Base is not None

    def test_package_level_base_attr_works_without_email_validator(self, email_validator_blocked):
        """Package-level lazy re-export of a non-pydantic name must also stay
        scoped -- accessing ``Base`` must not import ``schemas.user``."""
        import autobot_shared.user_management as um

        assert um.Base.__name__ == "Base"

    def test_schemas_user_mover_still_fails_when_touched(self, email_validator_blocked):
        """The one name that genuinely needs email_validator still raises --
        proving the scoping is real, not a name that silently never worked."""
        import autobot_shared.user_management as um

        with pytest.raises(ImportError):
            _ = um.RoleResponse

    def test_all_previously_exported_names_still_resolve_normally(self):
        """No public name was dropped to dodge the dependency -- every name
        that was ever exported still resolves when email_validator IS present.
        """
        import autobot_shared.user_management as um

        for name in um.__all__:
            assert getattr(um, name) is not None
