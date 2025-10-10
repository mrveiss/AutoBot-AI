#!/usr/bin/env bash
#
# Agent Optimization Wrapper Script
#
# Provides easy access to agent optimization functionality with
# environment-based configuration and CLI integration.
#
# Usage:
#   ./scripts/utilities/agent-optimize.sh [--force] [--dry-run] [--stats] [--enable] [--disable]
#
# Options:
#   --force      Force regeneration of all agents
#   --dry-run    Show what would be done without changes
#   --stats      Show detailed optimization statistics
#   --enable     Enable optimized agents for Claude CLI
#   --disable    Disable optimized agents (use originals)
#   --help       Show this help message

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Paths
SOURCE_DIR="$PROJECT_ROOT/.claude/agents"
TARGET_DIR="$PROJECT_ROOT/.claude/agents-optimized"
ACTIVE_LINK="$PROJECT_ROOT/.claude/agents-active"
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

    # Check optimizer script exists
    if [ ! -f "$OPTIMIZER_SCRIPT" ]; then
        print_error "Optimizer script not found: $OPTIMIZER_SCRIPT"
        exit 1
    fi

    # Check source directory exists
    if [ ! -d "$SOURCE_DIR" ]; then
        print_error "Agent source directory not found: $SOURCE_DIR"
        exit 1
    fi
}

run_optimization() {
    local force_flag=""
    local dry_run_flag=""
    local stats_flag="--stats"  # Always show stats

    if [ "$FORCE" = true ]; then
        force_flag="--force"
    fi

    if [ "$DRY_RUN" = true ]; then
        dry_run_flag="--dry-run"
    fi

    print_header "Running Agent Optimization"

    # Run Python optimizer
    cd "$PROJECT_ROOT"
    python3 "$OPTIMIZER_SCRIPT" $force_flag $dry_run_flag $stats_flag

    if [ "$DRY_RUN" != true ]; then
        print_success "Optimization complete!"
        print_info "Optimized agents available in: $TARGET_DIR"
    fi
}

enable_optimized_agents() {
    print_header "Enabling Optimized Agents"

    # Check if optimized directory exists
    if [ ! -d "$TARGET_DIR" ]; then
        print_warning "Optimized agents not found. Running optimization first..."
        run_optimization
    fi

    # Create symbolic link to optimized directory
    if [ -L "$ACTIVE_LINK" ] || [ -e "$ACTIVE_LINK" ]; then
        rm -f "$ACTIVE_LINK"
    fi

    ln -s "$(basename "$TARGET_DIR")" "$ACTIVE_LINK"

    print_success "Optimized agents enabled"
    print_info "Claude CLI will now use agents from: $TARGET_DIR"
    print_info "Symlink created: $ACTIVE_LINK -> $(basename "$TARGET_DIR")"

    # Show token savings
    echo ""
    print_info "To use optimized agents in Claude CLI:"
    echo "  export CLAUDE_AGENT_DIR=\"$ACTIVE_LINK\""
    echo ""
    print_info "Or add to your ~/.bashrc or ~/.zshrc:"
    echo "  export CLAUDE_AGENT_DIR=\"\$HOME/.config/claude/agents-optimized\""
}

disable_optimized_agents() {
    print_header "Disabling Optimized Agents"

    # Remove symbolic link
    if [ -L "$ACTIVE_LINK" ]; then
        rm -f "$ACTIVE_LINK"
        print_success "Optimized agents disabled"
        print_info "Claude CLI will now use original agents from: $SOURCE_DIR"
    else
        print_info "Optimized agents are not currently enabled"
    fi

    # Reset environment variable
    echo ""
    print_info "To use original agents, unset CLAUDE_AGENT_DIR:"
    echo "  unset CLAUDE_AGENT_DIR"
}

show_status() {
    print_header "Agent Optimization Status"

    # Check if optimized directory exists
    if [ -d "$TARGET_DIR" ]; then
        local file_count=$(ls -1 "$TARGET_DIR"/*.md 2>/dev/null | wc -l)
        print_success "Optimized agents: $file_count files in $TARGET_DIR"

        # Check if cache exists
        if [ -f "$TARGET_DIR/.optimization_cache.json" ]; then
            print_info "Optimization cache present"
        fi
    else
        print_warning "Optimized agents not generated yet"
    fi

    # Check if active link exists
    if [ -L "$ACTIVE_LINK" ]; then
        local target=$(readlink "$ACTIVE_LINK")
        print_success "Optimized agents ENABLED via symlink: $ACTIVE_LINK -> $target"
    else
        print_info "Optimized agents DISABLED (using originals)"
    fi

    # Check environment variable
    if [ -n "$CLAUDE_AGENT_DIR" ]; then
        print_info "CLAUDE_AGENT_DIR is set to: $CLAUDE_AGENT_DIR"
    else
        print_info "CLAUDE_AGENT_DIR is not set"
    fi

    echo ""
}

show_help() {
    cat << EOF
Agent Optimization Tool

Optimizes Claude agent files by removing code blocks and verbose content
to reduce token usage while preserving functionality.

USAGE:
    $0 [OPTIONS]

OPTIONS:
    --force         Force regeneration of all optimized agents
    --dry-run       Show what would be done without making changes
    --stats         Show detailed optimization statistics
    --enable        Enable optimized agents for Claude CLI use
    --disable       Disable optimized agents (revert to originals)
    --status        Show current optimization status
    --help          Show this help message

EXAMPLES:
    # Run optimization with default settings
    $0

    # Force regeneration and show detailed stats
    $0 --force --stats

    # Enable optimized agents for use
    $0 --enable

    # Check current status
    $0 --status

    # Dry run to preview changes
    $0 --dry-run

ENVIRONMENT VARIABLES:
    CLAUDE_AGENT_DIR    Override agent directory for Claude CLI

NOTES:
    - Original agent files are NEVER modified
    - Optimized copies are created in separate directory
    - Use --enable to switch Claude CLI to optimized agents
    - Use --disable to revert to original agents
    - Optimization is cached for performance

For more information, see: docs/developer/AGENT_OPTIMIZATION.md
EOF
}

# Parse command line arguments
FORCE=false
DRY_RUN=false
STATS=false
ENABLE=false
DISABLE=false
STATUS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --stats)
            STATS=true
            shift
            ;;
        --enable)
            ENABLE=true
            shift
            ;;
        --disable)
            DISABLE=true
            shift
            ;;
        --status)
            STATUS=true
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

if [ "$STATUS" = true ]; then
    show_status
    exit 0
fi

if [ "$ENABLE" = true ]; then
    enable_optimized_agents
    exit 0
fi

if [ "$DISABLE" = true ]; then
    disable_optimized_agents
    exit 0
fi

# Default: run optimization
run_optimization

# Suggest enabling if not already enabled
if [ ! -L "$ACTIVE_LINK" ] && [ "$DRY_RUN" != true ]; then
    echo ""
    print_info "Tip: Run '$0 --enable' to activate optimized agents"
fi
