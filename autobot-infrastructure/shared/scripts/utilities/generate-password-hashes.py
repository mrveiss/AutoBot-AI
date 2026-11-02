#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Generate password hashes for AutoBot authentication system
Usage: python generate-password-hashes.py
"""

import getpass
import sys
from pathlib import Path

# Runs from any directory with no PYTHONPATH: put the repository root on the path for
# `autobot_shared` (#18289).
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from autobot_shared.auth import hash_password  # noqa: E402


def main():
    """Entry point for interactive password hash generation."""
    print("AutoBot Password Hash Generator")
    print("=" * 40)

    # Default users
    users = ["admin", "user"]

    for username in users:
        print(f"\n🔐 Setting password for user '{username}':")
        while True:
            password = getpass.getpass("Enter password: ")
            if len(password) < 6:
                print("❌ Password must be at least 6 characters")
                continue

            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                print("❌ Passwords don't match")
                continue

            # Generate hash
            password_hash = hash_password(password)
            print(f"✅ Hash generated for {username}")
            print(f"Hash: {password_hash}")

            # Update config suggestion
            print(f"\n📝 Update config.yaml for user '{username}':")
            print(f"    {username}:")
            print(f'      password_hash: "{password_hash}"')
            break

    print("\n✅ All password hashes generated successfully!")
    print("\n📋 Security Notes:")
    print("- Replace the placeholder hashes in config/config.yaml")
    print("- Store the plaintext passwords securely for initial login")
    print("- Consider implementing password change functionality")
    print("- Use strong, unique passwords for production deployment")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Password generation cancelled")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
