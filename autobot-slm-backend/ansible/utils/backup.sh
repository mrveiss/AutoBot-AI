#!/bin/bash
#
# AutoBot Backup Utility
# Comprehensive backup solution for the Hyper-V deployment
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_PROJECT_ROOT="$SCRIPT_DIR"
while [ "$_PROJECT_ROOT" != "/" ] && [ ! -f "$_PROJECT_ROOT/.env" ]; do
    _PROJECT_ROOT="$(dirname "$_PROJECT_ROOT")"
done
source "$_PROJECT_ROOT/infrastructure/shared/scripts/lib/ssot-config.sh" 2>/dev/null || true
ANSIBLE_DIR="$(dirname "$SCRIPT_DIR")"
INVENTORY_FILE="$ANSIBLE_DIR/inventory/production.yml"
BACKUP_BASE_DIR="/opt/autobot/backups"
LOG_DIR="/var/log/autobot/backup"
LOG_FILE="$LOG_DIR/backup-$(date +%Y%m%d-%H%M%S).log"

# VM endpoints (from SSOT config with fallbacks)
DATABASE_HOST="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-172.16.168.20}"
AIML_HOST="${AUTOBOT_AI_STACK_HOST:-172.16.168.24}"
FRONTEND_HOST="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
BROWSER_HOST="${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging function
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    mkdir -p "$LOG_DIR"

    case "$level" in
        "INFO")  echo -e "${GREEN}[INFO]${NC}  $message" | tee -a "$LOG_FILE" ;;
        "WARN")  echo -e "${YELLOW}[WARN]${NC}  $message" | tee -a "$LOG_FILE" ;;
        "ERROR") echo -e "${RED}[ERROR]${NC} $message" | tee -a "$LOG_FILE" ;;
        "DEBUG") echo -e "${BLUE}[DEBUG]${NC} $message" | tee -a "$LOG_FILE" ;;
        *)       echo "[$level] $message" | tee -a "$LOG_FILE" ;;
    esac
}

# Create backup directory with timestamp
create_backup_dir() {
    local backup_type="$1"
    local timestamp=$(date +%Y%m%d-%H%M%S)
    local backup_dir="$BACKUP_BASE_DIR/$backup_type-$timestamp"

    mkdir -p "$backup_dir"
    echo "$backup_dir"
}

# Backup Redis database
backup_redis() {
    local backup_dir="$1"

    log "INFO" "🗄️ Backing up Redis database..."

    # Create Redis backup using BGSAVE
    if ssh "autobot@$DATABASE_HOST" "redis-cli -h localhost -p 6379 BGSAVE"; then
        # Wait for backup to complete
        sleep 10

        # Copy RDB file
        if scp "autobot@$DATABASE_HOST:/var/lib/redis-stack/dump.rdb" "$backup_dir/redis-dump.rdb"; then
            log "INFO" "✅ Redis RDB backup completed"
        else
            log "ERROR" "❌ Failed to copy Redis RDB file"
            return 1
        fi

        # Copy AOF file if it exists
        if scp "autobot@$DATABASE_HOST:/var/lib/redis-stack/appendonly.aof" "$backup_dir/redis-appendonly.aof" 2>/dev/null; then
            log "INFO" "✅ Redis AOF backup completed"
        else
            log "WARN" "⚠️ Redis AOF file not found or not accessible"
        fi

        # Export individual databases
        for db in {0..9} 15; do
            if ssh "autobot@$DATABASE_HOST" "redis-cli -h localhost -p 6379 -n $db --rdb /tmp/redis-db-$db.rdb" >/dev/null 2>&1; then
                scp "autobot@$DATABASE_HOST:/tmp/redis-db-$db.rdb" "$backup_dir/" 2>/dev/null || true
                ssh "autobot@$DATABASE_HOST" "rm -f /tmp/redis-db-$db.rdb" 2>/dev/null || true
            fi
        done

        # Get Redis info
        ssh "autobot@$DATABASE_HOST" "redis-cli -h localhost -p 6379 info" > "$backup_dir/redis-info.txt"

        return 0
    else
        log "ERROR" "❌ Failed to create Redis backup"
        return 1
    fi
}

# Backup model files
backup_models() {
    local backup_dir="$1"

    log "INFO" "🤖 Backing up AI/ML models..."

    local model_backup_dir="$backup_dir/models"
    mkdir -p "$model_backup_dir"

    # Sync model files from AI/ML VM
    if rsync -av --compress "autobot@$AIML_HOST:/var/lib/autobot/models/" "$model_backup_dir/"; then
        log "INFO" "✅ Model files backup completed"

        # Create model inventory
        find "$model_backup_dir" -type f -exec ls -lh {} \; > "$backup_dir/model-inventory.txt"

        return 0
    else
        log "ERROR" "❌ Failed to backup model files"
        return 1
    fi
}

# Backup configuration files
backup_configs() {
    local backup_dir="$1"

    log "INFO" "⚙️ Backing up configuration files..."

    local config_backup_dir="$backup_dir/config"
    mkdir -p "$config_backup_dir"

    # Backup from each VM
    for vm_host in "$FRONTEND_HOST:frontend" "$BACKEND_HOST:backend" "$DATABASE_HOST:database" "$AIML_HOST:aiml" "$BROWSER_HOST:browser"; do
        IFS=':' read -r host vm_name <<< "$vm_host"

        local vm_config_dir="$config_backup_dir/$vm_name"
        mkdir -p "$vm_config_dir"

        # Backup system configuration
        rsync -av --compress "autobot@$host:/etc/autobot/" "$vm_config_dir/etc-autobot/" 2>/dev/null || true

        # Backup service configurations
        case "$vm_name" in
            "frontend")
                rsync -av --compress "autobot@$host:/etc/nginx/sites-available/" "$vm_config_dir/nginx/" 2>/dev/null || true
                ;;
            "backend")
                rsync -av --compress "autobot@$host:/etc/systemd/system/autobot-*" "$vm_config_dir/systemd/" 2>/dev/null || true
                ;;
            "database")
                rsync -av --compress "autobot@$host:/etc/redis-stack/" "$vm_config_dir/redis/" 2>/dev/null || true
                ;;
            "aiml")
                rsync -av --compress "autobot@$host:/opt/intel/openvino/" "$vm_config_dir/openvino/" 2>/dev/null || true
                ;;
            "browser")
                rsync -av --compress "autobot@$host:/home/autobot/.vnc/" "$vm_config_dir/vnc/" 2>/dev/null || true
                ;;
        esac
    done

    log "INFO" "✅ Configuration backup completed"
    return 0
}

# Backup application data
backup_app_data() {
    local backup_dir="$1"

    log "INFO" "📁 Backing up application data..."

    local data_backup_dir="$backup_dir/data"
    mkdir -p "$data_backup_dir"

    # Backup backend data
    if rsync -av --compress "autobot@$BACKEND_HOST:/var/lib/autobot/data/" "$data_backup_dir/backend/"; then
        log "INFO" "✅ Backend data backup completed"
    else
        log "WARN" "⚠️ Backend data backup failed or no data found"
    fi

    # Backup logs from all VMs
    local logs_backup_dir="$data_backup_dir/logs"
    mkdir -p "$logs_backup_dir"

    for vm_host in "$FRONTEND_HOST:frontend" "$BACKEND_HOST:backend" "$DATABASE_HOST:database" "$AIML_HOST:aiml" "$BROWSER_HOST:browser"; do
        IFS=':' read -r host vm_name <<< "$vm_host"

        rsync -av --compress --exclude="*.tmp" "autobot@$host:/var/log/autobot/" "$logs_backup_dir/$vm_name/" 2>/dev/null || true
    done

    log "INFO" "✅ Application data backup completed"
    return 0
}

# Create system inventory
create_inventory() {
    local backup_dir="$1"

    log "INFO" "📋 Creating system inventory..."

    local inventory_file="$backup_dir/system-inventory.txt"

    cat > "$inventory_file" << EOF
AutoBot System Inventory
========================
Backup Date: $(date)
Backup Directory: $backup_dir

VM Configuration:
EOF

    for vm_host in "$FRONTEND_HOST:Frontend" "$BACKEND_HOST:Backend" "$DATABASE_HOST:Database" "$AIML_HOST:AI/ML" "$BROWSER_HOST:Browser"; do
        IFS=':' read -r host vm_name <<< "$vm_host"

        echo "" >> "$inventory_file"
        echo "$vm_name VM ($host):" >> "$inventory_file"
        echo "=========================" >> "$inventory_file"

        # Get system info
        ssh "autobot@$host" "uname -a" >> "$inventory_file" 2>/dev/null || echo "  System info: Not available" >> "$inventory_file"
        ssh "autobot@$host" "df -h" >> "$inventory_file" 2>/dev/null || echo "  Disk info: Not available" >> "$inventory_file"
        ssh "autobot@$host" "free -h" >> "$inventory_file" 2>/dev/null || echo "  Memory info: Not available" >> "$inventory_file"
        ssh "autobot@$host" "systemctl list-units --type=service --state=active | grep autobot" >> "$inventory_file" 2>/dev/null || echo "  AutoBot services: Not available" >> "$inventory_file"
    done

    log "INFO" "✅ System inventory created"
    return 0
}

# Full backup
full_backup() {
    log "INFO" "🚀 Starting full AutoBot backup..."

    local backup_dir
    backup_dir=$(create_backup_dir "full")

    local start_time=$(date +%s)
    local success=0

    # Perform all backup types
    backup_redis "$backup_dir" || ((success++))
    backup_models "$backup_dir" || ((success++))
    backup_configs "$backup_dir" || ((success++))
    backup_app_data "$backup_dir" || ((success++))
    create_inventory "$backup_dir" || ((success++))

    # Create backup manifest
    cat > "$backup_dir/backup-manifest.txt" << EOF
AutoBot Full Backup Manifest
============================
Backup Date: $(date)
Backup Directory: $backup_dir
Backup Duration: $(( $(date +%s) - start_time )) seconds

Components Backed Up:
- Redis Database: $([ -f "$backup_dir/redis-dump.rdb" ] && echo "Yes" || echo "No")
- AI/ML Models: $([ -d "$backup_dir/models" ] && echo "Yes" || echo "No")
- Configuration: $([ -d "$backup_dir/config" ] && echo "Yes" || echo "No")
- Application Data: $([ -d "$backup_dir/data" ] && echo "Yes" || echo "No")
- System Inventory: $([ -f "$backup_dir/system-inventory.txt" ] && echo "Yes" || echo "No")

Backup Size: $(du -sh "$backup_dir" | cut -f1)

Restoration Command:
./restore.sh --from-backup="$backup_dir"
EOF

    # Compress backup if requested
    if [[ "${COMPRESS_BACKUP:-false}" == "true" ]]; then
        log "INFO" "🗜️ Compressing backup..."
        tar -czf "$backup_dir.tar.gz" -C "$(dirname "$backup_dir")" "$(basename "$backup_dir")"
        rm -rf "$backup_dir"
        backup_dir="$backup_dir.tar.gz"
    fi

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    if [[ $success -eq 0 ]]; then
        log "INFO" "🎉 Full backup completed successfully in ${duration} seconds"
        log "INFO" "📁 Backup location: $backup_dir"
    else
        log "WARN" "⚠️ Backup completed with $success warnings/errors in ${duration} seconds"
        log "INFO" "📁 Backup location: $backup_dir"
    fi

    return $success
}

# Quick backup (Redis only)
quick_backup() {
    log "INFO" "⚡ Starting quick backup (Redis only)..."

    local backup_dir
    backup_dir=$(create_backup_dir "quick")

    backup_redis "$backup_dir"

    log "INFO" "✅ Quick backup completed"
    log "INFO" "📁 Backup location: $backup_dir"
}

# Cleanup old backups
cleanup_backups() {
    local retention_days="${1:-30}"

    log "INFO" "🧹 Cleaning up backups older than $retention_days days..."

    find "$BACKUP_BASE_DIR" -name "*-20*" -type d -mtime "+$retention_days" -exec rm -rf {} \; 2>/dev/null || true
    find "$BACKUP_BASE_DIR" -name "*.tar.gz" -mtime "+$retention_days" -exec rm -f {} \; 2>/dev/null || true

    log "INFO" "✅ Backup cleanup completed"
}

# List available backups
list_backups() {
    log "INFO" "📋 Available AutoBot backups:"

    if [[ -d "$BACKUP_BASE_DIR" ]]; then
        find "$BACKUP_BASE_DIR" -maxdepth 1 -name "*-20*" -type d -o -name "*.tar.gz" | sort -r | while read -r backup; do
            local backup_name=$(basename "$backup")
            local backup_size=$(du -sh "$backup" 2>/dev/null | cut -f1 || echo "Unknown")
            local backup_date=$(stat -c %y "$backup" 2>/dev/null | cut -d' ' -f1 || echo "Unknown")

            echo "  📦 $backup_name ($backup_size) - $backup_date"
        done
    else
        log "INFO" "No backups found at $BACKUP_BASE_DIR"
    fi
}

# Usage information
show_usage() {
    cat << EOF
AutoBot Backup Utility

USAGE:
  $0 [OPTIONS]

OPTIONS:
  --full              Complete backup (Redis, models, configs, data)
  --quick             Quick backup (Redis database only)
  --redis             Backup Redis database only
  --models            Backup AI/ML models only
  --configs           Backup configuration files only
  --data              Backup application data only
  --compress          Compress backup (works with --full)
  --cleanup [days]    Clean up backups older than N days (default: 30)
  --list              List available backups
  --help              Show this help

EXAMPLES:
  $0 --full                    # Full backup
  $0 --full --compress         # Full backup with compression
  $0 --quick                   # Quick Redis backup
  $0 --cleanup 7               # Remove backups older than 7 days
  $0 --list                    # List available backups

BACKUP LOCATIONS:
  Base Directory: $BACKUP_BASE_DIR
  Log File: $LOG_FILE

PREREQUISITES:
  - SSH key authentication to all VMs
  - Sufficient disk space for backups
  - Network connectivity to all VMs

EOF
}

# Main execution
main() {
    if [[ $# -eq 0 ]]; then
        show_usage
        exit 1
    fi

    while [[ $# -gt 0 ]]; do
        case $1 in
            --full)
                full_backup
                ;;
            --quick)
                quick_backup
                ;;
            --redis)
                local backup_dir
                backup_dir=$(create_backup_dir "redis")
                backup_redis "$backup_dir"
                ;;
            --models)
                local backup_dir
                backup_dir=$(create_backup_dir "models")
                backup_models "$backup_dir"
                ;;
            --configs)
                local backup_dir
                backup_dir=$(create_backup_dir "configs")
                backup_configs "$backup_dir"
                ;;
            --data)
                local backup_dir
                backup_dir=$(create_backup_dir "data")
                backup_app_data "$backup_dir"
                ;;
            --compress)
                export COMPRESS_BACKUP=true
                ;;
            --cleanup)
                shift
                cleanup_backups "${1:-30}"
                ;;
            --list)
                list_backups
                ;;
            --help)
                show_usage
                exit 0
                ;;
            *)
                log "ERROR" "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
        shift
    done
}

# Execute main function
main "$@"
