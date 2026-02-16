# Frontend Deployment Checklist
## Quick Reference for AutoBot Code Deployments

> **SLM Interface:** https://172.16.168.19/code-sync

---

## ✅ Pre-Deployment (One-Time Setup)

- [ ] **Code Source Configured**
  - Log into SLM → Code Sync → Configure button
  - Node: `01-Backend` (or code source machine)
  - Path: `/home/kali/Desktop/AutoBot`
  - Branch: `Dev_new_gui` (or `main` for prod)

- [ ] **SSH Keys Deployed**
  ```bash
  # Verify key exists
  ls -la ~/.ssh/autobot_key

  # Test SSH to frontend
  ssh -i ~/.ssh/autobot_key autobot@172.16.168.21 "echo success"
  ```

- [ ] **Git Hook Installed**
  ```bash
  # Check symlink
  ls -la .git/hooks/post-commit
  # Should point to: scripts/hooks/slm-post-commit
  ```

---

## 🚀 Deployment Steps

### Phase 1: Code Preparation

- [ ] **Build Succeeds Locally**
  ```bash
  cd autobot-user-frontend
  npm run build
  # Should complete without errors
  ```

- [ ] **TypeScript Compiles**
  ```bash
  npm run type-check
  # Check for errors in YOUR files only
  ```

- [ ] **Commit & Push**
  ```bash
  git add <your-files>
  git commit -m "feat(frontend): description (#issue-number)"
  git push origin Dev_new_gui
  ```

- [ ] **Post-Commit Hook Executed**
  ```bash
  # Check if hook ran (no output = success)
  # Verify in SLM: Latest Version should update
  ```

### Phase 2: SLM Deployment

- [ ] **Access SLM**
  - Browser: https://172.16.168.19
  - Login with admin credentials
  - Navigate to "Code Sync" in sidebar

- [ ] **Verify Status**
  - ✅ Latest Version = your commit hash (e.g., 745e45ee)
  - ✅ Outdated Nodes > 0 (should show Frontend)
  - ✅ Frontend node in "Pending Updates" table

- [ ] **Configure Sync Options**
  - Strategy: `graceful` (recommended) or `immediate`
  - ✅ Enable "Restart After Sync" checkbox

- [ ] **Trigger Sync**
  - Click **"Sync Now"** button for Frontend node
  - Alternative: Click **"Sync Role"** for all frontend nodes

- [ ] **Monitor Progress**
  - Blue banner: "Sync in Progress"
  - Stages: Pull → Install → Build → Deploy → Reload
  - Duration: 2-5 minutes
  - Green banner: "Node synchronized successfully"

### Phase 3: Verification

- [ ] **Check SLM Status**
  - "Outdated Nodes" = 0 / total
  - Green badge: "All Up To Date"
  - Frontend node removed from table

- [ ] **Test Frontend Access**
  ```bash
  # Check homepage loads
  curl -Ik https://172.16.168.21

  # Check your new feature (Phase 2 example)
  curl -Ik https://172.16.168.21/analytics/evolution
  ```

- [ ] **Browser Testing**
  - Open: https://172.16.168.21
  - Hard refresh: Ctrl+F5 (clear cache)
  - Check console: F12 → Console (no red errors)
  - Navigate to your feature
  - Test functionality (clicks, data loading, etc.)

- [ ] **Mobile/Responsive Check**
  - F12 → Toggle device toolbar (Ctrl+Shift+M)
  - Test on mobile sizes (320px, 768px, 1024px)

---

## 🔥 Fast Track (Experienced Users)

```bash
# 1. Build & commit
cd autobot-user-frontend && npm run build && cd ..
git add <files> && git commit -m "feat: change" && git push

# 2. Deploy via SLM
# https://172.16.168.19/code-sync → Sync Now

# 3. Verify
curl -Ik https://172.16.168.21
```

**Expected Time:** 3-7 minutes total

---

## 🐛 Troubleshooting Quick Fixes

### Sync Fails

```bash
# Check SLM logs
ssh autobot@172.16.168.19
journalctl -u autobot-slm-backend -n 100 --no-pager

# Check SSH connectivity
ssh autobot@172.16.168.21 "echo test"

# Verify disk space
ssh autobot@172.16.168.21 "df -h"
```

### Changes Not Visible

```bash
# Hard refresh browser
Ctrl + F5  (or Cmd + Shift + R on Mac)

# Clear browser cache
F12 → Application → Clear Storage → Clear site data

# Check nginx serving correct files
ssh autobot@172.16.168.21 "ls -lt /var/www/autobot-frontend/ | head -10"

# Check file timestamp
ssh autobot@172.16.168.21 "stat /var/www/autobot-frontend/index.html"
```

### Build Fails on VM

```bash
# Check node version (need 16+)
ssh autobot@172.16.168.21 "node --version"

# Check npm install errors
ssh autobot@172.16.168.21 "cd /opt/autobot/autobot-user-frontend && npm install"

# Check build errors
ssh autobot@172.16.168.21 "cd /opt/autobot/autobot-user-frontend && npm run build"
```

### Rollback to Previous Version

```bash
# 1. Get previous commit hash
git log --oneline -5

# 2. Revert to previous commit
git reset --hard <previous-commit-hash>
git push --force-with-lease origin Dev_new_gui

# 3. Notify SLM
bash scripts/hooks/slm-post-commit

# 4. Re-sync in SLM interface
# https://172.16.168.19/code-sync → Sync Now
```

---

## 📊 Status Indicators

| Indicator | Meaning | Action |
|-----------|---------|--------|
| 🟢 All Up To Date | No outdated nodes | ✅ All good |
| 🟡 Updates Available | Nodes need sync | Click "Sync Now" |
| 🔵 Sync in Progress | Deployment running | Wait 2-5 min |
| ✅ Sync Complete | Success | Verify in browser |
| ❌ Sync Failed | Error occurred | Check logs |

---

## 🔗 Quick Links

| Resource | URL |
|----------|-----|
| SLM Admin | https://172.16.168.19 |
| Code Sync | https://172.16.168.19/code-sync |
| User Frontend | https://172.16.168.21 |
| Backend Docs | https://172.16.168.20:8443/docs |
| GitHub Issues | https://github.com/mrveiss/AutoBot-AI/issues |

---

## 📞 Get Help

**Documentation:**
- Full Guide: `docs/deployment/FRONTEND_DEPLOYMENT_GUIDE.md`
- Troubleshooting: `docs/troubleshooting/INDEX.md`
- System State: `docs/system-state.md`

**Logs:**
```bash
# SLM Backend
journalctl -u autobot-slm-backend -f

# Frontend VM Nginx
ssh autobot@172.16.168.21 "journalctl -u nginx -f"

# Frontend VM System
ssh autobot@172.16.168.21 "tail -f /var/log/syslog"
```

---

**Document Version:** 1.0
**Last Updated:** 2026-02-16
**Issue:** #243 (Phase 2 - Code Evolution Dashboard)
