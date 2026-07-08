# Scoped + Shareable Skills/Agents — T0+T1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the custom-skill restart-loss bug (T0) and build the reusable scope/grant authorization core (T1) for umbrella #11277.

**Architecture:** T0 adds a boot-time re-registration path so custom/hub skill definitions reappear in the in-process `SkillRegistry` after a backend restart. T1 adds a standalone authorization primitive — a `ScopeLevel` enum, a generic `resource_grants` table, and a pure `is_visible()` rule plus a DB-backed grant store — with no behavior change to existing flows. T2 (skills adopt scoping) and T3 (agents) build on these; they are out of scope for this plan.

**Tech Stack:** Python 3.14 (async), SQLAlchemy 2.0 (async, `Mapped`/`mapped_column`), Alembic, pydantic v2, pytest + `pytest.mark.asyncio`.

## Global Constraints

- Copyright header on every new `.py` file: the 4-line `# Copyright 2025-2026 mrveiss` / `# SPDX-License-Identifier: Apache-2.0` / `# AutoBot ...` / `# Author: mrveiss` block (copy from any existing file in `autobot-backend/skills/`).
- No commit trailers (no `Co-Authored-By`, no `Generated-with`). `mrveiss` is sole author.
- Logging via `from autobot_shared.logging_manager import get_logger` — never `print`.
- Tests are co-located as `<module>_test.py` next to the module.
- Commits happen inside the worktree `.worktrees/issue-11277/`. Commit message format: `<type>(scope): <desc> (#11277)`.
- Branch target: `Dev_new_gui`.
- New models inherit `Base` from `user_management.models.base`.
- ORGANIZATION is the scope ceiling; default scope for resources is `ORGANIZATION`.

---

## Task 0 (context, no code): where things live

- Registry: `autobot-backend/skills/registry.py` — `SkillRegistry` (singleton via `get_skill_registry()`), `register()`, Pass-2 declarative registration at ~L294–323, `_rebuild_routing_index()`, `_publish_skill_promoted()`.
- Manager: `autobot-backend/skills/manager.py` — `SkillManager.initialize()` (L42), `_load_persisted_configs()` (L153), module-level `_get_redis()` (L317).
- Hub: `autobot-backend/skills/hub.py` — `SkillHub.list_installed() -> list[InstalledSkill]` (records: `id, name, mcp_url, version, installed_at`).
- Manifest/declarative: `autobot-backend/skills/base_skill.py` — `SkillManifest` (pydantic), `DeclarativeSkill(manifest)`.
- Migrations: `autobot-backend/migrations/versions/` — filename `YYYYMMDD_NNN_<slug>.py`.

---

## Task 1: `SkillRegistry.register_declarative(manifest)` public method

Reason: T0 needs to register a manifest as a declarative skill from outside `discover_builtin_skills()`. Today that logic is inline in Pass 2. Extract a public method (DRY) and have Pass 2 call it.

**Files:**
- Modify: `autobot-backend/skills/registry.py`
- Test: `autobot-backend/skills/registry_register_declarative_test.py`

**Interfaces:**
- Produces: `SkillRegistry.register_declarative(self, manifest: SkillManifest) -> bool` — returns `True` if newly registered, `False` if a skill of that name already exists. Rebuilds the routing index on success.

- [ ] **Step 1: Write the failing test**

```python
# autobot-backend/skills/registry_register_declarative_test.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
from skills.base_skill import SkillManifest
from skills.registry import SkillRegistry


def test_register_declarative_adds_skill():
    reg = SkillRegistry()
    m = SkillManifest(name="my-custom", version="2.0.0", description="d", tools=["do_x"])
    assert reg.register_declarative(m) is True
    assert reg.get("my-custom") is not None
    assert reg.get_skill_detail("my-custom")["tools"] == ["do_x"]


def test_register_declarative_is_idempotent_by_name():
    reg = SkillRegistry()
    m = SkillManifest(name="dup", version="1.0.0", description="d")
    assert reg.register_declarative(m) is True
    assert reg.register_declarative(m) is False  # already present
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest skills/registry_register_declarative_test.py -v`
Expected: FAIL with `AttributeError: 'SkillRegistry' object has no attribute 'register_declarative'`

- [ ] **Step 3: Add the method to `SkillRegistry`**

Add to `autobot-backend/skills/registry.py` (inside the `SkillRegistry` class, near `register`). Import `DeclarativeSkill` at top if not already imported (it is: `from skills.base_skill import ... DeclarativeSkill ...`).

```python
    def register_declarative(self, manifest: "SkillManifest") -> bool:
        """Register a SKILL.md-style manifest as a DeclarativeSkill.

        Returns True if newly registered, False if a skill of that name exists.
        Used by builtin Pass-2 discovery and by boot-time custom-skill reload.
        """
        with self._lock:
            if manifest.name in self._skills:
                return False
            self._skills[manifest.name] = DeclarativeSkill(manifest)
        self._rebuild_routing_index()
        self._publish_skill_promoted(manifest.name, manifest.tools)
        logger.info("Registered declarative skill: %s v%s", manifest.name, manifest.version)
        return True
```

Then refactor Pass 2 in `discover_builtin_skills()` to call it (replace the inline `instance = DeclarativeSkill(manifest); with self._lock: self._skills[...] = instance; ...; self._publish_skill_promoted(...)` block):

```python
                if self.register_declarative(manifest):
                    count += 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest skills/registry_register_declarative_test.py skills/registry_skillmd_test.py -v`
Expected: PASS (both the new tests and the existing declarative-discovery test still green)

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/skills/registry.py autobot-backend/skills/registry_register_declarative_test.py
git commit -m "refactor(skills): extract SkillRegistry.register_declarative() public method (#11277)"
```

---

## Task 2: Boot-time custom/hub skill re-registration (T0 fix)

Reason: `SkillManager.initialize()` only re-loads config for already-registered skills; hub-installed skill definitions (persisted in Redis) are never re-registered, so they vanish from the registry on restart. Add `_load_custom_definitions()` and call it from `initialize()`.

**Files:**
- Modify: `autobot-backend/skills/manager.py`
- Test: `autobot-backend/skills/manager_reload_test.py`

**Interfaces:**
- Consumes: `SkillRegistry.register_declarative(manifest) -> bool` (Task 1); `SkillHub.list_installed() -> list[InstalledSkill]`.
- Produces: `SkillManager._load_custom_definitions(self) -> int` — number of custom skills re-registered; called by `initialize()` after `discover_builtin_skills()`.

- [ ] **Step 1: Write the failing test**

```python
# autobot-backend/skills/manager_reload_test.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
import pytest

from skills.base_skill import SkillManifest
from skills.manager import SkillManager
from skills.registry import SkillRegistry


class _FakeInstalled:
    def __init__(self, name, version):
        self.id = name
        self.name = name
        self.version = version
        self.mcp_url = ""
        self.installed_at = ""


@pytest.mark.asyncio
async def test_load_custom_definitions_reregisters_hub_skills(monkeypatch):
    reg = SkillRegistry()
    mgr = SkillManager(registry=reg)

    async def fake_list_installed(self):
        return [_FakeInstalled("hub-alpha", "1.2.0")]

    monkeypatch.setattr("skills.hub.SkillHub.list_installed", fake_list_installed)

    count = await mgr._load_custom_definitions()

    assert count == 1
    assert reg.get("hub-alpha") is not None
    assert reg.get_skill_detail("hub-alpha")["version"] == "1.2.0"


@pytest.mark.asyncio
async def test_load_custom_definitions_skips_names_already_registered(monkeypatch):
    reg = SkillRegistry()
    reg.register_declarative(SkillManifest(name="hub-alpha", version="9.9.9", description="d"))
    mgr = SkillManager(registry=reg)

    async def fake_list_installed(self):
        return [_FakeInstalled("hub-alpha", "1.2.0")]

    monkeypatch.setattr("skills.hub.SkillHub.list_installed", fake_list_installed)

    count = await mgr._load_custom_definitions()

    assert count == 0  # already present, not overwritten
    assert reg.get_skill_detail("hub-alpha")["version"] == "9.9.9"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest skills/manager_reload_test.py -v`
Expected: FAIL with `AttributeError: 'SkillManager' object has no attribute '_load_custom_definitions'`

- [ ] **Step 3: Implement `_load_custom_definitions` and call it from `initialize`**

In `autobot-backend/skills/manager.py`, add the method to `SkillManager`:

```python
    async def _load_custom_definitions(self) -> int:
        """Re-register custom/hub skill definitions so they survive restart (#11277 T0).

        Hub skills persist to Redis but are otherwise lost from the in-process
        registry on restart. Re-register each as a declarative descriptor so it
        reappears in list/route. (MCP process reattachment is handled in T2.2.)
        """
        from skills.base_skill import SkillManifest
        from skills.hub import SkillHub

        registered = 0
        try:
            installed = await SkillHub().list_installed()
        except Exception:
            logger.exception("Failed to list hub skills during reload")
            return 0
        for rec in installed:
            manifest = SkillManifest(
                name=rec.name,
                version=rec.version or "1.0.0",
                description=f"Hub skill {rec.name}",
                category="hub",
            )
            if self._registry.register_declarative(manifest):
                registered += 1
        if registered:
            logger.info("Re-registered %d custom/hub skill(s) at boot", registered)
        return registered
```

Then update `initialize()` to call it:

```python
    async def initialize(self) -> Dict[str, Any]:
        """Initialize the skills system: discover and load all skills."""
        count = self._registry.discover_builtin_skills()
        custom = await self._load_custom_definitions()
        await self._load_persisted_configs()

        return {
            "skills_discovered": count,
            "custom_reregistered": custom,
            "total_registered": self._registry.skill_count,
            "categories": list(self._registry.categories),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest skills/manager_reload_test.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/skills/manager.py autobot-backend/skills/manager_reload_test.py
git commit -m "fix(skills): re-register custom/hub skills at boot so they survive restart (#11277)"
```

---

## Task 3: `ScopeLevel` enum (T1 core)

**Files:**
- Create: `autobot-backend/autobot_shared/scoping/scope_level.py` (if `autobot_shared/scoping/` doesn't exist, create it with an empty `__init__.py`)
- Test: `autobot-backend/autobot_shared/scoping/scope_level_test.py`

**Interfaces:**
- Produces: `ScopeLevel(str, Enum)` with members `USER, SESSION, SHARED, GROUP, ORGANIZATION`; `ScopeLevel.default() -> ScopeLevel` returning `ORGANIZATION`.

- [ ] **Step 1: Write the failing test**

```python
# autobot-backend/autobot_shared/scoping/scope_level_test.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
from autobot_shared.scoping.scope_level import ScopeLevel


def test_scope_level_members_mirror_secrets():
    assert {s.value for s in ScopeLevel} == {
        "user", "session", "shared", "group", "organization"
    }


def test_default_is_organization():
    assert ScopeLevel.default() is ScopeLevel.ORGANIZATION
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest autobot_shared/scoping/scope_level_test.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'autobot_shared.scoping'`

- [ ] **Step 3: Create the package + enum**

Create `autobot-backend/autobot_shared/scoping/__init__.py` (empty file with copyright header) and:

```python
# autobot-backend/autobot_shared/scoping/scope_level.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Resource visibility scope, mirroring SecretScope (#11277). Authorization only."""

from enum import Enum


class ScopeLevel(str, Enum):
    """Visibility scope for a shareable resource (skill or agent)."""

    USER = "user"
    SESSION = "session"
    SHARED = "shared"
    GROUP = "group"
    ORGANIZATION = "organization"

    @classmethod
    def default(cls) -> "ScopeLevel":
        """Default scope for new resources: company-wide."""
        return cls.ORGANIZATION
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest autobot_shared/scoping/scope_level_test.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/autobot_shared/scoping/
git commit -m "feat(scoping): add ScopeLevel enum mirroring SecretScope (#11277)"
```

---

## Task 4: `resource_grants` table + model + migration

**Files:**
- Create: `autobot-backend/models/resource_grant.py`
- Create: `autobot-backend/migrations/versions/20260708_068_resource_grants.py` (verify NNN/down_revision — see Step 3)
- Test: `autobot-backend/models/resource_grant_test.py`

**Interfaces:**
- Produces: `ResourceGrant(Base)` with columns `id (UUID pk)`, `resource_type (str)`, `resource_id (str)`, `grantee_type (str: user|group)`, `grantee_id (str)`, `permission (str: view|use|manage)`, `created_by (UUID|None)`, `created_at`. Unique on `(resource_type, resource_id, grantee_type, grantee_id)` named `uq_resource_grants_target`.

- [ ] **Step 1: Write the failing test (model shape)**

```python
# autobot-backend/models/resource_grant_test.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
from models.resource_grant import ResourceGrant


def test_resource_grant_table_and_columns():
    assert ResourceGrant.__tablename__ == "resource_grants"
    cols = set(ResourceGrant.__table__.columns.keys())
    assert cols == {
        "id", "resource_type", "resource_id", "grantee_type",
        "grantee_id", "permission", "created_by", "created_at",
    }


def test_resource_grant_unique_constraint_present():
    names = {c.name for c in ResourceGrant.__table__.constraints}
    assert "uq_resource_grants_target" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest models/resource_grant_test.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'models.resource_grant'`

- [ ] **Step 3: Create the model**

```python
# autobot-backend/models/resource_grant.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Generic per-grantee access grant for shareable resources (#11277).

One row grants a user or group a permission on a skill or agent. Sharing = add
a row; revoking = delete a row. Authorization only — no crypto envelope.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from user_management.models.base import Base


class ResourceGrant(Base):
    """One grant: (resource_type, resource_id) accessible to (grantee_type, grantee_id)."""

    __tablename__ = "resource_grants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # skill|agent
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    grantee_type: Mapped[str] = mapped_column(String(16), nullable=False)  # user|group
    grantee_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(16), nullable=False, default="use")  # view|use|manage
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "resource_type", "resource_id", "grantee_type", "grantee_id",
            name="uq_resource_grants_target",
        ),
    )
```

- [ ] **Step 4: Run model test to verify it passes**

Run: `cd autobot-backend && python -m pytest models/resource_grant_test.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Create the migration**

First find the current head:

Run: `cd autobot-backend && python -m alembic heads`
- If output is a single revision, use it as `down_revision`. If it prints multiple heads, this plan's migration must merge them (set `down_revision` to the tuple of heads). At time of writing the latest file is `20260708_067`; verify and adjust the filename `NNN` and `down_revision` accordingly.

```python
# autobot-backend/migrations/versions/20260708_068_resource_grants.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add resource_grants table for scoped/shareable skills and agents (#11277)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260708_068"
down_revision: Union[str, Sequence[str], None] = "20260708_067"  # verify via `alembic heads`
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resource_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("grantee_type", sa.String(length=16), nullable=False),
        sa.Column("grantee_id", sa.String(length=255), nullable=False),
        sa.Column("permission", sa.String(length=16), nullable=False, server_default="use"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "resource_type", "resource_id", "grantee_type", "grantee_id",
            name="uq_resource_grants_target",
        ),
    )
    op.create_index("ix_resource_grants_resource_type", "resource_grants", ["resource_type"])
    op.create_index("ix_resource_grants_resource_id", "resource_grants", ["resource_id"])
    op.create_index("ix_resource_grants_grantee_id", "resource_grants", ["grantee_id"])


def downgrade() -> None:
    op.drop_index("ix_resource_grants_grantee_id", table_name="resource_grants")
    op.drop_index("ix_resource_grants_resource_id", table_name="resource_grants")
    op.drop_index("ix_resource_grants_resource_type", table_name="resource_grants")
    op.drop_table("resource_grants")
```

- [ ] **Step 6: Verify migration applies (in an env with the test DB)**

Run: `cd autobot-backend && python -m alembic upgrade head && python -m alembic downgrade -1 && python -m alembic upgrade head`
Expected: no errors; `resource_grants` created, dropped, recreated.

- [ ] **Step 7: Commit**

```bash
git add autobot-backend/models/resource_grant.py autobot-backend/models/resource_grant_test.py autobot-backend/migrations/versions/20260708_068_resource_grants.py
git commit -m "feat(scoping): add resource_grants table + model + migration (#11277)"
```

---

## Task 5: `is_visible()` authorization rule (pure function)

Reason: the core visibility decision, testable in isolation before any DB wiring. Later tasks (T2/T3) call it with resource rows and grant lookups.

**Files:**
- Create: `autobot-backend/autobot_shared/scoping/visibility.py`
- Test: `autobot-backend/autobot_shared/scoping/visibility_test.py`

**Interfaces:**
- Consumes: `ScopeLevel` (Task 3).
- Produces:
  - `@dataclass Principal(user_id: str, company_id: str | None, group_ids: frozenset[str])`
  - `@dataclass ResourceDescriptor(owner_id: str, company_id: str | None, scope: ScopeLevel, group_id: str | None)`
  - `is_visible(principal: Principal, resource: ResourceDescriptor, has_grant: bool) -> bool` — pure rule; `has_grant` is the pre-computed "a matching resource_grants row exists" result (Task 6 supplies it).

- [ ] **Step 1: Write the failing test (truth table)**

```python
# autobot-backend/autobot_shared/scoping/visibility_test.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
from autobot_shared.scoping.scope_level import ScopeLevel
from autobot_shared.scoping.visibility import Principal, ResourceDescriptor, is_visible


def _p(user="u1", company="c1", groups=()):
    return Principal(user_id=user, company_id=company, group_ids=frozenset(groups))


def _r(owner="owner", company="c1", scope=ScopeLevel.ORGANIZATION, group=None):
    return ResourceDescriptor(owner_id=owner, company_id=company, scope=scope, group_id=group)


def test_owner_always_sees_own_resource():
    assert is_visible(_p(user="me"), _r(owner="me", scope=ScopeLevel.USER, company="other"), False)


def test_organization_scope_visible_to_same_company():
    assert is_visible(_p(company="c1"), _r(scope=ScopeLevel.ORGANIZATION, company="c1"), False)


def test_organization_scope_hidden_from_other_company():
    assert not is_visible(_p(company="c2"), _r(scope=ScopeLevel.ORGANIZATION, company="c1"), False)


def test_group_scope_visible_to_member():
    assert is_visible(_p(groups={"g1"}), _r(scope=ScopeLevel.GROUP, group="g1"), False)


def test_group_scope_hidden_from_non_member():
    assert not is_visible(_p(groups={"g2"}), _r(scope=ScopeLevel.GROUP, group="g1"), False)


def test_user_scope_hidden_from_non_owner_without_grant():
    assert not is_visible(_p(user="stranger"), _r(owner="owner", scope=ScopeLevel.USER), False)


def test_explicit_grant_overrides_scope():
    assert is_visible(_p(user="stranger", company="c2"),
                      _r(owner="owner", scope=ScopeLevel.USER, company="c1"), True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest autobot_shared/scoping/visibility_test.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'autobot_shared.scoping.visibility'`

- [ ] **Step 3: Implement the rule**

```python
# autobot-backend/autobot_shared/scoping/visibility.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pure visibility rule for scoped resources (#11277)."""

from dataclasses import dataclass

from autobot_shared.scoping.scope_level import ScopeLevel


@dataclass(frozen=True)
class Principal:
    """Who is asking."""

    user_id: str
    company_id: str | None
    group_ids: frozenset[str]


@dataclass(frozen=True)
class ResourceDescriptor:
    """The resource's ownership + scope."""

    owner_id: str
    company_id: str | None
    scope: ScopeLevel
    group_id: str | None = None


def is_visible(principal: Principal, resource: ResourceDescriptor, has_grant: bool) -> bool:
    """Decide whether `principal` may access `resource`.

    `has_grant` is the pre-computed result of "a matching resource_grants row
    exists for this principal" (Task 6). An explicit grant always grants access.
    """
    if principal.user_id == resource.owner_id:
        return True
    if has_grant:
        return True
    if resource.scope is ScopeLevel.ORGANIZATION:
        return resource.company_id is not None and resource.company_id == principal.company_id
    if resource.scope is ScopeLevel.GROUP:
        return resource.group_id is not None and resource.group_id in principal.group_ids
    # USER / SESSION / SHARED are private absent ownership or an explicit grant.
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest autobot_shared/scoping/visibility_test.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/autobot_shared/scoping/visibility.py autobot-backend/autobot_shared/scoping/visibility_test.py
git commit -m "feat(scoping): add is_visible() authorization rule (#11277)"
```

---

## Task 6: `ResourceGrantStore` (DB-backed grant CRUD + has_grant lookup)

**Files:**
- Create: `autobot-backend/services/resource_grant_store.py`
- Test: `autobot-backend/services/resource_grant_store_test.py`

**Interfaces:**
- Consumes: `ResourceGrant` model (Task 4), `Principal` (Task 5).
- Produces (async, take an `AsyncSession`):
  - `grant(session, resource_type, resource_id, grantee_type, grantee_id, permission, created_by) -> ResourceGrant` (idempotent upsert on the unique key)
  - `revoke(session, resource_type, resource_id, grantee_type, grantee_id) -> bool`
  - `has_grant(session, resource_type, resource_id, principal: Principal) -> bool` (True if a row matches the principal's user_id OR any of their group_ids)

- [ ] **Step 1: Write the failing test**

Use the repo's existing async-session test fixture. Search for one first:

Run: `cd autobot-backend && grep -rl "async_session" services/*_test.py | head -1`
Use the same fixture import that file uses. The test below assumes a `db_session` async fixture yielding an `AsyncSession` bound to a schema-migrated test DB (follow the located file's pattern; adjust the fixture name if the codebase uses e.g. `session`).

```python
# autobot-backend/services/resource_grant_store_test.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
import pytest

from autobot_shared.scoping.visibility import Principal
from services import resource_grant_store as store


@pytest.mark.asyncio
async def test_grant_then_has_grant_for_user(db_session):
    await store.grant(db_session, "skill", "s1", "user", "u1", "use", None)
    p = Principal(user_id="u1", company_id="c1", group_ids=frozenset())
    assert await store.has_grant(db_session, "skill", "s1", p) is True
    other = Principal(user_id="u2", company_id="c1", group_ids=frozenset())
    assert await store.has_grant(db_session, "skill", "s1", other) is False


@pytest.mark.asyncio
async def test_group_grant_matches_member(db_session):
    await store.grant(db_session, "skill", "s2", "group", "g1", "use", None)
    member = Principal(user_id="u9", company_id="c1", group_ids=frozenset({"g1"}))
    assert await store.has_grant(db_session, "skill", "s2", member) is True


@pytest.mark.asyncio
async def test_grant_is_idempotent(db_session):
    await store.grant(db_session, "skill", "s3", "user", "u1", "use", None)
    await store.grant(db_session, "skill", "s3", "user", "u1", "manage", None)  # same target
    p = Principal(user_id="u1", company_id="c1", group_ids=frozenset())
    assert await store.has_grant(db_session, "skill", "s3", p) is True


@pytest.mark.asyncio
async def test_revoke_removes_access(db_session):
    await store.grant(db_session, "skill", "s4", "user", "u1", "use", None)
    assert await store.revoke(db_session, "skill", "s4", "user", "u1") is True
    p = Principal(user_id="u1", company_id="c1", group_ids=frozenset())
    assert await store.has_grant(db_session, "skill", "s4", p) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest services/resource_grant_store_test.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.resource_grant_store'`

- [ ] **Step 3: Implement the store**

```python
# autobot-backend/services/resource_grant_store.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""DB-backed CRUD + lookup for resource_grants (#11277)."""

import uuid

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.scoping.visibility import Principal
from models.resource_grant import ResourceGrant


async def grant(
    session: AsyncSession,
    resource_type: str,
    resource_id: str,
    grantee_type: str,
    grantee_id: str,
    permission: str = "use",
    created_by: uuid.UUID | None = None,
) -> ResourceGrant:
    """Add or update a grant (idempotent on the unique target key)."""
    existing = (
        await session.execute(
            select(ResourceGrant).where(
                ResourceGrant.resource_type == resource_type,
                ResourceGrant.resource_id == resource_id,
                ResourceGrant.grantee_type == grantee_type,
                ResourceGrant.grantee_id == grantee_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.permission = permission
        await session.flush()
        return existing
    row = ResourceGrant(
        resource_type=resource_type,
        resource_id=resource_id,
        grantee_type=grantee_type,
        grantee_id=grantee_id,
        permission=permission,
        created_by=created_by,
    )
    session.add(row)
    await session.flush()
    return row


async def revoke(
    session: AsyncSession,
    resource_type: str,
    resource_id: str,
    grantee_type: str,
    grantee_id: str,
) -> bool:
    """Delete a grant. Returns True if a row was removed."""
    result = await session.execute(
        delete(ResourceGrant).where(
            ResourceGrant.resource_type == resource_type,
            ResourceGrant.resource_id == resource_id,
            ResourceGrant.grantee_type == grantee_type,
            ResourceGrant.grantee_id == grantee_id,
        )
    )
    await session.flush()
    return (result.rowcount or 0) > 0


async def has_grant(
    session: AsyncSession,
    resource_type: str,
    resource_id: str,
    principal: Principal,
) -> bool:
    """True if any grant row matches the principal's user or a group they're in."""
    grantee_clauses = [
        and_(ResourceGrant.grantee_type == "user", ResourceGrant.grantee_id == principal.user_id)
    ]
    if principal.group_ids:
        grantee_clauses.append(
            and_(
                ResourceGrant.grantee_type == "group",
                ResourceGrant.grantee_id.in_(list(principal.group_ids)),
            )
        )
    row = (
        await session.execute(
            select(ResourceGrant.id).where(
                ResourceGrant.resource_type == resource_type,
                ResourceGrant.resource_id == resource_id,
                or_(*grantee_clauses),
            ).limit(1)
        )
    ).first()
    return row is not None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest services/resource_grant_store_test.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/services/resource_grant_store.py autobot-backend/services/resource_grant_store_test.py
git commit -m "feat(scoping): add ResourceGrantStore CRUD + has_grant lookup (#11277)"
```

---

## Task 7: `visible_to()` resolver + company-keyed cache

Reason: compose Tasks 5+6 into the single entry point T2/T3 call, plus the resolution cache from the spec (invalidated on grant/scope change).

**Files:**
- Create: `autobot-backend/services/resource_visibility.py`
- Test: `autobot-backend/services/resource_visibility_test.py`

**Interfaces:**
- Consumes: `is_visible` + `Principal`/`ResourceDescriptor` (Task 5), `resource_grant_store.has_grant` (Task 6).
- Produces:
  - `async can_access(session, principal: Principal, resource_type: str, resource_id: str, resource: ResourceDescriptor) -> bool`
  - `invalidate(resource_type: str, resource_id: str) -> None` — clears cached decisions for a resource (called on grant/scope change).

- [ ] **Step 1: Write the failing test**

```python
# autobot-backend/services/resource_visibility_test.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
import pytest

from autobot_shared.scoping.scope_level import ScopeLevel
from autobot_shared.scoping.visibility import Principal, ResourceDescriptor
from services import resource_visibility as rv


@pytest.mark.asyncio
async def test_can_access_uses_grant_when_scope_denies(db_session):
    from services import resource_grant_store as store

    await store.grant(db_session, "skill", "sX", "user", "u1", "use", None)
    rv.invalidate("skill", "sX")
    p = Principal(user_id="u1", company_id="c2", group_ids=frozenset())
    r = ResourceDescriptor(owner_id="owner", company_id="c1", scope=ScopeLevel.USER)
    assert await rv.can_access(db_session, p, "skill", "sX", r) is True


@pytest.mark.asyncio
async def test_can_access_org_scope_no_grant(db_session):
    p = Principal(user_id="u1", company_id="c1", group_ids=frozenset())
    r = ResourceDescriptor(owner_id="owner", company_id="c1", scope=ScopeLevel.ORGANIZATION)
    assert await rv.can_access(db_session, p, "skill", "sY", r) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest services/resource_visibility_test.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.resource_visibility'`

- [ ] **Step 3: Implement resolver + cache**

```python
# autobot-backend/services/resource_visibility.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Compose is_visible() + grant lookup into the single access entry point (#11277).

Includes a small per-process decision cache keyed by (resource, principal); the
spec's company-keyed cache — invalidated on grant/scope change via invalidate().
"""

from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.scoping.visibility import Principal, ResourceDescriptor, is_visible
from services import resource_grant_store as store

logger = get_logger(__name__)

# (resource_type, resource_id) -> { principal_key: bool }
_cache: dict[tuple[str, str], dict[str, bool]] = {}


def _principal_key(p: Principal) -> str:
    return f"{p.user_id}|{p.company_id}|{','.join(sorted(p.group_ids))}"


def invalidate(resource_type: str, resource_id: str) -> None:
    """Drop cached decisions for a resource (call on grant/scope change)."""
    _cache.pop((resource_type, resource_id), None)


async def can_access(
    session: AsyncSession,
    principal: Principal,
    resource_type: str,
    resource_id: str,
    resource: ResourceDescriptor,
) -> bool:
    """Return True if principal may access the resource (scope OR explicit grant)."""
    bucket = _cache.setdefault((resource_type, resource_id), {})
    pkey = _principal_key(principal)
    if pkey in bucket:
        return bucket[pkey]
    has = await store.has_grant(session, resource_type, resource_id, principal)
    decision = is_visible(principal, resource, has)
    bucket[pkey] = decision
    return decision
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest services/resource_visibility_test.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the whole T1 suite + commit**

Run: `cd autobot-backend && python -m pytest autobot_shared/scoping/ services/resource_grant_store_test.py services/resource_visibility_test.py models/resource_grant_test.py -v`
Expected: all PASS

```bash
git add autobot-backend/services/resource_visibility.py autobot-backend/services/resource_visibility_test.py
git commit -m "feat(scoping): add can_access() resolver + decision cache (#11277)"
```

---

## Self-Review notes

- **Spec coverage (T0+T1 only):** boot-reload fix → Tasks 1–2; `ScopeLevel` → Task 3; `resource_grants` table+migration → Task 4; `visible_to`/enforcement rule → Tasks 5+7; grant store → Task 6; resolution cache → Task 7. T2/T3/T4 are explicitly out of scope for this plan (separate plans).
- **Type consistency:** `Principal`/`ResourceDescriptor` defined in Task 5 and consumed unchanged in Tasks 6–7; `register_declarative(manifest) -> bool` defined in Task 1 and consumed in Task 2; `has_grant`/`can_access` signatures stable across tasks.
- **Known caveat:** Task 2 re-registers hub skills as *declarative descriptors* (restores registry visibility); MCP subprocess reattachment for hub skills is deferred to T2.2 and noted in-code. This is the correct minimal T0 fix (registry no longer loses them on restart).
- **DB test fixture:** Tasks 6–7 depend on the repo's async-session test fixture; Step 1 of Task 6 locates the existing pattern rather than inventing one.
