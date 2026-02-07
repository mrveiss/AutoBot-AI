# Quick Start: Browser VNC Real-Time Viewing

## TL;DR - Using the System

### For Users

1. **Open AutoBot** → Navigate to **Browser** tab
2. **VNC iframe loads automatically** showing Browser VM desktop
3. **Enter URL** in address bar → Click "Navigate"
4. **Watch in real-time** as browser loads the page
5. **Agent can also control** the same browser via Playwright tools

### For Developers

```bash
# Check system status
ssh autobot@172.16.168.25 'sudo systemctl status browser-*.service'

# View Playwright logs
ssh autobot@172.16.168.25 'sudo journalctl -u browser-playwright -f'

# Test navigation
curl -X POST http://172.16.168.25:3000/navigate \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# Restart all services
ssh autobot@172.16.168.25 'sudo systemctl restart browser-*.service'
```

## Access Points

| Service | URL | Purpose |
|---------|-----|---------|
| **noVNC Web** | http://172.16.168.25:6080/vnc.html | Direct VNC access |
| **Playwright API** | http://172.16.168.25:3000 | Browser automation |
| **Frontend** | Browser tab in AutoBot | Integrated experience |

## Architecture

```
User/Agent → Frontend Browser Tab
                    ↓ (noVNC iframe)
           Browser VM (172.16.168.25)
                    ↓
           ┌────────┴────────┐
           │                  │
      VNC Server         Playwright
     (port 5901)         (headed mode)
           │                  │
           └────────┬────────┘
                    ↓
            Chromium Browser
         (visible on DISPLAY :1)
```

## Key Features

✅ **Real-time Viewing** - See browser as agent navigates
✅ **Collaborative Control** - Both user and agent can navigate
✅ **Automatic Startup** - All services start on boot
✅ **Auto-restart** - Services recover from crashes
✅ **Production Ready** - Systemd service management

## Service Status

```bash
# Quick health check
ssh autobot@172.16.168.25 "
  sudo systemctl is-active browser-vnc browser-vnc-websockify browser-playwright &&
  ss -tuln | grep -E ':(5901|6080|3000)'
"

# Expected output:
# active
# active
# active
# tcp LISTEN 0.0.0.0:5901  (VNC)
# tcp LISTEN 0.0.0.0:6080  (noVNC)
# tcp LISTEN 0.0.0.0:3000  (Playwright)
```

## Common Operations

### Navigate to URL

**Via Frontend:**
1. Open Browser tab
2. Enter URL in address bar
3. Click "Navigate"

**Via API:**
```bash
curl -X POST http://172.16.168.25:3000/navigate \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com"}'
```

### Reload Page

```bash
curl -X POST http://172.16.168.25:3000/reload \
  -H "Content-Type: application/json" \
  -d '{"wait_until": "networkidle"}'
```

## Troubleshooting

### VNC Not Loading

```bash
# Check VNC service
ssh autobot@172.16.168.25 'sudo systemctl status browser-vnc'

# Restart if needed
ssh autobot@172.16.168.25 'sudo systemctl restart browser-vnc'
```

### Browser Not Visible in VNC

```bash
# Check Playwright is in headed mode
ssh autobot@172.16.168.25 'sudo journalctl -u browser-playwright | grep mode'

# Should show: "headless":false,"mode":"headed"
```

### Services Not Starting

```bash
# Check service logs
ssh autobot@172.16.168.25 'sudo journalctl -xe'

# Redeploy all services
./scripts/infrastructure/deploy_browser_vnc_services.sh
```

## Files Created

**Infrastructure as Code:**
- `scripts/infrastructure/browser-vnc.service`
- `scripts/infrastructure/browser-vnc-websockify.service`
- `scripts/infrastructure/browser-playwright.service`
- `scripts/infrastructure/deploy_browser_vnc_services.sh`

**Frontend Integration:**
- `autobot-user-frontend/src/config/ServiceDiscovery.js` (updated)
- `autobot-user-frontend/src/components/PopoutChromiumBrowser.vue` (updated)

**Documentation:**
- `docs/infrastructure/BROWSER_VNC_SETUP.md` (full guide)
- `docs/QUICK_START_BROWSER_VNC.md` (this file)

## Next Steps

1. ✅ System deployed and running
2. ✅ Test navigation via frontend
3. ✅ Test agent automation
4. 🔄 Monitor performance under load
5. 🔄 Implement session recording (future)
6. 🔄 Add clipboard sync (future)

## Need Help?

**Full Documentation:** `docs/infrastructure/BROWSER_VNC_SETUP.md`

**Support:** Check logs first, then consult full documentation for detailed troubleshooting.

---

**Status:** ✅ Operational
**Last Updated:** 2025-11-14
