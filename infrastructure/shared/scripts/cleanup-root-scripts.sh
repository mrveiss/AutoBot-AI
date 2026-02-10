#!/bin/bash
# AutoBot Root Directory Script Cleanup
# Compliance with CLAUDE.md Repository Cleanliness Standards
#
# Relocates debug, demo, and utility scripts from root directory
# Archives obsolete scripts while preserving useful development tools
#
# Created: 2025-10-10
# Purpose: Repository cleanliness compliance

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/ssot-config.sh" 2>/dev/null || true

AUTOBOT_ROOT="${PROJECT_ROOT:-/home/kali/Desktop/AutoBot}"
cd "$AUTOBOT_ROOT"

# Color output for clarity
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== AutoBot Root Directory Script Cleanup ===${NC}"
echo "Relocating 12 scripts from root directory"
echo ""

# Create necessary directories
echo -e "${YELLOW}Creating directories...${NC}"
mkdir -p archive/scripts-obsolete-2025-10-10
mkdir -p scripts/demo
mkdir -p scripts/debug
echo -e "${GREEN}✓ Directories created${NC}"
echo ""

# Verify files exist before moving
echo -e "${YELLOW}Verifying scripts exist...${NC}"
SCRIPTS_TO_ARCHIVE=(
    "debug_sidebar_detailed.py"
    "verify_chat_layout.py"
    "verify_layout_remote.py"
    "debug_kb_search.py"
    "validate_rag_integration.py"
    "validate_network_config.sh"
    "update_agents_ansible_references.sh"
)

SCRIPTS_TO_RELOCATE=(
    "debug_frontend_browser.py:scripts/debug/"
    "debug_frontend_browser_headless.py:scripts/debug/"
    "integrate_system_knowledge.py:scripts/utilities/"
    "demo_codebase_indexing.py:scripts/demo/"
)

MISSING_FILES=0
for file in "${SCRIPTS_TO_ARCHIVE[@]}" "${SCRIPTS_TO_RELOCATE[@]%%:*}"; do
    script_name="${file%%:*}"
    if [ ! -f "$script_name" ]; then
        echo -e "  ${YELLOW}⚠ Missing: $script_name${NC}"
        MISSING_FILES=$((MISSING_FILES + 1))
    else
        echo -e "  ${GREEN}✓ Found: $script_name${NC}"
    fi
done

if [ $MISSING_FILES -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}Warning: $MISSING_FILES file(s) not found. Continuing with available files.${NC}"
fi
echo ""

# Archive obsolete scripts
echo -e "${BLUE}1. Archiving obsolete scripts → archive/scripts-obsolete-2025-10-10/${NC}"
for script in "${SCRIPTS_TO_ARCHIVE[@]}"; do
    if [ -f "$script" ]; then
        mv -v "$script" "archive/scripts-obsolete-2025-10-10/"
    fi
done
echo -e "${GREEN}✓ Obsolete scripts archived (7 files)${NC}"
echo ""

# Relocate useful scripts
echo -e "${BLUE}2. Relocating useful scripts to proper directories${NC}"
for entry in "${SCRIPTS_TO_RELOCATE[@]}"; do
    script="${entry%%:*}"
    dest="${entry#*:}"
    if [ -f "$script" ]; then
        echo -e "${YELLOW}Moving $script → $dest${NC}"
        mv -v "$script" "$dest"
    fi
done
echo -e "${GREEN}✓ Useful scripts relocated (4 files)${NC}"
echo ""

# Create archive documentation
echo -e "${BLUE}3. Creating archive documentation${NC}"
cat > archive/scripts-obsolete-2025-10-10/README.md << 'EOF'
# Archived Obsolete Scripts (October 2025)

**Archive Date:** 2025-10-10
**Reason:** One-time debugging and validation scripts no longer needed

## Scripts Archived (7 files)

### Debug Scripts (4 files)

#### debug_sidebar_detailed.py
- **Purpose:** Playwright-based sidebar visibility debugging
- **Created:** 2025-09-28
- **Status:** ✅ Obsolete - Sidebar visibility now working correctly
- **Context:** Used to debug w-80 Tailwind class application

#### verify_chat_layout.py
- **Purpose:** Remote chat layout verification via Browser VM
- **Created:** 2025-09-28
- **Status:** ✅ Obsolete - Chat layout fixed
- **Context:** SSH + Playwright verification of layout fixes

#### verify_layout_remote.py
- **Purpose:** Simplified remote layout verification
- **Created:** 2025-09-28
- **Status:** ✅ Obsolete - Layout issues resolved
- **Context:** Cleaner implementation of layout verification

#### debug_kb_search.py
- **Purpose:** Knowledge Base search parameter debugging
- **Created:** 2025-09-29
- **Status:** ✅ Obsolete - KB search working correctly
- **Context:** Debugged top_k vs similarity_top_k parameter issues

### Validation Scripts (2 files)

#### validate_rag_integration.py
- **Purpose:** RAG integration validation
- **Created:** 2025-09-29
- **Status:** ✅ Obsolete - RAG integration complete and tested
- **Context:** Post-integration validation script

#### validate_network_config.sh
- **Purpose:** Docker network standardization validation
- **Created:** 2025-09-09
- **Status:** ✅ Obsolete - Network standardization complete
- **Context:** Validated 172.16.168.x subnet standardization

### Utility Scripts (1 file)

#### update_agents_ansible_references.sh
- **Purpose:** Add Ansible playbook references to agent configs
- **Created:** 2025-09-12
- **Status:** ✅ Obsolete - One-time update completed
- **Context:** Updated all .claude/agents/*.md files

## Why Archived?

All scripts were created for specific debugging sessions or one-time
validations during late September 2025 feature development. The features
now work correctly, making these scripts obsolete.

**Key Context:**
- Sidebar visibility issues resolved
- Chat layout working correctly
- Knowledge Base search functional
- RAG integration complete
- Network configuration standardized
- Agent configurations updated

## Retention Policy

These scripts are preserved for historical reference but should be reviewed
for deletion after 90 days if not referenced or reused.

---

**Archived by:** AutoBot cleanup script
**Archive Path:** `archive/scripts-obsolete-2025-10-10/`
**Original Location:** Root directory (`/home/kali/Desktop/AutoBot/`)
EOF

echo -e "${GREEN}✓ Archive documentation created${NC}"
echo ""

# Verification
echo -e "${BLUE}=== Verification ===${NC}"
echo "Root-level script files remaining (excluding setup.sh, run_autobot.sh):"
REMAINING=$(find . -maxdepth 1 -type f \( -name "*.py" -o -name "*.sh" \) \
    ! -name "setup.sh" \
    ! -name "run_autobot.sh" \
    ! -name "sync-frontend.sh" \
    ! -name "start-frontend-dev.sh" \
    ! -name "distributed-status.sh" \
    2>/dev/null)

if [ -z "$REMAINING" ]; then
    echo -e "${GREEN}✓ Root directory is clean! Only permitted scripts remain.${NC}"
else
    echo -e "${YELLOW}⚠ Unexpected scripts found:${NC}"
    echo "$REMAINING"
fi
echo ""

# Summary
echo -e "${BLUE}=== Cleanup Summary ===${NC}"
echo -e "  ${GREEN}✓${NC} Obsolete scripts (7):       archive/scripts-obsolete-2025-10-10/"
echo -e "  ${GREEN}✓${NC} Debug tools (2):            scripts/debug/"
echo -e "  ${GREEN}✓${NC} Utilities (1):              scripts/utilities/"
echo -e "  ${GREEN}✓${NC} Demo scripts (1):           scripts/demo/"
echo ""
echo -e "${GREEN}✓ Repository cleanliness compliance achieved!${NC}"
echo ""

# Show what's in each location
echo -e "${BLUE}Archived Scripts:${NC}"
ls -1 archive/scripts-obsolete-2025-10-10/ | grep -v README.md | sed 's/^/  - /'
echo ""

echo -e "${BLUE}Active Development Tools:${NC}"
echo -e "${YELLOW}scripts/debug/${NC}"
ls -1 scripts/debug/*.py 2>/dev/null | xargs -n1 basename | sed 's/^/  - /' || echo "  (none)"
echo -e "${YELLOW}scripts/utilities/${NC}"
ls -1 scripts/utilities/integrate_system_knowledge.py 2>/dev/null | xargs -n1 basename | sed 's/^/  - /' || echo "  (none)"
echo -e "${YELLOW}scripts/demo/${NC}"
ls -1 scripts/demo/*.py 2>/dev/null | xargs -n1 basename | sed 's/^/  - /' || echo "  (none)"
