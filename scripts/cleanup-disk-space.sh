#!/bin/bash
# AutoBot Disk Space Cleanup Script
# Compliance with CLAUDE.md Repository Cleanliness Standards
#
# Cleans up temporary files, Python cache, and old backups
# Does NOT modify git tracking - only removes files from disk
#
# Created: 2025-10-10
# Updated: 2025-10-10 (added dry-run mode)
# Purpose: Disk space management and cleanup
#
# Usage:
#   ./cleanup-disk-space.sh           # Execute cleanup
#   ./cleanup-disk-space.sh --dry-run # Preview what would be deleted
#   ./cleanup-disk-space.sh -n        # Preview (short form)
#   ./cleanup-disk-space.sh --help    # Show help

set -e  # Exit on any error

# Parse command line arguments
DRY_RUN=false
SHOW_HELP=false

for arg in "$@"; do
    case $arg in
        --dry-run|-n)
            DRY_RUN=true
            shift
            ;;
        --help|-h)
            SHOW_HELP=true
            shift
            ;;
        *)
            echo "Unknown option: $arg"
            SHOW_HELP=true
            ;;
    esac
done

# Show help if requested
if [ "$SHOW_HELP" = true ]; then
    cat << 'EOF'
AutoBot Disk Space Cleanup Script

USAGE:
    ./cleanup-disk-space.sh [OPTIONS]

OPTIONS:
    --dry-run, -n    Preview what would be deleted without actually deleting
    --help, -h       Show this help message

DESCRIPTION:
    Cleans up temporary files, Python cache, and old backups from the
    AutoBot repository. Does NOT modify git tracking.

    Removes:
    - Python cache files (*.pyc, __pycache__)
    - Large log backups (*.log.bak)
    - Old backup directories
    - Temporary files (*.tmp, *.temp)
    - Editor temporary files (*.swp, *.swo, *~)

EXAMPLES:
    # Preview cleanup (safe to run anytime)
    ./cleanup-disk-space.sh --dry-run

    # Actually perform cleanup
    ./cleanup-disk-space.sh

EOF
    exit 0
fi

AUTOBOT_ROOT="/home/kali/Desktop/AutoBot"
cd "$AUTOBOT_ROOT"

# Color output for clarity
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== AutoBot Disk Space Cleanup ===${NC}"
if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}🔍 DRY RUN MODE - No files will be deleted${NC}"
    echo "Showing what would be cleaned up..."
else
    echo "Cleaning temporary files, caches, and old backups"
fi
echo ""

# Track space reclaimed
START_SIZE=$(du -sb . 2>/dev/null | cut -f1)

# Safety check: verify we're in AutoBot directory
if [ ! -f "CLAUDE.md" ] || [ ! -f "setup.sh" ]; then
    echo -e "${RED}ERROR: Not in AutoBot root directory!${NC}"
    echo "Expected: /home/kali/Desktop/AutoBot/"
    echo "Current: $(pwd)"
    exit 1
fi

echo -e "${GREEN}✓ Verified AutoBot root directory${NC}"
echo ""

# 1. Clean Python cache files (331 .pyc + 39 __pycache__ directories)
echo -e "${BLUE}1. Cleaning Python cache files${NC}"
echo "Finding .pyc files outside venv..."
PYC_COUNT=$(find . -type f -name "*.pyc" -not -path "./venv/*" -not -path "./.git/*" 2>/dev/null | wc -l)
echo "Found: $PYC_COUNT .pyc files"

if [ "$PYC_COUNT" -gt 0 ]; then
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}Would delete: $PYC_COUNT .pyc files${NC}"
    else
        find . -type f -name "*.pyc" -not -path "./venv/*" -not -path "./.git/*" -delete 2>/dev/null
        echo -e "${GREEN}✓ Deleted $PYC_COUNT .pyc files${NC}"
    fi
else
    echo -e "${GREEN}✓ No .pyc files to clean${NC}"
fi

echo ""
echo "Finding __pycache__ directories outside venv..."
PYCACHE_COUNT=$(find . -type d -name "__pycache__" -not -path "./venv/*" -not -path "./.git/*" 2>/dev/null | wc -l)
echo "Found: $PYCACHE_COUNT __pycache__ directories"

if [ "$PYCACHE_COUNT" -gt 0 ]; then
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}Would delete: $PYCACHE_COUNT __pycache__ directories${NC}"
    else
        find . -type d -name "__pycache__" -not -path "./venv/*" -not -path "./.git/*" -exec rm -rf {} + 2>/dev/null || true
        echo -e "${GREEN}✓ Deleted $PYCACHE_COUNT __pycache__ directories${NC}"
    fi
else
    echo -e "${GREEN}✓ No __pycache__ directories to clean${NC}"
fi
echo ""

# 2. Delete massive log backup (113MB)
echo -e "${BLUE}2. Cleaning large log backup files${NC}"
LOG_BACKUP="logs/backup/autobot_backend_20250819_100021.log.bak"
if [ -f "$LOG_BACKUP" ]; then
    LOG_SIZE=$(du -h "$LOG_BACKUP" | cut -f1)
    echo "Found: $LOG_BACKUP ($LOG_SIZE)"
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}Would delete: $LOG_SIZE log backup${NC}"
    else
        rm "$LOG_BACKUP"
        echo -e "${GREEN}✓ Deleted $LOG_SIZE log backup${NC}"
    fi
else
    echo -e "${YELLOW}ℹ Log backup already removed${NC}"
fi
echo ""

# 3. Clean old backup directories from disk (not in git)
echo -e "${BLUE}3. Cleaning old backup directories${NC}"

# .accessibility-fix-backups/ (17 files from August 2025)
if [ -d ".accessibility-fix-backups" ]; then
    BACKUP_SIZE=$(du -sh .accessibility-fix-backups/ 2>/dev/null | cut -f1)
    FILE_COUNT=$(find .accessibility-fix-backups/ -type f | wc -l)
    echo "Found: .accessibility-fix-backups/ ($BACKUP_SIZE, $FILE_COUNT files)"
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}Would delete: .accessibility-fix-backups/ ($BACKUP_SIZE)${NC}"
    else
        rm -rf .accessibility-fix-backups/
        echo -e "${GREEN}✓ Deleted .accessibility-fix-backups/ ($BACKUP_SIZE)${NC}"
    fi
else
    echo -e "${YELLOW}ℹ .accessibility-fix-backups/ already removed${NC}"
fi

# backup/ directory
if [ -d "backup" ]; then
    BACKUP_SIZE=$(du -sh backup/ 2>/dev/null | cut -f1)
    FILE_COUNT=$(find backup/ -type f | wc -l)
    echo "Found: backup/ ($BACKUP_SIZE, $FILE_COUNT files)"
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}Would delete: backup/ ($BACKUP_SIZE)${NC}"
    else
        rm -rf backup/
        echo -e "${GREEN}✓ Deleted backup/ ($BACKUP_SIZE)${NC}"
    fi
else
    echo -e "${YELLOW}ℹ backup/ already removed${NC}"
fi

# backups/ directory (if contains .backup files)
if [ -d "backups" ]; then
    BACKUP_COUNT=$(find backups/ -name "*.backup" -o -name "*.bak" 2>/dev/null | wc -l)
    if [ "$BACKUP_COUNT" -gt 0 ]; then
        echo "Found: backups/ with $BACKUP_COUNT backup files"
        if [ "$DRY_RUN" = true ]; then
            echo -e "${YELLOW}Would delete: $BACKUP_COUNT backup files from backups/${NC}"
        else
            find backups/ -name "*.backup" -delete 2>/dev/null
            find backups/ -name "*.bak" -delete 2>/dev/null
            echo -e "${GREEN}✓ Cleaned $BACKUP_COUNT backup files from backups/${NC}"
        fi
    else
        echo -e "${YELLOW}ℹ backups/ contains no old backup files${NC}"
    fi
fi
echo ""

# 4. Clean old temporary files
echo -e "${BLUE}4. Cleaning temporary files${NC}"
TEMP_COUNT=$(find . -name "*.tmp" -o -name "*.temp" -not -path "./venv/*" -not -path "./.git/*" 2>/dev/null | wc -l)
if [ "$TEMP_COUNT" -gt 0 ]; then
    echo "Found: $TEMP_COUNT temporary files"
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}Would delete: $TEMP_COUNT temporary files${NC}"
    else
        find . -name "*.tmp" -not -path "./venv/*" -not -path "./.git/*" -delete 2>/dev/null
        find . -name "*.temp" -not -path "./venv/*" -not -path "./.git/*" -delete 2>/dev/null
        echo -e "${GREEN}✓ Deleted $TEMP_COUNT temporary files${NC}"
    fi
else
    echo -e "${GREEN}✓ No temporary files to clean${NC}"
fi
echo ""

# 5. Clean old .swp and .swo files (vim/editor temporary files)
echo -e "${BLUE}5. Cleaning editor temporary files${NC}"
EDITOR_TEMP_COUNT=$(find . \( -name "*.swp" -o -name "*.swo" -o -name "*~" \) -not -path "./venv/*" -not -path "./.git/*" 2>/dev/null | wc -l)
if [ "$EDITOR_TEMP_COUNT" -gt 0 ]; then
    echo "Found: $EDITOR_TEMP_COUNT editor temporary files"
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}Would delete: $EDITOR_TEMP_COUNT editor temporary files${NC}"
    else
        find . -name "*.swp" -not -path "./venv/*" -not -path "./.git/*" -delete 2>/dev/null
        find . -name "*.swo" -not -path "./venv/*" -not -path "./.git/*" -delete 2>/dev/null
        find . -name "*~" -not -path "./venv/*" -not -path "./.git/*" -delete 2>/dev/null
        echo -e "${GREEN}✓ Deleted $EDITOR_TEMP_COUNT editor temporary files${NC}"
    fi
else
    echo -e "${GREEN}✓ No editor temporary files to clean${NC}"
fi
echo ""

# Calculate space reclaimed (only in actual cleanup mode)
if [ "$DRY_RUN" = false ]; then
    END_SIZE=$(du -sb . 2>/dev/null | cut -f1)
    RECLAIMED=$((START_SIZE - END_SIZE))
    RECLAIMED_MB=$((RECLAIMED / 1048576))
fi

# Summary
echo -e "${BLUE}=== Cleanup Summary ===${NC}"
if [ "$DRY_RUN" = true ]; then
    echo -e "  ${YELLOW}🔍 DRY RUN - No files were actually deleted${NC}"
    echo ""
    echo "Categories scanned:"
else
    echo ""
fi
echo -e "  ${GREEN}✓${NC} Python cache files (*.pyc, __pycache__)"
echo -e "  ${GREEN}✓${NC} Large log backups (*.log.bak)"
echo -e "  ${GREEN}✓${NC} Old backup directories"
echo -e "  ${GREEN}✓${NC} Temporary files (*.tmp, *.temp)"
echo -e "  ${GREEN}✓${NC} Editor temporary files (*.swp, *.swo, *~)"
echo ""
if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}To actually perform cleanup, run:${NC}"
    echo -e "  ${BLUE}./scripts/cleanup-disk-space.sh${NC}"
else
    echo -e "${BLUE}Disk Space Reclaimed:${NC} ${GREEN}${RECLAIMED_MB} MB${NC}"
    echo ""
    echo -e "${GREEN}✓ Disk cleanup complete!${NC}"
fi
echo ""

# Optional: Show largest directories remaining
echo -e "${BLUE}Top 10 Largest Directories:${NC}"
du -h --max-depth=1 2>/dev/null | sort -hr | head -10
