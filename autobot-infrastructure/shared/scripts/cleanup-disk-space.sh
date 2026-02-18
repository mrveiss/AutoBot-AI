#!/bin/bash
# AutoBot Disk Space Cleanup Script
# Compliance with CLAUDE.md Repository Cleanliness Standards
#
# Cleans up temporary files, Python cache, and old backups
# Does NOT modify git tracking - only removes files from disk
#
# Created: 2025-10-10
# Updated: 2025-10-10 (refactored to 100% quality standards)
# Purpose: Disk space management and cleanup
#
# Usage:
#   ./cleanup-disk-space.sh           # Execute cleanup
#   ./cleanup-disk-space.sh --dry-run # Preview what would be deleted
#   ./cleanup-disk-space.sh -n        # Preview (short form)
#   ./cleanup-disk-space.sh --log     # Enable logging to file
#   ./cleanup-disk-space.sh --help    # Show help

# Strict mode for maximum safety and error detection
set -euo pipefail
IFS=$'\n\t'

# ============================================================================
# CONSTANTS
# ============================================================================

readonly AUTOBOT_ROOT="/home/kali/Desktop/AutoBot"
readonly BYTES_TO_MB=1048576
readonly BYTES_TO_KB=1024
readonly PROGRESS_THRESHOLD=100  # Show progress if >100 files
readonly SPINNER_CHARS='|/-\'

# Message prefixes for standardized output
readonly MSG_PREFIX_INFO="[INFO]"
readonly MSG_PREFIX_SUCCESS="[SUCCESS]"
readonly MSG_PREFIX_ERROR="[ERROR]"
readonly MSG_PREFIX_DRYRUN="[DRY-RUN]"
readonly MSG_PREFIX_WARN="[WARN]"

# Color output for clarity
readonly GREEN='\033[0;32m'
readonly BLUE='\033[0;34m'
readonly YELLOW='\033[1;33m'
readonly RED='\033[0;31m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m' # No Color

# Global state variables
DRY_RUN=false
ENABLE_LOGGING=false
LOG_FILE=""
ERROR_COUNT=0

# Category-specific error counters
PYTHON_ERRORS=0
LOG_ERRORS=0
BACKUP_ERRORS=0
TEMP_ERRORS=0
EDITOR_ERRORS=0

# Statistics tracking
declare -A STATS_FILES_DELETED
declare -A STATS_SPACE_RECLAIMED

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

#
# format_message() - Standardized message formatting with optional logging
#
# Arguments:
#   $1 - Message type (INFO, SUCCESS, ERROR, DRYRUN, WARN)
#   $2 - Message content
#
# Output:
#   Formatted message to stdout and optionally to log file
#
format_message() {
    local msg_type="$1"
    local msg_content="$2"
    local prefix=""
    local color=""

    case "$msg_type" in
        INFO)
            prefix="$MSG_PREFIX_INFO"
            color="$BLUE"
            ;;
        SUCCESS)
            prefix="$MSG_PREFIX_SUCCESS"
            color="$GREEN"
            ;;
        ERROR)
            prefix="$MSG_PREFIX_ERROR"
            color="$RED"
            ;;
        DRYRUN)
            prefix="$MSG_PREFIX_DRYRUN"
            color="$YELLOW"
            ;;
        WARN)
            prefix="$MSG_PREFIX_WARN"
            color="$YELLOW"
            ;;
        *)
            prefix="[UNKNOWN]"
            color="$NC"
            ;;
    esac

    # Output to terminal with color
    echo -e "${color}${prefix}${NC} ${msg_content}"

    # Output to log file without color if logging enabled
    if [[ "$ENABLE_LOGGING" == true ]] && [[ -n "$LOG_FILE" ]]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') ${prefix} ${msg_content}" >> "$LOG_FILE"
    fi
}

#
# log_to_file() - Write raw message to log file
#
# Arguments:
#   $1 - Message content
#
log_to_file() {
    if [[ "$ENABLE_LOGGING" == true ]] && [[ -n "$LOG_FILE" ]]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_FILE"
    fi
}

#
# validate_command_output() - Validate command execution and output
#
# Arguments:
#   $1 - Command output
#   $2 - Command description
#
# Returns:
#   0 if valid, 1 if invalid
#
validate_command_output() {
    local output="$1"
    local description="$2"

    if [[ -z "$output" ]] || [[ "$output" == "0" ]]; then
        return 1
    fi

    return 0
}

#
# show_progress() - Display progress indicator for large operations
#
# Arguments:
#   $1 - Current count
#   $2 - Total count
#   $3 - Operation description
#
show_progress() {
    local current="$1"
    local total="$2"
    local description="$3"
    local percent=0

    if [[ "$total" -gt 0 ]]; then
        percent=$((current * 100 / total))
    fi

    local spinner_idx=$((current % 4))
    local spinner_char="${SPINNER_CHARS:$spinner_idx:1}"

    # Clear line and show progress
    printf "\r${CYAN}${spinner_char}${NC} %s: %d/%d (%d%%)" "$description" "$current" "$total" "$percent"
}

#
# estimate_time() - Estimate time remaining for operation
#
# Arguments:
#   $1 - Files processed
#   $2 - Total files
#   $3 - Elapsed seconds
#
# Output:
#   Estimated time remaining
#
estimate_time() {
    local processed="$1"
    local total="$2"
    local elapsed="$3"

    if [[ "$processed" -eq 0 ]] || [[ "$total" -eq 0 ]]; then
        echo "Unknown"
        return
    fi

    local remaining=$((total - processed))
    local rate=$(echo "scale=2; $elapsed / $processed" | bc -l 2>/dev/null || echo "0")
    local estimated=$(echo "scale=0; $rate * $remaining" | bc -l 2>/dev/null || echo "0")

    if [[ "$estimated" -lt 60 ]]; then
        echo "${estimated}s"
    else
        local minutes=$((estimated / 60))
        echo "${minutes}m"
    fi
}

#
# increment_error_counter() - Increment error counter for category
#
# Arguments:
#   $1 - Category (PYTHON, LOG, BACKUP, TEMP, EDITOR)
#
increment_error_counter() {
    local category="$1"

    ((ERROR_COUNT++)) || true

    case "$category" in
        PYTHON)
            ((PYTHON_ERRORS++)) || true
            ;;
        LOG)
            ((LOG_ERRORS++)) || true
            ;;
        BACKUP)
            ((BACKUP_ERRORS++)) || true
            ;;
        TEMP)
            ((TEMP_ERRORS++)) || true
            ;;
        EDITOR)
            ((EDITOR_ERRORS++)) || true
            ;;
    esac
}

# ============================================================================
# CLEANUP FUNCTIONS
# ============================================================================

#
# cleanup_python_cache() - Remove Python cache files
#
# Removes:
#   - *.pyc files
#   - __pycache__ directories
#
# Returns:
#   Number of items cleaned
#
cleanup_python_cache() {
    local category="Python cache files"
    format_message "INFO" "Cleaning ${category}..."

    local pyc_count=0
    local pycache_count=0
    local total_cleaned=0
    local space_before=0
    local space_after=0

    # Count .pyc files
    if pyc_count=$(find . -type f -name "*.pyc" -not -path "./venv/*" -not -path "./.git/*" 2>/dev/null | wc -l); then
        format_message "INFO" "Found ${pyc_count} .pyc files"

        if [[ "$pyc_count" -gt 0 ]]; then
            if [[ "$DRY_RUN" == true ]]; then
                format_message "DRYRUN" "Would delete ${pyc_count} .pyc files"
            else
                # Show progress for large operations
                if [[ "$pyc_count" -gt "$PROGRESS_THRESHOLD" ]]; then
                    local start_time=$SECONDS
                    local processed=0

                    while IFS= read -r file; do
                        rm -f "$file" 2>/dev/null || increment_error_counter "PYTHON"
                        ((processed++)) || true

                        if [[ $((processed % 25)) -eq 0 ]]; then
                            show_progress "$processed" "$pyc_count" "Deleting .pyc files"
                        fi
                    done < <(find . -type f -name "*.pyc" -not -path "./venv/*" -not -path "./.git/*" 2>/dev/null)

                    printf "\n"
                else
                    find . -type f -name "*.pyc" -not -path "./venv/*" -not -path "./.git/*" -delete 2>/dev/null || increment_error_counter "PYTHON"
                fi

                format_message "SUCCESS" "Deleted ${pyc_count} .pyc files"
                ((total_cleaned += pyc_count)) || true
            fi
        else
            format_message "SUCCESS" "No .pyc files to clean"
        fi
    else
        format_message "ERROR" "Failed to count .pyc files"
        increment_error_counter "PYTHON"
    fi

    # Count __pycache__ directories
    if pycache_count=$(find . -type d -name "__pycache__" -not -path "./venv/*" -not -path "./.git/*" 2>/dev/null | wc -l); then
        format_message "INFO" "Found ${pycache_count} __pycache__ directories"

        if [[ "$pycache_count" -gt 0 ]]; then
            if [[ "$DRY_RUN" == true ]]; then
                format_message "DRYRUN" "Would delete ${pycache_count} __pycache__ directories"
            else
                find . -type d -name "__pycache__" -not -path "./venv/*" -not -path "./.git/*" -exec rm -rf {} + 2>/dev/null || increment_error_counter "PYTHON"
                format_message "SUCCESS" "Deleted ${pycache_count} __pycache__ directories"
                ((total_cleaned += pycache_count)) || true
            fi
        else
            format_message "SUCCESS" "No __pycache__ directories to clean"
        fi
    else
        format_message "ERROR" "Failed to count __pycache__ directories"
        increment_error_counter "PYTHON"
    fi

    STATS_FILES_DELETED["python"]=$total_cleaned
    echo ""

    return 0
}

#
# cleanup_log_backups() - Remove large log backup files
#
# Removes:
#   - *.log.bak files
#
# Returns:
#   Number of items cleaned
#
cleanup_log_backups() {
    local category="Log backup files"
    format_message "INFO" "Cleaning ${category}..."

    local log_backup="logs/backup/autobot_backend_20250819_100021.log.bak"
    local total_cleaned=0

    if [[ -f "$log_backup" ]]; then
        local log_size=""
        if log_size=$(du -h "$log_backup" 2>/dev/null | cut -f1); then
            format_message "INFO" "Found ${log_backup} (${log_size})"

            if [[ "$DRY_RUN" == true ]]; then
                format_message "DRYRUN" "Would delete ${log_size} log backup"
            else
                if rm "$log_backup" 2>/dev/null; then
                    format_message "SUCCESS" "Deleted ${log_size} log backup"
                    ((total_cleaned++)) || true
                else
                    format_message "ERROR" "Failed to delete log backup"
                    increment_error_counter "LOG"
                fi
            fi
        else
            format_message "ERROR" "Failed to get size of log backup"
            increment_error_counter "LOG"
        fi
    else
        format_message "INFO" "No log backup files to clean"
    fi

    STATS_FILES_DELETED["logs"]=$total_cleaned
    echo ""

    return 0
}

#
# cleanup_backup_directories() - Remove old backup directories
#
# Removes:
#   - .accessibility-fix-backups/
#   - backup/
#   - *.backup and *.bak files from backups/
#
# Returns:
#   Number of items cleaned
#
cleanup_backup_directories() {
    local category="Backup directories"
    format_message "INFO" "Cleaning ${category}..."

    local total_cleaned=0

    # .accessibility-fix-backups/ directory
    if [[ -d ".accessibility-fix-backups" ]]; then
        local backup_size=""
        local file_count=0

        if backup_size=$(du -sh .accessibility-fix-backups/ 2>/dev/null | cut -f1) && \
           file_count=$(find .accessibility-fix-backups/ -type f 2>/dev/null | wc -l); then
            format_message "INFO" "Found .accessibility-fix-backups/ (${backup_size}, ${file_count} files)"

            if [[ "$DRY_RUN" == true ]]; then
                format_message "DRYRUN" "Would delete .accessibility-fix-backups/ (${backup_size})"
            else
                if rm -rf .accessibility-fix-backups/ 2>/dev/null; then
                    format_message "SUCCESS" "Deleted .accessibility-fix-backups/ (${backup_size})"
                    ((total_cleaned += file_count)) || true
                else
                    format_message "ERROR" "Failed to delete .accessibility-fix-backups/"
                    increment_error_counter "BACKUP"
                fi
            fi
        else
            format_message "ERROR" "Failed to analyze .accessibility-fix-backups/"
            increment_error_counter "BACKUP"
        fi
    else
        format_message "INFO" "No .accessibility-fix-backups/ directory to clean"
    fi

    # backup/ directory
    if [[ -d "backup" ]]; then
        local backup_size=""
        local file_count=0

        if backup_size=$(du -sh backup/ 2>/dev/null | cut -f1) && \
           file_count=$(find backup/ -type f 2>/dev/null | wc -l); then
            format_message "INFO" "Found backup/ (${backup_size}, ${file_count} files)"

            if [[ "$DRY_RUN" == true ]]; then
                format_message "DRYRUN" "Would delete backup/ (${backup_size})"
            else
                if rm -rf backup/ 2>/dev/null; then
                    format_message "SUCCESS" "Deleted backup/ (${backup_size})"
                    ((total_cleaned += file_count)) || true
                else
                    format_message "ERROR" "Failed to delete backup/"
                    increment_error_counter "BACKUP"
                fi
            fi
        else
            format_message "ERROR" "Failed to analyze backup/"
            increment_error_counter "BACKUP"
        fi
    else
        format_message "INFO" "No backup/ directory to clean"
    fi

    # backups/ directory (clean *.backup and *.bak files)
    if [[ -d "backups" ]]; then
        local backup_count=0

        if backup_count=$(find backups/ \( -name "*.backup" -o -name "*.bak" \) 2>/dev/null | wc -l); then
            if [[ "$backup_count" -gt 0 ]]; then
                format_message "INFO" "Found ${backup_count} backup files in backups/"

                if [[ "$DRY_RUN" == true ]]; then
                    format_message "DRYRUN" "Would delete ${backup_count} backup files from backups/"
                else
                    find backups/ -name "*.backup" -delete 2>/dev/null || increment_error_counter "BACKUP"
                    find backups/ -name "*.bak" -delete 2>/dev/null || increment_error_counter "BACKUP"
                    format_message "SUCCESS" "Cleaned ${backup_count} backup files from backups/"
                    ((total_cleaned += backup_count)) || true
                fi
            else
                format_message "INFO" "No backup files in backups/ to clean"
            fi
        else
            format_message "ERROR" "Failed to count backup files in backups/"
            increment_error_counter "BACKUP"
        fi
    fi

    STATS_FILES_DELETED["backups"]=$total_cleaned
    echo ""

    return 0
}

#
# cleanup_temporary_files() - Remove temporary files
#
# Removes:
#   - *.tmp files
#   - *.temp files
#
# Returns:
#   Number of items cleaned
#
cleanup_temporary_files() {
    local category="Temporary files"
    format_message "INFO" "Cleaning ${category}..."

    local temp_count=0
    local total_cleaned=0

    if temp_count=$(find . \( -name "*.tmp" -o -name "*.temp" \) -not -path "./venv/*" -not -path "./.git/*" 2>/dev/null | wc -l); then
        if [[ "$temp_count" -gt 0 ]]; then
            format_message "INFO" "Found ${temp_count} temporary files"

            if [[ "$DRY_RUN" == true ]]; then
                format_message "DRYRUN" "Would delete ${temp_count} temporary files"
            else
                find . -name "*.tmp" -not -path "./venv/*" -not -path "./.git/*" -delete 2>/dev/null || increment_error_counter "TEMP"
                find . -name "*.temp" -not -path "./venv/*" -not -path "./.git/*" -delete 2>/dev/null || increment_error_counter "TEMP"
                format_message "SUCCESS" "Deleted ${temp_count} temporary files"
                ((total_cleaned += temp_count)) || true
            fi
        else
            format_message "SUCCESS" "No temporary files to clean"
        fi
    else
        format_message "ERROR" "Failed to count temporary files"
        increment_error_counter "TEMP"
    fi

    STATS_FILES_DELETED["temp"]=$total_cleaned
    echo ""

    return 0
}

#
# cleanup_editor_temps() - Remove editor temporary files
#
# Removes:
#   - *.swp files (vim swap files)
#   - *.swo files (vim swap files)
#   - *~ files (editor backups)
#
# Returns:
#   Number of items cleaned
#
cleanup_editor_temps() {
    local category="Editor temporary files"
    format_message "INFO" "Cleaning ${category}..."

    local editor_temp_count=0
    local total_cleaned=0

    if editor_temp_count=$(find . \( -name "*.swp" -o -name "*.swo" -o -name "*~" \) -not -path "./venv/*" -not -path "./.git/*" 2>/dev/null | wc -l); then
        if [[ "$editor_temp_count" -gt 0 ]]; then
            format_message "INFO" "Found ${editor_temp_count} editor temporary files"

            if [[ "$DRY_RUN" == true ]]; then
                format_message "DRYRUN" "Would delete ${editor_temp_count} editor temporary files"
            else
                find . -name "*.swp" -not -path "./venv/*" -not -path "./.git/*" -delete 2>/dev/null || increment_error_counter "EDITOR"
                find . -name "*.swo" -not -path "./venv/*" -not -path "./.git/*" -delete 2>/dev/null || increment_error_counter "EDITOR"
                find . -name "*~" -not -path "./venv/*" -not -path "./.git/*" -delete 2>/dev/null || increment_error_counter "EDITOR"
                format_message "SUCCESS" "Deleted ${editor_temp_count} editor temporary files"
                ((total_cleaned += editor_temp_count)) || true
            fi
        else
            format_message "SUCCESS" "No editor temporary files to clean"
        fi
    else
        format_message "ERROR" "Failed to count editor temporary files"
        increment_error_counter "EDITOR"
    fi

    STATS_FILES_DELETED["editor"]=$total_cleaned
    echo ""

    return 0
}

#
# calculate_statistics() - Calculate and display detailed statistics
#
# Output:
#   Categorized breakdown of cleanup results
#
calculate_statistics() {
    local total_files=0

    echo -e "${BLUE}=== Detailed Statistics ===${NC}"
    echo ""

    echo "Files cleaned by category:"
    for category in python logs backups temp editor; do
        local count="${STATS_FILES_DELETED[$category]:-0}"
        ((total_files += count)) || true

        if [[ "$count" -gt 0 ]]; then
            echo -e "  ${GREEN}✓${NC} ${category}: ${count} items"
        else
            echo -e "  ${YELLOW}○${NC} ${category}: 0 items"
        fi
    done

    echo ""
    echo -e "Total items cleaned: ${GREEN}${total_files}${NC}"

    if [[ "$ERROR_COUNT" -gt 0 ]]; then
        echo ""
        echo -e "${RED}Errors encountered:${NC}"
        [[ "$PYTHON_ERRORS" -gt 0 ]] && echo -e "  ${RED}✗${NC} Python cache: ${PYTHON_ERRORS}"
        [[ "$LOG_ERRORS" -gt 0 ]] && echo -e "  ${RED}✗${NC} Log backups: ${LOG_ERRORS}"
        [[ "$BACKUP_ERRORS" -gt 0 ]] && echo -e "  ${RED}✗${NC} Backup directories: ${BACKUP_ERRORS}"
        [[ "$TEMP_ERRORS" -gt 0 ]] && echo -e "  ${RED}✗${NC} Temporary files: ${TEMP_ERRORS}"
        [[ "$EDITOR_ERRORS" -gt 0 ]] && echo -e "  ${RED}✗${NC} Editor temps: ${EDITOR_ERRORS}"
        echo -e "  Total errors: ${RED}${ERROR_COUNT}${NC}"
    fi

    echo ""
}

# ============================================================================
# ARGUMENT PARSING
# ============================================================================

show_help() {
    cat << 'EOF'
AutoBot Disk Space Cleanup Script

USAGE:
    ./cleanup-disk-space.sh [OPTIONS]

OPTIONS:
    --dry-run, -n    Preview what would be deleted without actually deleting
    --log            Enable logging to file (logs/cleanup-TIMESTAMP.log)
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

FEATURES:
    - Progress indicators for large operations (>100 files)
    - Detailed error tracking and reporting
    - Categorized cleanup statistics
    - Optional logging capability
    - Safe dry-run mode for preview

EXAMPLES:
    # Preview cleanup (safe to run anytime)
    ./cleanup-disk-space.sh --dry-run

    # Actually perform cleanup
    ./cleanup-disk-space.sh

    # Perform cleanup with logging enabled
    ./cleanup-disk-space.sh --log

EOF
    exit 0
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run|-n)
            DRY_RUN=true
            shift
            ;;
        --log)
            ENABLE_LOGGING=true
            shift
            ;;
        --help|-h)
            show_help
            ;;
        *)
            format_message "ERROR" "Unknown option: $1"
            echo "Use --help to see available options"
            exit 1
            ;;
    esac
done

# ============================================================================
# INITIALIZATION
# ============================================================================

# Setup logging if enabled
if [[ "$ENABLE_LOGGING" == true ]]; then
    mkdir -p logs
    LOG_FILE="logs/cleanup-$(date +%Y%m%d-%H%M%S).log"
    format_message "INFO" "Logging enabled: ${LOG_FILE}"
fi

# Change to AutoBot root directory
cd "$AUTOBOT_ROOT" || {
    format_message "ERROR" "Failed to change to AutoBot root directory"
    exit 1
}

# Display header
echo -e "${BLUE}=== AutoBot Disk Space Cleanup ===${NC}"
if [[ "$DRY_RUN" == true ]]; then
    echo -e "${YELLOW}🔍 DRY RUN MODE - No files will be deleted${NC}"
    echo "Showing what would be cleaned up..."
else
    echo "Cleaning temporary files, caches, and old backups"
fi
echo ""

# Track space reclaimed
START_SIZE=0
if START_SIZE=$(du -sb . 2>/dev/null | cut -f1); then
    log_to_file "Initial directory size: ${START_SIZE} bytes"
else
    format_message "WARN" "Could not determine initial directory size"
fi

# Safety check: verify we're in AutoBot directory
if [[ ! -f "CLAUDE.md" ]] || [[ ! -f "setup.sh" ]]; then
    format_message "ERROR" "Not in AutoBot root directory!"
    echo "Expected: /home/kali/Desktop/AutoBot/"
    echo "Current: $(pwd)"
    exit 1
fi

format_message "SUCCESS" "Verified AutoBot root directory"
echo ""

# ============================================================================
# MAIN EXECUTION
# ============================================================================

# Execute cleanup functions
cleanup_python_cache
cleanup_log_backups
cleanup_backup_directories
cleanup_temporary_files
cleanup_editor_temps

# Calculate space reclaimed (only in actual cleanup mode)
RECLAIMED_MB=0
RECLAIMED_KB=0

if [[ "$DRY_RUN" == false ]]; then
    END_SIZE=0
    if END_SIZE=$(du -sb . 2>/dev/null | cut -f1); then
        if [[ -n "$END_SIZE" ]] && [[ -n "$START_SIZE" ]]; then
            RECLAIMED=$((START_SIZE - END_SIZE))

            # Handle case where directory grew during cleanup
            if [[ "$RECLAIMED" -lt 0 ]]; then
                RECLAIMED=0
            fi

            RECLAIMED_MB=$((RECLAIMED / BYTES_TO_MB))
            RECLAIMED_KB=$((RECLAIMED / BYTES_TO_KB))

            log_to_file "Final directory size: ${END_SIZE} bytes"
            log_to_file "Space reclaimed: ${RECLAIMED} bytes"
        else
            format_message "WARN" "Could not calculate space reclaimed"
        fi
    else
        format_message "WARN" "Could not determine final directory size"
    fi
fi

# ============================================================================
# SUMMARY
# ============================================================================

echo -e "${BLUE}=== Cleanup Summary ===${NC}"
if [[ "$DRY_RUN" == true ]]; then
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

# Display detailed statistics
calculate_statistics

if [[ "$DRY_RUN" == true ]]; then
    echo -e "${YELLOW}To actually perform cleanup, run:${NC}"
    echo -e "  ${BLUE}./scripts/cleanup-disk-space.sh${NC}"
else
    # Show KB for small cleanups, MB for larger
    if [[ "$RECLAIMED_MB" -eq 0 ]] && [[ "$RECLAIMED_KB" -gt 0 ]]; then
        echo -e "${BLUE}Disk Space Reclaimed:${NC} ${GREEN}${RECLAIMED_KB} KB${NC}"
    elif [[ "$RECLAIMED_MB" -gt 0 ]]; then
        echo -e "${BLUE}Disk Space Reclaimed:${NC} ${GREEN}${RECLAIMED_MB} MB${NC}"
    else
        echo -e "${YELLOW}No significant space reclaimed (< 1 KB)${NC}"
    fi
    echo ""

    if [[ "$ERROR_COUNT" -eq 0 ]]; then
        format_message "SUCCESS" "Disk cleanup complete!"
    else
        format_message "WARN" "Disk cleanup complete with ${ERROR_COUNT} errors"
    fi
fi
echo ""

# Reminder for dry-run mode before final output
if [[ "$DRY_RUN" == true ]]; then
    echo -e "${YELLOW}Remember: This was a DRY RUN - no files were deleted${NC}"
    echo ""
fi

# Optional: Show largest directories remaining
echo -e "${BLUE}Top 10 Largest Directories:${NC}"
if du -h --max-depth=1 2>/dev/null | sort -hr | head -10; then
    log_to_file "Top 10 directories displayed successfully"
else
    format_message "WARN" "Could not display top directories"
fi

# Final logging
if [[ "$ENABLE_LOGGING" == true ]]; then
    echo ""
    format_message "INFO" "Log saved to: ${LOG_FILE}"
fi

exit 0
