#!/bin/bash
################################################################################
# AutoBot TLS Certificate Renewal Script
#
# Purpose: Renew TLS certificates before expiration
# Usage: ./scripts/security/renew-certificates.sh [--check-only] [--force]
#
# Features:
# - Checks certificate expiration dates
# - Renews certificates within 30 days of expiry
# - Maintains same CA for trust continuity
# - Automatically distributes renewed certificates
################################################################################

set -euo pipefail

# Configuration
CERT_DIR="/home/kali/Desktop/AutoBot/certs"
CA_DIR="${CERT_DIR}/ca"
WARNING_DAYS=30
VALIDITY_DAYS=365
KEY_SIZE=4096

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Flags
CHECK_ONLY=false
FORCE_RENEWAL=false

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
        --check-only)
            CHECK_ONLY=true
            shift
            ;;
        --force)
            FORCE_RENEWAL=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--check-only] [--force]"
            echo ""
            echo "Options:"
            echo "  --check-only  Check expiration status without renewing"
            echo "  --force       Force renewal even if not expired"
            echo "  -h, --help    Show this help message"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# VM Configuration
declare -a VMS=(
    "main-host:172.16.168.20:autobot-backend"
    "frontend:172.16.168.21:autobot-frontend"
    "npu-worker:172.16.168.22:autobot-npu-worker"
    "redis:172.16.168.23:autobot-redis"
    "ai-stack:172.16.168.24:autobot-ai-stack"
    "browser:172.16.168.25:autobot-browser"
)

################################################################################
# Function: Check certificate expiration
################################################################################

check_expiration() {
    local cert_file="$1"
    local cert_name="$2"

    if [ ! -f "$cert_file" ]; then
        log_error "Certificate not found: $cert_file"
        return 2
    fi

    # Get expiration date
    local expiry_date=$(openssl x509 -in "$cert_file" -noout -enddate | cut -d= -f2)
    local expiry_epoch=$(date -d "$expiry_date" +%s)
    local current_epoch=$(date +%s)
    local days_until_expiry=$(( ($expiry_epoch - $current_epoch) / 86400 ))

    if [ $days_until_expiry -lt 0 ]; then
        log_error "${cert_name}: EXPIRED ${days_until_expiry#-} days ago"
        return 1
    elif [ $days_until_expiry -lt $WARNING_DAYS ]; then
        log_warn "${cert_name}: Expires in ${days_until_expiry} days (${expiry_date})"
        return 1
    else
        log_info "${cert_name}: Valid for ${days_until_expiry} days (${expiry_date})"
        return 0
    fi
}

################################################################################
# Function: Renew service certificate
################################################################################

renew_certificate() {
    local service_name="$1"
    local ip_address="$2"
    local common_name="$3"

    log_info "Renewing certificate for: ${service_name}"

    local SERVICE_DIR="${CERT_DIR}/${service_name}"

    # Backup existing certificate
    if [ -f "${SERVICE_DIR}/server-cert.pem" ]; then
        local backup_date=$(date +%Y%m%d_%H%M%S)
        cp "${SERVICE_DIR}/server-cert.pem" "${SERVICE_DIR}/server-cert.pem.backup_${backup_date}"
        log_info "  Backed up existing certificate"
    fi

    # Generate new CSR (reuse existing key)
    log_info "  Generating new CSR"
    openssl req -new \
        -key "${SERVICE_DIR}/server-key.pem" \
        -out "${SERVICE_DIR}/server.csr" \
        -config "${SERVICE_DIR}/server.conf"

    # Sign new certificate with CA
    log_info "  Signing new certificate with CA"
    openssl x509 -req -days ${VALIDITY_DAYS} \
        -in "${SERVICE_DIR}/server.csr" \
        -CA "${CA_DIR}/ca-cert.pem" \
        -CAkey "${CA_DIR}/ca-key.pem" \
        -CAcreateserial \
        -out "${SERVICE_DIR}/server-cert.pem" \
        -extensions v3_req \
        -extfile "${SERVICE_DIR}/server.conf"

    chmod 644 "${SERVICE_DIR}/server-cert.pem"

    # Verify new certificate
    if openssl verify -CAfile "${CA_DIR}/ca-cert.pem" "${SERVICE_DIR}/server-cert.pem" > /dev/null 2>&1; then
        log_info "  ✓ New certificate verified successfully"
    else
        log_error "  ✗ Certificate verification failed"
        return 1
    fi

    # Clean up CSR
    rm -f "${SERVICE_DIR}/server.csr"

    log_info "  ✓ Certificate renewed for ${service_name}"
    return 0
}

################################################################################
# Main Renewal Logic
################################################################################

log_info "Starting TLS Certificate Renewal Check"
log_info "Warning threshold: ${WARNING_DAYS} days"
log_info "Certificate directory: ${CERT_DIR}"
echo ""

# Check CA certificate
log_info "Checking CA certificate"
if ! check_expiration "${CA_DIR}/ca-cert.pem" "CA Certificate"; then
    log_error "CA certificate requires renewal - this requires manual intervention"
    log_error "CA renewal affects all service certificates"
    log_error "Please contact security team for CA renewal procedure"
    exit 1
fi
echo ""

# Check and optionally renew service certificates
CERTS_TO_RENEW=()
RENEWAL_STATUS=()

log_info "Checking service certificates"
echo ""

for vm in "${VMS[@]}"; do
    IFS=':' read -r service_name ip_address common_name <<< "$vm"

    SERVICE_DIR="${CERT_DIR}/${service_name}"
    CERT_FILE="${SERVICE_DIR}/server-cert.pem"

    if ! check_expiration "$CERT_FILE" "${service_name}"; then
        CERTS_TO_RENEW+=("${service_name}:${ip_address}:${common_name}")
    elif [ "$FORCE_RENEWAL" = true ]; then
        log_warn "${service_name}: Forcing renewal (--force flag)"
        CERTS_TO_RENEW+=("${service_name}:${ip_address}:${common_name}")
    fi
done

echo ""

# Perform renewals if not in check-only mode
if [ ${#CERTS_TO_RENEW[@]} -gt 0 ]; then
    if [ "$CHECK_ONLY" = true ]; then
        log_info "Certificates requiring renewal: ${#CERTS_TO_RENEW[@]}"
        for cert_info in "${CERTS_TO_RENEW[@]}"; do
            IFS=':' read -r service_name _ _ <<< "$cert_info"
            log_warn "  - ${service_name}"
        done
        log_info ""
        log_info "Run without --check-only to perform renewal"
        exit 0
    else
        log_info "Renewing ${#CERTS_TO_RENEW[@]} certificate(s)"
        echo ""

        for cert_info in "${CERTS_TO_RENEW[@]}"; do
            IFS=':' read -r service_name ip_address common_name <<< "$cert_info"

            if renew_certificate "$service_name" "$ip_address" "$common_name"; then
                RENEWAL_STATUS+=("${service_name}:SUCCESS")
            else
                RENEWAL_STATUS+=("${service_name}:FAILED")
            fi
            echo ""
        done

        # Distribute renewed certificates
        log_info "Distributing renewed certificates to VMs"
        if [ -f "/home/kali/Desktop/AutoBot/scripts/security/distribute-certificates.sh" ]; then
            /home/kali/Desktop/AutoBot/scripts/security/distribute-certificates.sh
        else
            log_warn "Certificate distribution script not found"
            log_warn "Please distribute certificates manually"
        fi
    fi
else
    log_info "✓ All certificates are valid - no renewal required"
fi

################################################################################
# Summary
################################################################################

echo ""
log_info "Certificate Renewal Summary"
log_info "============================"

if [ ${#RENEWAL_STATUS[@]} -gt 0 ]; then
    for status in "${RENEWAL_STATUS[@]}"; do
        IFS=':' read -r service_name result <<< "$status"
        if [ "$result" = "SUCCESS" ]; then
            log_info "✓ ${service_name}: Renewed successfully"
        else
            log_error "✗ ${service_name}: Renewal failed"
        fi
    done
else
    log_info "No certificates were renewed"
fi

echo ""
log_info "Next certificate check recommended: $(date -d "+7 days" +%Y-%m-%d)"

exit 0
