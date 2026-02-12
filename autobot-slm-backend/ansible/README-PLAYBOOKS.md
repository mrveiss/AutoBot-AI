# AutoBot Ansible Playbook Guide

> **Complete infrastructure-as-code for provisioning AutoBot fleet nodes from blank Ubuntu 22.04**

## Quick Start

```bash
# Provision a fresh node
ansible-playbook setup-npu-worker.yml --limit 172.16.168.22

# Update all nodes with latest code
ansible-playbook update-all-nodes.yml

# Update specific service
ansible-playbook update-all-nodes.yml --tags backend
```

---

## Playbook Catalog

### 🚀 Node Setup Playbooks (Fresh Install)

| Playbook | Purpose | Target Host Group | Time |
|----------|---------|-------------------|------|
| `setup-user-backend.yml` | Main AutoBot backend + VNC | `main` | ~8 min |
| `setup-user-frontend.yml` | User frontend (nginx + Vue) | `frontend` | ~5 min |
| `setup-npu-worker.yml` | NPU acceleration worker | `npu_worker` | ~6 min |
| `setup-browser-worker.yml` | Playwright automation | `browser_worker` | ~7 min |
| `setup-ai-stack.yml` | ChromaDB + Ollama (optional) | `ai_stack` | ~4 min |
| `setup-redis-stack.yml` | Redis with modules | `redis` | ~3 min |
| `deploy-slm-manager.yml` | SLM backend + frontend | `slm_server` | ~10 min |

### ⚡ Fast Update Playbooks

| Playbook | Purpose | Scope | Time |
|----------|---------|-------|------|
| `update-all-nodes.yml` | Code sync + restart (all nodes) | Fleet | ~2 min |
| `update-all-nodes.yml --tags backend` | Backend code only | Single service | ~30s |
| `provision-fleet-roles.yml` | Full re-provision | Fleet | ~45 min |

---

## Usage Examples

### Fresh Node Provisioning

**Scenario:** You have a blank Ubuntu 22.04 VM and want to make it an NPU worker.

```bash
# 1. Add to inventory
echo "172.16.168.22 ansible_host=172.16.168.22 ansible_user=autobot" >> inventory/hosts

# 2. Add to npu_worker group in inventory/hosts
# [npu_worker]
# 172.16.168.22

# 3. Run setup playbook
cd /home/kali/Desktop/AutoBot/autobot-slm-backend/ansible
ansible-playbook setup-npu-worker.yml --limit 172.16.168.22

# 4. Verify
ssh autobot@172.16.168.22 "systemctl status autobot-npu-worker"
curl http://172.16.168.22:8081/health
```

**Result:** Fully configured NPU worker with:
- ✅ System packages + OpenVINO
- ✅ autobot-npu-worker code at /opt/autobot/autobot-npu-worker/
- ✅ Python venv with dependencies
- ✅ Systemd service running
- ✅ TLS certificates
- ✅ Firewall configured

---

### Migrating Old Structure

**Scenario:** NPU worker is using old `/opt/autobot/npu-worker/` structure.

```bash
# The playbook detects old structure automatically
ansible-playbook setup-npu-worker.yml --limit 172.16.168.22

# It will:
# 1. Detect /opt/autobot/npu-worker/ exists
# 2. Provision new /opt/autobot/autobot-npu-worker/
# 3. Backup old structure to /opt/autobot/backups/npu-worker.backup.<timestamp>
# 4. Update systemd service to use new path
# 5. Restart service
```

---

### Fleet-Wide Code Update

**Scenario:** You committed new code and want to deploy to all nodes.

```bash
# Update everything (rolling 3 nodes at a time)
ansible-playbook update-all-nodes.yml

# Update only frontend nodes
ansible-playbook update-all-nodes.yml --limit frontend

# Update only backend code (no restart)
ansible-playbook update-all-nodes.yml --tags backend --skip-tags restart

# Update backend + NPU workers
ansible-playbook update-all-nodes.yml --tags backend,npu
```

**Speed Comparison:**
- Full provision: 5-10 minutes per node
- Code update: 30 seconds per node
- Fleet update (9 nodes): 2 minutes total

---

### Disaster Recovery

**Scenario:** VM crashed, need to rebuild from scratch.

```bash
# 1. Rebuild OS (Ubuntu 22.04)
# 2. Configure SSH keys
ssh-copy-id autobot@172.16.168.22

# 3. Run appropriate setup playbook
ansible-playbook setup-npu-worker.yml --limit 172.16.168.22

# Done! Node is back to production state.
```

---

## Playbook Architecture

### Standard Structure

Each setup playbook follows this pattern:

```yaml
- name: Setup <Service> Node
  hosts: <group>
  become: true

  vars:
    # Service-specific configuration

  pre_tasks:
    # Pre-flight checks
    # Migration detection

  roles:
    - common      # Base system setup
    - <service>   # Service-specific setup

  post_tasks:
    # Health verification
    # Summary report
```

### Common Role

The `common` role (applied to all nodes) provides:
- System package updates
- User/group creation
- Directory structure
- Time synchronization
- Base firewall rules
- SSH hardening
- Logging configuration

### Service Roles

Each service role is:
- **Idempotent**: Safe to run multiple times
- **Modular**: Can be used standalone or combined
- **Validated**: Post-tasks verify successful deployment
- **Documented**: Clear variable definitions

---

## Inventory Structure

```ini
# inventory/hosts

[main]
172.16.168.20 ansible_host=172.16.168.20 ansible_user=autobot

[frontend]
172.16.168.21 ansible_host=172.16.168.21 ansible_user=autobot

[npu_worker]
172.16.168.22 ansible_host=172.16.168.22 ansible_user=autobot

[redis]
172.16.168.23 ansible_host=172.16.168.23 ansible_user=autobot

[ai_stack]
172.16.168.24 ansible_host=172.16.168.24 ansible_user=autobot

[browser_worker]
172.16.168.25 ansible_host=172.16.168.25 ansible_user=autobot

[slm_server]
172.16.168.19 ansible_host=172.16.168.19 ansible_user=autobot

# Aggregate groups
[infrastructure:children]
main
frontend
npu_worker
redis
ai_stack
browser_worker
slm_server
```

---

## Advanced Usage

### Dry Run (Check Mode)

```bash
# See what would change without making changes
ansible-playbook setup-npu-worker.yml --limit 172.16.168.22 --check --diff
```

### Verbose Output

```bash
# Debug connection issues
ansible-playbook setup-npu-worker.yml --limit 172.16.168.22 -vvv
```

### Targeted Tags

```bash
# Only run specific tasks
ansible-playbook setup-user-backend.yml --limit main --tags verify
ansible-playbook update-all-nodes.yml --tags backend,restart
```

### Override Variables

```bash
# Change configuration on-the-fly
ansible-playbook setup-npu-worker.yml --limit 172.16.168.22 \
  --extra-vars "npu_worker_port=8082 backend_host=172.16.168.30"
```

---

## Troubleshooting

### SSH Connection Failed

```bash
# Test connectivity
ansible npu_worker -m ping

# If fails, check SSH keys
ssh-copy-id autobot@172.16.168.22
```

### Service Won't Start

```bash
# Check logs remotely
ansible npu_worker -m shell -a "journalctl -u autobot-npu-worker -n 50"

# Run playbook with verbose logging
ansible-playbook setup-npu-worker.yml --limit 172.16.168.22 -vvv
```

### Stale Code

```bash
# Force fresh sync
ansible-playbook update-all-nodes.yml --tags npu --extra-vars "delete=true"
```

---

## Best Practices

### 1. **Always Use Version Control**
- Commit changes before running playbooks
- Tag releases for rollback capability
- Document infrastructure changes in git

### 2. **Test on Single Node First**
```bash
# Test on one node
ansible-playbook update-all-nodes.yml --limit 172.16.168.22

# If successful, run fleet-wide
ansible-playbook update-all-nodes.yml
```

### 3. **Use Check Mode for Validation**
```bash
# Preview changes
ansible-playbook setup-npu-worker.yml --limit 172.16.168.22 --check
```

### 4. **Monitor During Updates**
```bash
# Terminal 1: Run playbook
ansible-playbook update-all-nodes.yml

# Terminal 2: Watch service status
watch -n 1 'ansible all -m shell -a "systemctl is-active autobot-*"'
```

### 5. **Keep Inventory Updated**
- Add new nodes immediately to inventory
- Remove decommissioned nodes
- Use group_vars for shared configuration

---

## Integration with Existing Tools

### sync-to-slm.sh

The existing sync script now uses these playbooks internally:

```bash
# Old way (still works)
./infrastructure/shared/scripts/utilities/sync-to-slm.sh --deploy

# New way (more control)
cd autobot-slm-backend/ansible
ansible-playbook deploy-slm-manager.yml
```

### provision-fleet-roles.yml

Full 8-phase fleet provisioning:

```bash
# Provision entire fleet from scratch
ansible-playbook provision-fleet-roles.yml

# Provision specific phases
ansible-playbook provision-fleet-roles.yml --tags phase-common,phase-agent
```

---

## Maintenance Schedule

### Daily
- `update-all-nodes.yml` - Fast code deployment

### Weekly
- Review playbook execution logs
- Update group_vars if infrastructure changed

### Monthly
- Run full `provision-fleet-roles.yml` to ensure config drift hasn't occurred
- Review and update firewall rules
- Certificate renewal checks

### Quarterly
- Disaster recovery drill (rebuild node from scratch)
- Review and update roles for new features

---

## Support

For issues or questions:
1. Check playbook output for error messages
2. Review logs: `journalctl -u <service-name>`
3. Consult `/home/kali/Desktop/AutoBot/CLAUDE.md`
4. Create GitHub issue with playbook output

---

**Last Updated:** 2026-02-12
**AutoBot Version:** Phase 9
