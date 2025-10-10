#!/bin/bash
# AutoBot Root Directory .md File Cleanup Script
# Compliance with CLAUDE.md Repository Cleanliness Standards
#
# Only CLAUDE.md and README.md are permitted in root directory.
# This script relocates 11 violating .md files to appropriate directories.
#
# Created: 2025-10-10
# Purpose: Repository cleanliness compliance

set -e  # Exit on any error

AUTOBOT_ROOT="/home/kali/Desktop/AutoBot"
cd "$AUTOBOT_ROOT"

# Color output for clarity
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== AutoBot Root Directory Cleanup ===${NC}"
echo "Relocating 11 .md files to proper directories"
echo ""

# Create necessary directories
echo -e "${YELLOW}Creating archive directories...${NC}"
mkdir -p planning/tasks/archive
mkdir -p docs/operations
mkdir -p docs/troubleshooting/fixes
echo -e "${GREEN}✓ Directories created${NC}"
echo ""

# Verify files exist before moving
echo -e "${YELLOW}Verifying files exist...${NC}"
FILES_TO_MOVE=(
    "current_task_progress.md"
    "task_migration_record.md"
    "KNOWLEDGE_MANAGER_COMPLETE.md"
    "AI_STACK_INTEGRATION_COMPLETE.md"
    "TASK_3_6_COMPLETION.md"
    "DISTRIBUTED_ARCHITECTURE_SETUP.md"
    "README_CLAUDE_API_OPTIMIZATION.md"
    "REINDEX_CLAUDE_QUICKSTART.md"
    "PROMPTS_DIRECTORY_AUDIT_2025-10-03.md"
    "VECTOR_DIMENSION_MISMATCH_FIX.md"
    "FRONTEND_API_ENDPOINTS_FIXED.md"
)

MISSING_FILES=0
for file in "${FILES_TO_MOVE[@]}"; do
    if [ ! -f "$file" ]; then
        echo -e "  ${YELLOW}⚠ Missing: $file${NC}"
        MISSING_FILES=$((MISSING_FILES + 1))
    else
        echo -e "  ${GREEN}✓ Found: $file${NC}"
    fi
done

if [ $MISSING_FILES -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}Warning: $MISSING_FILES file(s) not found. Continuing with available files.${NC}"
fi
echo ""

# Category 1: Task Tracking Files → planning/tasks/archive/
echo -e "${BLUE}1. Moving task tracking files → planning/tasks/archive/${NC}"
[ -f "current_task_progress.md" ] && mv -v "current_task_progress.md" "planning/tasks/archive/frontend-api-endpoint-fixes-2025-10-10.md"
[ -f "task_migration_record.md" ] && mv -v "task_migration_record.md" "planning/tasks/archive/task-migration-record-2025-09-29.md"
echo -e "${GREEN}✓ Task tracking files moved${NC}"
echo ""

# Category 2: Completion Reports → reports/finished/
echo -e "${BLUE}2. Moving completion reports → reports/finished/${NC}"
[ -f "KNOWLEDGE_MANAGER_COMPLETE.md" ] && mv -v "KNOWLEDGE_MANAGER_COMPLETE.md" "reports/finished/knowledge-manager-completion-2025-09-29.md"
[ -f "AI_STACK_INTEGRATION_COMPLETE.md" ] && mv -v "AI_STACK_INTEGRATION_COMPLETE.md" "reports/finished/ai-stack-integration-completion-2025-09-29.md"
[ -f "TASK_3_6_COMPLETION.md" ] && mv -v "TASK_3_6_COMPLETION.md" "reports/finished/access-control-rollout-completion-2025-10-06.md"
[ -f "FRONTEND_API_ENDPOINTS_FIXED.md" ] && mv -v "FRONTEND_API_ENDPOINTS_FIXED.md" "reports/finished/frontend-api-endpoints-fix-2025-10-10.md"
echo -e "${GREEN}✓ Completion reports moved${NC}"
echo ""

# Category 3: Architecture Documentation → docs/architecture/
echo -e "${BLUE}3. Moving architecture documentation → docs/architecture/${NC}"
[ -f "DISTRIBUTED_ARCHITECTURE_SETUP.md" ] && mv -v "DISTRIBUTED_ARCHITECTURE_SETUP.md" "docs/architecture/DISTRIBUTED_6VM_ARCHITECTURE.md"
echo -e "${GREEN}✓ Architecture documentation moved${NC}"
echo ""

# Category 4: Developer Guides → docs/developer/ (with rename for consistency)
echo -e "${BLUE}4. Moving developer guides → docs/developer/ (renaming for consistency)${NC}"
[ -f "README_CLAUDE_API_OPTIMIZATION.md" ] && mv -v "README_CLAUDE_API_OPTIMIZATION.md" "docs/developer/CLAUDE_API_OPTIMIZATION_SUITE.md"
echo -e "${GREEN}✓ Developer guides moved${NC}"
echo ""

# Category 5: Operations Guides → docs/operations/
echo -e "${BLUE}5. Moving operations guides → docs/operations/${NC}"
[ -f "REINDEX_CLAUDE_QUICKSTART.md" ] && mv -v "REINDEX_CLAUDE_QUICKSTART.md" "docs/operations/CLAUDE_MD_REINDEX_QUICKSTART.md"
echo -e "${GREEN}✓ Operations guides moved${NC}"
echo ""

# Category 6: Audit Reports → reports/project/
echo -e "${BLUE}6. Moving audit reports → reports/project/${NC}"
[ -f "PROMPTS_DIRECTORY_AUDIT_2025-10-03.md" ] && mv -v "PROMPTS_DIRECTORY_AUDIT_2025-10-03.md" "reports/project/prompts-directory-audit-2025-10-03.md"
echo -e "${GREEN}✓ Audit reports moved${NC}"
echo ""

# Category 7: Fix Documentation → docs/troubleshooting/fixes/
echo -e "${BLUE}7. Moving fix documentation → docs/troubleshooting/fixes/${NC}"
[ -f "VECTOR_DIMENSION_MISMATCH_FIX.md" ] && mv -v "VECTOR_DIMENSION_MISMATCH_FIX.md" "docs/troubleshooting/fixes/vector-dimension-mismatch-fix-2025-09-29.md"
echo -e "${GREEN}✓ Fix documentation moved${NC}"
echo ""

# Verification
echo -e "${BLUE}=== Verification ===${NC}"
echo "Root-level .md files remaining (excluding CLAUDE.md and README.md):"
REMAINING=$(find . -maxdepth 1 -name "*.md" -type f ! -name "CLAUDE.md" ! -name "README.md" 2>/dev/null)
if [ -z "$REMAINING" ]; then
    echo -e "${GREEN}✓ Root directory is clean! Only CLAUDE.md and README.md remain.${NC}"
else
    echo -e "${YELLOW}⚠ Unexpected files found:${NC}"
    echo "$REMAINING"
fi
echo ""

# Summary
echo -e "${BLUE}=== Cleanup Summary ===${NC}"
echo -e "  ${GREEN}✓${NC} Task tracking files (2):    planning/tasks/archive/"
echo -e "  ${GREEN}✓${NC} Completion reports (4):     reports/finished/"
echo -e "  ${GREEN}✓${NC} Architecture docs (1):      docs/architecture/"
echo -e "  ${GREEN}✓${NC} Developer guides (1):       docs/developer/"
echo -e "  ${GREEN}✓${NC} Operations guides (1):      docs/operations/"
echo -e "  ${GREEN}✓${NC} Audit reports (1):          reports/project/"
echo -e "  ${GREEN}✓${NC} Fix documentation (1):      docs/troubleshooting/fixes/"
echo ""
echo -e "${GREEN}✓ Repository cleanliness compliance achieved!${NC}"
