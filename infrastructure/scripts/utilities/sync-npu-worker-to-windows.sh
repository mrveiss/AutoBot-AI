#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Sync NPU Worker to Windows Host
# This script syncs the Windows NPU worker package from WSL2 to the Windows host.
#
# Usage:
#   ./sync-npu-worker-to-windows.sh [options]
#
# Options:
#   -d, --destination    Windows destination path (default: /mnt/c/AutoBot/NPU)
#   -s, --source         Source path (default: resources/windows-npu-worker)
#   -n, --dry-run        Show what would be copied without copying
#   -f, --force          Force overwrite without confirmation
#   -h, --help           Show this help message

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SOURCE_PATH="${PROJECT_ROOT}/resources/windows-npu-worker"
DEST_PATH="/mnt/c/AutoBot/NPU"

# Options
DRY_RUN=false
FORCE=false

# Function to print colored output
print_info() { echo -e "${CYAN}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Function to show help
show_help() {
    cat << EOF
AutoBot NPU Worker - Sync to Windows Script

Syncs the Windows NPU worker package from WSL2 to the Windows host filesystem.

Usage:
    $(basename "$0") [options]

Options:
    -d, --destination PATH    Windows destination path (default: /mnt/c/AutoBot/NPU)
    -s, --source PATH         Source path (default: resources/windows-npu-worker)
    -n, --dry-run             Show what would be copied without copying
    -f, --force               Force overwrite without confirmation
    -h, --help                Show this help message

Examples:
    # Sync to default location (C:\AutoBot\NPU)
    $(basename "$0")

    # Dry run to see what would be synced
    $(basename "$0") --dry-run

    # Sync to custom Windows location
    $(basename "$0") --destination /mnt/d/AutoBot/NPU

    # Force sync without confirmation
    $(basename "$0") --force

Prerequisites:
    - Running in WSL2 environment
    - Windows filesystem mounted at /mnt/c (or other drive)
    - Source directory exists: ${SOURCE_PATH}

After syncing:
    1. Open PowerShell as Administrator on Windows
    2. Navigate to the destination: cd C:\AutoBot\NPU
    3. Run installation: .\scripts\install.ps1

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--destination)
            DEST_PATH="$2"
            shift 2
            ;;
        -s|--source)
            SOURCE_PATH="$2"
            shift 2
            ;;
        -n|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Banner
echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  AutoBot NPU Worker - Sync to Windows${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# Check if running in WSL2
if [[ ! -d /mnt/c ]]; then
    print_error "Windows filesystem not mounted at /mnt/c"
    print_info "This script requires WSL2 with Windows filesystem access"
    exit 1
fi

# Check source directory exists
if [[ ! -d "$SOURCE_PATH" ]]; then
    print_error "Source directory not found: $SOURCE_PATH"
    exit 1
fi

print_info "Source: $SOURCE_PATH"
print_info "Destination: $DEST_PATH"

# Check if destination exists
if [[ -d "$DEST_PATH" ]] && [[ "$FORCE" != true ]] && [[ "$DRY_RUN" != true ]]; then
    print_warning "Destination already exists: $DEST_PATH"
    read -p "Do you want to overwrite? (y/N): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        print_info "Sync cancelled"
        exit 0
    fi
fi

# Create parent directories
DEST_PARENT=$(dirname "$DEST_PATH")
if [[ ! -d "$DEST_PARENT" ]]; then
    if [[ "$DRY_RUN" == true ]]; then
        print_info "[DRY RUN] Would create directory: $DEST_PARENT"
    else
        print_info "Creating parent directory: $DEST_PARENT"
        mkdir -p "$DEST_PARENT"
    fi
fi

# Perform sync
echo ""
if [[ "$DRY_RUN" == true ]]; then
    print_info "Dry run - showing what would be synced:"
    echo ""
    rsync -avhn --delete \
        --exclude '__pycache__' \
        --exclude '*.pyc' \
        --exclude '*.pyo' \
        --exclude '.pytest_cache' \
        --exclude 'venv' \
        --exclude 'logs/*.log' \
        --exclude 'models/*.bin' \
        --exclude 'models/*.onnx' \
        --exclude 'data/*.db' \
        "$SOURCE_PATH/" "$DEST_PATH/"
else
    print_info "Syncing files..."
    rsync -avh --delete \
        --exclude '__pycache__' \
        --exclude '*.pyc' \
        --exclude '*.pyo' \
        --exclude '.pytest_cache' \
        --exclude 'venv' \
        --exclude 'logs/*.log' \
        --exclude 'models/*.bin' \
        --exclude 'models/*.onnx' \
        --exclude 'data/*.db' \
        "$SOURCE_PATH/" "$DEST_PATH/"
fi

# Summary
echo ""
if [[ "$DRY_RUN" == true ]]; then
    print_info "Dry run complete - no files were copied"
else
    print_success "Sync complete!"
    echo ""
    print_info "Files synced to: $DEST_PATH"
    echo ""

    # Convert WSL path to Windows path for display
    WINDOWS_PATH=$(echo "$DEST_PATH" | sed 's|/mnt/\([a-z]\)|\U\1:|' | sed 's|/|\\|g')

    echo -e "${YELLOW}Next steps on Windows:${NC}"
    echo ""
    echo "  1. Open PowerShell as Administrator"
    echo ""
    echo "  2. Navigate to the installation directory:"
    echo -e "     ${CYAN}cd $WINDOWS_PATH${NC}"
    echo ""
    echo "  3. Run the installation script:"
    echo -e "     ${CYAN}.\\scripts\\install.ps1${NC}"
    echo ""
    echo "  4. Verify the service is running:"
    echo -e "     ${CYAN}.\\scripts\\check-health.ps1${NC}"
    echo ""
    echo "  Or test ONNX Runtime OpenVINO EP availability:"
    echo -e "     ${CYAN}python -c \"import onnxruntime as ort; print(ort.get_available_providers())\"${NC}"
    echo ""
    echo "  Check for Intel NPU device:"
    echo -e "     ${CYAN}python -c \"from openvino import Core; print(Core().available_devices)\"${NC}"
    echo ""
fi

# Display Windows connectivity info
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Network Configuration${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
print_info "Windows NPU Worker will listen on:"
echo "  - Port: 8082"
echo "  - Bind: 0.0.0.0 (all interfaces)"
echo ""
print_info "From WSL2, connect to Windows host at:"
HOST_IP=$(ip route show | grep -i default | head -1 | awk '{print $3}')
echo "  - http://${HOST_IP}:8082/health"
echo ""
print_info "Backend configuration update required:"
echo "  - Update NPU_WORKER_URL in config to: http://${HOST_IP}:8082"
echo ""
