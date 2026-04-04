# Grafana Quick Reference Card

**AutoBot SLM Monitoring - Grafana Configuration Cheat Sheet**

---

## 🚀 Quick Commands

### Check Grafana Status
```bash
# Local Grafana (SLM server)
curl http://localhost:3000/api/health
systemctl status grafana-server

# External Grafana (monitoring VM)
curl http://<reserved-ip>:3000/api/health
ssh autobot@<reserved-ip> "systemctl status grafana-server"

# Via nginx proxy
curl -k https://<slm-manager-ip>/grafana/api/health
```

### Test Dashboard Access
```bash
# All dashboard types
for dash in autobot-system autobot-overview autobot-performance autobot-multi-machine autobot-redis autobot-api-health; do
  echo -n "$dash: "
  curl -k -s -o /dev/null -w "%{http_code}\n" "https://<slm-manager-ip>/grafana/d/$dash?kiosk=tv"
done
```

### View Grafana Logs
```bash
# Local
sudo journalctl -u grafana-server -f

# External
ssh autobot@<reserved-ip> "sudo journalctl -u grafana-server -f"
```

---

## 📁 Important File Locations

### SLM Server (<slm-manager-ip>)
```
/etc/grafana/grafana.ini                    - Grafana configuration
/var/lib/grafana/dashboards/                - Dashboard JSON files
/etc/grafana/provisioning/dashboards/       - Dashboard provisioning
/etc/grafana/provisioning/datasources/      - Data source config
/etc/nginx/sites-available/autobot-slm      - Nginx proxy config
/var/log/grafana/                           - Grafana logs
```

### Ansible
```
autobot-slm-backend/ansible/
├── migrate-grafana-to-vm.yml               - Migration playbook
├── inventory-grafana-migration.ini         - Inventory template
└── roles/slm_manager/
    ├── defaults/main.yml                   - Grafana variables
    ├── tasks/grafana.yml                   - Grafana tasks
    └── templates/autobot-slm.conf.j2       - Nginx template
```

### Documentation
```
docs/infrastructure/
├── GRAFANA_EXTERNAL_HOST_SETUP.md          - Complete guide
└── GRAFANA_QUICK_REFERENCE.md              - This file
```

---

## 🔧 Common Operations

### Restart Grafana
```bash
# Local
sudo systemctl restart grafana-server

# External
ssh autobot@<reserved-ip> "sudo systemctl restart grafana-server"
```

### Reload Nginx (after config change)
```bash
sudo nginx -t && sudo systemctl reload nginx
```

### View Active Dashboards
```bash
curl -s http://localhost:3000/api/search | jq -r '.[] | "\(.title) - \(.uid)"'
```

### Check Prometheus Connection
```bash
# From Grafana VM
curl -s http://<slm-manager-ip>:9090/api/v1/query?query=up | jq
```

---

## 🎯 Configuration Modes

### Mode 1: Local Grafana (Default)
```yaml
# No configuration needed - works out of box
grafana_mode: local
```

**URLs:**
- Direct: http://localhost:3000
- Proxied: https://<slm-manager-ip>/grafana/

### Mode 2: External Grafana (Dedicated VM)
```yaml
grafana_mode: external
grafana_external_host: <reserved-ip>
grafana_enable_cors: true
```

**URLs:**
- Direct: http://<reserved-ip>:3000
- Proxied: https://<slm-manager-ip>/grafana/

### Mode 3: External Grafana (Cloud/Remote)
```yaml
grafana_mode: external
grafana_external_host: grafana.example.com
grafana_enable_cors: true
prometheus_host: <slm-manager-ip>  # Public IP
```

---

## 🔄 Migration Commands

### One-Line Migration
```bash
cd autobot-slm-backend/ansible && \
  ansible-playbook migrate-grafana-to-vm.yml -i inventory-migration.ini
```

### Step-by-Step Migration
```bash
# 1. Copy and edit inventory
cp inventory-grafana-migration.ini inventory-migration.ini
vim inventory-migration.ini  # Set monitoring_vm host

# 2. Test connectivity
ansible -i inventory-migration.ini monitoring_vm -m ping

# 3. Run migration
ansible-playbook migrate-grafana-to-vm.yml -i inventory-migration.ini

# 4. Verify
curl -k https://<slm-manager-ip>/grafana/api/health
```

### Rollback to Local
```bash
ansible-playbook deploy-slm-manager.yml -i inventory.ini \
  --extra-vars "grafana_mode=local grafana_install=true"
```

---

## 🐛 Troubleshooting

### Problem: No Data in Dashboards
```bash
# Check Prometheus
curl http://<slm-manager-ip>:9090/api/v1/query?query=up

# Check firewall
sudo ufw status | grep 9090

# Check Grafana data source
curl -s http://localhost:3000/api/datasources | jq
```

### Problem: 502 Bad Gateway
```bash
# Check Grafana is running
systemctl status grafana-server

# Check Grafana is listening
sudo netstat -tlnp | grep 3000

# Check nginx config
sudo nginx -t
cat /etc/nginx/sites-enabled/autobot-slm | grep grafana -A 5
```

### Problem: CORS Errors
```bash
# Check nginx CORS headers
curl -k -I https://<slm-manager-ip>/grafana/api/health | grep Access-Control

# Check Grafana settings
grep -E "allow_embedding|cookie_samesite" /etc/grafana/grafana.ini | grep -v '^;'
```

### Problem: Authentication Required
```bash
# Enable anonymous auth
sudo sed -i '/\[auth.anonymous\]/,/\[/{s/^;*enabled = .*/enabled = true/}' /etc/grafana/grafana.ini
sudo systemctl restart grafana-server
```

### Problem: 301 Redirects
```bash
# Check serve_from_sub_path
grep serve_from_sub_path /etc/grafana/grafana.ini

# Should be:
# serve_from_sub_path = true

# Check nginx proxy_pass
grep -A 2 "location /grafana/" /etc/nginx/sites-enabled/autobot-slm

# Should end with:
# proxy_pass http://HOST:3000/grafana/;
```

---

## 📊 Dashboard URLs

### Direct Access (Kiosk Mode)
```
https://<slm-manager-ip>/grafana/d/autobot-system?kiosk=tv
https://<slm-manager-ip>/grafana/d/autobot-overview?kiosk=tv
https://<slm-manager-ip>/grafana/d/autobot-performance?kiosk=tv
https://<slm-manager-ip>/grafana/d/autobot-multi-machine?kiosk=tv
https://<slm-manager-ip>/grafana/d/autobot-redis?kiosk=tv
https://<slm-manager-ip>/grafana/d/autobot-api-health?kiosk=tv
```

### SLM Frontend Integration
```
https://<slm-manager-ip>/monitoring/system
```

---

## 🔐 Security Checklist

### Minimum Required Access
```bash
# SLM Server firewall
sudo ufw allow from <reserved-ip> to any port 9090 comment "Grafana to Prometheus"

# Monitoring VM firewall
sudo ufw allow from <slm-manager-ip> to any port 3000 comment "Nginx to Grafana"
```

### Production Hardening
```ini
# /etc/grafana/grafana.ini

[auth.anonymous]
enabled = false  # Require login

[security]
admin_password = <strong-password>
secret_key = <random-64-chars>
disable_gravatar = true

[users]
allow_sign_up = false
allow_org_create = false

[auth]
disable_login_form = false
disable_signout_menu = false
```

---

## 📈 Performance Tuning

### Grafana Configuration
```ini
[database]
max_idle_conn = 2
max_open_conn = 0
conn_max_lifetime = 14400

[dataproxy]
timeout = 300
keep_alive_seconds = 300

[metrics]
enabled = true
```

### Nginx Configuration
```nginx
# Rate limiting
limit_req_zone $binary_remote_addr zone=grafana:10m rate=10r/s;

location /grafana/ {
    limit_req zone=grafana burst=20 nodelay;
    proxy_buffering on;
    proxy_cache_valid 200 1m;
}
```

---

## 🔍 Health Check Script

Save as `check-grafana-health.sh`:

```bash
#!/bin/bash
# AutoBot Grafana Health Check

GRAFANA_HOST="${1:-<slm-manager-ip>}"
GRAFANA_PORT="${2:-3000}"

echo "=== Grafana Health Check ==="
echo

# 1. Service Status
echo "1. Service Status:"
systemctl is-active grafana-server && echo "✅ Running" || echo "❌ Stopped"
echo

# 2. API Health
echo "2. API Health:"
curl -s "http://$GRAFANA_HOST:$GRAFANA_PORT/api/health" | jq || echo "❌ Failed"
echo

# 3. Dashboard Count
echo "3. Dashboards:"
DASH_COUNT=$(curl -s "http://$GRAFANA_HOST:$GRAFANA_PORT/api/search" | jq '. | length')
echo "Found $DASH_COUNT dashboards"
echo

# 4. Data Source
echo "4. Data Sources:"
curl -s "http://$GRAFANA_HOST:$GRAFANA_PORT/api/datasources" | jq -r '.[] | "\(.name): \(.url)"'
echo

# 5. Test Dashboard Access
echo "5. Dashboard Access:"
for dash in autobot-system autobot-overview; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://$GRAFANA_HOST:$GRAFANA_PORT/grafana/d/$dash?kiosk=tv")
  if [ "$STATUS" = "200" ]; then
    echo "✅ $dash"
  else
    echo "❌ $dash (HTTP $STATUS)"
  fi
done
echo

echo "=== Health Check Complete ==="
```

Usage:
```bash
chmod +x check-grafana-health.sh
./check-grafana-health.sh                    # Local
./check-grafana-health.sh <reserved-ip>      # External
```

---

## 📞 Quick Support

### Documentation
- Full Guide: `docs/infrastructure/GRAFANA_EXTERNAL_HOST_SETUP.md`
- This Reference: `docs/infrastructure/GRAFANA_QUICK_REFERENCE.md`

### Related Issues
- #853: Grafana dashboard fixes
- #854: External host support

### Useful Commands
```bash
# Show Grafana config summary
grep -E "^(http_addr|http_port|domain|root_url|serve_from_sub_path|enabled|org_role|allow_embedding|cookie_samesite)" /etc/grafana/grafana.ini | grep -v '^;'

# Show all AutoBot dashboards
find /var/lib/grafana/dashboards/ -name "*.json" -exec basename {} \;

# Show Grafana version
grafana-server -v

# Restart all monitoring services
sudo systemctl restart grafana-server prometheus nginx
```

---

**Quick Reference Version:** 1.0.0
**Last Updated:** 2026-02-12
**Related Docs:** GRAFANA_EXTERNAL_HOST_SETUP.md
