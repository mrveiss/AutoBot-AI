#!/bin/bash
# AutoBot - Self-Hosted Runner Pyenv Setup Script
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# This script installs pyenv on the GitHub Actions self-hosted runner
# and configures Python 3.10 with pip for CI/CD workflows.
#
# Usage: Run this script on the self-hosted runner machine (github-runner)
# as user 'martins': bash setup-runner-pyenv.sh

set -e  # Exit on error

echo "=================================================="
echo "🐍 AutoBot Self-Hosted Runner Pyenv Setup"
echo "=================================================="
echo ""

# Check if running as correct user
CURRENT_USER=$(whoami)
if [ "$CURRENT_USER" != "martins" ]; then
    echo "⚠️  Warning: This script should be run as user 'martins'"
    echo "   Current user: $CURRENT_USER"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "📦 Step 1: Installing pyenv dependencies..."
sudo apt update
sudo apt install -y build-essential libssl-dev zlib1g-dev \
    libbz2-dev libreadline-dev libsqlite3-dev curl git \
    libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev \
    libffi-dev liblzma-dev

echo ""
echo "📥 Step 2: Installing pyenv..."
if [ -d "$HOME/.pyenv" ]; then
    echo "⚠️  Pyenv already exists at $HOME/.pyenv"
    read -p "Remove and reinstall? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$HOME/.pyenv"
    else
        echo "Skipping pyenv installation"
    fi
fi

if [ ! -d "$HOME/.pyenv" ]; then
    curl https://pyenv.run | bash
fi

echo ""
echo "⚙️  Step 3: Configuring shell environment..."

# Backup existing .bashrc
if [ -f "$HOME/.bashrc" ]; then
    cp "$HOME/.bashrc" "$HOME/.bashrc.backup.$(date +%Y%m%d_%H%M%S)"
fi

# Add pyenv to .bashrc if not already present
if ! grep -q "PYENV_ROOT" "$HOME/.bashrc"; then
    echo '' >> "$HOME/.bashrc"
    echo '# Pyenv configuration' >> "$HOME/.bashrc"
    echo 'export PYENV_ROOT="$HOME/.pyenv"' >> "$HOME/.bashrc"
    echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> "$HOME/.bashrc"
    echo 'eval "$(pyenv init -)"' >> "$HOME/.bashrc"
    echo "✅ Added pyenv to .bashrc"
else
    echo "✅ Pyenv already configured in .bashrc"
fi

# Source the configuration
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"

echo ""
echo "🐍 Step 4: Installing Python 3.10.15..."
if pyenv versions | grep -q "3.10.15"; then
    echo "✅ Python 3.10.15 already installed"
else
    pyenv install 3.10.15
fi

echo ""
echo "🎯 Step 5: Setting Python 3.10.15 as global default..."
pyenv global 3.10.15

echo ""
echo "✅ Step 6: Verifying installation..."
echo "Python version:"
python3 --version
echo ""
echo "Python location:"
which python3
echo ""
echo "Pip version:"
python3 -m pip --version

echo ""
echo "=================================================="
echo "✅ Pyenv Setup Complete!"
echo "=================================================="
echo ""
echo "📋 Next Steps:"
echo "1. Restart your shell or run: source ~/.bashrc"
echo "2. Verify pyenv is working: pyenv version"
echo "3. Re-run GitHub Actions workflows"
echo ""
echo "📍 Python 3.10.15 is now the global default"
echo "📍 All GitHub Actions workflows will use this Python"
echo ""
