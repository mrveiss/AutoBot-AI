# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Team errors, and request validation and instance building for adding a member (#620).

Split out of ``team_service`` so that file does not grow past its size ceiling (#19630); the
errors are re-exported from ``team_service``, where callers import them."""

import uuid
from typing import TYPE_CHECKING

from autobot_shared.time_utils import now_utc
from autobot_shared.user_management.models.team import Team, TeamMembership


class TeamServiceError(Exception):
    """Base exception for team service errors."""


class TeamNotFoundError(TeamServiceError):
    """Raised when team is not found."""


class DuplicateTeamError(TeamServiceError):
    """Raised when attempting to create a duplicate team."""


class MembershipError(TeamServiceError):
    """Raised for membership-related errors."""


class TeamMembershipRequestMixin:
    """Mixed into ``TeamService``: needs ``VALID_ROLES``, ``get_team`` and ``_get_membership``."""

    VALID_ROLES: set[str]

    if TYPE_CHECKING:

        async def get_team(self, team_id: uuid.UUID) -> Team | None: ...

        async def _get_membership(self, team_id: uuid.UUID, user_id: uuid.UUID) -> TeamMembership | None: ...

    async def _validate_membership_request(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
    ) -> Team:
        """
        Validate a membership request before adding a member.

        Checks role validity, team existence, and existing membership. Issue #620.

        Args:
            team_id: Team ID
            user_id: User ID to add
            role: Requested role

        Returns:
            Team instance if validation passes

        Raises:
            MembershipError: If role invalid or user already a member
            TeamNotFoundError: If team not found
        """
        if role not in self.VALID_ROLES:
            raise MembershipError(f"Invalid role '{role}'. Must be one of: {self.VALID_ROLES}")

        team = await self.get_team(team_id)
        if not team:
            raise TeamNotFoundError(f"Team {team_id} not found")

        existing = await self._get_membership(team_id, user_id)
        if existing:
            raise MembershipError(f"User {user_id} is already a member of team {team_id}")

        return team

    def _create_membership_instance(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
    ) -> TeamMembership:
        """
        Create a new TeamMembership instance.

        Issue #620.

        Args:
            team_id: Team ID
            user_id: User ID
            role: Membership role

        Returns:
            New TeamMembership instance
        """
        return TeamMembership(
            id=uuid.uuid4(),
            team_id=team_id,
            user_id=user_id,
            role=role,
            joined_at=now_utc(),
        )
