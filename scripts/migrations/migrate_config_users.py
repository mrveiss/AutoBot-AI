#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migrate Users from YAML Config to PostgreSQL Database

This script migrates existing users from the security_config YAML configuration
to the PostgreSQL database for the new user management system.

Usage:
    python scripts/migrations/migrate_config_users.py [--dry-run] [--org-name "Organization Name"]

Options:
    --dry-run       Preview migration without making changes
    --org-name      Organization name to create (default: "Default Organization")
    --org-slug      Organization slug (default: "default")

Environment:
    Requires AUTOBOT_USER_MODE to be set to single_company, multi_company, or provider
    Requires PostgreSQL connection environment variables
"""

import argparse
import asyncio
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.config import UnifiedConfigManager
from src.user_management.config import DeploymentMode, get_deployment_config
from src.user_management.database import db_session_context, init_database
from src.user_management.models import (
    Organization,
    User,
    Role,
    Permission,
    RolePermission,
    UserRole,
)
from src.user_management.models.role import SYSTEM_PERMISSIONS, SYSTEM_ROLES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ConfigUserMigrator:
    """Migrates users from YAML config to PostgreSQL."""

    def __init__(self, dry_run: bool = False, org_name: str = "Default Organization", org_slug: str = "default"):
        self.dry_run = dry_run
        self.org_name = org_name
        self.org_slug = org_slug
        self.config = UnifiedConfigManager()
        self.stats = {
            "organizations_created": 0,
            "users_migrated": 0,
            "users_skipped": 0,
            "roles_created": 0,
            "permissions_created": 0,
        }

    async def migrate(self) -> dict:
        """
        Run the full migration.

        Returns:
            Migration statistics
        """
        deployment_config = get_deployment_config()

        if deployment_config.mode == DeploymentMode.SINGLE_USER:
            logger.warning(
                "Deployment mode is 'single_user'. User management system is not "
                "needed in this mode. Set AUTOBOT_USER_MODE to single_company,"
                "multi_company, or provider to enable database user management."
            )
            return self.stats

        if not deployment_config.postgres_enabled:
            logger.error(
                "PostgreSQL is not enabled for this deployment mode. "
                "Please configure PostgreSQL connection settings."
            )
            return self.stats

        logger.info("Starting user migration from config to PostgreSQL")
        logger.info("Deployment mode: %s", deployment_config.mode.value)
        logger.info("Dry run: %s", self.dry_run)

        try:
            await init_database()

            async with db_session_context() as session:
                # Step 1: Create system permissions
                await self._create_system_permissions(session)

                # Step 2: Create organization (for single_company+ modes)
                org = await self._create_organization(session)

                # Step 3: Create system roles
                await self._create_system_roles(session, org)

                # Step 4: Migrate users
                await self._migrate_users(session, org)

                if not self.dry_run:
                    await session.commit()
                    logger.info("Migration committed successfully")
                else:
                    await session.rollback()
                    logger.info("Dry run - changes rolled back")

        except Exception as e:
            logger.error("Migration failed: %s", e)
            raise

        self._print_summary()
        return self.stats

    async def _create_system_permissions(self, session) -> dict[str, uuid.UUID]:
        """Create system permissions from constants."""
        logger.info("Creating system permissions...")
        permission_ids = {}

        for perm_data in SYSTEM_PERMISSIONS:
            perm_id = uuid.uuid4()
            permission = Permission(
                id=perm_id,
                name=perm_data["name"],
                description=perm_data["description"],
                resource=perm_data["resource"],
                action=perm_data["action"],
            )
            session.add(permission)
            permission_ids[perm_data["name"]] = perm_id
            self.stats["permissions_created"] += 1
            logger.debug("Created permission: %s", perm_data["name"])

        await session.flush()
        logger.info("Created %d system permissions", self.stats["permissions_created"])
        return permission_ids

    async def _create_organization(self, session) -> Organization:
        """Create the default organization."""
        logger.info("Creating organization: %s (%s)", self.org_name, self.org_slug)

        org = Organization(
            id=uuid.uuid4(),
            name=self.org_name,
            slug=self.org_slug,
            description="Migrated from config-based authentication",
            settings={},
            subscription_tier="free",
            max_users=-1,  # Unlimited
            is_active=True,
        )
        session.add(org)
        await session.flush()

        self.stats["organizations_created"] += 1
        logger.info("Created organization with ID: %s", org.id)
        return org

    async def _create_system_roles(
        self, session, org: Organization
    ) -> dict[str, uuid.UUID]:
        """Create system roles from constants."""
        logger.info("Creating system roles...")
        role_ids = {}

        for role_data in SYSTEM_ROLES:
            role_id = uuid.uuid4()

            # System roles have no org_id (they're global)
            # But we also create org-specific copies for user assignment
            role = Role(
                id=role_id,
                org_id=None,  # Global system role
                name=role_data["name"],
                description=role_data["description"],
                is_system=True,
                priority=role_data["priority"],
            )
            session.add(role)
            role_ids[role_data["name"]] = role_id
            self.stats["roles_created"] += 1
            logger.debug("Created role: %s", role_data["name"])

        await session.flush()
        logger.info("Created %d system roles", self.stats["roles_created"])
        return role_ids

    async def _migrate_users(self, session, org: Organization) -> None:
        """Migrate users from security_config."""
        logger.info("Migrating users from config...")

        security_config = self.config.get("security_config", {})
        allowed_users = security_config.get("allowed_users", {})
        config_roles = security_config.get("roles", {})

        if not allowed_users:
            logger.warning("No users found in security_config.allowed_users")
            return

        # Get role mapping from config roles to system roles
        role_mapping = self._map_config_roles_to_system(config_roles)

        for username, user_data in allowed_users.items():
            await self._migrate_user(session, org, username, user_data, role_mapping)

        logger.info(
            "Migrated %d users, skipped %d",
            self.stats["users_migrated"],
            self.stats["users_skipped"],
        )

    def _map_config_roles_to_system(self, config_roles: dict) -> dict[str, str]:
        """
        Map config role names to system role names.

        The config uses 'admin', 'developer', 'readonly' etc.
        System uses 'Platform Admin', 'Org Admin', 'Member', 'Viewer'.
        """
        mapping = {
            "admin": "Platform Admin",
            "developer": "Org Admin",  # Map developer to org admin
            "readonly": "Viewer",
            "user": "Member",
            "member": "Member",
            "viewer": "Viewer",
            "guest": "Viewer",
        }

        # Log any unmapped roles
        for role_name in config_roles:
            if role_name.lower() not in mapping:
                logger.warning(
                    "Unknown config role '%s', will map to 'Member'", role_name
                )
                mapping[role_name.lower()] = "Member"

        return mapping

    async def _migrate_user(
        self,
        session,
        org: Organization,
        username: str,
        user_data: dict,
        role_mapping: dict[str, str],
    ) -> None:
        """Migrate a single user."""
        email = user_data.get("email", f"{username}@autobot.local")
        config_role = user_data.get("role", "user")
        password_hash = user_data.get("password_hash")
        created_at_str = user_data.get("created_at")

        # Parse created_at if available
        created_at = datetime.now(timezone.utc)
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        # Determine if platform admin
        is_platform_admin = config_role.lower() == "admin"

        logger.info("Migrating user: %s (role=%s, email=%s)", username, config_role, email)

        user = User(
            id=uuid.uuid4(),
            org_id=org.id,
            email=email,
            username=username,
            password_hash=password_hash,
            display_name=username.title(),
            is_active=True,
            is_verified=True,  # Existing users are verified
            mfa_enabled=False,
            is_platform_admin=is_platform_admin,
            preferences={},
            created_at=created_at,
            updated_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.flush()

        # Assign role
        system_role_name = role_mapping.get(config_role.lower(), "Member")
        await self._assign_user_role(session, user.id, system_role_name)

        self.stats["users_migrated"] += 1

    async def _assign_user_role(
        self, session, user_id: uuid.UUID, role_name: str
    ) -> None:
        """Assign a role to a user by role name."""
        from sqlalchemy import select

        # Find the role
        result = await session.execute(select(Role).where(Role.name == role_name))
        role = result.scalar_one_or_none()

        if not role:
            logger.warning("Role '%s' not found, skipping role assignment", role_name)
            return

        user_role = UserRole(
            user_id=user_id,
            role_id=role.id,
            assigned_by=None,  # System migration
        )
        session.add(user_role)
        logger.debug("Assigned role '%s' to user %s", role_name, user_id)

    def _print_summary(self) -> None:
        """Print migration summary."""
        logger.info("")
        logger.info("=" * 50)
        logger.info("Migration Summary")
        logger.info("=" * 50)
        logger.info("Organizations created: %d", self.stats["organizations_created"])
        logger.info("Permissions created:   %d", self.stats["permissions_created"])
        logger.info("Roles created:         %d", self.stats["roles_created"])
        logger.info("Users migrated:        %d", self.stats["users_migrated"])
        logger.info("Users skipped:         %d", self.stats["users_skipped"])
        logger.info("=" * 50)


async def main():
    parser = argparse.ArgumentParser(
        description="Migrate users from YAML config to PostgreSQL database"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview migration without making changes",
    )
    parser.add_argument(
        "--org-name",
        default="Default Organization",
        help="Organization name to create",
    )
    parser.add_argument(
        "--org-slug",
        default="default",
        help="Organization slug",
    )

    args = parser.parse_args()

    migrator = ConfigUserMigrator(
        dry_run=args.dry_run,
        org_name=args.org_name,
        org_slug=args.org_slug,
    )

    try:
        stats = await migrator.migrate()
        if stats["users_migrated"] > 0 or args.dry_run:
            sys.exit(0)
        else:
            logger.error("No users were migrated")
            sys.exit(1)
    except Exception as e:
        logger.error("Migration failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
