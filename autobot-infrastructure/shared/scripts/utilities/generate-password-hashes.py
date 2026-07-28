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

import bcrypt


def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


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
            print('      password_hash: "{password_hash}"')
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
