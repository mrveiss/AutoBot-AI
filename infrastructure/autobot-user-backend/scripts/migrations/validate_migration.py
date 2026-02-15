#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration Validation Script

Validates the data migration was successful:
- Verifies all sessions have owner_id
- Verifies all secrets have owner_id and scope
- Reports any orphaned entities
- Checks data integrity
- Generates validation report

Part of Issue #875 - Session & Secret Data Migration (#608 Phase 7)
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# Add autobot modules to path
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "autobot-user-backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "autobot-shared"))

from autobot_shared.redis_client import get_redis_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MigrationValidator:
    """Validates migration completion and data integrity"""

    def __init__(self, verbose: bool = False):
        """Initialize validator.

        Args:
            verbose: If True, show detailed information for each entity
        """
        self.verbose = verbose
        self.redis_client = None
        self.issues: List[Dict] = []
        self.stats = {
            "sessions": {
                "total": 0,
                "with_owner": 0,
                "without_owner": 0,
                "with_created_at": 0,
                "without_created_at": 0,
                "empty": 0
            },
            "secrets": {
                "total": 0,
                "with_owner": 0,
                "without_owner": 0,
                "with_scope": 0,
                "without_scope": 0,
                "encrypted": 0,
                "unencrypted": 0
            },
            "messages": {
                "total": 0,
                "with_user_id": 0,
                "without_user_id": 0
            },
            "activities": {
                "total": 0,
                "with_user_id": 0,
                "without_user_id": 0
            },
            "indices": {
                "user_sessions": 0,
                "user_secrets": 0,
                "org_sessions": 0,
                "team_sessions": 0
            }
        }

    async def connect_redis(self) -> None:
        """Connect to Redis database"""
        try:
            self.redis_client = await get_redis_client(
                async_client=True,
                database="main"
            )
            await self.redis_client.ping()
            logger.info("Connected to Redis successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def validate_sessions(self) -> None:
        """Validate all sessions have required fields"""
        logger.info("Validating sessions...")

        # Get all session keys
        keys = await self.redis_client.keys("chat:session:*")
        session_ids = [
            key.decode('utf-8').split(':', 2)[2]
            for key in keys
        ]

        self.stats["sessions"]["total"] = len(session_ids)

        for session_id in session_ids:
            try:
                # Get session data
                key = f"chat:session:{session_id}"
                data = await self.redis_client.get(key)

                if not data:
                    self.stats["sessions"]["empty"] += 1
                    self.issues.append({
                        "type": "session",
                        "id": session_id,
                        "severity": "error",
                        "issue": "Session data is empty"
                    })
                    continue

                if isinstance(data, bytes):
                    data = data.decode('utf-8')

                session = json.loads(data)
                metadata = session.get('metadata', {})

                # Check owner
                has_owner = bool(
                    metadata.get('owner') or metadata.get('user_id')
                )
                if has_owner:
                    self.stats["sessions"]["with_owner"] += 1
                else:
                    self.stats["sessions"]["without_owner"] += 1
                    self.issues.append({
                        "type": "session",
                        "id": session_id,
                        "severity": "error",
                        "issue": "Missing owner_id"
                    })

                # Check created_at
                if session.get('created_at'):
                    self.stats["sessions"]["with_created_at"] += 1
                else:
                    self.stats["sessions"]["without_created_at"] += 1
                    self.issues.append({
                        "type": "session",
                        "id": session_id,
                        "severity": "warning",
                        "issue": "Missing created_at timestamp"
                    })

                if self.verbose and has_owner:
                    logger.info(
                        f"Session {session_id}: owner={metadata.get('owner')}"
                    )

            except Exception as e:
                logger.error(f"Error validating session {session_id}: {e}")
                self.issues.append({
                    "type": "session",
                    "id": session_id,
                    "severity": "error",
                    "issue": f"Validation error: {e}"
                })

    async def validate_secrets(self) -> None:
        """Validate all secrets have required fields"""
        logger.info("Validating secrets...")

        # Get all secret keys
        keys = await self.redis_client.keys("secret:*")
        secret_ids = [
            key.decode('utf-8').split(':', 1)[1]
            for key in keys
        ]

        self.stats["secrets"]["total"] = len(secret_ids)

        for secret_id in secret_ids:
            try:
                # Get secret data (stored as hash)
                key = f"secret:{secret_id}"
                secret_data = await self.redis_client.hgetall(key)

                if not secret_data:
                    self.issues.append({
                        "type": "secret",
                        "id": secret_id,
                        "severity": "error",
                        "issue": "Secret data is empty"
                    })
                    continue

                # Decode hash data
                decoded = {}
                for k, v in secret_data.items():
                    key_str = k.decode('utf-8') if isinstance(k, bytes) else k
                    val_str = v.decode('utf-8') if isinstance(v, bytes) else v
                    decoded[key_str] = val_str

                # Check owner_id
                if decoded.get('owner_id'):
                    self.stats["secrets"]["with_owner"] += 1
                else:
                    self.stats["secrets"]["without_owner"] += 1
                    self.issues.append({
                        "type": "secret",
                        "id": secret_id,
                        "severity": "error",
                        "issue": "Missing owner_id"
                    })

                # Check scope
                if decoded.get('scope'):
                    self.stats["secrets"]["with_scope"] += 1
                else:
                    self.stats["secrets"]["without_scope"] += 1
                    self.issues.append({
                        "type": "secret",
                        "id": secret_id,
                        "severity": "error",
                        "issue": "Missing scope"
                    })

                # Check encryption
                value = decoded.get('value', '')
                if self._appears_encrypted(value):
                    self.stats["secrets"]["encrypted"] += 1
                else:
                    self.stats["secrets"]["unencrypted"] += 1
                    self.issues.append({
                        "type": "secret",
                        "id": secret_id,
                        "severity": "warning",
                        "issue": "Value may not be encrypted"
                    })

                if self.verbose and decoded.get('owner_id'):
                    logger.info(
                        f"Secret {secret_id}: "
                        f"owner={decoded.get('owner_id')}, "
                        f"scope={decoded.get('scope')}"
                    )

            except Exception as e:
                logger.error(f"Error validating secret {secret_id}: {e}")
                self.issues.append({
                    "type": "secret",
                    "id": secret_id,
                    "severity": "error",
                    "issue": f"Validation error: {e}"
                })

    def _appears_encrypted(self, value: str) -> bool:
        """Check if a value appears to be encrypted.

        Args:
            value: Value to check

        Returns:
            True if value looks encrypted
        """
        if not value:
            return False

        import re
        base64_pattern = re.compile(r'^[A-Za-z0-9+/]+=*$')
        return bool(base64_pattern.match(value) and len(value) > 20)

    async def validate_messages(self) -> None:
        """Validate messages have user_id"""
        logger.info("Validating messages...")

        # Get all message lists
        message_keys = await self.redis_client.keys("chat:messages:*")

        for messages_key in message_keys:
            try:
                # Get all messages
                message_count = await self.redis_client.llen(messages_key)
                self.stats["messages"]["total"] += message_count

                if message_count == 0:
                    continue

                messages_data = await self.redis_client.lrange(
                    messages_key,
                    0,
                    -1
                )

                session_id = messages_key.decode('utf-8').split(':', 2)[2]

                for msg_data in messages_data:
                    try:
                        message = json.loads(msg_data)

                        # Check user_id
                        if message.get('user_id'):
                            self.stats["messages"]["with_user_id"] += 1
                        else:
                            # Only flag user role messages without user_id
                            if message.get('role') == 'user':
                                self.stats["messages"]["without_user_id"] += 1
                                self.issues.append({
                                    "type": "message",
                                    "id": session_id,
                                    "severity": "warning",
                                    "issue": "User message missing user_id"
                                })

                    except Exception as e:
                        logger.debug(f"Error parsing message: {e}")

            except Exception as e:
                logger.error(f"Error validating messages: {e}")

    async def validate_activities(self) -> None:
        """Validate activities have user_id"""
        logger.info("Validating activities...")

        # Get all activity keys
        activity_keys = await self.redis_client.keys("activity:*")
        self.stats["activities"]["total"] = len(activity_keys)

        for activity_key in activity_keys:
            try:
                activity_data = await self.redis_client.hgetall(activity_key)

                if not activity_data:
                    continue

                # Decode activity data
                decoded = {}
                for k, v in activity_data.items():
                    key_str = k.decode('utf-8') if isinstance(k, bytes) else k
                    val_str = v.decode('utf-8') if isinstance(v, bytes) else v
                    decoded[key_str] = val_str

                # Check user_id
                if decoded.get('user_id'):
                    self.stats["activities"]["with_user_id"] += 1
                else:
                    self.stats["activities"]["without_user_id"] += 1
                    activity_id = (
                        activity_key.decode('utf-8')
                        if isinstance(activity_key, bytes)
                        else activity_key
                    )
                    self.issues.append({
                        "type": "activity",
                        "id": activity_id,
                        "severity": "warning",
                        "issue": "Activity missing user_id"
                    })

            except Exception as e:
                logger.debug(f"Error validating activity: {e}")

    async def validate_indices(self) -> None:
        """Validate Redis indices are properly populated"""
        logger.info("Validating indices...")

        # Count user sessions
        user_keys = await self.redis_client.keys("user:sessions:*")
        self.stats["indices"]["user_sessions"] = len(user_keys)

        # Count user secrets
        user_secret_keys = await self.redis_client.keys("user:secrets:*")
        self.stats["indices"]["user_secrets"] = len(user_secret_keys)

        # Count org sessions
        org_keys = await self.redis_client.keys("org:sessions:*")
        self.stats["indices"]["org_sessions"] = len(org_keys)

        # Count team sessions
        team_keys = await self.redis_client.keys("team:sessions:*")
        self.stats["indices"]["team_sessions"] = len(team_keys)

    def _format_stat_with_pct(
        self,
        label: str,
        value: int,
        total: int
    ) -> str:
        """Format a statistic with percentage.

        Helper for generate_report to avoid E501 line length violations.
        """
        pct = self._percentage(value, total)
        return f"  {label}: {value} ({pct}%)"

    def generate_report(self) -> str:
        """Generate validation report.

        Returns:
            Report text
        """
        report = []
        report.append("=" * 70)
        report.append("MIGRATION VALIDATION REPORT")
        report.append(f"Generated: {datetime.utcnow().isoformat()}")
        report.append("=" * 70)
        report.append("")

        # Sessions
        report.append("SESSIONS:")
        report.append(f"  Total: {self.stats['sessions']['total']}")
        report.append(self._format_stat_with_pct(
            "With owner",
            self.stats["sessions"]["with_owner"],
            self.stats["sessions"]["total"]
        ))
        report.append(self._format_stat_with_pct(
            "Without owner",
            self.stats["sessions"]["without_owner"],
            self.stats["sessions"]["total"]
        ))
        report.append(self._format_stat_with_pct(
            "With created_at",
            self.stats["sessions"]["with_created_at"],
            self.stats["sessions"]["total"]
        ))
        report.append(f"  Empty sessions: {self.stats['sessions']['empty']}")
        report.append("")

        # Secrets
        report.append("SECRETS:")
        report.append(f"  Total: {self.stats['secrets']['total']}")
        report.append(
                        self._format_stat_with_pct(
            "With owner",  # noqa: E122
            self.stats["secrets"]["with_owner"],  # noqa: E122
            self.stats["secrets"]["total"]  # noqa: E122
            )  # noqa: E122
            )
        report.append(
                        self._format_stat_with_pct(
            "Without owner",  # noqa: E122
            self.stats["secrets"]["without_owner"],  # noqa: E122
            self.stats["secrets"]["total"]  # noqa: E122
            )  # noqa: E122
            )
        report.append(
                        self._format_stat_with_pct(
            "With scope",  # noqa: E122
            self.stats["secrets"]["with_scope"],  # noqa: E122
            self.stats["secrets"]["total"]  # noqa: E122
            )  # noqa: E122
            )
        report.append(
                        self._format_stat_with_pct(
            "Encrypted",  # noqa: E122
            self.stats["secrets"]["encrypted"],  # noqa: E122
            self.stats["secrets"]["total"]  # noqa: E122
            )  # noqa: E122
            )
        report.append("")

        # Messages
        report.append("MESSAGES:")
        report.append(f"  Total: {self.stats['messages']['total']}")
        report.append(
                        self._format_stat_with_pct(
            "With user_id",  # noqa: E122
            self.stats["messages"]["with_user_id"],  # noqa: E122
            self.stats["messages"]["total"]  # noqa: E122
            )  # noqa: E122
            )
        report.append(
            f"  Without user_id: {self.stats['messages']['without_user_id']}"
        )
        report.append("")

        # Activities
        report.append("ACTIVITIES:")
        report.append(f"  Total: {self.stats['activities']['total']}")
        report.append(
                        self._format_stat_with_pct(
            "With user_id",  # noqa: E122
            self.stats["activities"]["with_user_id"],  # noqa: E122
            self.stats["activities"]["total"]  # noqa: E122
            )  # noqa: E122
            )
        report.append(
            f"  Without user_id: {self.stats['activities']['without_user_id']}"
        )
        report.append("")

        # Indices
        report.append("INDICES:")
        report.append(
            f"  User sessions: {self.stats['indices']['user_sessions']}"
        )
        report.append(
            f"  User secrets: {self.stats['indices']['user_secrets']}"
        )
        report.append(
            f"  Org sessions: {self.stats['indices']['org_sessions']}"
        )
        report.append(
            f"  Team sessions: {self.stats['indices']['team_sessions']}"
        )
        report.append("")

        # Issues
        if self.issues:
            report.append("ISSUES FOUND:")
            report.append(
                f"  Total: {len(self.issues)}"
            )

            errors = [i for i in self.issues if i["severity"] == "error"]
            warnings = [i for i in self.issues if i["severity"] == "warning"]

            report.append(f"  Errors: {len(errors)}")
            report.append(f"  Warnings: {len(warnings)}")
            report.append("")

            # Show first 20 issues
            report.append("First 20 issues:")
            for issue in self.issues[:20]:
                report.append(
                    f"  [{issue['severity'].upper()}] {issue['type']} "
                    f"{issue['id']}: {issue['issue']}"
                )

            if len(self.issues) > 20:
                report.append(
                    f"  ... and {len(self.issues) - 20} more issues"
                )
        else:
            report.append("NO ISSUES FOUND - Migration completed successfully!")

        report.append("")
        report.append("=" * 70)

        return '\n'.join(report)

    def _percentage(self, value: int, total: int) -> str:
        """Calculate percentage with 1 decimal place.

        Args:
            value: Numerator
            total: Denominator

        Returns:
            Percentage string
        """
        if total == 0:
            return "0.0"
        return f"{(value / total * 100):.1f}"

    async def run(self) -> None:
        """Run validation"""
        logger.info("Starting migration validation")

        await self.connect_redis()

        # Run all validations
        await self.validate_sessions()
        await self.validate_secrets()
        await self.validate_messages()
        await self.validate_activities()
        await self.validate_indices()

        # Generate and save report
        report = self.generate_report()
        print("\n" + report)

        # Save to file
        report_file = Path("/tmp/migration_validation_report.txt")
        report_file.write_text(report)
        logger.info(f"\nReport saved to: {report_file}")

        # Save issues to JSON
        if self.issues:
            issues_file = Path("/tmp/migration_issues.json")
            issues_file.write_text(
                json.dumps(self.issues, indent=2)
            )
            logger.info(f"Issues details saved to: {issues_file}")

        # Exit with error code if issues found
        if any(i["severity"] == "error" for i in self.issues):
            sys.exit(1)


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Validate migration completion"
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed information for each entity'
    )
    args = parser.parse_args()

    validator = MigrationValidator(verbose=args.verbose)
    await validator.run()


if __name__ == '__main__':
    asyncio.run(main())
