# TLS Certificate Management - AutoBot Platform

## Overview

This document describes the TLS certificate infrastructure for the AutoBot enterprise AI platform, including generation, distribution, renewal, and troubleshooting procedures.

## Table of Contents

1. [Architecture](#architecture)
2. [Certificate Generation](#certificate-generation)
3. [Certificate Distribution](#certificate-distribution)
4. [Certificate Renewal](#certificate-renewal)
5. [Security Best Practices](#security-best-practices)
6. [Troubleshooting](#troubleshooting)
7. [Emergency Procedures](#emergency-procedures)

---

## Architecture

### Certificate Hierarchy

```
AutoBot Internal CA (Root)
├── ca-cert.pem (CA Certificate)
├── ca-key.pem (CA Private Key - CRITICAL)
└── Service Certificates
    ├── main-host (172.16.168.20) - Backend API
    ├── frontend (172.16.168.21) - Web Interface
    ├── npu-worker (172.16.168.22) - NPU Acceleration
    ├── redis (172.16.168.23) - Data Layer
    ├── ai-stack (172.16.168.24) - AI Processing
    └── browser (172.16.168.25) - Web Automation
```

### Certificate Specifications

- **Key Algorithm**: RSA 4096-bit
- **Signature Algorithm**: SHA-256
- **Validity Period**: 365 days
- **Subject Alternative Names (SAN)**:
  - DNS entries: Common Name, Service Name, localhost
  - IP entries: Service IP, 127.0.0.1
- **Key Usage**: Digital Signature, Key Encipherment
- **Extended Key Usage**: Server Authentication, Client Authentication

### Directory Structure

```
/home/kali/Desktop/AutoBot/certs/
├── ca/
│   ├── ca-key.pem          # CA private key (600 permissions) - BACKUP REQUIRED
│   ├── ca-cert.pem         # CA certificate (644 permissions)
│   ├── ca.conf             # CA configuration
│   └── ca-cert.srl         # Serial number tracker
├── main-host/
│   ├── server-key.pem      # Private key (600 permissions)
│   ├── server-cert.pem     # Certificate (644 permissions)
│   └── server.conf         # Certificate configuration
├── frontend/
│   ├── server-key.pem
│   ├── server-cert.pem
│   └── server.conf
├── [other services...]
└── certificate-summary.txt  # Complete certificate inventory
```

### Remote VM Certificate Locations

All VMs store certificates in: `/etc/autobot/certs/`

```
/etc/autobot/certs/
├── ca-cert.pem         # CA certificate for verification
├── server-cert.pem     # Service-specific certificate
└── server-key.pem      # Service-specific private key
```

---

## Certificate Generation

### Initial Setup

Generate all certificates for the first time:

```bash
cd /home/kali/Desktop/AutoBot
./scripts/security/generate-tls-certificates.sh
```

**What this does:**
1. Creates certificate directory structure
2. Generates internal Certificate Authority (CA)
3. Creates service certificates for all 6 hosts
4. Configures proper Subject Alternative Names (SAN)
5. Sets appropriate file permissions
6. Generates certificate summary report
7. Updates .gitignore to exclude certificate files

### Verification

After generation, verify certificates:

```bash
# View certificate summary
cat /home/kali/Desktop/AutoBot/certs/certificate-summary.txt

# Verify CA certificate
openssl x509 -in certs/ca/ca-cert.pem -noout -text

# Verify service certificate (example: frontend)
openssl x509 -in certs/frontend/server-cert.pem -noout -text

# Verify certificate chain
openssl verify -CAfile certs/ca/ca-cert.pem certs/frontend/server-cert.pem
```

### Manual Certificate Generation

If you need to generate a certificate for a new service:

```bash
# Define service details
SERVICE_NAME="new-service"
IP_ADDRESS="172.16.168.26"
COMMON_NAME="autobot-new-service"

# Create service directory
mkdir -p certs/${SERVICE_NAME}

# Generate private key
openssl genrsa -out certs/${SERVICE_NAME}/server-key.pem 4096
chmod 600 certs/${SERVICE_NAME}/server-key.pem

# Create certificate configuration
cat > certs/${SERVICE_NAME}/server.conf <<EOF
[req]
default_bits = 4096
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = v3_req

[dn]
C=US
ST=California
L=San Francisco
O=AutoBot
OU=${SERVICE_NAME}
CN=${COMMON_NAME}

[v3_req]
subjectAltName = @alt_names
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth, clientAuth

[alt_names]
DNS.1 = ${COMMON_NAME}
DNS.2 = ${SERVICE_NAME}
DNS.3 = localhost
IP.1 = ${IP_ADDRESS}
IP.2 = 127.0.0.1
EOF

# Generate CSR
openssl req -new \
    -key certs/${SERVICE_NAME}/server-key.pem \
    -out certs/${SERVICE_NAME}/server.csr \
    -config certs/${SERVICE_NAME}/server.conf

# Sign with CA
openssl x509 -req -days 365 \
    -in certs/${SERVICE_NAME}/server.csr \
    -CA certs/ca/ca-cert.pem \
    -CAkey certs/ca/ca-key.pem \
    -CAcreateserial \
    -out certs/${SERVICE_NAME}/server-cert.pem \
    -extensions v3_req \
    -extfile certs/${SERVICE_NAME}/server.conf

chmod 644 certs/${SERVICE_NAME}/server-cert.pem

# Verify
openssl verify -CAfile certs/ca/ca-cert.pem certs/${SERVICE_NAME}/server-cert.pem
```

---

## Certificate Distribution

### Automated Distribution

Distribute certificates to all VMs:

```bash
cd /home/kali/Desktop/AutoBot
./scripts/security/distribute-certificates.sh
```

### Distribute to Specific VM

```bash
# Distribute to frontend only
./scripts/security/distribute-certificates.sh --vm frontend

# Distribute to ai-stack only
./scripts/security/distribute-certificates.sh --vm ai-stack
```

### Dry Run (Preview Changes)

```bash
./scripts/security/distribute-certificates.sh --dry-run
```

### What Distribution Does

1. Verifies SSH connectivity to each VM
2. Creates `/etc/autobot/certs/` directory on remote host
3. Copies CA certificate to VM
4. Copies service-specific certificate to VM
5. Copies service-specific private key to VM
6. Sets proper permissions:
   - `ca-cert.pem`: 644 (readable by all)
   - `server-cert.pem`: 644 (readable by all)
   - `server-key.pem`: 600 (readable by root only)
7. Verifies certificate chain on remote host
8. Displays certificate details

### Manual Distribution

If automated distribution fails, distribute manually:

```bash
SERVICE="frontend"
IP="172.16.168.21"
SSH_KEY="$HOME/.ssh/autobot_key"

# Create directory on remote VM
ssh -i ${SSH_KEY} autobot@${IP} "sudo mkdir -p /etc/autobot/certs"

# Copy certificates
scp -i ${SSH_KEY} certs/ca/ca-cert.pem autobot@${IP}:/tmp/
scp -i ${SSH_KEY} certs/${SERVICE}/server-cert.pem autobot@${IP}:/tmp/
scp -i ${SSH_KEY} certs/${SERVICE}/server-key.pem autobot@${IP}:/tmp/

# Move to proper location with correct permissions
ssh -i ${SSH_KEY} autobot@${IP} << 'EOF'
sudo mv /tmp/ca-cert.pem /etc/autobot/certs/
sudo mv /tmp/server-cert.pem /etc/autobot/certs/
sudo mv /tmp/server-key.pem /etc/autobot/certs/
sudo chmod 644 /etc/autobot/certs/ca-cert.pem
sudo chmod 644 /etc/autobot/certs/server-cert.pem
sudo chmod 600 /etc/autobot/certs/server-key.pem
sudo chown root:root /etc/autobot/certs/*.pem
EOF
```

---

## Certificate Renewal

### Automatic Renewal Check

Check certificate expiration status (no changes):

```bash
./scripts/security/renew-certificates.sh --check-only
```

### Renew Expiring Certificates

Certificates are automatically renewed when within 30 days of expiration:

```bash
./scripts/security/renew-certificates.sh
```

### Force Renewal

Force renewal regardless of expiration date:

```bash
./scripts/security/renew-certificates.sh --force
```

### Renewal Process

1. **Check Expiration**: Verifies current certificate validity
2. **Backup**: Creates backup of existing certificate
3. **Generate CSR**: Creates new certificate signing request (reuses existing key)
4. **Sign Certificate**: CA signs new certificate with same parameters
5. **Verify**: Validates new certificate chain
6. **Distribute**: Automatically distributes renewed certificates to VMs
7. **Service Restart**: Services must be restarted to use new certificates

### Scheduled Renewal

Set up automated renewal check (add to crontab):

```bash
# Check certificates weekly, renew if within 30 days of expiry
0 2 * * 0 /home/kali/Desktop/AutoBot/scripts/security/renew-certificates.sh >> /home/kali/Desktop/AutoBot/logs/certificate-renewal.log 2>&1
```

### Renewal Notifications

Set up expiration warnings (add to crontab):

```bash
# Daily check with email notification
0 8 * * * /home/kali/Desktop/AutoBot/scripts/security/renew-certificates.sh --check-only | mail -s "AutoBot Certificate Status" admin@example.com
```

---

## Security Best Practices

### CA Private Key Protection

**CRITICAL**: The CA private key (`ca-key.pem`) is the most sensitive file in the certificate infrastructure.

**Security Measures:**

1. **File Permissions**: Always 600 (owner read/write only)
   ```bash
   chmod 600 certs/ca/ca-key.pem
   ```

2. **Backup Strategy**:
   ```bash
   # Encrypted backup
   tar czf - certs/ca/ca-key.pem | gpg -e -r admin@example.com > ca-key-backup.tar.gz.gpg

   # Store backup in secure location (offline storage recommended)
   ```

3. **Access Control**:
   - Only authorized administrators should have access
   - Never commit to version control (covered by .gitignore)
   - Never transmit over unencrypted channels

4. **Audit Trail**:
   ```bash
   # Log all access to CA key
   auditctl -w certs/ca/ca-key.pem -p rwxa -k ca_key_access
   ```

### Certificate Validation

Always verify certificates after generation or renewal:

```bash
# Verify certificate chain
openssl verify -CAfile certs/ca/ca-cert.pem certs/frontend/server-cert.pem

# Check certificate details
openssl x509 -in certs/frontend/server-cert.pem -noout -text

# Verify SAN entries
openssl x509 -in certs/frontend/server-cert.pem -noout -ext subjectAltName

# Check expiration
openssl x509 -in certs/frontend/server-cert.pem -noout -dates
```

### Private Key Security

**Service Private Keys** (`server-key.pem`):

1. **Never expose private keys**:
   - Not in logs
   - Not in error messages
   - Not in backups (unless encrypted)

2. **Proper permissions on all hosts**:
   ```bash
   # Local
   chmod 600 certs/*/server-key.pem

   # Remote VMs
   ssh -i ~/.ssh/autobot_key autobot@<IP> "sudo chmod 600 /etc/autobot/certs/server-key.pem"
   ```

3. **Key rotation**: Generate new keys if compromise suspected

### TLS Configuration Best Practices

When configuring services to use certificates:

1. **Use strong TLS protocols**: TLSv1.2 and TLSv1.3 only
2. **Strong cipher suites**: ECDHE-based ciphers with AES-GCM
3. **Disable weak protocols**: SSLv3, TLSv1.0, TLSv1.1
4. **Enable HSTS**: Force HTTPS connections
5. **Certificate validation**: Always verify certificate chains

Example nginx configuration:

```nginx
ssl_certificate /etc/autobot/certs/server-cert.pem;
ssl_certificate_key /etc/autobot/certs/server-key.pem;
ssl_trusted_certificate /etc/autobot/certs/ca-cert.pem;

ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
ssl_prefer_server_ciphers on;
ssl_session_cache shared:SSL:10m;
ssl_session_timeout 10m;

add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

---

## Troubleshooting

### Certificate Verification Failures

**Problem**: Certificate verification fails

```bash
# Error: unable to get local issuer certificate
openssl verify -CAfile certs/ca/ca-cert.pem certs/frontend/server-cert.pem
```

**Solutions**:

1. **Verify CA certificate is correct**:
   ```bash
   openssl x509 -in certs/ca/ca-cert.pem -noout -subject -issuer
   ```

2. **Check certificate chain**:
   ```bash
   openssl x509 -in certs/frontend/server-cert.pem -noout -issuer
   ```

3. **Regenerate certificate** if signed with wrong CA:
   ```bash
   ./scripts/security/renew-certificates.sh --force
   ```

### SSH Connection Failures

**Problem**: Cannot distribute certificates to VM

```bash
# Error: Connection refused or timeout
./scripts/security/distribute-certificates.sh --vm frontend
```

**Solutions**:

1. **Verify VM is running**:
   ```bash
   ping -c 3 172.16.168.21
   ```

2. **Check SSH connectivity**:
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.21 "echo 'Connection OK'"
   ```

3. **Verify SSH key permissions**:
   ```bash
   chmod 600 ~/.ssh/autobot_key
   ```

4. **Check SSH authorized_keys on VM**:
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.21 "cat ~/.ssh/authorized_keys"
   ```

### Certificate Expiration

**Problem**: Certificate expired

```bash
# Error: certificate has expired
openssl verify -CAfile certs/ca/ca-cert.pem certs/frontend/server-cert.pem
```

**Solutions**:

1. **Renew immediately**:
   ```bash
   ./scripts/security/renew-certificates.sh --force
   ```

2. **Distribute renewed certificate**:
   ```bash
   ./scripts/security/distribute-certificates.sh
   ```

3. **Restart affected services**:
   ```bash
   # Example for frontend
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.21 "sudo systemctl restart nginx"
   ```

### Wrong SAN Entries

**Problem**: Certificate SAN doesn't match service IP/hostname

```bash
# Check SAN entries
openssl x509 -in certs/frontend/server-cert.pem -noout -ext subjectAltName
```

**Solutions**:

1. **Update service configuration**:
   ```bash
   # Edit certs/frontend/server.conf
   # Update IP addresses and DNS names in [alt_names] section
   ```

2. **Regenerate certificate**:
   ```bash
   ./scripts/security/renew-certificates.sh --force
   ```

### Permission Errors

**Problem**: Cannot read certificate or key files

**Solutions**:

1. **Fix local permissions**:
   ```bash
   chmod 644 certs/*/server-cert.pem
   chmod 644 certs/ca/ca-cert.pem
   chmod 600 certs/*/server-key.pem
   chmod 600 certs/ca/ca-key.pem
   ```

2. **Fix remote permissions**:
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@<IP> << 'EOF'
   sudo chmod 644 /etc/autobot/certs/ca-cert.pem
   sudo chmod 644 /etc/autobot/certs/server-cert.pem
   sudo chmod 600 /etc/autobot/certs/server-key.pem
   sudo chown root:root /etc/autobot/certs/*.pem
   EOF
   ```

---

## Emergency Procedures

### CA Certificate Compromise

If the CA private key is compromised:

1. **Immediate Actions**:
   ```bash
   # Revoke all certificates immediately
   # Generate new CA
   # Regenerate all service certificates
   # Distribute new certificates to all VMs
   ```

2. **Full CA Rotation**:
   ```bash
   # Backup current CA (for forensics)
   cp -r certs/ca certs/ca.compromised.$(date +%Y%m%d)

   # Remove compromised CA
   rm certs/ca/ca-key.pem certs/ca/ca-cert.pem

   # Generate new CA and certificates
   ./scripts/security/generate-tls-certificates.sh

   # Distribute new certificates
   ./scripts/security/distribute-certificates.sh

   # Restart all services
   ansible all -i ansible/inventory/production.yml -m systemd -a "name=autobot-* state=restarted" -b
   ```

3. **Post-Incident**:
   - Investigate how compromise occurred
   - Update security procedures
   - Document incident
   - Notify stakeholders

### Service Certificate Compromise

If a single service certificate is compromised:

1. **Revoke and Replace**:
   ```bash
   SERVICE="frontend"

   # Backup compromised certificate
   cp certs/${SERVICE}/server-cert.pem certs/${SERVICE}/server-cert.pem.compromised.$(date +%Y%m%d)

   # Generate new key and certificate
   openssl genrsa -out certs/${SERVICE}/server-key.pem 4096
   chmod 600 certs/${SERVICE}/server-key.pem

   # Renew certificate with new key
   ./scripts/security/renew-certificates.sh --force

   # Distribute
   ./scripts/security/distribute-certificates.sh --vm ${SERVICE}
   ```

2. **Service Restart**:
   ```bash
   # Restart affected service
   ssh -i ~/.ssh/autobot_key autobot@<IP> "sudo systemctl restart <service>"
   ```

### Lost CA Private Key

If CA private key is lost (but not compromised):

**Recovery Options**:

1. **If backup exists**:
   ```bash
   # Restore from encrypted backup
   gpg -d ca-key-backup.tar.gz.gpg | tar xzf - -C certs/ca/
   chmod 600 certs/ca/ca-key.pem
   ```

2. **If no backup**:
   ```bash
   # Must generate new CA and all certificates
   # This will require updating all services
   ./scripts/security/generate-tls-certificates.sh
   ./scripts/security/distribute-certificates.sh
   ```

### Mass Certificate Expiration

If multiple certificates expire simultaneously:

```bash
# Force renewal of all certificates
./scripts/security/renew-certificates.sh --force

# Verify all certificates renewed
for cert in certs/*/server-cert.pem; do
    echo "Checking: $cert"
    openssl x509 -in "$cert" -noout -dates
done

# Distribute all renewed certificates
./scripts/security/distribute-certificates.sh

# Restart all services
ansible all -i ansible/inventory/production.yml -m systemd -a "name=autobot-* state=restarted" -b
```

---

## Appendix

### Certificate File Reference

| File | Location | Purpose | Permissions | Backup Required |
|------|----------|---------|-------------|-----------------|
| `ca-key.pem` | `certs/ca/` | CA private key | 600 | **YES - CRITICAL** |
| `ca-cert.pem` | `certs/ca/` | CA certificate | 644 | Yes |
| `ca.conf` | `certs/ca/` | CA configuration | 644 | Yes |
| `server-key.pem` | `certs/<service>/` | Service private key | 600 | Yes |
| `server-cert.pem` | `certs/<service>/` | Service certificate | 644 | Yes |
| `server.conf` | `certs/<service>/` | Service config | 644 | Yes |

### Command Reference

```bash
# Generate all certificates
./scripts/security/generate-tls-certificates.sh

# Distribute to all VMs
./scripts/security/distribute-certificates.sh

# Distribute to specific VM
./scripts/security/distribute-certificates.sh --vm <service-name>

# Check certificate expiration
./scripts/security/renew-certificates.sh --check-only

# Renew expiring certificates
./scripts/security/renew-certificates.sh

# Force certificate renewal
./scripts/security/renew-certificates.sh --force

# Verify certificate
openssl verify -CAfile certs/ca/ca-cert.pem certs/<service>/server-cert.pem

# View certificate details
openssl x509 -in certs/<service>/server-cert.pem -noout -text

# Check certificate expiration
openssl x509 -in certs/<service>/server-cert.pem -noout -dates

# Test TLS connection
openssl s_client -connect <IP>:443 -CAfile certs/ca/ca-cert.pem
```

### VM Service Mapping

| VM Name | IP Address | Service Name | Certificate Location |
|---------|------------|--------------|---------------------|
| main-host | 172.16.168.20 | autobot-backend | `/etc/autobot/certs/` |
| frontend | 172.16.168.21 | nginx | `/etc/autobot/certs/` |
| npu-worker | 172.16.168.22 | npu-worker | `/etc/autobot/certs/` |
| redis | 172.16.168.23 | redis-stack-server | `/etc/autobot/certs/` |
| ai-stack | 172.16.168.24 | backend | `/etc/autobot/certs/` |
| browser | 172.16.168.25 | playwright | `/etc/autobot/certs/` |

### Support Contacts

- **Security Team**: security@autobot.local
- **DevOps Team**: devops@autobot.local
- **Emergency Hotline**: [To be configured]

---

**Document Version**: 1.0
**Last Updated**: 2025-10-03
**Maintained By**: AutoBot Security Team
