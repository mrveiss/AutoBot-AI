#!/bin/bash
################################################################################
# AutoBot TLS Certificate Generation Script
#
# Purpose: Generate internal CA and service certificates for all AutoBot VMs
# Usage: ./scripts/security/generate-tls-certificates.sh
#
# Creates:
# - Internal Certificate Authority (CA)
# - Service certificates for all 6 hosts
# - Proper SAN configuration for IP addresses
################################################################################

set -euo pipefail

# Configuration
CERT_DIR="/home/kali/Desktop/AutoBot/certs"
CA_DIR="${CERT_DIR}/ca"
VALIDITY_DAYS=365
KEY_SIZE=4096

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

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

# Check if OpenSSL is installed
if ! command -v openssl &> /dev/null; then
    log_error "OpenSSL is not installed. Please install it first."
    exit 1
fi

log_info "Starting AutoBot TLS Certificate Generation"
log_info "Certificate directory: ${CERT_DIR}"

# VM Configuration: service_name:ip_address:common_name
declare -a VMS=(
    "main-host:172.16.168.20:autobot-backend"
    "frontend:172.16.168.21:autobot-frontend"
    "npu-worker:172.16.168.22:autobot-npu-worker"
    "redis:172.16.168.23:autobot-redis"
    "ai-stack:172.16.168.24:autobot-ai-stack"
    "browser:172.16.168.25:autobot-browser"
)

################################################################################
# Step 1: Generate Certificate Authority (CA)
################################################################################

log_info "Step 1: Generating Certificate Authority (CA)"

# Create CA configuration file
cat > "${CA_DIR}/ca.conf" <<EOF
[req]
default_bits = ${KEY_SIZE}
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_ca

[dn]
C=US
ST=California
L=San Francisco
O=AutoBot
OU=Security
CN=AutoBot Internal CA

[v3_ca]
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always,issuer
basicConstraints = critical,CA:true
keyUsage = critical, digitalSignature, cRLSign, keyCertSign
EOF

# Generate CA private key
if [ ! -f "${CA_DIR}/ca-key.pem" ]; then
    log_info "Generating CA private key (${KEY_SIZE}-bit RSA)"
    openssl genrsa -out "${CA_DIR}/ca-key.pem" ${KEY_SIZE}
    chmod 600 "${CA_DIR}/ca-key.pem"
    log_info "CA private key generated: ${CA_DIR}/ca-key.pem"
else
    log_warn "CA private key already exists, skipping generation"
fi

# Generate CA certificate
if [ ! -f "${CA_DIR}/ca-cert.pem" ]; then
    log_info "Generating CA certificate (valid for ${VALIDITY_DAYS} days)"
    openssl req -new -x509 -days ${VALIDITY_DAYS} \
        -key "${CA_DIR}/ca-key.pem" \
        -out "${CA_DIR}/ca-cert.pem" \
        -config "${CA_DIR}/ca.conf"
    chmod 644 "${CA_DIR}/ca-cert.pem"
    log_info "CA certificate generated: ${CA_DIR}/ca-cert.pem"
else
    log_warn "CA certificate already exists, skipping generation"
fi

# Display CA certificate information
log_info "CA Certificate Information:"
openssl x509 -in "${CA_DIR}/ca-cert.pem" -noout -subject -issuer -dates

################################################################################
# Step 2: Generate Service Certificates
################################################################################

log_info "Step 2: Generating service certificates for all VMs"

for vm in "${VMS[@]}"; do
    IFS=':' read -r service_name ip_address common_name <<< "$vm"

    log_info "Processing: ${service_name} (${ip_address})"

    SERVICE_DIR="${CERT_DIR}/${service_name}"

    # Create service-specific configuration
    cat > "${SERVICE_DIR}/server.conf" <<EOF
[req]
default_bits = ${KEY_SIZE}
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = v3_req

[dn]
C=US
ST=California
L=San Francisco
O=AutoBot
OU=${service_name}
CN=${common_name}

[v3_req]
subjectAltName = @alt_names
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth, clientAuth

[alt_names]
DNS.1 = ${common_name}
DNS.2 = ${service_name}
DNS.3 = localhost
IP.1 = ${ip_address}
IP.2 = 127.0.0.1
EOF

    # Generate private key
    if [ ! -f "${SERVICE_DIR}/server-key.pem" ]; then
        log_info "  Generating private key for ${service_name}"
        openssl genrsa -out "${SERVICE_DIR}/server-key.pem" ${KEY_SIZE}
        chmod 600 "${SERVICE_DIR}/server-key.pem"
    else
        log_warn "  Private key already exists for ${service_name}, skipping"
    fi

    # Generate Certificate Signing Request (CSR)
    if [ ! -f "${SERVICE_DIR}/server.csr" ]; then
        log_info "  Generating CSR for ${service_name}"
        openssl req -new \
            -key "${SERVICE_DIR}/server-key.pem" \
            -out "${SERVICE_DIR}/server.csr" \
            -config "${SERVICE_DIR}/server.conf"
    else
        log_warn "  CSR already exists for ${service_name}, skipping"
    fi

    # Sign certificate with CA
    if [ ! -f "${SERVICE_DIR}/server-cert.pem" ]; then
        log_info "  Signing certificate for ${service_name} with CA"
        openssl x509 -req -days ${VALIDITY_DAYS} \
            -in "${SERVICE_DIR}/server.csr" \
            -CA "${CA_DIR}/ca-cert.pem" \
            -CAkey "${CA_DIR}/ca-key.pem" \
            -CAcreateserial \
            -out "${SERVICE_DIR}/server-cert.pem" \
            -extensions v3_req \
            -extfile "${SERVICE_DIR}/server.conf"
        chmod 644 "${SERVICE_DIR}/server-cert.pem"
        log_info "  Certificate signed: ${SERVICE_DIR}/server-cert.pem"
    else
        log_warn "  Certificate already exists for ${service_name}, skipping"
    fi

    # Verify certificate
    log_info "  Verifying certificate for ${service_name}"
    if openssl verify -CAfile "${CA_DIR}/ca-cert.pem" "${SERVICE_DIR}/server-cert.pem" > /dev/null 2>&1; then
        log_info "  ✓ Certificate verification successful for ${service_name}"
    else
        log_error "  ✗ Certificate verification failed for ${service_name}"
        exit 1
    fi

    # Clean up CSR
    rm -f "${SERVICE_DIR}/server.csr"

    log_info "  Certificate generation complete for ${service_name}"
    echo ""
done

################################################################################
# Step 3: Generate Certificate Summary
################################################################################

log_info "Step 3: Generating certificate summary"

SUMMARY_FILE="${CERT_DIR}/certificate-summary.txt"

cat > "${SUMMARY_FILE}" <<EOF
AutoBot TLS Certificate Summary
Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
================================================================================

Certificate Authority (CA):
- Location: ${CA_DIR}/ca-cert.pem
- Key Location: ${CA_DIR}/ca-key.pem
- Validity: ${VALIDITY_DAYS} days
- Key Size: ${KEY_SIZE} bits

Service Certificates:
EOF

for vm in "${VMS[@]}"; do
    IFS=':' read -r service_name ip_address common_name <<< "$vm"
    SERVICE_DIR="${CERT_DIR}/${service_name}"

    cat >> "${SUMMARY_FILE}" <<EOF

${service_name} (${ip_address}):
- Certificate: ${SERVICE_DIR}/server-cert.pem
- Private Key: ${SERVICE_DIR}/server-key.pem
- Common Name: ${common_name}
- SAN: DNS:${common_name}, DNS:${service_name}, DNS:localhost, IP:${ip_address}, IP:127.0.0.1
- Validity: $(openssl x509 -in "${SERVICE_DIR}/server-cert.pem" -noout -dates | grep notAfter | cut -d= -f2)
EOF
done

cat >> "${SUMMARY_FILE}" <<EOF

================================================================================

Certificate Verification Commands:

# Verify CA certificate
openssl x509 -in ${CA_DIR}/ca-cert.pem -noout -text

# Verify service certificate (example: frontend)
openssl x509 -in ${CERT_DIR}/frontend/server-cert.pem -noout -text

# Verify certificate chain
openssl verify -CAfile ${CA_DIR}/ca-cert.pem ${CERT_DIR}/frontend/server-cert.pem

# Test TLS connection (after deployment)
openssl s_client -connect 172.16.168.21:443 -CAfile ${CA_DIR}/ca-cert.pem

Security Notes:
1. CA private key (ca-key.pem) must be secured - permissions set to 600
2. Service private keys (server-key.pem) must be secured - permissions set to 600
3. Certificates are valid for ${VALIDITY_DAYS} days - plan renewal before expiry
4. All certificates are added to .gitignore to prevent accidental commits
5. Backup CA private key securely - required for certificate renewal

Next Steps:
1. Distribute certificates to VMs using: ./scripts/security/distribute-certificates.sh
2. Configure services to use TLS certificates
3. Test TLS connections between services
4. Set up certificate renewal reminders (30 days before expiry)

================================================================================
EOF

log_info "Certificate summary saved: ${SUMMARY_FILE}"

################################################################################
# Step 4: Update .gitignore
################################################################################

log_info "Step 4: Updating .gitignore to exclude certificates"

GITIGNORE_FILE="/home/kali/Desktop/AutoBot/.gitignore"

if ! grep -q "^certs/" "${GITIGNORE_FILE}" 2>/dev/null; then
    cat >> "${GITIGNORE_FILE}" <<EOF

# TLS Certificates (generated by scripts/security/generate-tls-certificates.sh)
certs/
*.pem
*.csr
*.key
*.crt
EOF
    log_info ".gitignore updated to exclude certificate files"
else
    log_warn "Certificate exclusions already exist in .gitignore"
fi

################################################################################
# Completion
################################################################################

log_info "TLS Certificate Generation Complete!"
log_info ""
log_info "Summary:"
log_info "  - CA Certificate: ${CA_DIR}/ca-cert.pem"
log_info "  - Service Certificates: 6 generated"
log_info "  - Certificate Summary: ${SUMMARY_FILE}"
log_info ""
log_info "Next Steps:"
log_info "  1. Review certificate summary: cat ${SUMMARY_FILE}"
log_info "  2. Distribute to VMs: ./scripts/security/distribute-certificates.sh"
log_info "  3. Configure services for TLS"
log_info ""
log_info "Security Reminders:"
log_info "  - CA private key is critical - backup securely"
log_info "  - Certificates expire in ${VALIDITY_DAYS} days"
log_info "  - Set renewal reminder for $(date -d "+335 days" +%Y-%m-%d)"

exit 0
