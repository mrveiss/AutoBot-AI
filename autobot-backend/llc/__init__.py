# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""LLC (Lean Lifecycle Controller) module (GH#8204).

Entry point for the LLC module. Exports the FastAPI router so
initialization/router_registry/feature_routers.py can include it.

``router`` is loaded lazily so that importing ``llc`` (or any sub-package
such as ``llc.adapters``) does not pull in the full FastAPI application
stack.  ``from llc import router`` still works — Python calls
``__getattr__`` for names that are not defined at module level.
"""

__version__ = "0.1.0"


def __getattr__(name: str):  # noqa: ANN001
    if name == "router":
        from .api import router  # noqa: PLC0415

        return router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["router"]
