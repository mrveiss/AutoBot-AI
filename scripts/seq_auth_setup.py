#!/usr/bin/env python3
"""
Seq Authentication and Basic Setup
=================================

Handles Seq authentication and creates basic analytics setup for AutoBot.
"""

import json
import sys
from pathlib import Path

import requests


def create_seq_api_key(
    seq_url="http://localhost:5341", username="admin", password="Autobot123!"  # pragma: allowlist secret
):
    """Create API key for Seq access."""

    print("🔐 Setting up Seq API authentication...")

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


def setup_basic_seq_queries(seq_url="http://localhost:5341", api_key=None):
    """Setup basic queries using direct SQL approach."""

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

    print(f"📋 Queries available for manual creation in Seq:")
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


def verify_seq_logs(seq_url="http://localhost:5341"):
    """Verify that logs are being received in Seq."""

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
    seq_url = "http://localhost:5341"

    print("🚀 AutoBot Seq Analytics Configuration")
    print(f"   Seq URL: {seq_url}")

    # Create API key
    api_key = create_seq_api_key(seq_url)

    # Setup basic queries
    setup_basic_seq_queries(seq_url, api_key)

    # Verify logs are present
    has_logs = verify_seq_logs(seq_url)

    print(f"\n🎉 Seq configuration complete!")
    print(f"   🔐 API Key created: {'Yes' if api_key else 'No'}")
    print(f"   📊 Logs present: {'Yes' if has_logs else 'No'}")
    print(f"\n🌐 Next steps:")
    print(f"   1. Access Seq at: {seq_url}")
    print(f"   2. Login with: admin / autobot123")
    print(f"   3. Manually create the queries shown above")
    print(f"   4. Create dashboards using those queries")
    print(f"   5. Set up alerts for critical errors")


if __name__ == "__main__":
    main()
