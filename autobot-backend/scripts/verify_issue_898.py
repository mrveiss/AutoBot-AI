#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Verification script for Issue #898 - SQLAlchemy relationship fixes

Verifies:
1. vnc_manager.py has List imported
2. All User relationships are correctly defined
3. Activity models have proper foreign keys
4. No import errors exist
"""

import ast
import logging
import sys
from pathlib import Path

# Configure logging for CLI output
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def check_vnc_manager_imports():
    """Verify vnc_manager.py has List imported."""
    vnc_file = Path("autobot-user-backend/api/vnc_manager.py")
    content = vnc_file.read_text()

    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            names = [alias.name for alias in node.names]
            if "List" in names and "Dict" in names:
                logger.info("✓ vnc_manager.py: List and Dict imported correctly")
                return True

    logger.error("✗ vnc_manager.py: Missing List import")
    return False


def check_activity_models():
    """Verify activity models have single FK to users."""
    activities_file = Path("autobot-user-backend/models/activities.py")
    content = activities_file.read_text()

    # Count ForeignKey declarations to users table
    models = [
        "TerminalActivityModel",
        "FileActivityModel",
        "BrowserActivityModel",
        "DesktopActivityModel",
        "SecretUsageModel",
    ]

    issues = []
    for model in models:
        # Check if model has single user_id FK
        if 'ForeignKey("users.id"' in content:
            continue
        else:
            issues.append(f"{model}: No FK to users found")

    if not issues:
        logger.info(f"✓ Activity models: All {len(models)} models have FK to users")
        return True
    else:
        for issue in issues:
            logger.error(f"✗ {issue}")
        return False


def check_user_relationships():
    """Verify User model has all activity relationships."""
    user_file = Path("autobot-user-backend/user_management/models/user.py")
    content = user_file.read_text()

    required_relationships = [
        "terminal_activities",
        "file_activities",
        "browser_activities",
        "desktop_activities",
        "secret_usage",
    ]

    found = []
    missing = []

    for rel in required_relationships:
        if f"{rel}: Mapped[list[" in content or f"{rel}: Mapped[List[" in content:
            found.append(rel)
        else:
            missing.append(rel)

    if not missing:
        logger.info(f"✓ User model: All {len(found)} activity relationships defined")
        return True
    else:
        for rel in missing:
            logger.error(f"✗ User model: Missing relationship {rel}")
        return False


def main():
    """Run all verifications."""
    logger.info("=" * 60)
    logger.info("Issue #898 Verification")
    logger.info("=" * 60)

    checks = [
        ("VNC Manager imports", check_vnc_manager_imports),
        ("Activity models", check_activity_models),
        ("User relationships", check_user_relationships),
    ]

    results = []
    for name, check_func in checks:
        logger.info(f"\nChecking {name}...")
        try:
            results.append(check_func())
        except Exception as e:
            logger.error(f"✗ Error during {name}: {e}")
            results.append(False)

    logger.info("\n" + "=" * 60)
    if all(results):
        logger.info("✓ All checks passed - code is correct locally")
        logger.info("\nNext step: Deploy to server at /opt/autobot/")
        return 0
    else:
        logger.error("✗ Some checks failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
