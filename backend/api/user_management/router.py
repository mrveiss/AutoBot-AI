# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
User Management API Router

Main router that aggregates all user management endpoints.
"""

from fastapi import APIRouter

from backend.api.user_management.organizations import router as organizations_router
from backend.api.user_management.teams import router as teams_router
from backend.api.user_management.users import router as users_router

router = APIRouter(prefix="/user-management", tags=["User Management"])

# Include sub-routers
router.include_router(users_router)
router.include_router(teams_router)
router.include_router(organizations_router)
