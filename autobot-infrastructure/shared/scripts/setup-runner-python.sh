#!/bin/bash
# AutoBot - Self-Hosted Runner Python Setup Script
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Issue #1898: Standardize Python to deadsnakes PPA + Python 3.14 venv.
# Replaced pyenv with deadsnakes PPA for consistency with Docker and production.
#
# This script installs Python 3.14 via deadsnakes PPA on the GitHub Actions
# self-hosted runner (github-runner, user 'martins').
#
# Usage: Run this script on the self-hosted runner machine (github-runner)
# as user 'martins': bash setup-runner-python.sh

set -e  # Exit on error

echo "=================================================="
echo "AutoBot Self-Hosted Runner Python 3.14 Setup"
echo "=================================================="
echo ""

# Check if running as correct user
CURRENT_USER=$(whoami)
if [ "$CURRENT_USER" != "martins" ]; then
    echo "Warning: This script should be run as user 'martins'"
    echo "   Current user: $CURRENT_USER"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "Step 1: Installing software-properties-common..."
sudo apt-get update
sudo apt-get install -y software-properties-common

echo ""
echo "Step 2: Adding deadsnakes PPA..."
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update

echo ""
echo "Step 3: Installing Python 3.14..."
sudo apt-get install -y python3.14 python3.14-venv python3.14-dev

echo ""
echo "Step 4: Verifying installation..."
echo "Python version:"
python3.14 --version
echo ""
echo "Python location:"
which python3.14
echo ""
echo "Pip version:"
python3.14 -m pip --version 2>/dev/null || echo "pip not available in base install (use venv)"

echo ""
echo "=================================================="
echo "Python 3.14 Setup Complete!"
echo "=================================================="
echo ""
echo "Next Steps:"
echo "1. Re-run GitHub Actions workflows"
echo "2. Workflows use: python3.14 -m venv .venv"
echo ""
echo "Python 3.14 (deadsnakes PPA) is now installed"
echo "All GitHub Actions workflows will use python3.14"
echo ""
