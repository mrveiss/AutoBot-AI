#!/bin/bash
# AutoBot - Legacy Python Environment Cleanup Script
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Issue #1924: Remove stale pyenv and conda installations from VMs.
# After standardizing to deadsnakes PPA + Python 3.14 (#1898), legacy
# pyenv and conda directories are no longer needed.
#
# Usage: Run on each VM as the autobot user (or with sudo for system-wide cleanup):
#   bash cleanup-legacy-python.sh
#
# Safety: This script verifies python3.14 is available before removing anything.

set -e  # Exit on error

echo "=================================================="
echo "AutoBot Legacy Python Cleanup"
echo "=================================================="
echo ""

# -------------------------------------------------------------------
# Safety check: verify python3.14 is installed before removing legacy
# -------------------------------------------------------------------
echo "Step 1: Verifying python3.14 is available..."
if ! command -v python3.14 &>/dev/null; then
    echo "ERROR: python3.14 is NOT installed."
    echo "Install python3.14 via deadsnakes PPA before running this script."
    echo "See: setup-runner-python.sh"
    exit 1
fi

PYTHON_VERSION=$(python3.14 --version 2>&1)
echo "  Found: ${PYTHON_VERSION}"
echo ""

# -------------------------------------------------------------------
# Remove pyenv if present
# -------------------------------------------------------------------
echo "Step 2: Checking for pyenv..."
PYENV_DIR="${HOME}/.pyenv"
if [ -d "${PYENV_DIR}" ]; then
    echo "  Found pyenv at: ${PYENV_DIR}"
    PYENV_SIZE=$(du -sh "${PYENV_DIR}" 2>/dev/null | cut -f1)
    echo "  Size: ${PYENV_SIZE}"
    rm -rf "${PYENV_DIR}"
    echo "  Removed ${PYENV_DIR}"
else
    echo "  No pyenv directory found. Skipping."
fi
echo ""

# -------------------------------------------------------------------
# Remove conda/miniconda if present
# -------------------------------------------------------------------
echo "Step 3: Checking for conda/miniconda..."
CONDA_DIR="${HOME}/miniconda3"
if [ -d "${CONDA_DIR}" ]; then
    echo "  Found miniconda at: ${CONDA_DIR}"
    CONDA_SIZE=$(du -sh "${CONDA_DIR}" 2>/dev/null | cut -f1)
    echo "  Size: ${CONDA_SIZE}"
    rm -rf "${CONDA_DIR}"
    echo "  Removed ${CONDA_DIR}"
else
    echo "  No miniconda3 directory found. Skipping."
fi

# Also check for anaconda3
ANACONDA_DIR="${HOME}/anaconda3"
if [ -d "${ANACONDA_DIR}" ]; then
    echo "  Found anaconda at: ${ANACONDA_DIR}"
    ANACONDA_SIZE=$(du -sh "${ANACONDA_DIR}" 2>/dev/null | cut -f1)
    echo "  Size: ${ANACONDA_SIZE}"
    rm -rf "${ANACONDA_DIR}"
    echo "  Removed ${ANACONDA_DIR}"
else
    echo "  No anaconda3 directory found. Skipping."
fi
echo ""

# -------------------------------------------------------------------
# Clean up bashrc pyenv/conda blocks
# -------------------------------------------------------------------
echo "Step 4: Cleaning up shell configuration..."
BASHRC="${HOME}/.bashrc"
CLEANED=0

if [ -f "${BASHRC}" ]; then
    # Remove pyenv init blocks
    if grep -q 'pyenv' "${BASHRC}" 2>/dev/null; then
        echo "  Removing pyenv references from .bashrc..."
        sed -i '/# >>> pyenv/,/# <<< pyenv/d' "${BASHRC}"
        sed -i '/PYENV_ROOT/d' "${BASHRC}"
        sed -i '/\.pyenv/d' "${BASHRC}"
        sed -i '/pyenv init/d' "${BASHRC}"
        sed -i '/pyenv virtualenv-init/d' "${BASHRC}"
        CLEANED=1
    fi

    # Remove conda init blocks
    if grep -q 'conda' "${BASHRC}" 2>/dev/null; then
        echo "  Removing conda references from .bashrc..."
        sed -i '/# >>> conda initialize/,/# <<< conda initialize/d' "${BASHRC}"
        sed -i '/miniconda3/d' "${BASHRC}"
        sed -i '/anaconda3/d' "${BASHRC}"
        CLEANED=1
    fi

    if [ "${CLEANED}" -eq 0 ]; then
        echo "  No pyenv/conda references found in .bashrc. Skipping."
    else
        echo "  Cleaned .bashrc successfully."
    fi
else
    echo "  No .bashrc found. Skipping."
fi

# Also clean .bash_profile if it exists
BASH_PROFILE="${HOME}/.bash_profile"
if [ -f "${BASH_PROFILE}" ]; then
    if grep -q 'pyenv\|conda\|miniconda' "${BASH_PROFILE}" 2>/dev/null; then
        echo "  Removing pyenv/conda references from .bash_profile..."
        sed -i '/pyenv/d' "${BASH_PROFILE}"
        sed -i '/conda/d' "${BASH_PROFILE}"
        sed -i '/miniconda/d' "${BASH_PROFILE}"
        sed -i '/anaconda/d' "${BASH_PROFILE}"
        echo "  Cleaned .bash_profile successfully."
    fi
fi
echo ""

# -------------------------------------------------------------------
# Final verification
# -------------------------------------------------------------------
echo "Step 5: Final verification..."
echo "  python3.14 location: $(which python3.14)"
echo "  python3.14 version:  $(python3.14 --version 2>&1)"

if [ -d "${PYENV_DIR}" ]; then
    echo "  WARNING: pyenv directory still exists at ${PYENV_DIR}"
else
    echo "  pyenv: removed"
fi

if [ -d "${CONDA_DIR}" ] || [ -d "${ANACONDA_DIR}" ]; then
    echo "  WARNING: conda directory still exists"
else
    echo "  conda: removed"
fi

echo ""
echo "=================================================="
echo "Legacy Python Cleanup Complete!"
echo "=================================================="
echo ""
echo "Python 3.14 (deadsnakes PPA) remains as the standard."
echo "Removed: pyenv, conda/miniconda (if present)."
echo ""
