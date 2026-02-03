# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
FastAPI router endpoints for codebase analytics API

DEPRECATED: This file is maintained for backward compatibility only.
All endpoint logic has been moved to modular files in the endpoints/ directory.

For new development, see:
- backend/api/codebase_analytics/router.py (main router)
- backend/api/codebase_analytics/endpoints/* (individual endpoint modules)
"""

# Import the main router for backward compatibility
from .router import router

# Re-export router so existing imports still work:
# from backend.api.codebase_analytics.routes import router
__all__ = ["router"]
