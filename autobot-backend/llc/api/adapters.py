# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""LLC adapter introspection API (GH#10219).

Exposes the registered agent adapter types + their availability so the frontend
can populate an adapter-type selector when configuring an LLC agent, and grey
out adapters whose CLI is absent or that are not yet implemented.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from api.user_management.dependencies import get_current_user

from ..adapters import get_adapter, registered_adapter_types

router = APIRouter(prefix="/adapters", tags=["llc-adapters"])


@router.get("")
async def list_adapters(
    _current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """List registered adapter types with availability.

    - ``implemented``: False for stub adapters that raise NotImplementedError
      (detected by the absence of the subprocess ``is_cli_available`` hook).
    - ``available``: implemented AND (for subprocess adapters) the required CLI
      is on PATH.
    - ``requires_cli``: the CLI binary name, or null for in-process adapters.
    """
    out: List[Dict[str, Any]] = []
    for atype in registered_adapter_types():
        adapter = get_adapter(atype)
        implemented = hasattr(adapter, "is_cli_available")
        requires_cli = getattr(adapter, "_required_cli", None)
        available = implemented
        if implemented:
            try:
                available = bool(adapter.is_cli_available())
            except Exception:
                available = False
        out.append(
            {
                "type": atype,
                "available": available,
                "requires_cli": requires_cli,
                "implemented": implemented,
            }
        )
    return out
