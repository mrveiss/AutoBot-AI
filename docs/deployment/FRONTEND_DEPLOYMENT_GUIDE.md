# Frontend Deployment Guide
## Using SLM Code Sync Interface

> **Quick Link:** https://172.16.168.19/code-sync

---

## Overview

AutoBot uses a **pull-based deployment system** managed through the SLM (Service Lifecycle Manager) web interface. When code is committed to git, the post-commit hook notifies the SLM server, which marks fleet nodes as "outdated". Nodes then pull and build updates through the Code Sync interface.

---

## Part 1: Step-by-Step Visual Guide

### Step 1: Access SLM Admin Interface

1. **Open Browser**: Navigate to `https://172.16.168.19`
2. **Login**: Use your SLM admin credentials
   - Default: `admin` / (check `/etc/autobot/slm-secrets.env` on SLM server)
   - Browser will warn about self-signed certificate - this is expected, click "Advanced" → "Proceed"

### Step 2: Navigate to Code Sync Page

1. **Sidebar Navigation**: Click "Code Sync" in the left sidebar
2. **Page Load**: The interface shows 4 main sections:
   - **Status Banner** (top): Latest version, outdated node count, last fetch time
   - **Code Source Card**: Shows which node is the git source
   - **Pending Updates Table**: Lists nodes needing updates
   - **Role-Based Sync**: Quick sync by role (frontend, backend, etc.)

### Step 3: Understand the Status Banner

```
┌─────────────────────────────────────────────────────────────┐
│ Latest Version    Last Fetch           Outdated Nodes       │
│ 745e45ee         2026-02-16 20:48      1 / 9    [WARNING]  │
└─────────────────────────────────────────────────────────────┘
```

- **Latest Version**: Most recent commit hash (your Phase 2: 745e45ee)
- **Outdated Nodes**: Shows which nodes need updates (should show 1 for Frontend VM)
- **Warning Badge**: Yellow "Updates Available" if any nodes outdated

### Step 4: Configure Code Source (One-Time Setup)

**⚠️ IMPORTANT:** This must be configured before first deployment.

1. **Click "Configure"** button in Code Source card
2. **Select Source Node**: Choose "01-Backend" or whichever node has git access
   - Typically the Main server (172.16.168.20) or development machine
3. **Repository Path**: `/home/kali/Desktop/AutoBot` (or `/opt/autobot` if different)
4. **Branch**: `Dev_new_gui` (or `main` for production)
5. **Click "Save"**

The Code Source card will now show:
```
┌─────────────────────────────────────────────────────────────┐
│ Code Source                                    [Edit Button] │
│ 01-Backend (Main)                                            │
│ /home/kali/Desktop/AutoBot (Dev_new_gui)                    │
│ Last commit: 745e45ee                                        │
│                                          [Remove Button]     │
└─────────────────────────────────────────────────────────────┘
```

### Step 5: Sync Individual Node (Recommended for Testing)

**For your Phase 2 Evolution Dashboard deployment:**

1. **Locate Frontend Node** in the Pending Updates table:
   ```
   ┌──────────────────────────────────────────────────────────────┐
   │ Node ID       Hostname      Current    Target    Actions     │
   │ ─────────────────────────────────────────────────────────── │
   │ □ frontend-01 Frontend VM   997018a9   745e45ee  [Sync Now] │
   └──────────────────────────────────────────────────────────────┘
   ```

2. **Click "Sync Now"** button for the Frontend node
3. **Monitor Progress**: A blue progress banner appears:
   ```
   ┌─────────────────────────────────────────────────────────────┐
   │ 🔄 Sync in Progress                                          │
   │ Phase 1/5: Pulling code from source...                       │
   └─────────────────────────────────────────────────────────────┘
   ```

4. **Wait for Completion**: The process takes 2-5 minutes:
   - Phase 1: Pull code from git source
   - Phase 2: Run `npm install` (dependencies)
   - Phase 3: Run `npm run build` (production build)
   - Phase 4: Deploy build to nginx webroot
   - Phase 5: Reload nginx (if `restartAfterSync` enabled)

5. **Success Confirmation**: Progress banner turns green:
   ```
   ┌─────────────────────────────────────────────────────────────┐
   │ ✓ Node synchronized successfully                             │
   └─────────────────────────────────────────────────────────────┘
   ```

6. **Node Removed from Table**: Frontend node disappears from "Outdated Nodes" list

### Step 6: Sync Options (Before Clicking Sync)

**Configure behavior using dropdown menus:**

1. **Sync Strategy** (top-right):
   - `immediate`: Sync and restart immediately (may cause brief downtime)
   - `graceful`: Wait for idle period, then sync (default, recommended)
   - `manual`: Sync only, don't restart services

2. **Restart After Sync** checkbox:
   - ✓ Checked: Nginx reloads after build (recommended for frontend)
   - ✗ Unchecked: Build completes but old version still served

### Step 7: Alternative - Sync by Role (Batch Deployment)

**To deploy to ALL frontend nodes at once:**

1. **Scroll to "Role-Based Sync"** section
2. **Find "frontend" role**:
   ```
   ┌─────────────────────────────────────────────────────────────┐
   │ Role       Nodes    Outdated    Action                       │
   │ ────────────────────────────────────────────────────────── │
   │ frontend   3        1           [Sync Role]                 │
   │ backend    2        0           [Sync Role] (disabled)      │
   └─────────────────────────────────────────────────────────────┘
   ```
3. **Click "Sync Role"** for frontend
4. **Confirmation**: "Sync 1 frontend node?"
5. **Proceed**: All outdated frontend nodes sync in rolling fashion

### Step 8: Verify Deployment

1. **Check Status Banner**: "Outdated Nodes" should show `0 / 9`
2. **Green Badge**: "All Up To Date" appears
3. **Test Frontend**: Open `https://172.16.168.21/analytics/evolution`
   - New Evolution Dashboard should be visible in Analytics menu
   - Charts and UI should match Phase 2 implementation

---

## Part 2: Technical Documentation

### How Code Sync Works

**Architecture:**
```
┌─────────────┐  git commit   ┌─────────────┐  notify   ┌─────────────┐
│ Dev Machine │──────────────>│ Post-Commit │──────────>│ SLM Server  │
│ (.20)       │               │ Hook        │           │ (.19)       │
└─────────────┘               └─────────────┘           └──────┬──────┘
                                                                │
                                                        mark outdated
                                                                │
                              ┌─────────────────────────────────┘
                              │
                              v
                  ┌───────────────────────┐
                  │ Outdated Nodes:       │
                  │ - Frontend VM (.21)   │ ─┐
                  │ - NPU VM (.22)        │  │ pull via
                  │ - Browser VM (.25)    │  │ SLM API
                  └───────────────────────┘ ─┘
```

**Post-Commit Hook Flow:**
1. Developer commits to git on Main server (.20)
2. `.git/hooks/post-commit` executes `scripts/hooks/slm-post-commit`
3. Hook calls `POST https://172.16.168.19/api/code-source/notify`
4. SLM updates `CodeSource` table with new commit hash
5. SLM marks all fleet nodes as `CodeStatus.OUTDATED`
6. Nodes appear in Code Sync "Pending Updates" table

**Node Sync Process:**
1. **User triggers sync** via Code Sync UI
2. **SLM calls** `POST /api/code-sync/nodes/{node_id}/sync`
3. **Backend executes**:
   ```python
   # Pseudo-code of sync process
   1. SSH to source node (code-source)
   2. git pull latest changes
   3. rsync code to target node
   4. SSH to target node
   5. npm install (if package.json changed)
   6. npm run build (create production dist/)
   7. Deploy dist/ to nginx webroot
   8. Reload nginx (if restart enabled)
   9. Update node status: CodeStatus.UP_TO_DATE
   ```

4. **WebSocket progress updates** sent to UI (Issue #880)
5. **Completion** triggers page refresh

### API Endpoints Used

**Code Source Management:**
- `GET /api/code-source` - Get active code source
- `POST /api/code-source/assign` - Assign code source node
- `POST /api/code-source/notify` - Git post-commit notification
- `DELETE /api/code-source` - Remove code source

**Code Sync Operations:**
- `GET /api/code-sync/status` - Overall sync status
- `GET /api/code-sync/pending` - List outdated nodes
- `POST /api/code-sync/nodes/{id}/sync` - Sync single node
- `POST /api/code-sync/fleet` - Batch sync multiple nodes
- `POST /api/code-sync/roles/{role}/sync` - Sync all nodes with role
- `POST /api/code-sync/pull` - Pull from source (SLM server itself)

**WebSocket Events:**
- `sync_progress` - Real-time sync stage updates

### Database Schema

**Relevant Tables:**
```sql
-- Code source configuration
CodeSource (
    node_id VARCHAR PRIMARY KEY,
    repo_path VARCHAR,
    branch VARCHAR,
    last_known_commit VARCHAR,
    last_notified_at TIMESTAMP,
    is_active BOOLEAN
)

-- Fleet node status
Node (
    node_id VARCHAR PRIMARY KEY,
    hostname VARCHAR,
    ip_address VARCHAR,
    code_version VARCHAR,          -- Current commit hash
    code_status VARCHAR,            -- UP_TO_DATE | OUTDATED | SYNCING
    last_sync_at TIMESTAMP
)

-- Node roles (for role-based sync)
NodeRole (
    id INTEGER PRIMARY KEY,
    node_id VARCHAR,
    role_name VARCHAR,              -- 'frontend', 'backend', etc.
    status VARCHAR
)
```

### Configuration Files

**Environment Variables (SLM Server):**
```bash
# /etc/autobot/slm-secrets.env
AUTOBOT_SLM_HOST=172.16.168.19
AUTOBOT_CODE_SOURCE_NODE=01-Backend
SLM_REPO_PATH=/opt/autobot
SLM_SSH_KEY=/home/autobot/.ssh/autobot_key
```

**Git Hook (Code Source Node):**
```bash
# .git/hooks/post-commit (symlink to scripts/hooks/slm-post-commit)
# Automatically notifies SLM of commits
```

---

## Part 3: Deployment Checklist

### Pre-Deployment Checklist

**One-Time Setup (if not already done):**
- [ ] Code Source configured in SLM (Step 4 above)
- [ ] SSH keys deployed to all fleet VMs (`~/.ssh/autobot_key`)
- [ ] Git repository accessible from code source node
- [ ] Post-commit hook installed (`.git/hooks/post-commit`)
- [ ] All fleet nodes registered in SLM database
- [ ] Node roles assigned (`frontend`, `backend`, etc.)

**Before Each Deployment:**
- [ ] Code committed to git (`git commit`)
- [ ] Committed to correct branch (`Dev_new_gui` or `main`)
- [ ] Code pushed to remote (`git push`) if using remote git
- [ ] Post-commit hook executed successfully (check SLM logs)
- [ ] Frontend build succeeds locally (`npm run build` in `autobot-user-frontend/`)
- [ ] No TypeScript compilation errors (`npm run type-check`)
- [ ] Code changes don't require database migrations (or migrations ready)

### Deployment Execution Checklist

**Step-by-Step:**
- [ ] 1. Access SLM interface at https://172.16.168.19/code-sync
- [ ] 2. Verify "Latest Version" shows your commit hash (745e45ee for Phase 2)
- [ ] 3. Confirm "Outdated Nodes" count > 0 (should show Frontend VM)
- [ ] 4. Check "Pending Updates" table lists Frontend node
- [ ] 5. Set Sync Strategy to "graceful" (recommended)
- [ ] 6. Enable "Restart After Sync" checkbox
- [ ] 7. Click "Sync Now" for Frontend node
- [ ] 8. Monitor progress banner (2-5 minutes)
- [ ] 9. Wait for green success message
- [ ] 10. Verify node removed from "Outdated Nodes" table
- [ ] 11. Refresh page - "Outdated Nodes" should show 0

### Post-Deployment Verification

**Automated Checks:**
- [ ] Status Banner shows "All Up To Date" (green badge)
- [ ] Latest Version matches your commit hash
- [ ] Frontend node shows `code_status: UP_TO_DATE` in database
- [ ] `last_sync_at` timestamp is recent (within last 5 minutes)

**Manual Testing:**
- [ ] Open frontend: https://172.16.168.21
- [ ] Check browser console for errors (F12 → Console)
- [ ] Navigate to new feature: `/analytics/evolution` (Phase 2)
- [ ] Verify UI renders correctly (no missing components)
- [ ] Test API connectivity (trigger analysis, check charts)
- [ ] Check responsive layout (desktop + mobile)
- [ ] Verify authentication still works (login/logout)

**Browser Cache Clearing (if changes not visible):**
- [ ] Hard refresh: Ctrl+F5 (Windows/Linux) or Cmd+Shift+R (Mac)
- [ ] Clear site data: F12 → Application → Clear Storage
- [ ] Test in incognito/private window

**Rollback Plan (if deployment fails):**
- [ ] Note previous commit hash (from "Current" column before sync)
- [ ] Revert git: `git reset --hard <previous-commit>`
- [ ] Push revert: `git push --force-with-lease`
- [ ] Trigger post-commit hook: `bash scripts/hooks/slm-post-commit`
- [ ] Re-sync Frontend node via Code Sync interface

### Troubleshooting Checklist

**If sync fails:**
- [ ] Check SLM backend logs: `journalctl -u autobot-slm-backend -n 100`
- [ ] Verify SSH connectivity: `ssh autobot@172.16.168.21 "echo test"`
- [ ] Check disk space on Frontend VM: `df -h` (need >1GB free)
- [ ] Verify git repository accessible: `ls -la /home/kali/Desktop/AutoBot/.git`
- [ ] Check npm/node versions on Frontend VM: `node --version` (need 16+)

**If build succeeds but changes not visible:**
- [ ] Verify nginx serving correct directory: `nginx -T | grep root`
- [ ] Check nginx error log: `journalctl -u nginx -n 50`
- [ ] Verify dist/ files were copied: `ls -la /var/www/autobot-frontend/`
- [ ] Check file timestamps: `stat /var/www/autobot-frontend/index.html`
- [ ] Clear browser cache completely

**If progress hangs:**
- [ ] Check WebSocket connection in browser (F12 → Network → WS)
- [ ] Verify SLM backend not crashed: `systemctl status autobot-slm-backend`
- [ ] Check node SSH connection still alive: `ssh autobot@172.16.168.21`
- [ ] Review sync timeout settings (default: 10 minutes)

---

## Quick Reference Card

### 🚀 Fast Track Deployment

**For Experienced Users:**

```bash
# 1. Commit & push code
git add . && git commit -m "feat: your change" && git push

# 2. Access SLM
https://172.16.168.19/code-sync

# 3. Click "Sync Now" for outdated nodes

# 4. Verify
https://172.16.168.21  # Check your changes live
```

### 🔧 Configuration Quick Access

| Item | Location |
|------|----------|
| SLM Admin UI | https://172.16.168.19 |
| Code Sync Page | https://172.16.168.19/code-sync |
| User Frontend | https://172.16.168.21 |
| Backend API | https://172.16.168.20:8443/docs |
| SLM Backend Logs | `journalctl -u autobot-slm-backend -f` |
| Post-Commit Hook | `.git/hooks/post-commit` |

### 📱 Support Resources

- **Troubleshooting Guide**: `docs/troubleshooting/INDEX.md`
- **System State**: `docs/system-state.md`
- **CLAUDE.md**: Complete development notes
- **Issue Tracking**: https://github.com/mrveiss/AutoBot-AI/issues

---

## Document Metadata

- **Created**: 2026-02-16
- **Issue**: #243 (Phase 2 - Code Evolution Dashboard deployment)
- **Related Issues**: #741 (Code Sync), #779 (Code Source), #880 (Progress Tracking)
- **SLM Version**: Phase 9+
- **Last Updated**: 2026-02-16
- **Maintainer**: AutoBot Development Team
