#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Post health check results to MVA-12 and file issues for anomalies
"""

import subprocess
import json
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def post_to_github(issue_number, comment_body):
    """Post comment to GitHub issue"""
    try:
        result = subprocess.run(
            ["gh", "issue", "comment", str(issue_number), "--body", comment_body],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info(f"Posted comment to issue #{issue_number}")
            return True
        else:
            logger.error(f"Failed to post comment: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Error posting to GitHub: {e}")
        return False


def file_issue(title, body):
    """File a new GitHub issue"""
    try:
        cmd = ["gh", "issue", "create", "--title", title, "--body", body]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            logger.info(f"Filed issue: {title}")
            return True
        else:
            logger.error(f"Failed to file issue: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Error filing issue: {e}")
        return False


def main():
    # Read the health check report
    report_file = Path("/tmp/autobot-health-check.md")
    if not report_file.exists():
        logger.error("Health check report not found")
        return 1

    report = report_file.read_text()

    # Parse the report to extract issues
    issues = []
    has_failures = "❌" in report
    if "Issues Found" in report:
        lines = report.split("Issues Found")[1].split("\n")
        for line in lines:
            if line.startswith("- "):
                issues.append(line[2:].strip())

    # Try to post to MVA-12 if it exists, otherwise to a discovery issue
    # First check if MVA-12 exists
    check_mva12 = subprocess.run(["gh", "issue", "view", "12"], capture_output=True, text=True, timeout=10)

    if check_mva12.returncode == 0:
        # MVA-12 exists, post to it
        mva_issue = "12"
        success = post_to_github(mva_issue, report)
        if success:
            logger.info(f"Posted health check report to issue #{mva_issue}")
        else:
            logger.warning("Failed to post to MVA-12")
    else:
        logger.info("MVA-12 not found in GitHub, creating standalone health check report")
        # Create a new discovery issue with the report instead
        report_title = "discovery(health-check): Daily health check report"
        file_issue(report_title, report)

    # File issues for each detected anomaly
    if issues and has_failures:
        logger.info(f"Found {len(issues)} issues to file")
        for issue in issues:
            # File discovery issue for each anomaly
            title = f"discovery(health-check): {issue[:60]}"
            body = f"Detected by daily health check:\n\n**Issue:** {issue}\n\n**Timestamp:** {datetime.now().isoformat()}\n\nPlease investigate and fix the underlying cause."
            file_issue(title, body)
    else:
        logger.info("No critical issues detected")

    return 0


if __name__ == "__main__":
    exit(main())
