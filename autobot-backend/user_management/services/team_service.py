# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Team Service

Business logic for team management operations including CRUD,
membership management, and role assignment within teams.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from user_management.models import Team, TeamMembership
from user_management.models.audit import AuditAction, AuditLog, AuditResourceType
from user_management.services.base_service import BaseService, TenantContext

logger = logging.getLogger(__name__)


class TeamServiceError(Exception):
    """Base exception for team service errors."""


class TeamNotFoundError(TeamServiceError):
    """Raised when team is not found."""


class DuplicateTeamError(TeamServiceError):
    """Raised when attempting to create a duplicate team."""


class MembershipError(TeamServiceError):
    """Raised for membership-related errors."""


class TeamService(BaseService):
    """
    Team management service.

    Provides CRUD operations for teams and team membership management
    with multi-tenancy support.
    """

    # Team membership roles
    ROLE_OWNER = "owner"
    ROLE_ADMIN = "admin"
    ROLE_MEMBER = "member"

    VALID_ROLES = {ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER}

    def __init__(self, session: AsyncSession, context: Optional[TenantContext] = None):
        """Initialize team service."""
        super().__init__(session, context)

    # -------------------------------------------------------------------------
    # Team CRUD Operations
    # -------------------------------------------------------------------------

    async def _validate_unique_team_name(self, name: str) -> None:
        """Validate team name is unique within organization. Issue #620."""
        existing = await self._find_team_by_name(name)
        if existing:
            raise DuplicateTeamError(
                f"Team with name '{name}' already exists in this organization"
            )

    def _build_team_object(
        self,
        name: str,
        description: Optional[str],
        settings: Optional[dict],
        is_default: bool,
    ) -> Team:
        """Build Team model instance with provided attributes. Issue #620."""
        return Team(
            id=uuid.uuid4(),
            org_id=self.context.org_id,
            name=name,
            description=description,
            settings=settings or {},
            is_default=is_default,
        )

    async def _log_team_creation(
        self,
        team: Team,
        name: str,
        is_default: bool,
        effective_owner: Optional[uuid.UUID],
    ) -> None:
        """Log audit entry for team creation. Issue #620."""
        await self._audit_log(
            action=AuditAction.TEAM_CREATED,
            resource_type=AuditResourceType.TEAM,
            resource_id=team.id,
            details={
                "name": name,
                "is_default": is_default,
                "owner_id": str(effective_owner) if effective_owner else None,
            },
        )

    async def create_team(
        self,
        name: str,
        description: Optional[str] = None,
        settings: Optional[dict] = None,
        is_default: bool = False,
        owner_id: Optional[uuid.UUID] = None,
    ) -> Team:
        """
        Create a new team.

        Args:
            name: Team name (unique within organization)
            description: Team description
            settings: Team settings JSON
            is_default: Whether this is the default team
            owner_id: User ID to set as owner (uses context user if not provided)

        Returns:
            Created Team instance

        Raises:
            DuplicateTeamError: If team name already exists in org
        """
        self._require_org_context()
        await self._validate_unique_team_name(name)

        team = self._build_team_object(name, description, settings, is_default)
        self.session.add(team)
        await self.session.flush()

        effective_owner = owner_id or self.context.user_id
        if effective_owner:
            await self.add_member(team.id, effective_owner, role=self.ROLE_OWNER)

        await self._log_team_creation(team, name, is_default, effective_owner)
        logger.info("Created team: %s (id=%s)", name, team.id)
        return team

    async def get_team(self, team_id: uuid.UUID) -> Optional[Team]:
        """
        Get team by ID.

        Args:
            team_id: Team UUID

        Returns:
            Team instance or None
        """
        query = (
            select(Team)
            .options(selectinload(Team.memberships).selectinload(TeamMembership.user))
            .where(Team.id == team_id)
            .where(Team.deleted_at.is_(None))
        )
        query = self.apply_tenant_filter(query, Team)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    def _build_list_teams_base_query(
        self, include_deleted: bool, search: Optional[str]
    ):
        """
        Build base query for listing teams with filters applied.

        Issue #620: Extracted from list_teams.

        Args:
            include_deleted: Whether to include soft-deleted teams
            search: Optional search term for name/description

        Returns:
            SQLAlchemy select query with filters applied
        """
        base_query = select(Team)
        base_query = self.apply_tenant_filter(base_query, Team)

        if not include_deleted:
            base_query = base_query.where(Team.deleted_at.is_(None))

        if search:
            search_pattern = f"%{search}%"
            base_query = base_query.where(
                or_(
                    Team.name.ilike(search_pattern),
                    Team.description.ilike(search_pattern),
                )
            )
        return base_query

    async def list_teams(
        self,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        search: Optional[str] = None,
    ) -> tuple[List[Team], int]:
        """
        List teams with pagination.

        Args:
            limit: Maximum number of teams to return
            offset: Number of teams to skip
            include_deleted: Include deleted teams
            search: Search term for name or description

        Returns:
            Tuple of (teams list, total count)
        """
        self._require_org_context()
        base_query = self._build_list_teams_base_query(include_deleted, search)

        count_query = select(func.count()).select_from(base_query.subquery())
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0

        query = (
            base_query.options(
                selectinload(Team.memberships).selectinload(TeamMembership.user)
            )
            .order_by(Team.name)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        teams = list(result.scalars().all())

        return teams, total

    async def _apply_team_name_update(
        self, team: Team, name: str, team_id: uuid.UUID, changes: dict
    ) -> None:
        """
        Apply name update to team if name has changed.

        Issue #620: Extracted from update_team.

        Args:
            team: Team instance to update
            name: New name value
            team_id: Team UUID for duplicate check
            changes: Dict to record changes for audit

        Raises:
            DuplicateTeamError: If new name already exists
        """
        if name and name != team.name:
            existing = await self._find_team_by_name(name)
            if existing and existing.id != team_id:
                raise DuplicateTeamError(f"Team name '{name}' already exists")
            changes["name"] = {"old": team.name, "new": name}
            team.name = name

    async def update_team(
        self,
        team_id: uuid.UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        settings: Optional[dict] = None,
    ) -> Team:
        """
        Update team.

        Args:
            team_id: Team ID to update
            name: New name (optional)
            description: New description (optional)
            settings: New settings (optional)

        Returns:
            Updated Team instance

        Raises:
            TeamNotFoundError: If team not found
            DuplicateTeamError: If new name already exists
        """
        team = await self.get_team(team_id)
        if not team:
            raise TeamNotFoundError(f"Team {team_id} not found")

        changes = {}
        await self._apply_team_name_update(team, name, team_id, changes)

        if description is not None:
            changes["description"] = {"old": team.description, "new": description}
            team.description = description

        if settings is not None:
            team.settings = settings

        team.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

        if changes:
            await self._audit_log(
                action=AuditAction.TEAM_UPDATED,
                resource_type=AuditResourceType.TEAM,
                resource_id=team_id,
                details={"changes": changes},
            )
        return team

    async def delete_team(self, team_id: uuid.UUID, hard_delete: bool = False) -> bool:
        """
        Delete a team.

        Args:
            team_id: Team ID to delete
            hard_delete: If True, permanently delete

        Returns:
            True if deleted

        Raises:
            TeamNotFoundError: If team not found
        """
        team = await self.get_team(team_id)
        if not team:
            raise TeamNotFoundError(f"Team {team_id} not found")

        if hard_delete:
            await self.session.delete(team)
        else:
            team.deleted_at = datetime.now(timezone.utc)

        await self.session.flush()

        await self._audit_log(
            action=AuditAction.TEAM_DELETED,
            resource_type=AuditResourceType.TEAM,
            resource_id=team_id,
            details={"hard_delete": hard_delete, "name": team.name},
        )

        logger.info("Deleted team: %s (hard=%s)", team_id, hard_delete)
        return True

    # -------------------------------------------------------------------------
    # Membership Management
    # -------------------------------------------------------------------------

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
            raise MembershipError(
                f"Invalid role '{role}'. Must be one of: {self.VALID_ROLES}"
            )

        team = await self.get_team(team_id)
        if not team:
            raise TeamNotFoundError(f"Team {team_id} not found")

        existing = await self._get_membership(team_id, user_id)
        if existing:
            raise MembershipError(
                f"User {user_id} is already a member of team {team_id}"
            )

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
            joined_at=datetime.now(timezone.utc),
        )

    async def add_member(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str = "member",
    ) -> TeamMembership:
        """
        Add a user to a team.

        Args:
            team_id: Team ID
            user_id: User ID to add
            role: Membership role (owner, admin, member)

        Returns:
            Created TeamMembership instance

        Raises:
            TeamNotFoundError: If team not found
            MembershipError: If user already a member or invalid role
        """
        await self._validate_membership_request(team_id, user_id, role)

        membership = self._create_membership_instance(team_id, user_id, role)
        self.session.add(membership)
        await self.session.flush()

        await self._audit_log(
            action=AuditAction.TEAM_MEMBER_ADDED,
            resource_type=AuditResourceType.TEAM,
            resource_id=team_id,
            details={"user_id": str(user_id), "role": role},
        )

        logger.info("Added user %s to team %s with role %s", user_id, team_id, role)
        return membership

    async def remove_member(self, team_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """
        Remove a user from a team.

        Args:
            team_id: Team ID
            user_id: User ID to remove

        Returns:
            True if removed

        Raises:
            MembershipError: If user is not a member or is the last owner
        """
        membership = await self._get_membership(team_id, user_id)
        if not membership:
            raise MembershipError(f"User {user_id} is not a member of team {team_id}")

        # Prevent removing the last owner
        if membership.role == self.ROLE_OWNER:
            owner_count = await self._count_owners(team_id)
            if owner_count <= 1:
                raise MembershipError(
                    "Cannot remove the last owner. Transfer ownership first."
                )

        await self.session.delete(membership)
        await self.session.flush()

        await self._audit_log(
            action=AuditAction.TEAM_MEMBER_REMOVED,
            resource_type=AuditResourceType.TEAM,
            resource_id=team_id,
            details={"user_id": str(user_id), "previous_role": membership.role},
        )

        logger.info("Removed user %s from team %s", user_id, team_id)
        return True

    async def _validate_role_change(
        self,
        team_id: uuid.UUID,
        old_role: str,
        new_role: str,
    ) -> None:
        """
        Validate that a role change is allowed.

        Issue #620.
        """
        if old_role == self.ROLE_OWNER and new_role != self.ROLE_OWNER:
            owner_count = await self._count_owners(team_id)
            if owner_count <= 1:
                raise MembershipError(
                    "Cannot demote the last owner. Add another owner first."
                )

    async def _log_role_change(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        old_role: str,
        new_role: str,
    ) -> None:
        """
        Log audit and info for role change.

        Issue #620.
        """
        await self._audit_log(
            action=AuditAction.TEAM_MEMBER_ROLE_CHANGED,
            resource_type=AuditResourceType.TEAM,
            resource_id=team_id,
            details={
                "user_id": str(user_id),
                "old_role": old_role,
                "new_role": new_role,
            },
        )
        logger.info(
            "Changed role for user %s in team %s: %s -> %s",
            user_id,
            team_id,
            old_role,
            new_role,
        )

    async def change_member_role(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        new_role: str,
    ) -> TeamMembership:
        """
        Change a member's role in a team.

        Args:
            team_id: Team ID
            user_id: User ID
            new_role: New role

        Returns:
            Updated TeamMembership instance

        Raises:
            MembershipError: If invalid role or operation not allowed
        """
        if new_role not in self.VALID_ROLES:
            raise MembershipError(
                f"Invalid role '{new_role}'. Must be one of: {self.VALID_ROLES}"
            )

        membership = await self._get_membership(team_id, user_id)
        if not membership:
            raise MembershipError(f"User {user_id} is not a member of team {team_id}")

        old_role = membership.role
        await self._validate_role_change(team_id, old_role, new_role)

        membership.role = new_role
        membership.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

        await self._log_role_change(team_id, user_id, old_role, new_role)
        return membership

    async def get_team_members(
        self,
        team_id: uuid.UUID,
        role: Optional[str] = None,
    ) -> List[TeamMembership]:
        """
        Get all members of a team.

        Args:
            team_id: Team ID
            role: Filter by role (optional)

        Returns:
            List of TeamMembership instances with user data
        """
        query = (
            select(TeamMembership)
            .options(selectinload(TeamMembership.user))
            .where(TeamMembership.team_id == team_id)
        )

        if role:
            query = query.where(TeamMembership.role == role)

        query = query.order_by(
            # Order: owners first, then admins, then members
            TeamMembership.role.desc(),
            TeamMembership.joined_at,
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_user_teams(self, user_id: uuid.UUID) -> List[Team]:
        """
        Get all teams a user is a member of.

        Args:
            user_id: User ID

        Returns:
            List of Team instances
        """
        query = (
            select(Team)
            .join(TeamMembership)
            .where(TeamMembership.user_id == user_id)
            .where(Team.deleted_at.is_(None))
        )
        query = self.apply_tenant_filter(query, Team)
        query = query.order_by(Team.name)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def is_team_member(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        required_role: Optional[str] = None,
    ) -> bool:
        """
        Check if a user is a member of a team.

        Args:
            team_id: Team ID
            user_id: User ID
            required_role: If specified, check for this specific role

        Returns:
            True if user is a member (with required role if specified)
        """
        membership = await self._get_membership(team_id, user_id)
        if not membership:
            return False

        if required_role:
            return membership.role == required_role

        return True

    async def is_team_admin(self, team_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Check if user is a team owner or admin."""
        membership = await self._get_membership(team_id, user_id)
        if not membership:
            return False
        return membership.role in {self.ROLE_OWNER, self.ROLE_ADMIN}

    # -------------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------------

    async def _find_team_by_name(self, name: str) -> Optional[Team]:
        """Find team by name within current organization."""
        query = (
            select(Team)
            .where(func.lower(Team.name) == name.lower())
            .where(Team.deleted_at.is_(None))
        )
        query = self.apply_tenant_filter(query, Team)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def _get_membership(
        self, team_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[TeamMembership]:
        """Get membership record."""
        result = await self.session.execute(
            select(TeamMembership).where(
                TeamMembership.team_id == team_id,
                TeamMembership.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def _count_owners(self, team_id: uuid.UUID) -> int:
        """Count owners of a team."""
        result = await self.session.execute(
            select(func.count())
            .select_from(TeamMembership)
            .where(
                TeamMembership.team_id == team_id,
                TeamMembership.role == self.ROLE_OWNER,
            )
        )
        return result.scalar() or 0

    async def _audit_log(
        self,
        action: str,
        resource_type: str,
        resource_id: Optional[uuid.UUID],
        details: dict,
        outcome: str = "success",
    ) -> None:
        """Create audit log entry."""
        audit_entry = AuditLog(
            id=uuid.uuid4(),
            org_id=self.context.org_id,
            user_id=self.context.user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            details=details,
        )
        self.session.add(audit_entry)
