> **IP addresses** in this document use role placeholders (e.g. `<backend-ip>`). Replace with your actual VM IPs. See [VM_ROLES.md](../architecture/VM_ROLES.md) for role definitions.

# Runbook: Deploy a Code Update

**Issue #926 Phase 8** | Last updated: 2026-10-31

---

## Overview

This runbook describes how to deploy a code update to the AutoBot fleet after committing changes to the git repository. The update process is role-scoped — only nodes running the affected role(s) are updated.

---

## The rule

Updates go through the builtin updater only, on test and production alike. Do not update a system
with a hand-run `ansible-playbook`, `git pull` or `rsync`. If the updater cannot do something, that
is a gap to fix in the updater.

---

## Standard Code Update Flow

### 1. Land the change

Changes reach `main` through a pull request. The updater takes its code from GitHub.

### 2. Review what is outdated

In the SLM web UI (`https://<slm-manager-ip>/slm/`), open **Maintenance > Updates**, then the
**Code Sync** tab. It shows the nodes that are behind and the commit each one is on.

### 3. Run the update

- **Update Everything** runs the full pipeline: fetch from GitHub, update the code source, update
  this SLM server, then the fleet.
- **Sync All**, or a single node's action, updates only the fleet nodes.

The frontend and `autobot_shared` are part of these updates. They need no separate step.

### 4. Monitor progress

The Code Sync tab shows the progress of the running update.

### 5. Verify

```bash
# Every node should be UP_TO_DATE: this prints the ones that are not
curl -sk https://<slm-manager-ip>/api/nodes \
  -H "Authorization: Bearer ${SLM_TOKEN}" \
  | jq '.[] | select(.code_status != "UP_TO_DATE") | {node_id, code_status}'

# Backend health
ssh autobot@<slm-manager-ip> 'curl --insecure https://<backend-ip>:8443/api/health'

# Frontend
curl -sk https://<frontend-ip>/api/health
```

The update also refreshes the install's `docs/` and core `plugins/` directories from the
code-source checkout and fails if the recorded docs commit differs from the code-source
commit. The install has no maintained `autobot-infrastructure/` copy: run infrastructure
scripts from the code-source checkout, never from an install-level copy.

---

## Going back to an earlier commit

The updater can deploy an earlier commit of `main`. Use it to undo a bad change quickly; the
lasting fix is still a revert merged through a pull request.

1. In the SLM web UI open **Maintenance > Updates > Code Sync**. In **Roll back to an earlier
   version**, pick a version from the list. Each line is a date and a subject; you never type a
   commit id. Only commits that are part of `main`'s history are offered.
2. Choose **Review rollback**. The SLM checks the choice again on the server and checks both
   databases (the SLM database and the backend database) for a migration in the way. A migration
   is in the way when the database has applied one that the chosen commit does not have. In that
   case the rollback is **refused** and the message names the database and the migration. If the
   SLM cannot read a database or the commit's migrations it also refuses: not knowing is not a
   pass. The updater never runs a migration downgrade, because a downgrade loses data.
3. Read what the rollback will do and choose **Roll back**. It needs the same permission as
   Update Everything, is refused while any update is running, and is recorded in the audit trail
   (`code.rollback`) before it starts.

A rollback runs as the same job as Update Everything and shows in the same progress view: it
fetches, updates this SLM server to the chosen commit (the service restarts, and the job resumes
after the restart exactly as Update Everything does), then updates every fleet node that is on a
different commit. The update pull stage is skipped.

**What the page shows afterwards.** The SLM keeps recording the latest commit of `main`, so every
node that was rolled back reads **outdated** against it and appears under the nodes that are
behind. That is the truth, not a fault. Nothing re-applies the latest by itself: the next code sync
of a node deploys `main` again.

**Returning to the latest.** Run **Update Everything**. It moves forward from the rolled-back
commit as it does from any other.

**Not covered.** A rollback does not undo database changes (see above), and it does not restore
data. It is refused when this SLM already runs the chosen commit.

## Recovery when the SLM dashboard itself is unreachable (#15462)

A failed SLM frontend build can leave `/slm/` serving 403 for the whole
dashboard — including the "Update Everything" button and the code-sync UI you
would normally use to fix it — while every `autobot-*` service still reports
`active (running)`. The backend API stays reachable throughout; only its UI
is gone.

For that situation, a static, dependency-free recovery page is served
directly by the SLM backend, independent of the frontend build:

```
https://<slm-manager-ip>/slm/api/recovery
```

It shows the backend's own `/api/health` (including the frontend-bundle
probe below), and lets you sign in and trigger the same self-update the
dashboard's "Update Everything" button runs — with no build step of its own,
so a broken frontend build cannot take it down too.

A degraded `frontend` field in `/api/health` (`unhealthy: build output has
no index.html — a build failed or was never published`) is the signal that
this is the situation you are in, versus a process actually being down.

---

## Triggering a self-update from the SLM host itself, with no credentials (#15728)

`POST /api/code-sync/self-update` requires an authenticated user — correct
for the network-facing API, but it means routine maintenance run from a
shell already on the box still needs a password every time, which is
exactly the kind of place a credential ends up typed into a script or a
CI job where it shouldn't be.

An operator with a shell on the SLM host has a second, credential-free way
to fire the SAME update — no login, no bearer token, nothing on a command
line to leak into shell history:

```bash
curl -s --unix-socket /run/autobot/slm-self-update.sock \
  -X POST http://localhost/self-update
```

`/run/autobot/slm-self-update.sock` is the **default** path, not a fixed one:
it comes from the `slm_self_update_socket_path` variable in the `slm_manager`
role's defaults, and a deployment may override it. On a host where it has been
overridden the command above targets a socket that does not exist and fails
with a connection error rather than anything explanatory. Confirm the actual
path first:

```bash
systemctl show autobot-slm-self-update.socket -p Listen
```

This reaches a second ASGI listener bound ONLY to a Unix domain socket that
systemd's `autobot-slm-self-update.socket` unit creates and owns. The
socket file's own permissions (root, or a member of the backend's service
group) ARE the access control — the same boundary that already lets that
operator restart every service on the box by hand. Nothing here is a secret
to type, store, or rotate: reachability of the socket IS the credential.

Ansible role `slm_manager`'s `slm_self_update_socket_enabled` (default
`true`) can turn both the socket unit and the backend's `Sockets=` wiring
off for a host that should not carry this surface at all.

This is deliberately NOT a replacement for `/recovery` above: `/recovery`
solves a BROKEN frontend, reachable from any browser, off-host included.
This solves "trigger routine maintenance from a shell that already has
root, without a password" — a different problem, and neither folds into
the other.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Nodes stay OUTDATED after an update | The update failed for that node | Read the failure in the Code Sync tab, fix it, run the update again |
| Ansible `UNREACHABLE` | SSH key issue | Test: `ssh -i /etc/autobot/ssh/autobot_key autobot@<node-ip> echo ok` |
| Backend takes 6 min after restart | Normal startup (GPUSemanticChunker + ChromaDB) | Wait; check `/var/log/autobot/backend.log` |
| Node shows wrong commit | Heartbeat overwrote mark-synced | Issue fixed in #918; check `code_version` in DB |
| `/slm/` returns 403, all services green | Frontend build failed/incomplete (#15462) | Use `https://<slm-manager-ip>/slm/api/recovery` — see section above |

---

## Post-Update Verification Checklist

- [ ] All nodes show `code_status: UP_TO_DATE` in SLM
- [ ] Backend health check returns 200: `curl -sk https://<slm-manager-ip> 'curl --insecure https://<backend-ip>:8443/api/health'`
- [ ] Frontend serves updated build: `curl -sk https://<frontend-ip>/ | grep <version-or-feature>`
- [ ] No error spikes in logs: `ssh autobot@<backend-ip> "tail -50 /var/log/autobot/backend.log" | grep -i error`

---

## Related

- `docs/architecture/UPDATE_FLOWS.md` — flow diagrams for all update channels
- `update-all-nodes.yml` — the playbook the updater runs; not for running by hand. A rollback passes it `deploy_ref` (the chosen commit) and `deploy_is_rollback` (#20214)
- `autobot-slm-backend/services/code_rollback.py` — the rollback path (#20214)
- `docs/runbooks/SYSTEM_UPDATE.md` — OS package updates (separate from code)
- `autobot-slm-backend/static/recovery.html` — backend-served recovery page (#15462)
- `autobot-slm-backend/services/local_admin_socket.py` — credential-free local self-update socket (#15728)
