# Runbook: System Package Update

**Issue #926 Phase 8** | Last updated: 2026-10-31

---

## Overview

This runbook describes how to apply OS package updates (`apt upgrade`) to fleet nodes. System updates are **independent** from code updates — they update Ubuntu packages, not AutoBot application code.

---

## The rule

Apply OS updates through the SLM web UI, not with a hand-run `ansible-playbook` or `apt`. If the UI
cannot do something, that is a gap to fix in the SLM.

---

## Update Policies

Each role declares its update policy in `autobot-infrastructure/autobot-<role>/manifest.yml`.

| Policy | Applies To | Packages Updated | Reboot Strategy |
|--------|-----------|-----------------|-----------------|
| `full` | `.21` (frontend), `.25` (browser), `.26`, `.27` | All packages | Immediate reboot if required |
| `security` | `.19` (SLM), `.20` (backend), `.22` (NPU), `.24` (AI stack) | Security packages only | Scheduled reboot (maintenance window) |
| `manual` | `.23` (database) | None — manual only | Manual with pre-approved downtime |

The `manual` policy means updates are not applied automatically. Schedule downtime, then apply them to that node from the System Updates tab.

---

## Step-by-Step Procedure

### 1. Check pending updates

In the SLM web UI, open **Maintenance > Updates**, then the **System Updates** tab, and choose
**Check for Updates**. It lists the upgradable packages per node, with their severity.

### 2. Apply updates

Select packages and apply them, or use **Upgrade All**. Each run appears under
**Update Jobs**, where it can be followed or cancelled.

### 3. Handle reboots

Applying updates through this tab does not reboot a node, and nothing in the tab shows which nodes need a reboot. Reboot from **Fleet Overview**, one node
at a time, and wait for each to come back before the next. The reboot action does not check
maintenance windows (#17661), so choosing the time is up to you.

**Backend `.20` reboot note:** the backend takes about 6 minutes to fully initialize after a restart.

### 4. Verify

Run **Check for Updates** again; nothing applied should still be listed.

```bash
ssh autobot@<slm-manager-ip> "systemctl is-active autobot-slm-backend"
ssh autobot@<slm-manager-ip> 'curl --insecure https://<backend-ip>:8443/api/health | jq .status'
```

---

## Kernel Updates

Kernel updates require a reboot to take effect. Use the same reboot procedure above, but note:

- Never reboot `.19` (SLM) and `.20` (backend) simultaneously
- Reboot `.23` (database/Redis) only during scheduled maintenance — all backends will lose Redis connection temporarily

After rebooting `.19`:
1. Wait for SLM health check: `curl -sk https://<slm-manager-ip>/api/health`
2. Verify SLM agents reconnect: SLM GUI → Fleet Overview → all nodes reconnect within 60s

---

## Unattended Security Updates

Update modes and schedules in the UI are tracked in #18488. The earlier command for this used a tag
that does not exist in the playbook.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `apt` lock error | Another apt process running | Wait or: `ssh autobot@<node> "sudo kill $(lsof /var/lib/dpkg/lock | awk 'NR>1{print $2}')"` |
| Node unreachable after reboot | Service failed to start | SSH to node, check `systemctl status autobot-<role>`, check logs |
| Backend 504 after reboot | Backend still initializing | Wait 6 min, then retry — check `/var/log/autobot/backend.log` |
| Redis clients disconnected | Redis restarted | Backends auto-reconnect; monitor for 60s |
| Package held back | `apt-mark hold` in place | Check: `apt-mark showhold`; unhold if safe |
| Reboot loop after kernel update | Faulty kernel | Boot to previous kernel from GRUB; report to team |

---

## Scheduling Maintenance Windows

For stateful nodes (`.19`, `.20`, `.22`, `.23`, `.24`), plan reboots around:

- **`.20` backend:** 6-minute startup time; avoid during peak chat usage
- **`.23` Redis:** Redis restart disconnects all clients for ~5 seconds; schedule at 02:00–04:00
- **`.19` SLM:** SLM restart disconnects all SLM agents for ~30 seconds; schedule during low-traffic period

Recommended maintenance window: **Tuesday 02:00–04:00** (weekly).

---

## Related

- `system-update.yml` — apt update playbook; not for running by hand
- `docs/architecture/UPDATE_FLOWS.md` — update flow diagrams
- `docs/runbooks/CODE_UPDATE.md` — deploying application code (separate from OS updates)
- `docs/runbooks/EMERGENCY_RECOVERY.md` — if a node fails to come back after reboot
