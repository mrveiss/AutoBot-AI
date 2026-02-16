# Grafana External Host Setup Guide

**AutoBot SLM Monitoring - External Grafana Configuration**

> **⚠️ IMPORTANT NOTE:**
>
> **Current Production Configuration (Issue #859):**
> - Grafana is deployed on **SLM Server (172.16.168.19)** via Ansible playbooks (`slm_manager` role)
> - Prometheus and AlertManager also run on SLM Server (172.16.168.19)
> - Redis VM (172.16.168.23) runs only Redis Stack
>
> **This document covers OPTIONAL external deployment** for advanced use cases requiring dedicated monitoring infrastructure. For standard deployments, Grafana remains colocated with the SLM backend on 172.16.168.19.

This document describes how to deploy Grafana on a dedicated external host for AutoBot SLM monitoring, instead of running it locally on the SLM server.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [When to Use External Grafana](#when-to-use-external-grafana)
3. [Quick Start Migration](#quick-start-migration)
4. [Manual Setup Guide](#manual-setup-guide)
5. [Configuration Reference](#configuration-reference)
6. [Troubleshooting](#troubleshooting)
7. [Security Considerations](#security-considerations)
8. [Rollback Procedure](#rollback-procedure)

---

## Architecture Overview

### Current Architecture (Local Grafana)

```
SLM Server (172.16.168.19)
├── Grafana :3000 (localhost only)
├── Prometheus :9090 (localhost only)
├── Nginx :443
│   ├── /grafana/ → http://localhost:3000/grafana/
│   └── Frontend served from /
└── AutoBot SLM Backend :8000
```

**Characteristics:**
- ✅ Simple configuration
- ✅ Low latency (localhost communication)
- ✅ No CORS complexity
- ❌ Shares resources with SLM server
- ❌ Single point of failure

### External Architecture (Dedicated Monitoring VM)

```
SLM Server (172.16.168.19)
├── Prometheus :9090 (exposed to monitoring VM)
├── Nginx :443
│   ├── /grafana/ → http://172.16.168.28:3000/grafana/
│   └── Frontend served from /
└── AutoBot SLM Backend :8000

Monitoring VM (172.16.168.28)
└── Grafana :3000
    └── Data Source → http://172.16.168.19:9090 (Prometheus)
```

**Characteristics:**
- ✅ Dedicated resources for Grafana
- ✅ Independent scaling
- ✅ Reduced load on SLM server
- ⚠️ Requires network access between hosts
- ⚠️ CORS configuration needed
- ⚠️ Additional firewall rules

---

## When to Use External Grafana

### ✅ **Use External Grafana When:**

1. **Resource Constraints**
   - SLM server CPU/memory usage is high
   - Grafana queries impact SLM backend performance
   - Need to scale monitoring independently

2. **High Availability Requirements**
   - Want monitoring available even if SLM server is down
   - Need Grafana clustering/HA setup
   - Require separate backup/recovery for monitoring

3. **Multi-Instance Deployment**
   - Managing multiple AutoBot installations
   - Want centralized monitoring across environments
   - Need unified dashboard access

4. **Compliance Requirements**
   - Regulatory requirement for monitoring isolation
   - Need separate audit logs for monitoring access
   - Security policy requires service separation

### ❌ **Keep Local Grafana When:**

1. **Resource Availability**
   - SLM server has sufficient resources
   - Low dashboard query load
   - Small deployment (< 10 nodes)

2. **Simplicity Priority**
   - Minimal infrastructure complexity desired
   - Limited networking between VMs
   - Single-server deployment model

3. **Network Constraints**
   - Unreliable network between hosts
   - High latency between VMs
   - Firewall restrictions

---

## Quick Start Migration

### Prerequisites

1. **Target VM prepared:**
   ```bash
   # Ubuntu 22.04 with SSH access
   ssh autobot@172.16.168.28 "uname -a"
   ```

2. **Ansible inventory configured:**
   ```bash
   cp autobot-slm-backend/ansible/inventory-grafana-migration.ini \
      autobot-slm-backend/ansible/inventory-migration.ini

   # Edit and set monitoring_vm host
   vim autobot-slm-backend/ansible/inventory-migration.ini
   ```

3. **Verify connectivity:**
   ```bash
   ansible -i autobot-slm-backend/ansible/inventory-migration.ini \
     monitoring_vm -m ping
   ```

### Migration Steps

```bash
cd autobot-slm-backend/ansible

# Step 1: Run migration playbook
ansible-playbook migrate-grafana-to-vm.yml \
  -i inventory-migration.ini

# Step 2: Verify migration
curl -k https://172.16.168.19/grafana/api/health

# Step 3: Test dashboard access
curl -k -I https://172.16.168.19/grafana/d/autobot-system?kiosk=tv

# Step 4: (Optional) Remove Grafana from SLM server
ansible-playbook migrate-grafana-to-vm.yml \
  -i inventory-migration.ini \
  --tags cleanup \
  --extra-vars "grafana_cleanup=true"
```

### Verification

1. **Direct Grafana access:**
   ```bash
   curl http://172.16.168.28:3000/grafana/api/health
   # Expected: {"database":"ok","version":"12.3.2"}
   ```

2. **Proxied access via SLM:**
   ```bash
   curl -k https://172.16.168.19/grafana/api/health
   # Expected: {"database":"ok","version":"12.3.2"}
   ```

3. **Dashboard access:**
   - Open browser: https://172.16.168.19/monitoring/system
   - Verify all 6 dashboard types load
   - Check Prometheus data is displayed

---

## Manual Setup Guide

### Phase 1: Install Grafana on External Host

```bash
# On monitoring VM (172.16.168.28)
sudo apt-get update

# Add Grafana APT repository
wget -q -O - https://apt.grafana.com/gpg.key | sudo apt-key add -
echo "deb https://apt.grafana.com stable main" | \
  sudo tee /etc/apt/sources.list.d/grafana.list

# Install Grafana
sudo apt-get update
sudo apt-get install -y grafana

# Verify installation
grafana-server -v
```

### Phase 2: Configure Grafana for External Access

Edit `/etc/grafana/grafana.ini`:

```ini
[server]
# Listen on all interfaces (not just localhost)
http_addr = 0.0.0.0
http_port = 3000

# Domain should be the SLM server (nginx proxy)
domain = 172.16.168.19

# Root URL includes the proxy path
root_url = https://172.16.168.19/grafana/

# Enable subpath serving
serve_from_sub_path = true

[auth.anonymous]
# Allow anonymous access for iframe embedding
enabled = true
org_name = Main Org.
org_role = Viewer

[security]
# Allow iframe embedding from SLM server
allow_embedding = true
cookie_samesite = none
cookie_secure = false  # Nginx handles HTTPS termination
```

### Phase 3: Deploy Dashboards

```bash
# On monitoring VM
sudo mkdir -p /var/lib/grafana/dashboards
sudo chown root:grafana /var/lib/grafana/dashboards
sudo chmod 755 /var/lib/grafana/dashboards

# Copy dashboards from SLM server
scp -r autobot@172.16.168.19:/var/lib/grafana/dashboards/*.json \
  /tmp/

sudo mv /tmp/*.json /var/lib/grafana/dashboards/
sudo chown root:grafana /var/lib/grafana/dashboards/*.json
sudo chmod 640 /var/lib/grafana/dashboards/*.json

# Configure provisioning
sudo tee /etc/grafana/provisioning/dashboards/default.yml > /dev/null << 'EOF'
apiVersion: 1
providers:
  - name: 'AutoBot'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: false
    options:
      path: /var/lib/grafana/dashboards
EOF
```

### Phase 4: Configure Data Sources

```bash
# Create Prometheus datasource
sudo tee /etc/grafana/provisioning/datasources/prometheus.yml > /dev/null << 'EOF'
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://172.16.168.19:9090
    isDefault: true
    editable: false
    jsonData:
      timeInterval: 5s
      queryTimeout: 300s
EOF
```

### Phase 5: Start Grafana

```bash
sudo systemctl enable grafana-server
sudo systemctl start grafana-server
sudo systemctl status grafana-server

# Wait for Grafana to be ready
sleep 5
curl http://localhost:3000/api/health
```

### Phase 6: Configure Firewall

```bash
# On monitoring VM - allow incoming from SLM server
sudo ufw allow from 172.16.168.19 to any port 3000 proto tcp \
  comment "Nginx to Grafana"

# On SLM server - allow incoming from monitoring VM
sudo ufw allow from 172.16.168.28 to any port 9090 proto tcp \
  comment "Grafana to Prometheus"

sudo ufw status numbered
```

### Phase 7: Update SLM Server Nginx

Edit `/etc/nginx/sites-available/autobot-slm`:

```nginx
# Update Grafana proxy location
location /grafana/ {
    # Point to external Grafana host
    proxy_pass http://172.16.168.28:3000/grafana/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Add CORS headers for iframe embedding
    add_header Access-Control-Allow-Origin "https://172.16.168.19" always;
    add_header Access-Control-Allow-Credentials "true" always;
}
```

Reload nginx:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

### Phase 8: Test End-to-End

```bash
# Test all components
curl http://172.16.168.28:3000/grafana/api/health  # Direct Grafana
curl -k https://172.16.168.19/grafana/api/health   # Proxied via nginx
curl -k -I https://172.16.168.19/grafana/d/autobot-system?kiosk=tv  # Dashboard

# Open in browser
xdg-open https://172.16.168.19/monitoring/system
```

---

## Configuration Reference

### Ansible Variable Configuration

To use external Grafana with the `slm_manager` role:

```yaml
# group_vars/slm_server.yml or inventory vars

# Set Grafana mode to external
grafana_mode: external

# Specify external Grafana host
grafana_external_host: 172.16.168.28

# Grafana port (default: 3000)
grafana_port: 3000

# Skip local installation and configuration
grafana_install: false
grafana_configure: false

# Still deploy dashboards if managing from SLM server
grafana_deploy_dashboards: false  # Set to true if deploying from Ansible

# Enable CORS for external access
grafana_enable_cors: true
grafana_cors_origin: "https://172.16.168.19"

# Prometheus must be accessible from external Grafana
prometheus_host: 172.16.168.19  # Expose on all interfaces or specific IP
prometheus_port: 9090
```

### Inventory Example

```ini
[slm_server]
172.16.168.19 ansible_user=autobot

[slm_server:vars]
grafana_mode=external
grafana_external_host=172.16.168.28
grafana_install=false
grafana_configure=false
grafana_enable_cors=true
prometheus_host=172.16.168.19
```

Run deployment:
```bash
ansible-playbook deploy-slm-manager.yml -i inventory.ini
```

---

## Troubleshooting

### Issue: Dashboards Show "No Data"

**Symptoms:**
- Dashboards load but show empty graphs
- "No data" or "N/A" in panels

**Diagnosis:**
```bash
# Check Prometheus accessibility from Grafana VM
ssh autobot@172.16.168.28 "curl -s http://172.16.168.19:9090/api/v1/query?query=up | jq"

# Check Grafana data source configuration
curl -s -u admin:admin http://172.16.168.28:3000/api/datasources | jq
```

**Solution:**
1. Verify firewall allows Grafana → Prometheus:
   ```bash
   sudo ufw status | grep 9090
   ```

2. Check Prometheus is listening on correct interface:
   ```bash
   sudo netstat -tlnp | grep 9090
   ```

3. Update Prometheus to listen on all interfaces if needed:
   ```yaml
   # /etc/prometheus/prometheus.yml
   global:
     external_labels:
       monitor: 'autobot'

   # Run with --web.listen-address=0.0.0.0:9090
   ```

### Issue: CORS Errors in Browser Console

**Symptoms:**
```
Access to XMLHttpRequest at 'https://172.16.168.19/grafana/...' from origin
'https://172.16.168.28:3000' has been blocked by CORS policy
```

**Solution:**
1. Verify nginx CORS headers:
   ```bash
   curl -k -I https://172.16.168.19/grafana/api/health | grep Access-Control
   ```

2. Check Grafana cookie settings:
   ```bash
   grep cookie_ /etc/grafana/grafana.ini | grep -v '^;'
   ```

3. Ensure `cookie_samesite = none` and `allow_embedding = true`

### Issue: 502 Bad Gateway

**Symptoms:**
- Browser shows nginx 502 error
- Nginx logs: "connect() failed (111: Connection refused)"

**Diagnosis:**
```bash
# Check Grafana is running
ssh autobot@172.16.168.28 "systemctl status grafana-server"

# Check Grafana is listening
ssh autobot@172.16.168.28 "netstat -tlnp | grep 3000"

# Test direct access
ssh autobot@172.16.168.28 "curl -I http://localhost:3000/grafana/api/health"
```

**Solution:**
1. Restart Grafana:
   ```bash
   sudo systemctl restart grafana-server
   ```

2. Check Grafana logs:
   ```bash
   sudo journalctl -u grafana-server -n 50 --no-pager
   ```

3. Verify grafana.ini configuration is valid

### Issue: 301 Redirect Loop

**Symptoms:**
- Dashboards redirect infinitely
- Browser shows "Too many redirects"

**Solution:**
1. Verify `serve_from_sub_path = true` in grafana.ini

2. Check `root_url` includes the subpath:
   ```ini
   root_url = https://172.16.168.19/grafana/
   ```

3. Ensure nginx proxy_pass keeps the prefix:
   ```nginx
   proxy_pass http://172.16.168.28:3000/grafana/;  # NOT /
   ```

### Issue: Authentication Required

**Symptoms:**
- Dashboards redirect to login page
- Iframe shows Grafana login form

**Solution:**
1. Enable anonymous authentication:
   ```ini
   [auth.anonymous]
   enabled = true
   org_role = Viewer
   ```

2. Restart Grafana:
   ```bash
   sudo systemctl restart grafana-server
   ```

---

## Security Considerations

### Network Security

1. **Firewall Rules:**
   ```bash
   # Minimal required access
   SLM Server → Monitoring VM:3000 (Nginx → Grafana)
   Monitoring VM → SLM Server:9090 (Grafana → Prometheus)
   ```

2. **Use IP Whitelisting:**
   ```bash
   # On monitoring VM
   sudo ufw deny 3000
   sudo ufw allow from 172.16.168.19 to any port 3000
   ```

3. **VPN/Private Network:**
   - Deploy on private VLAN if possible
   - Use VPN for external access
   - Avoid exposing Grafana directly to internet

### Authentication

1. **Disable Anonymous for Production:**
   ```ini
   [auth.anonymous]
   enabled = false  # Require login
   ```

2. **Enable SSO/OAuth:**
   ```ini
   [auth.generic_oauth]
   enabled = true
   name = OAuth
   client_id = xxx
   client_secret = xxx
   ```

3. **Strong Admin Password:**
   ```bash
   grafana-cli admin reset-admin-password --password-from-stdin
   ```

### TLS/Encryption

1. **Prometheus with TLS:**
   ```yaml
   # prometheus.yml
   tls_config:
     cert_file: /etc/prometheus/certs/cert.pem
     key_file: /etc/prometheus/certs/key.pem
   ```

2. **Grafana HTTPS Direct:**
   ```ini
   [server]
   protocol = https
   cert_file = /etc/grafana/certs/cert.pem
   cert_key = /etc/grafana/certs/key.pem
   ```

### Monitoring Access

1. **Audit Logging:**
   ```ini
   [log]
   mode = console file
   level = info

   [audit]
   enabled = true
   log_dashboard_views = true
   ```

2. **Rate Limiting:**
   ```nginx
   limit_req_zone $binary_remote_addr zone=grafana:10m rate=10r/s;

   location /grafana/ {
       limit_req zone=grafana burst=20;
       ...
   }
   ```

---

## Rollback Procedure

### Quick Rollback

If migration causes issues, rollback to local Grafana:

```bash
# On SLM server

# 1. Restore nginx config backup
sudo cp /etc/nginx/sites-available/autobot-slm.backup-<timestamp> \
     /etc/nginx/sites-available/autobot-slm
sudo nginx -t && sudo systemctl reload nginx

# 2. Start local Grafana
sudo systemctl start grafana-server
sudo systemctl enable grafana-server

# 3. Verify
curl http://localhost:3000/api/health
curl -k https://172.16.168.19/grafana/api/health

# 4. Test dashboards
xdg-open https://172.16.168.19/monitoring/system
```

### Ansible Rollback

```bash
cd autobot-slm-backend/ansible

# Deploy with local Grafana mode
ansible-playbook deploy-slm-manager.yml \
  -i inventory.ini \
  --extra-vars "grafana_mode=local grafana_install=true grafana_configure=true"
```

---

## Additional Resources

- **Grafana Documentation:** https://grafana.com/docs/
- **Prometheus Configuration:** https://prometheus.io/docs/prometheus/latest/configuration/configuration/
- **Nginx Reverse Proxy:** https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/
- **AutoBot Issue #853:** Grafana dashboard fixes and external host support

---

**Document Version:** 1.0.0
**Last Updated:** 2026-02-12
**Author:** mrveiss / Claude Sonnet 4.5
