# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which roles the registry had to leave out because no manifest resolved (#22067).

Dependency-free at import on purpose: ``role_manifest_shape`` fills it at import, and ``api/health.py``, the deployment
and the pre-flight read it, none of which may pull the registry (or the manifest loader) in just to ask.
"""

from __future__ import annotations

from typing import Dict

#: role name -> why it was left out of ``role_registry.DEFAULT_ROLES``. Empty when every role resolved.
MANIFEST_ERRORS: Dict[str, str] = {}


def manifest_errors() -> Dict[str, str]:
    """A copy of ``MANIFEST_ERRORS``: roles unavailable for want of a usable manifest; empty when healthy."""
    return dict(MANIFEST_ERRORS)


def no_manifest_preflight(node_id: str, role_name: str):
    """The pre-flight answer for a role with no usable manifest (#22067).

    Allowed, ``manifest_found=False`` when the role simply has none (as before); refused, naming the cause,
    when its manifest failed to resolve -- a deploy of it would guess its paths and units.
    """
    from models.schemas import PreflightConflict, PreflightResult

    why = MANIFEST_ERRORS.get(role_name)
    if why is None:
        return PreflightResult(allowed=True, role_name=role_name, node_id=node_id, manifest_found=False)
    conflict = PreflightConflict(kind="manifest_unavailable", role=role_name, detail=why)
    return PreflightResult(
        allowed=False, role_name=role_name, node_id=node_id, conflicts=[conflict], manifest_found=False
    )
