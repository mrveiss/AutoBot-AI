#!/bin/bash
# AutoBot Script Remediation Tool
# Automatically fixes SSH vulnerabilities in all AutoBot scripts
# Part of CVE-AUTOBOT-2025-001 remediation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}🔐 AutoBot Script Remediation Tool${NC}"
echo -e "${BLUE}CVE-AUTOBOT-2025-001 Remediation - Automated Script Fixing${NC}"
echo ""

AUTOBOT_ROOT="/home/kali/Desktop/AutoBot"
BACKUP_DIR="$AUTOBOT_ROOT/backups/ssh-remediation-$(date +%Y%m%d-%H%M%S)"
DRY_RUN=false
FIXED_COUNT=0
SKIPPED_COUNT=0

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run)
                DRY_RUN=true
                log_warn "DRY RUN MODE: No files will be modified"
                shift
                ;;
            --help|-h)
                show_usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
}

show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Automatically fixes SSH vulnerabilities in AutoBot scripts by removing
StrictHostKeyChecking=no and UserKnownHostsFile=/dev/null options.

OPTIONS:
    --dry-run    Show what would be changed without modifying files
    --help, -h   Show this help message

DESCRIPTION:
    This script will:
    1. Backup all files before modification
    2. Remove '-o StrictHostKeyChecking=no' from SSH/SCP commands
    3. Remove '-o UserKnownHostsFile=/dev/null' options
    4. Preserve all other SSH options and functionality
    5. Report all changes made

SAFETY:
    - All original files are backed up to $BACKUP_DIR
    - Use --dry-run to preview changes before applying
    - Only modifies shell scripts and Python files
EOF
}

# Create backup directory
create_backup_dir() {
    if [ "$DRY_RUN" = false ]; then
        mkdir -p "$BACKUP_DIR"
        log_info "Backup directory: $BACKUP_DIR"
    fi
}

# Backup file before modification
backup_file() {
    local file=$1
    
    if [ "$DRY_RUN" = false ]; then
        local relative_path="${file#$AUTOBOT_ROOT/}"
        local backup_path="$BACKUP_DIR/$relative_path"
        mkdir -p "$(dirname "$backup_path")"
        cp "$file" "$backup_path"
    fi
}

# Fix SSH options in a file
fix_ssh_options() {
    local file=$1
    
    # Check if file contains vulnerable patterns
    if ! grep -q "StrictHostKeyChecking=no\|UserKnownHostsFile=/dev/null" "$file" 2>/dev/null; then
        return 1  # No vulnerabilities found
    fi
    
    log_info "Processing: $file"
    
    if [ "$DRY_RUN" = true ]; then
        log_info "  Would remove StrictHostKeyChecking=no"
        log_info "  Would remove UserKnownHostsFile=/dev/null"
        ((FIXED_COUNT++))
        return 0
    fi
    
    # Backup original file
    backup_file "$file"
    
    # Create temporary file for modifications
    local temp_file="${file}.tmp"
    
    # Remove vulnerable SSH options using sed
    sed -e 's/-o StrictHostKeyChecking=no //g' \
        -e 's/-o StrictHostKeyChecking=no$//g' \
        -e "s/-o StrictHostKeyChecking=no'//g" \
        -e 's/-o UserKnownHostsFile=\/dev\/null //g' \
        -e 's/-o UserKnownHostsFile=\/dev\/null$//g' \
        -e "s/-o UserKnownHostsFile=\/dev\/null'//g" \
        -e 's/"StrictHostKeyChecking=no",//g' \
        -e "s/'StrictHostKeyChecking=no',//g" \
        -e 's/StrictHostKeyChecking=no //g' \
        -e 's/StrictHostKeyChecking no/StrictHostKeyChecking accept-new/g' \
        "$file" > "$temp_file"
    
    # Replace original file with modified version
    mv "$temp_file" "$file"
    
    log_success "  Fixed: $file"
    ((FIXED_COUNT++))
    return 0
}

# Find and fix all vulnerable scripts
fix_all_scripts() {
    log_info "Scanning for vulnerable scripts..."
    echo ""
    
    # Find all shell scripts with vulnerable patterns
    local vulnerable_scripts
    vulnerable_scripts=$(grep -rl "StrictHostKeyChecking=no\|UserKnownHostsFile=/dev/null" \
        "$AUTOBOT_ROOT/scripts/" \
        "$AUTOBOT_ROOT/ansible/" \
        "$AUTOBOT_ROOT/backend/" \
        "$AUTOBOT_ROOT"/*.sh 2>/dev/null || true)
    
    if [ -z "$vulnerable_scripts" ]; then
        log_success "No vulnerable scripts found!"
        return 0
    fi
    
    # Process each vulnerable file
    while IFS= read -r file; do
        # Skip backup directories
        if [[ "$file" == *"/backups/"* ]]; then
            ((SKIPPED_COUNT++))
            continue
        fi
        
        # Skip this script itself
        if [[ "$file" == *"fix-all-scripts.sh"* ]]; then
            ((SKIPPED_COUNT++))
            continue
        fi
        
        # Fix the file
        if fix_ssh_options "$file"; then
            :  # Successfully fixed
        else
            ((SKIPPED_COUNT++))
        fi
    done <<< "$vulnerable_scripts"
}

# Fix Ansible configurations
fix_ansible_configs() {
    log_info "Fixing Ansible configurations..."
    echo ""
    
    local ansible_cfg="$AUTOBOT_ROOT/ansible/ansible.cfg"
    local ansible_inventory="$AUTOBOT_ROOT/ansible/inventory/production.yml"
    
    # Fix ansible.cfg
    if [ -f "$ansible_cfg" ]; then
        if grep -q "UserKnownHostsFile=/dev/null" "$ansible_cfg"; then
            log_info "Fixing: $ansible_cfg"
            
            if [ "$DRY_RUN" = false ]; then
                backup_file "$ansible_cfg"
                sed -i 's/-o UserKnownHostsFile=\/dev\/null //g' "$ansible_cfg"
                sed -i 's/-o UserKnownHostsFile=\/dev\/null$//g' "$ansible_cfg"
                log_success "  Fixed: $ansible_cfg"
                ((FIXED_COUNT++))
            else
                log_info "  Would fix: $ansible_cfg"
                ((FIXED_COUNT++))
            fi
        fi
    fi
    
    # Fix production inventory
    if [ -f "$ansible_inventory" ]; then
        if grep -q "StrictHostKeyChecking=no\|UserKnownHostsFile=/dev/null" "$ansible_inventory"; then
            log_info "Fixing: $ansible_inventory"
            
            if [ "$DRY_RUN" = false ]; then
                backup_file "$ansible_inventory"
                sed -i "s/ansible_ssh_common_args: '-o StrictHostKeyChecking=no -o UserKnownHostsFile=\/dev\/null'/ansible_ssh_common_args: '-o ControlMaster=auto -o ControlPersist=60s'/g" "$ansible_inventory"
                log_success "  Fixed: $ansible_inventory"
                ((FIXED_COUNT++))
            else
                log_info "  Would fix: $ansible_inventory"
                ((FIXED_COUNT++))
            fi
        fi
    fi
}

# Generate remediation report
generate_report() {
    local report_file="$AUTOBOT_ROOT/reports/security/ssh-remediation-report-$(date +%Y%m%d-%H%M%S).md"
    
    if [ "$DRY_RUN" = false ]; then
        mkdir -p "$(dirname "$report_file")"
        
        cat > "$report_file" << EOF
# SSH Remediation Report
**Generated**: $(date)

## Summary
- Files Fixed: $FIXED_COUNT
- Files Skipped: $SKIPPED_COUNT
- Backup Location: $BACKUP_DIR

## Changes Made
All instances of the following vulnerable SSH options were removed:
- \`-o StrictHostKeyChecking=no\`
- \`-o UserKnownHostsFile=/dev/null\`

## Ansible Configuration Updates
- \`ansible.cfg\`: Removed UserKnownHostsFile=/dev/null
- \`production.yml\`: Updated ansible_ssh_common_args to remove vulnerable options

## Next Steps
1. Test SSH connections: \`ssh autobot@172.16.168.21 'echo OK'\`
2. Verify security: \`./scripts/security/ssh-hardening/verify-ssh-security.sh\`
3. Test all sync scripts: \`./scripts/utilities/sync-to-vm.sh --test-connection frontend\`
4. Run full AutoBot startup: \`bash run_autobot.sh --dev\`

## Rollback
If issues occur, restore from backup:
\`\`\`bash
cp -r $BACKUP_DIR/* $AUTOBOT_ROOT/
\`\`\`
EOF
        
        log_success "Remediation report: $report_file"
    fi
}

# Main execution
main() {
    parse_args "$@"
    
    echo -e "${CYAN}Starting script remediation...${NC}"
    echo ""
    
    create_backup_dir
    
    fix_all_scripts
    echo ""
    
    fix_ansible_configs
    echo ""
    
    # Summary
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}Remediation Summary${NC}"
    echo -e "${CYAN}========================================${NC}"
    echo ""
    log_info "Files Fixed: $FIXED_COUNT"
    log_info "Files Skipped: $SKIPPED_COUNT"
    
    if [ "$DRY_RUN" = false ]; then
        log_info "Backup Location: $BACKUP_DIR"
        echo ""
        generate_report
        echo ""
        log_success "✅ Script remediation complete!"
        echo ""
        log_info "Next steps:"
        echo "  1. Verify security: ./scripts/security/ssh-hardening/verify-ssh-security.sh"
        echo "  2. Test connections: ssh autobot@172.16.168.21 'echo OK'"
        echo "  3. Test sync: ./scripts/utilities/sync-to-vm.sh --test-connection all"
        echo ""
    else
        echo ""
        log_warn "DRY RUN completed - no files were modified"
        log_info "Run without --dry-run to apply changes"
        echo ""
    fi
}

main "$@"
