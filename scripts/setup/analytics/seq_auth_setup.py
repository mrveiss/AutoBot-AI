#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Seq Authentication and Basic Setup
=================================

Handles Seq authentication and creates basic analytics setup for AutoBot.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests


def create_seq_api_key(
    seq_url=None,
    username=None,
    password=None,
):
    """Create API key for Seq access."""

    # Get configuration from environment variables or prompt
    seq_url = seq_url or os.getenv("AUTOBOT_LOG_VIEWER_URL", "http://localhost:5341")
    username = username or os.getenv("SEQ_USERNAME", "admin")
    password = password or os.getenv("SEQ_PASSWORD")

    if not password:
        print("⚠️  No SEQ_PASSWORD environment variable found")
        password = input("Please enter Seq admin password: ").strip()
        if not password:
            print("❌ Password is required")
            return None

    print("🔐 Setting up Seq API authentication...")
    print(f"   URL: {seq_url}")
    print(f"   Username: {username}")

    session = requests.Session()

    try:
        # First, try to login to get session
        login_data = {"Username": username, "Password": password}

        response = session.post(f"{seq_url}/api/users/login", json=login_data)
        if response.status_code == 200:
            print("✅ Logged into Seq successfully")

            # Now try to create an API key
            api_key_data = {
                "Title": "AutoBot Analytics",
                "Token": "autobot-analytics-key",
                "AppliedPermissions": ["Ingest", "Read", "Setup", "Write"],
            }

            response = session.post(f"{seq_url}/api/apikeys", json=api_key_data)
            if response.status_code in [200, 201]:
                api_key_info = response.json()
                print(f"✅ Created API key: {api_key_info.get('Token', 'unknown')}")
                return api_key_info.get("Token")
            else:
                print(f"⚠️  Could not create API key: {response.status_code}")
                print(f"   Response: {response.text}")
                return None
        else:
            print(f"❌ Login failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return None

    except Exception as e:
        print(f"❌ Authentication error: {e}")
        return None


def reset_seq_admin_password(seq_url=None, new_password=None):
    """Reset Seq admin password using Docker container access."""

    seq_url = seq_url or os.getenv("AUTOBOT_LOG_VIEWER_URL", "http://localhost:5341")

    print("🔄 Attempting to reset Seq admin password...")

    try:
        import subprocess

        # Find the Seq container
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}", "--filter", "name=seq"],
            capture_output=True,
            text=True,
            check=True,
        )

        seq_containers = [line for line in result.stdout.strip().split("\n") if line]

        if not seq_containers:
            print("❌ No Seq container found")
            return False

        seq_container = seq_containers[0]
        print(f"📦 Found Seq container: {seq_container}")

        # Get new password if not provided
        if not new_password:
            new_password = input("Enter new admin password: ").strip()
            confirm_password = input("Confirm new password: ").strip()

            if new_password != confirm_password:
                print("❌ Passwords do not match")
                return False

        if not new_password:
            print("❌ Password cannot be empty")
            return False

        # Reset password using seqcli in the container
        reset_command = [
            "docker",
            "exec",
            seq_container,
            "seqcli",
            "user",
            "update",
            "-n",
            "admin",
            "-p",
            new_password,
            "-s",
            "http://localhost",
        ]

        print("🔐 Resetting admin password...")
        result = subprocess.run(reset_command, capture_output=True, text=True)

        if result.returncode == 0:
            print("✅ Password reset successfully")

            # Set environment variable for future use
            os.environ["SEQ_PASSWORD"] = new_password
            print("💡 Password set in environment variable SEQ_PASSWORD")

            return True
        else:
            print(f"❌ Password reset failed: {result.stderr}")
            return False

    except subprocess.CalledProcessError as e:
        print(f"❌ Docker command failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Error resetting password: {e}")
        return False


def setup_basic_seq_queries(seq_url=None, api_key=None):
    """Setup basic queries using direct SQL approach."""

    seq_url = seq_url or os.getenv("AUTOBOT_LOG_VIEWER_URL", "http://localhost:5341")

    print("📊 Setting up basic AutoBot queries in Seq...")

    headers = {"Content-Type": "application/json"}

    if api_key:
        headers["X-Seq-ApiKey"] = api_key

    # Basic queries that can be executed directly
    basic_queries = [
        {
            "name": "AutoBot Error Summary",
            "query": "select @l as Level, count(*) as Count from stream where Application = 'AutoBot' and @l = 'Error' group by @l",
            "description": "Summary of AutoBot errors",
        },
        {
            "name": "AutoBot Container Activity",
            "query": "select ContainerName, count(*) as LogCount from stream where LogType = 'DockerContainer' and @t >= Now() - 1h group by ContainerName",
            "description": "Recent container activity",
        },
        {
            "name": "AutoBot Recent Errors",
            "query": "select top 20 @t, Source, @mt from stream where Application = 'AutoBot' and @l = 'Error' order by @t desc",
            "description": "Most recent errors",
        },
    ]

    print("📋 Queries available for manual creation in Seq:")
    for i, query in enumerate(basic_queries, 1):
        print(f"\n{i}. {query['name']}")
        print(f"   Description: {query['description']}")
        print(f"   Query: {query['query']}")

    # Save queries to file for manual import
    queries_file = Path(__file__).parent.parent / "config" / "seq-basic-queries.json"
    with open(queries_file, "w") as f:
        json.dump(basic_queries, f, indent=2)

    print(f"\n💾 Queries saved to: {queries_file}")
    print(f"📝 You can manually create these queries in Seq at: {seq_url}")


def verify_seq_logs(seq_url=None):
    """Verify that logs are being received in Seq."""

    seq_url = seq_url or os.getenv("AUTOBOT_LOG_VIEWER_URL", "http://localhost:5341")

    print("🔍 Verifying AutoBot logs in Seq...")

    try:
        # Query for AutoBot logs
        response = requests.get(
            f"{seq_url}/api/events",
            params={"filter": "Application = 'AutoBot'", "count": 10},
        )

        if response.status_code == 200:
            events = response.json()
            event_count = len(events.get("Events", []))
            print(f"✅ Found {event_count} AutoBot log events in Seq")

            if event_count > 0:
                print("📝 Recent AutoBot log entries:")
                for event in events.get("Events", [])[:5]:
                    timestamp = event.get("@t", "unknown")
                    level = event.get("@l", "Info")
                    message = event.get("@mt", "No message")
                    source = event.get("Source", "Unknown")
                    print(
                        f"   [{timestamp[:19]}] {level}: {message[:80]}... (from {source})"
                    )

            return event_count > 0
        else:
            print(f"⚠️  Could not query Seq events: {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Error verifying Seq logs: {e}")
        return False


def main():
    """Entry point for Seq authentication and API key configuration."""
    seq_url = os.getenv("AUTOBOT_LOG_VIEWER_URL", "http://localhost:5341")

    print("🚀 AutoBot Seq Analytics Configuration")
    print(f"   Seq URL: {seq_url}")

    # Try to create API key
    api_key = create_seq_api_key(seq_url)

    # If authentication failed, offer to reset password
    if not api_key:
        print("\n❌ Authentication failed!")
        print("This often happens after Docker container restart.")

        reset_choice = (
            input("\nWould you like to reset the Seq admin password? (y/N): ")
            .strip()
            .lower()
        )

        if reset_choice in ["y", "yes"]:
            if reset_seq_admin_password(seq_url):
                print("\n🔄 Retrying authentication with new password...")
                api_key = create_seq_api_key(seq_url)
            else:
                print("❌ Password reset failed")
        else:
            print("💡 You can manually reset the password later by running:")
            print("   python scripts/seq_auth_setup.py --reset-password")

    # Setup basic queries
    setup_basic_seq_queries(seq_url, api_key)

    # Verify logs are present
    has_logs = verify_seq_logs(seq_url)

    print("\n🎉 Seq configuration complete!")
    print(f"   🔐 API Key created: {'Yes' if api_key else 'No'}")
    print(f"   📊 Logs present: {'Yes' if has_logs else 'No'}")
    print("\n🌐 Next steps:")
    print(f"   1. Access Seq at: {seq_url}")
    print("   2. Login with admin and the password you set")
    print("   3. Manually create the queries shown above")
    print("   4. Create dashboards using those queries")
    print("   5. Set up alerts for critical errors")

    # Save current password to environment if successful
    if api_key and os.getenv("SEQ_PASSWORD"):
        print("\n💡 To avoid prompts in the future, set:")
        print(f"   export SEQ_PASSWORD='{os.getenv('SEQ_PASSWORD')}'")
        print("   or add it to your .env file")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AutoBot Seq Analytics Configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/seq_auth_setup.py                    # Interactive setup
  python scripts/seq_auth_setup.py --reset-password   # Reset admin password

Environment Variables:
  AUTOBOT_LOG_VIEWER_URL  # Seq URL (default: http://localhost:5341)
  SEQ_USERNAME            # Username (default: admin)
  SEQ_PASSWORD            # Password (will prompt if not set)
        """,
    )

    parser.add_argument(
        "--reset-password", action="store_true", help="Reset Seq admin password"
    )

    parser.add_argument("--seq-url", help="Seq server URL")

    parser.add_argument("--username", help="Admin username")

    args = parser.parse_args()

    if args.reset_password:
        # Just reset password
        if reset_seq_admin_password(args.seq_url):
            print("✅ Password reset completed successfully")
            sys.exit(0)
        else:
            print("❌ Password reset failed")
            sys.exit(1)
    else:
        # Run full setup
        main()
