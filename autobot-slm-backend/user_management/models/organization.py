# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Organization Model

Represents a tenant/organization in the system.
In multi_company and provider modes, each organization is isolated.

The implementation now lives in
``autobot_shared.user_management.models.organization.OrganizationCore``
(#12647). SLM's organization model was a strict subset of backend's, so
nothing SLM-specific remains here — only the concrete table mapping, which
each backend must own separately because backend attaches LLC/PM-sync columns
(#8211, #8257) that SLM's schema does not carry.

Kept as a concrete class in this module, not a re-export, so every existing
``from user_management.models.organization import Organization`` importer
keeps working unchanged.
"""

from autobot_shared.user_management.models.organization import OrganizationCore


class Organization(OrganizationCore):
    """SLM's concrete ``organizations`` mapping.

    All columns, relationships and helpers come from ``OrganizationCore`` —
    see ``autobot_shared/user_management/models/organization.py`` for their
    documentation.
    """

    __tablename__ = "organizations"
