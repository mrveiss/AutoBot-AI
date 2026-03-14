#!/usr/bin/env bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Detect drift between canonical SLM agent code and Ansible role copy.
# Used by: .github/workflows/code-quality.yml
# Reference: Issue #1629
#
# The SLM agent code lives in two places:
#   - autobot-slm-backend/slm/agent/        (canonical, actively developed)
#   - autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent/  (Ansible copy)
#
# They MUST stay identical. This script fails if they diverge.

set -euo pipefail

CANONICAL="autobot-slm-backend/slm/agent"
ANSIBLE_COPY="autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent"

if [ ! -d "$CANONICAL" ]; then
    echo "ERROR: Canonical agent directory not found: $CANONICAL"
    exit 1
fi

if [ ! -d "$ANSIBLE_COPY" ]; then
    echo "ERROR: Ansible agent copy not found: $ANSIBLE_COPY"
    exit 1
fi

# Compare, excluding __pycache__ and test files
DIFF_OUTPUT=$(diff -r "$CANONICAL" "$ANSIBLE_COPY" \
    --exclude='__pycache__' \
    --exclude='*_test.py' \
    --exclude='*.pyc' \
    2>&1) || true

if [ -n "$DIFF_OUTPUT" ]; then
    echo "DRIFT DETECTED between canonical agent and Ansible copy (#1629)"
    echo ""
    echo "$DIFF_OUTPUT"
    echo ""
    echo "Fix: copy canonical files to Ansible role:"
    echo "  cp autobot-slm-backend/slm/agent/*.py \\"
    echo "     autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent/"
    exit 1
fi

echo "Agent code in sync: canonical == Ansible copy"
exit 0
