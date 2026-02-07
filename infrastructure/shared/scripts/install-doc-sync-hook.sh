#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Install documentation sync git hook
# Issue #250: Enable Chat Agent Self-Awareness
#
# This script installs the post-commit hook that automatically
# triggers documentation indexing when docs/ files are changed.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo -e "${CYAN}📚 AutoBot Documentation Sync Hook Installer${NC}"
echo "=================================================="
echo ""

# Check if we're in a git repository
if [ ! -d "$PROJECT_ROOT/.git" ]; then
    echo -e "${RED}❌ Error: Not a git repository${NC}"
    exit 1
fi

# Source hook location
HOOK_SOURCE="$PROJECT_ROOT/scripts/hooks/post-commit-doc-sync"
HOOK_DEST="$PROJECT_ROOT/.git/hooks/post-commit"

# Check if source hook exists
if [ ! -f "$HOOK_SOURCE" ]; then
    echo -e "${RED}❌ Error: Hook source not found: $HOOK_SOURCE${NC}"
    exit 1
fi

# Check if post-commit hook already exists
if [ -f "$HOOK_DEST" ]; then
    echo -e "${YELLOW}⚠️ Existing post-commit hook found${NC}"

    # Check if it's already our hook
    if grep -q "AutoBot Documentation Sync" "$HOOK_DEST" 2>/dev/null; then
        echo -e "${GREEN}✅ Documentation sync hook already installed${NC}"
        exit 0
    fi

    # Backup existing hook
    BACKUP="$HOOK_DEST.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$HOOK_DEST" "$BACKUP"
    echo -e "   Backed up to: $BACKUP"
fi

# Install the hook
cp "$HOOK_SOURCE" "$HOOK_DEST"
chmod +x "$HOOK_DEST"

echo -e "${GREEN}✅ Documentation sync hook installed${NC}"
echo ""
echo "The hook will automatically trigger incremental documentation"
echo "indexing when you commit changes to docs/ or CLAUDE.md"
echo ""
echo "To test the hook manually:"
echo "  python tools/index_documentation.py --incremental --dry-run"
echo ""
echo "=================================================="
echo ""
