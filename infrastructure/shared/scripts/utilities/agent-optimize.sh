#!/usr/bin/env bash
#
# Agent Optimization Wrapper Script - In-Place Edition
#
# Provides easy access to agent optimization functionality with git-based backup.
# Optimizes .claude/agents/ in-place using git for version control and rollback.
#
# Usage:
#   ./scripts/utilities/agent-optimize.sh [OPTIONS]
#
# Options:
#   --optimize      Run optimization (default action)
#   --restore       Restore from most recent git backup tag
#   --restore TAG   Restore from specific git backup tag
#   --list-backups  List all available backup tags
#   --status        Show git diff status of agents directory
#   --force         Force regeneration of all agents
#   --stats         Show detailed optimization statistics
#   --help          Show this help message

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

# Paths
AGENT_DIR="$PROJECT_ROOT/.claude/agents"
OPTIMIZER_SCRIPT="$SCRIPT_DIR/optimize_agents.py"

# Functions
print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

check_requirements() {
    # Check Python availability
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required but not found"
        exit 1
    fi

    # Check git availability
    if ! command -v git &> /dev/null; then
        print_error "Git is required but not found"
        exit 1
    fi

    # Check if in git repository
    if ! git rev-parse --git-dir &> /dev/null; then
        print_error "Not in a git repository"
        exit 1
    fi

    # Check optimizer script exists
    if [ ! -f "$OPTIMIZER_SCRIPT" ]; then
        print_error "Optimizer script not found: $OPTIMIZER_SCRIPT"
        exit 1
    fi

    # Check agent directory exists
    if [ ! -d "$AGENT_DIR" ]; then
        print_error "Agent directory not found: $AGENT_DIR"
        exit 1
    fi
}

run_optimization() {
    local force_flag=""
    local stats_flag="--stats"  # Always show stats

    if [ "$FORCE" = true ]; then
        force_flag="--force"
    fi

    print_header "Running Agent Optimization (In-Place)"

    # Run Python optimizer
    cd "$PROJECT_ROOT"
    python3 "$OPTIMIZER_SCRIPT" $force_flag $stats_flag

    print_success "Optimization complete!"
    print_info "Agents optimized in: $AGENT_DIR"
    echo ""
    print_info "To restore from backup:"
    echo "  $0 --restore"
}

restore_agents() {
    local tag="$1"

    print_header "Restoring Agents from Git Backup"

    cd "$PROJECT_ROOT"

    if [ -n "$tag" ]; then
        python3 "$OPTIMIZER_SCRIPT" --restore "$tag"
    else
        python3 "$OPTIMIZER_SCRIPT" --restore
    fi

    print_success "Agents restored successfully"
}

list_backups() {
    print_header "Available Backup Tags"

    cd "$PROJECT_ROOT"
    python3 "$OPTIMIZER_SCRIPT" --list-backups
}

show_status() {
    print_header "Agent Optimization Status"

    # Check if agents directory is tracked
    if [ -d "$AGENT_DIR" ]; then
        local file_count=$(ls -1 "$AGENT_DIR"/*.md 2>/dev/null | wc -l)
        print_info "Agent files: $file_count files in $AGENT_DIR"
    else
        print_error "Agent directory not found: $AGENT_DIR"
        exit 1
    fi

    # Show git status
    echo ""
    print_info "Git status of agents directory:"
    cd "$PROJECT_ROOT"
    git status --short .claude/agents/ || print_info "No changes"

    # Show recent backup tags
    echo ""
    print_info "Recent backup tags:"
    git tag --list 'agents-pre-optimization-*' --sort=-creatordate | head -5 || print_info "No backup tags found"

    # Check if optimization cache exists
    echo ""
    if [ -f "$AGENT_DIR/.optimization_cache.json" ]; then
        print_success "Optimization cache present"
    else
        print_info "No optimization cache (agents not yet optimized)"
    fi

    echo ""
}

show_help() {
    cat << EOF
Agent Optimization Tool - In-Place Edition

Optimizes Claude agent files by removing code blocks and verbose content
to reduce token usage. Uses git for backup and version control.

USAGE:
    $0 [OPTIONS]

OPTIONS:
    --optimize        Run optimization (default action)
    --restore         Restore from most recent git backup tag
    --restore TAG     Restore from specific git backup tag
    --list-backups    List all available backup tags
    --status          Show git diff status of agents directory
    --force           Force regeneration of all agents
    --stats           Show detailed optimization statistics
    --help            Show this help message

EXAMPLES:
    # Run optimization with default settings
    $0 --optimize

    # Force regeneration and show detailed stats
    $0 --optimize --force --stats

    # Restore from most recent backup
    $0 --restore

    # Restore from specific tag
    $0 --restore agents-pre-optimization-20251010-143022

    # Check current status
    $0 --status

    # List all backup tags
    $0 --list-backups

HOW IT WORKS:
    1. Creates timestamped git tag before optimization
    2. Optimizes .claude/agents/ files in-place
    3. Commits optimized files to git with statistics
    4. Fully reversible via git restore

NOTES:
    - Agents are optimized IN-PLACE in .claude/agents/
    - Git tags provide backup and rollback capability
    - Original files preserved in git history
    - Cache prevents unnecessary reprocessing
    - Safe to run multiple times

For more information, see: docs/developer/AGENT_OPTIMIZATION.md
EOF
}

# Parse command line arguments
FORCE=false
STATS=false
ACTION="optimize"
RESTORE_TAG=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --optimize)
            ACTION="optimize"
            shift
            ;;
        --restore)
            ACTION="restore"
            shift
            # Check if next arg is a tag name
            if [[ $# -gt 0 && ! "$1" =~ ^-- ]]; then
                RESTORE_TAG="$1"
                shift
            fi
            ;;
        --list-backups)
            ACTION="list-backups"
            shift
            ;;
        --status)
            ACTION="status"
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --stats)
            STATS=true
            shift
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Main execution
check_requirements

case "$ACTION" in
    optimize)
        run_optimization
        ;;
    restore)
        restore_agents "$RESTORE_TAG"
        ;;
    list-backups)
        list_backups
        ;;
    status)
        show_status
        ;;
    *)
        print_error "Unknown action: $ACTION"
        exit 1
        ;;
esac
