# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Where a DB role's grants apply, and the cache encoding that carries it (#18338).

A system role's grants apply platform-wide; a company role's only to a caller acting
in that company. Import-free on purpose: the RBAC middleware uses it, and that
module's test harnesses load it under stubbed packages.
"""

import uuid
from typing import Iterable

#: Separator between a permission name and the org an org-scoped grant is bound to.
_ORG_SCOPE = "@org:"


def grant_scope(org_id: uuid.UUID | None, is_system: bool) -> str | None:
    """Where a role's grants apply (#18338): ``"platform"``, ``"org:<uuid>"``, or None for nowhere.

    A system role grants platform-wide. A company role grants only inside its own
    company. A role with no company that is not a system role grants nothing: no
    rule makes its grants either platform-wide or bound to a company.
    """
    if org_id is not None:
        return f"org:{org_id}"
    return "platform" if is_system else None


def encode_grant(name: str, org_id: uuid.UUID | None, is_system: bool) -> str | None:
    """One cacheable grant: the bare name when platform-wide, ``name@org:<uuid>`` when org-bound."""
    scope = grant_scope(org_id, is_system)
    if scope is None:
        return None
    return name if scope == "platform" else f"{name}{_ORG_SCOPE}{org_id}"


def grants_in_scope(grants: Iterable[str], org_id: uuid.UUID | None) -> set[str]:
    """The permission names *grants* give a caller acting in *org_id* (None: platform grants only)."""
    names = set()
    for grant in grants:
        name, _, bound_org = grant.partition(_ORG_SCOPE)
        if not bound_org or (org_id is not None and bound_org == str(org_id)):
            names.add(name)
    return names
