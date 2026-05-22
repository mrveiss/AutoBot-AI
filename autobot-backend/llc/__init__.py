"""LLC (Lean Lifecycle Controller) module (GH#8204).

Entry point for the LLC module. Exports the FastAPI router so
initialization/router_registry/feature_routers.py can include it.
"""

__version__ = "0.1.0"

from .api import router

__all__ = ["router"]
