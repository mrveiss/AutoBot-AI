# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Team and Team Membership Models

Teams belong to organizations and contain users with specific roles.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from user_management.models.base import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from user_management.models.api_key import APIKey
    from user_management.models.organization import Organization
    from user_management.models.user import User


class TeamRole(str, Enum):
    """Team membership roles."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class Team(Base, TenantMixin, TimestampMixin):
    """
    Team model.

    Attributes:
        id: Unique identifier (UUID)
        org_id: Organization this team belongs to
        name: Team name (unique within organization)
        description: Team description
        settings: Team-specific settings (permissions, resources, etc.)
        is_default: Whether this is the default team for new users
    """

    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Team settings (permissions, workspace config, etc.)
    settings: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    # Default team for new users in this org
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Soft delete
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Unique constraint: team name unique within organization
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_team_org_name"),)

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="teams",
    )

    memberships: Mapped[list["TeamMembership"]] = relationship(
        "TeamMembership",
        back_populates="team",
        cascade="all, delete-orphan",
    )

    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey",
        back_populates="team",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Team(id={self.id}, name={self.name}, org_id={self.org_id})>"

    @property
    def is_deleted(self) -> bool:
        """Check if team is soft-deleted."""
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Soft delete the team."""
        self.deleted_at = datetime.utcnow()

    @property
    def member_count(self) -> int:
        """Get number of team members."""
        return len([m for m in self.memberships if m.user and not m.user.is_deleted])

    def get_members_by_role(self, role: TeamRole) -> list["User"]:
        """Get team members with a specific role."""
        return [
            m.user
            for m in self.memberships
            if m.role == role.value and m.user and not m.user.is_deleted
        ]

    @property
    def owners(self) -> list["User"]:
        """Get team owners."""
        return self.get_members_by_role(TeamRole.OWNER)

    @property
    def admins(self) -> list["User"]:
        """Get team admins."""
        return self.get_members_by_role(TeamRole.ADMIN)


class TeamMembership(Base, TimestampMixin):
    """
    Team membership model.

    Represents the relationship between a user and a team with a role.
    """

    __tablename__ = "team_memberships"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped[str] = mapped_column(
        String(50),
        default=TeamRole.MEMBER.value,
        nullable=False,
    )

    # When the user joined the team
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # Unique constraint: user can only be in a team once
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_user"),)

    # Relationships
    team: Mapped["Team"] = relationship(
        "Team",
        back_populates="memberships",
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="team_memberships",
    )

    def __repr__(self) -> str:
        return (
            f"<TeamMembership(team_id={self.team_id}, "
            f"user_id={self.user_id}, role={self.role})>"
        )

    def is_owner(self) -> bool:
        """Check if this is an owner membership."""
        return self.role == TeamRole.OWNER.value

    def is_admin(self) -> bool:
        """Check if this is an admin membership."""
        return self.role == TeamRole.ADMIN.value

    def can_manage_members(self) -> bool:
        """Check if this member can manage other members."""
        return self.role in (TeamRole.OWNER.value, TeamRole.ADMIN.value)
