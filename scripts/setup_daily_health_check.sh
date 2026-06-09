#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Setup daily health check via Ansible
#
# This script validates prerequisites and prints the Ansible command needed to
# install the health-check cron job.  Direct crontab manipulation was removed
# (MVA-291): cron installation is now handled by the Ansible monitoring role
# so the wrapper lives in /usr/local/bin/ and survives OS reboots.
#
# Usage:
#   bash scripts/setup_daily_health_check.sh
#   # Then run the printed Ansible command to deploy.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HEALTH_CHECK="$SCRIPT_DIR/daily_health_check.py"
POST_CHECK="$SCRIPT_DIR/post_health_check.py"
ANSIBLE_DIR="$(dirname "$SCRIPT_DIR")/autobot-slm-backend/ansible"

echo "AutoBot Daily Health Check — Ansible deployment"
echo "================================================"

# Validate required scripts exist
for script in "$HEALTH_CHECK" "$POST_CHECK"; do
    if [[ ! -f "$script" ]]; then
        echo "ERROR: Missing required script: $script" >&2
        exit 1
    fi
done

# Confirm Ansible is available
if ! command -v ansible-playbook &>/dev/null; then
    echo "ERROR: ansible-playbook not found in PATH." >&2
    echo "       Install Ansible, then re-run this script." >&2
    exit 1
fi

if [[ ! -d "$ANSIBLE_DIR" ]]; then
    echo "ERROR: Ansible directory not found at $ANSIBLE_DIR" >&2
    exit 1
fi

echo ""
echo "Prerequisites satisfied. Deploy with:"
echo ""
echo "  cd $ANSIBLE_DIR"
echo "  ansible-playbook setup-health-check-cron.yml -i inventory.yml"
echo ""
echo "The cron wrapper will be installed to /usr/local/bin/autobot-health-check-cron.sh"
echo "Logs: /var/log/autobot/health-check.log"
