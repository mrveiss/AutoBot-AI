#!/bin/bash
# Install and configure pre-commit hooks for AutoBot
# This script sets up automated code quality enforcement

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

echo "=========================================="
echo "AutoBot Pre-Commit Hooks Installation"
echo "=========================================="
echo ""

cd "$PROJECT_ROOT"

# Check Python version
echo "Step 1: Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "✅ Python version: $PYTHON_VERSION"
echo ""

# Install pre-commit
echo "Step 2: Installing pre-commit..."
if ! command -v pre-commit &> /dev/null; then
    pip install pre-commit
    echo "✅ pre-commit installed"
else
    echo "✅ pre-commit already installed ($(pre-commit --version))"
fi
echo ""

# Install code quality tools
echo "Step 3: Installing code quality tools..."
pip install black isort flake8 autoflake bandit[toml]
echo "✅ Code quality tools installed"
echo ""

# Install pre-commit hooks
echo "Step 4: Installing pre-commit hooks to .git/hooks/..."
pre-commit install
echo "✅ Pre-commit hooks installed"
echo ""

# Run pre-commit on all files (optional but recommended)
echo "Step 5: Running pre-commit on all files (initial check)..."
echo "This may take a few minutes on first run..."
echo ""

if pre-commit run --all-files; then
    echo ""
    echo "=========================================="
    echo "✅ SUCCESS: Pre-commit hooks installed!"
    echo "=========================================="
    echo ""
    echo "Code quality enforcement is now active:"
    echo "  ✓ Black formatting (88 char line length)"
    echo "  ✓ isort import sorting"
    echo "  ✓ flake8 linting"
    echo "  ✓ autoflake unused code removal"
    echo "  ✓ bandit security checks"
    echo "  ✓ Trailing whitespace removal"
    echo "  ✓ YAML/JSON validation"
    echo ""
    echo "These checks will run automatically on every commit."
    echo ""
    echo "Manual usage:"
    echo "  - Run on all files: pre-commit run --all-files"
    echo "  - Run on specific files: pre-commit run --files path/to/file.py"
    echo "  - Skip hooks (not recommended): git commit --no-verify"
    echo ""
else
    echo ""
    echo "=========================================="
    echo "⚠️  Initial check found issues"
    echo "=========================================="
    echo ""
    echo "Some files need fixes. Options:"
    echo ""
    echo "1. Auto-fix (recommended):"
    echo "   black --line-length=88 backend/ src/"
    echo "   isort --profile=black --line-length=88 backend/ src/"
    echo "   autoflake --in-place --recursive --remove-all-unused-imports --remove-unused-variables backend/ src/"
    echo ""
    echo "2. Fix manually based on error messages above"
    echo ""
    echo "3. Run pre-commit again after fixes:"
    echo "   pre-commit run --all-files"
    echo ""
    echo "Pre-commit hooks are installed and will enforce quality on future commits."
    exit 1
fi

echo "Next steps:"
echo "  1. Make a commit to test the hooks"
echo "  2. Check GitHub Actions for CI/CD enforcement"
echo "  3. Archive obsolete manual fix scripts"
echo ""
