#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Seq Authentication and Basic Setup
=================================

Handles Seq authentication and creates basic analytics setup for AutoBot.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


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
        logger.warning("No SEQ_PASSWORD environment variable found")
        password = input("Please enter Seq admin password: ").strip()
        if not password:
            logger.error("Password is required")
            return None

    logger.info("Setting up Seq API authentication...")
    logger.info("   URL: %s", seq_url)
    logger.info("   Username: %s", username)

    session = requests.Session()

    try:
        # First, try to login to get session
        # CodeQL: false positive — password must be sent to Seq login API
        login_data = {"Username": username, "Password": password}  # noqa: S106

        response = session.post(f"{seq_url}/api/users/login", json=login_data)
        if response.status_code == 200:
            logger.info("Logged into Seq successfully")

            # Now try to create an API key
            api_key_data = {
                "Title": "AutoBot Analytics",
                "Token": "autobot-analytics-key",
                "AppliedPermissions": ["Ingest", "Read", "Setup", "Write"],
            }

            response = session.post(f"{seq_url}/api/apikeys", json=api_key_data)
            if response.status_code in [200, 201]:
                api_key_info = response.json()
                token = api_key_info.get("Token")
                # Show only last 4 chars for confirmation
                suffix = token[-4:] if token else "????"
                logger.info("Created API key: ****%s", suffix)
                return token
            else:
                logger.warning("Could not create API key: %s", response.status_code)
                logger.warning("   Response: %s", response.text)
                return None
        else:
            logger.error("Login failed: %s", response.status_code)
            logger.error("   Response: %s", response.text)
            return None

    except Exception as e:
        logger.error("Authentication error: %s", e)
        return None


def _find_seq_container() -> str:
    """Find the running Seq Docker container name (#1792).

    Returns the first matching container name, or empty string if none found.
    """
    import subprocess

    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}", "--filter", "name=seq"],
        capture_output=True,
        text=True,
        check=True,
    )
    containers = [line for line in result.stdout.strip().split("\n") if line]
    return containers[0] if containers else ""


def _prompt_new_password() -> str:
    """Prompt user for a new password with confirmation (#1792).

    Returns the confirmed password, or empty string on mismatch/blank.
    """
    new_password = input("Enter new admin password: ").strip()
    confirm_password = input("Confirm new password: ").strip()
    if new_password != confirm_password:
        logger.error("Passwords do not match")
        return ""
    return new_password


def _run_seqcli_password_reset(seq_container: str, new_password: str) -> bool:
    """Execute seqcli password reset inside the given Docker container (#1792).

    Returns True on success, False on failure.
    """
    import subprocess

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
    logger.info("Resetting admin password...")
    result = subprocess.run(reset_command, capture_output=True, text=True)
    if result.returncode == 0:
        logger.info("Password reset successfully")
        os.environ["SEQ_PASSWORD"] = new_password
        logger.info("Password set in environment variable SEQ_PASSWORD")
        return True
    logger.error("Password reset failed: %s", result.stderr)
    return False


def reset_seq_admin_password(seq_url=None, new_password=None):
    """Reset Seq admin password using Docker container access (#1792)."""
    import subprocess

    seq_url = seq_url or os.getenv("AUTOBOT_LOG_VIEWER_URL", "http://localhost:5341")
    logger.info("Attempting to reset Seq admin password...")

    try:
        seq_container = _find_seq_container()
        if not seq_container:
            logger.error("No Seq container found")
            return False
        logger.info("Found Seq container: %s", seq_container)

        if not new_password:
            new_password = _prompt_new_password()

        if not new_password:
            logger.error("Password cannot be empty")
            return False

        return _run_seqcli_password_reset(seq_container, new_password)

    except subprocess.CalledProcessError as e:
        logger.error("Docker command failed: %s", e)
        return False
    except Exception as e:
        logger.error("Error resetting password: %s", e)
        return False


def setup_basic_seq_queries(seq_url=None, api_key=None):
    """Setup basic queries using direct SQL approach."""

    seq_url = seq_url or os.getenv("AUTOBOT_LOG_VIEWER_URL", "http://localhost:5341")

    logger.info("Setting up basic AutoBot queries in Seq...")

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

    logger.info("Queries available for manual creation in Seq:")
    for i, query in enumerate(basic_queries, 1):
        logger.info("%d. %s", i, query["name"])
        logger.info("   Description: %s", query["description"])
        logger.info("   Query: %s", query["query"])

    # Save queries to file for manual import
    queries_file = Path(__file__).parent.parent / "config" / "seq-basic-queries.json"
    with open(queries_file, "w", encoding="utf-8") as f:
        json.dump(basic_queries, f, indent=2)

    logger.info("Queries saved to: %s", queries_file)
    logger.info("You can manually create these queries in Seq at: %s", seq_url)


def verify_seq_logs(seq_url=None):
    """Verify that logs are being received in Seq."""

    seq_url = seq_url or os.getenv("AUTOBOT_LOG_VIEWER_URL", "http://localhost:5341")

    logger.info("Verifying AutoBot logs in Seq...")

    try:
        # Query for AutoBot logs
        response = requests.get(
            f"{seq_url}/api/events",
            params={"filter": "Application = 'AutoBot'", "count": 10},
        )

        if response.status_code == 200:
            events = response.json()
            event_count = len(events.get("Events", []))
            logger.info("Found %d AutoBot log events in Seq", event_count)

            if event_count > 0:
                logger.info("Recent AutoBot log entries:")
                for event in events.get("Events", [])[:5]:
                    timestamp = event.get("@t", "unknown")
                    level = event.get("@l", "Info")
                    message = event.get("@mt", "No message")
                    source = event.get("Source", "Unknown")
                    logger.info(
                        "   [%s] %s: %s... (from %s)",
                        timestamp[:19],
                        level,
                        message[:80],
                        source,
                    )

            return event_count > 0
        else:
            logger.warning("Could not query Seq events: %s", response.status_code)
            return False

    except Exception as e:
        logger.error("Error verifying Seq logs: %s", e)
        return False


def main():
    """Entry point for Seq authentication and API key configuration."""
    seq_url = os.getenv("AUTOBOT_LOG_VIEWER_URL", "http://localhost:5341")

    logger.info("AutoBot Seq Analytics Configuration")
    logger.info("   Seq URL: %s", seq_url)

    # Try to create API key
    api_key = create_seq_api_key(seq_url)

    # If authentication failed, offer to reset password
    if not api_key:
        logger.error("Authentication failed!")
        logger.info("This often happens after Docker container restart.")

        reset_choice = input("\nWould you like to reset the Seq admin password? (y/N): ").strip().lower()

        if reset_choice in ["y", "yes"]:
            if reset_seq_admin_password(seq_url):
                logger.info("Retrying authentication with new password...")
                api_key = create_seq_api_key(seq_url)
            else:
                logger.error("Password reset failed")
        else:
            logger.info("You can manually reset the password later by running:")
            logger.info("   python scripts/seq_auth_setup.py --reset-password")

    # Setup basic queries
    setup_basic_seq_queries(seq_url, api_key)

    # Verify logs are present
    has_logs = verify_seq_logs(seq_url)

    logger.info("Seq configuration complete!")
    logger.info("   API Key created: %s", "Yes" if api_key else "No")
    logger.info("   Logs present: %s", "Yes" if has_logs else "No")
    logger.info("Next steps:")
    logger.info("   1. Access Seq at: %s", seq_url)
    logger.info("   2. Login with admin and the password you set")
    logger.info("   3. Manually create the queries shown above")
    logger.info("   4. Create dashboards using those queries")
    logger.info("   5. Set up alerts for critical errors")

    # Save current password to environment if successful
    if api_key and os.getenv("SEQ_PASSWORD"):
        logger.info("To avoid prompts in the future, set:")
        logger.info("   export SEQ_PASSWORD='<your-password>'")
        logger.info("   or add it to your .env file")


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

    parser.add_argument("--reset-password", action="store_true", help="Reset Seq admin password")

    parser.add_argument("--seq-url", help="Seq server URL")

    parser.add_argument("--username", help="Admin username")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.reset_password:
        # Just reset password
        if reset_seq_admin_password(args.seq_url):
            logger.info("Password reset completed successfully")
            sys.exit(0)
        else:
            logger.error("Password reset failed")
            sys.exit(1)
    else:
        # Run full setup
        main()
