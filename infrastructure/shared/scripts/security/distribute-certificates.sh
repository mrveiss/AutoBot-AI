#!/bin/bash
################################################################################
# AutoBot TLS Certificate Distribution Script
#
# Purpose: Distribute TLS certificates to all AutoBot VMs
# Usage: ./scripts/security/distribute-certificates.sh [--dry-run] [--vm <name>]
#
# Distributes:
# - CA certificate to all VMs
# - Service-specific certificates to each VM
# - Sets proper permissions on remote hosts
################################################################################

set -euo pipefail

# Configuration
CERT_DIR="/home/kali/Desktop/AutoBot/certs"
CA_DIR="${CERT_DIR}/ca"
SSH_KEY="$HOME/.ssh/autobot_key"
REMOTE_USER="autobot"
REMOTE_CERT_DIR="/etc/autobot/certs"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Flags
DRY_RUN=false
SPECIFIC_VM=""

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --vm)
            SPECIFIC_VM="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--dry-run] [--vm <name>]"
            echo ""
            echo "Options:"
            echo "  --dry-run    Show what would be done without making changes"
            echo "  --vm <name>  Distribute to specific VM only (frontend, npu-worker, redis, ai-stack, browser)"
            echo "  -h, --help   Show this help message"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# VM Configuration: service_name:ip_address:remote_service_name
declare -a VMS=(
    "frontend:172.16.168.21:nginx"
    "npu-worker:172.16.168.22:npu-worker"
    "redis:172.16.168.23:redis-stack-server"
    "ai-stack:172.16.168.24:backend"
    "browser:172.16.168.25:playwright"
)

# Verify prerequisites
log_info "Verifying prerequisites"

if [ ! -f "${SSH_KEY}" ]; then
    log_error "SSH key not found: ${SSH_KEY}"
    log_error "Please ensure SSH key is configured"
    exit 1
fi

if [ ! -f "${CA_DIR}/ca-cert.pem" ]; then
    log_error "CA certificate not found: ${CA_DIR}/ca-cert.pem"
    log_error "Please run generate-tls-certificates.sh first"
    exit 1
fi

if [ "$DRY_RUN" = true ]; then
    log_warn "DRY RUN MODE - No changes will be made"
fi

################################################################################
# Function: Distribute certificates to a VM
################################################################################

distribute_to_vm() {
    local service_name="$1"
    local ip_address="$2"
    local remote_service="$3"

    log_info "Processing: ${service_name} (${ip_address})"

    local SERVICE_DIR="${CERT_DIR}/${service_name}"

    # Verify local certificates exist
    if [ ! -f "${SERVICE_DIR}/server-cert.pem" ] || [ ! -f "${SERVICE_DIR}/server-key.pem" ]; then
        log_error "Certificates not found for ${service_name}"
        log_error "Expected: ${SERVICE_DIR}/server-cert.pem and server-key.pem"
        return 1
    fi

    # Test SSH connectivity
    if ! ssh -i "${SSH_KEY}" -o ConnectTimeout=5 \
         "${REMOTE_USER}@${ip_address}" "echo 'SSH connection test'" > /dev/null 2>&1; then
        log_error "Cannot connect to ${ip_address} via SSH"
        log_error "Please ensure VM is running and SSH key is authorized"
        return 1
    fi

    if [ "$DRY_RUN" = true ]; then
        log_debug "Would create directory: ${REMOTE_CERT_DIR} on ${ip_address}"
        log_debug "Would copy CA cert: ${CA_DIR}/ca-cert.pem → ${ip_address}:${REMOTE_CERT_DIR}/"
        log_debug "Would copy service cert: ${SERVICE_DIR}/server-cert.pem → ${ip_address}:${REMOTE_CERT_DIR}/"
        log_debug "Would copy service key: ${SERVICE_DIR}/server-key.pem → ${ip_address}:${REMOTE_CERT_DIR}/"
        log_debug "Would set permissions on ${ip_address}"
        return 0
    fi

    # Create remote certificate directory
    log_info "  Creating certificate directory on ${service_name}"
    ssh -i "${SSH_KEY}" "${REMOTE_USER}@${ip_address}" \
        "sudo mkdir -p ${REMOTE_CERT_DIR} && sudo chown ${REMOTE_USER}:${REMOTE_USER} ${REMOTE_CERT_DIR}"

    # Copy CA certificate
    log_info "  Copying CA certificate to ${service_name}"
    scp -i "${SSH_KEY}" "${CA_DIR}/ca-cert.pem" \
        "${REMOTE_USER}@${ip_address}:${REMOTE_CERT_DIR}/ca-cert.pem"

    # Copy service certificate
    log_info "  Copying service certificate to ${service_name}"
    scp -i "${SSH_KEY}" "${SERVICE_DIR}/server-cert.pem" \
        "${REMOTE_USER}@${ip_address}:${REMOTE_CERT_DIR}/server-cert.pem"

    # Copy service private key
    log_info "  Copying service private key to ${service_name}"
    scp -i "${SSH_KEY}" "${SERVICE_DIR}/server-key.pem" \
        "${REMOTE_USER}@${ip_address}:${REMOTE_CERT_DIR}/server-key.pem"

    # Set proper permissions
    log_info "  Setting permissions on ${service_name}"
    ssh -i "${SSH_KEY}" "${REMOTE_USER}@${ip_address}" << 'EOF'
        sudo chmod 644 /etc/autobot/certs/ca-cert.pem
        sudo chmod 644 /etc/autobot/certs/server-cert.pem
        sudo chmod 600 /etc/autobot/certs/server-key.pem
        sudo chown root:root /etc/autobot/certs/*.pem
EOF

    # Verify certificates on remote host
    log_info "  Verifying certificates on ${service_name}"
    if ssh -i "${SSH_KEY}" "${REMOTE_USER}@${ip_address}" \
           "openssl verify -CAfile ${REMOTE_CERT_DIR}/ca-cert.pem ${REMOTE_CERT_DIR}/server-cert.pem" > /dev/null 2>&1; then
        log_info "  ✓ Certificate verification successful on ${service_name}"
    else
        log_error "  ✗ Certificate verification failed on ${service_name}"
        return 1
    fi

    # Display certificate info
    log_info "  Certificate details on ${service_name}:"
    ssh -i "${SSH_KEY}" "${REMOTE_USER}@${ip_address}" \
        "openssl x509 -in ${REMOTE_CERT_DIR}/server-cert.pem -noout -subject -issuer -dates" | sed 's/^/    /'

    log_info "  ✓ Certificate distribution complete for ${service_name}"
    echo ""

    return 0
}

################################################################################
# Main Distribution Logic
################################################################################

log_info "Starting TLS Certificate Distribution"
log_info "Certificate directory: ${CERT_DIR}"
log_info "SSH Key: ${SSH_KEY}"
log_info "Remote directory: ${REMOTE_CERT_DIR}"
echo ""

FAILED_VMS=()

if [ -n "$SPECIFIC_VM" ]; then
    log_info "Distributing to specific VM: ${SPECIFIC_VM}"

    VM_FOUND=false
    for vm in "${VMS[@]}"; do
        IFS=':' read -r service_name ip_address remote_service <<< "$vm"
        if [ "$service_name" = "$SPECIFIC_VM" ]; then
            VM_FOUND=true
            if ! distribute_to_vm "$service_name" "$ip_address" "$remote_service"; then
                FAILED_VMS+=("$service_name")
            fi
            break
        fi
    done

    if [ "$VM_FOUND" = false ]; then
        log_error "VM not found: ${SPECIFIC_VM}"
        log_error "Valid VMs: frontend, npu-worker, redis, ai-stack, browser"
        exit 1
    fi
else
    log_info "Distributing certificates to all VMs"
    echo ""

    for vm in "${VMS[@]}"; do
        IFS=':' read -r service_name ip_address remote_service <<< "$vm"

        if ! distribute_to_vm "$service_name" "$ip_address" "$remote_service"; then
            FAILED_VMS+=("$service_name")
        fi
    done
fi

################################################################################
# Summary
################################################################################

echo ""
log_info "Certificate Distribution Summary"
log_info "=================================="

if [ ${#FAILED_VMS[@]} -eq 0 ]; then
    log_info "✓ All certificates distributed successfully"

    if [ "$DRY_RUN" = false ]; then
        log_info ""
        log_info "Next Steps:"
        log_info "  1. Configure services to use TLS certificates"
        log_info "  2. Update service configurations (nginx, redis, backend, etc.)"
        log_info "  3. Test TLS connections between services"
        log_info "  4. Update firewall rules if necessary"
        log_info ""
        log_info "Certificate Locations on VMs:"
        log_info "  - CA Certificate: ${REMOTE_CERT_DIR}/ca-cert.pem"
        log_info "  - Service Certificate: ${REMOTE_CERT_DIR}/server-cert.pem"
        log_info "  - Service Private Key: ${REMOTE_CERT_DIR}/server-key.pem"
    fi
    exit 0
else
    log_error "✗ Failed to distribute certificates to some VMs:"
    for failed_vm in "${FAILED_VMS[@]}"; do
        log_error "  - ${failed_vm}"
    done

    log_info ""
    log_info "Troubleshooting:"
    log_info "  1. Verify VM is running and accessible"
    log_info "  2. Check SSH connectivity and key authorization"
    log_info "  3. Ensure certificates exist locally"
    log_info "  4. Review error messages above"
    exit 1
fi
