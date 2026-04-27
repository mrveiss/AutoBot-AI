# PKI CA Rotation Runbook

This document describes how to rotate the AutoBot Certificate Authority (CA) key
and re-sign all service certificates. CA rotation is a manual process because it
requires distributing a new trust anchor to every host **before** replacing service
certificates.

---

## When to Rotate the CA

- The CA private key is suspected or confirmed to be compromised.
- The CA certificate will expire within 30 days
  (`python3 -m pki.cli status` shows "RENEWAL NEEDED" for `ca`).
- A security policy requires periodic key rotation.

---

## Pre-Requisites

1. **Back up existing certificates.**
   ```bash
   cp -r certs/ certs.bak-$(date +%Y%m%d)/
   ```
2. **Notify the team** — all services will restart after the new CA is distributed.
3. Confirm `openssl` is available: `openssl version`.
4. Confirm SSH access to all VMs:
   ```bash
   python3 -m pki.cli verify-connectivity
   ```

---

## Rotation Steps

### 1. Generate a New CA Key and Certificate

```bash
# Generate new 4096-bit CA key
openssl genrsa -out certs/ca.key 4096

# Self-sign a new CA certificate (valid 3650 days = ~10 years)
openssl req -x509 -new -nodes \
    -key certs/ca.key \
    -sha256 -days 3650 \
    -out certs/ca.crt \
    -subj "/CN=AutoBot-CA/O=AutoBot/C=LV"
```

### 2. Re-Sign All Service Certificates Against the New CA

```bash
# Regenerate all service certificates (new keys + new certs signed by new CA)
python3 -m pki.cli renew --all --no-preserve-keys
```

This regenerates both the private key and the certificate for every service entry
in `VM_DEFINITIONS`. Omit `--no-preserve-keys` only if you want to keep existing
service private keys and re-sign the CSR — not recommended for a full CA rotation.

### 3. Distribute New CA Trust Bundle and Service Certificates to All VMs

```bash
python3 -m pki.cli distribute
```

This copies `certs/ca.crt` and each service's certificate/key to the target VMs
via SCP and updates the system trust store (`update-ca-certificates`).

### 4. Restart Affected Services

On each VM, restart services that hold open TLS connections:

```bash
# Example — adjust to actual service names
for vm in autobot-backend autobot-frontend nginx; do
    ssh "$vm" "sudo systemctl restart $vm"
done
```

Or trigger a full Ansible deploy which will restart services automatically:

```bash
ansible-playbook playbooks/deploy.yml
```

### 5. Verify

```bash
python3 -m pki.cli verify-distribution
python3 -m pki.cli status
```

All certificates should show as valid and no "RENEWAL NEEDED" entries should remain.

---

## Rollback Procedure

If the new CA causes issues, restore the backup:

```bash
# Stop services first to avoid partial-state reads
ansible-playbook playbooks/stop-services.yml

# Restore old certs
rm -rf certs/
cp -r certs.bak-<YYYYMMDD>/ certs/

# Re-distribute old certs
python3 -m pki.cli distribute

# Restart services
ansible-playbook playbooks/deploy.yml
```

---

## See Also

- `autobot-backend/pki/manager.py` — `PKIManager.renew()` (raises `ValueError` for CA entries)
- `autobot-backend/pki/generator.py` — `CertificateGenerator._renew_service_cert()`
- `docs/developer/INFRASTRUCTURE_DEPLOYMENT.md` — Ansible playbook reference
