# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Concrete Organization Service — implementation lives in autobot_shared (#12647).

`organization_service.py` was byte-identical across both backends (545 lines),
but it could not simply be relocated the way `team_service.py` was (#13164):
it queries the **concrete** `Organization` and `User` models, and those stay
backend-local under the abstract-core decision on #12645/#12647.

Per the owner's decision the canonical service takes those classes by
injection, so all this module does is bind them. Every existing
`from user_management.services.organization_service import ...` importer keeps
working unchanged — including the error classes, which are re-exported here.
"""

from autobot_shared.user_management import organization_service as shared_organization_service
from autobot_shared.user_management.organization_service import (  # noqa: F401
    DuplicateOrganizationError,
    OrganizationLimitError,
    OrganizationNotFoundError,
    OrganizationServiceError,
)
from user_management.models import Organization, User


class OrganizationService(shared_organization_service.OrganizationService):
    """This backend's Organization service, bound to its concrete models."""

    organization_model = Organization
    user_model = User


__all__ = [
    "OrganizationService",
    "OrganizationServiceError",
    "OrganizationNotFoundError",
    "DuplicateOrganizationError",
    "OrganizationLimitError",
]
