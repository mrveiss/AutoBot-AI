# Browser VM VNC Setup - Infrastructure as Code

## Overview

Real-time collaborative browser viewing system for AutoBot - enables both users and AI agents to observe and control the same browser instance through VNC on Browser VM (172.16.168.25).

## Architecture

```
Frontend (172.16.168.21:5173)
    ↓
Browser Tab Component (PopoutChromiumBrowser.vue)
    ↓
noVNC iframe → Browser VM (172.16.168.25:6080/vnc.html)
    ↓
websockify (port 6080) → VNC Server (port 5901)
    ↓
Xtigervnc (DISPLAY :1) ← Playwright (headed mode)
```

## Infrastructure Components

### Systemd Services (IaC)

All services are managed by systemd for automatic startup and restart:

1. **browser-vnc.service** - TigerVNC server on display :1
2. **browser-vnc-websockify.service** - noVNC WebSocket proxy
3. **browser-playwright.service** - Playwright API in headed mode

### Service Files Location

```
scripts/infrastructure/
├── browser-vnc.service
├── browser-vnc-websockify.service
├── browser-playwright.service
└── deploy_browser_vnc_services.sh
```

## Deployment

### Automated Deployment

```bash
# Deploy all services using IaC script
./scripts/infrastructure/deploy_browser_vnc_services.sh
```

This script:
- Copies service files to Browser VM
- Installs them to /etc/systemd/system/
- Enables services for auto-start
- Stops manual processes
- Starts all services

### Manual Deployment

If needed, deploy manually:

```bash
# Copy service files
scp scripts/infrastructure/browser-*.service autobot@172.16.168.25:/tmp/

# Install on Browser VM
ssh autobot@172.16.168.25
sudo mv /tmp/browser-*.service /etc/systemd/system/
sudo chmod 644 /etc/systemd/system/browser-*.service
sudo systemctl daemon-reload
sudo systemctl enable browser-vnc browser-vnc-websockify browser-playwright
sudo systemctl start browser-vnc browser-vnc-websockify browser-playwright
```

## Service Management

### Check Status

```bash
ssh autobot@172.16.168.25 'sudo systemctl status browser-vnc browser-vnc-websockify browser-playwright'
```

### View Logs

```bash
# Playwright logs (includes browser activity)
ssh autobot@172.16.168.25 'sudo journalctl -u browser-playwright -f'

# VNC server logs
ssh autobot@172.16.168.25 'sudo journalctl -u browser-vnc -f'

# websockify logs
ssh autobot@172.16.168.25 'sudo journalctl -u browser-vnc-websockify -f'
```

### Restart Services

```bash
# Restart all browser services
ssh autobot@172.16.168.25 'sudo systemctl restart browser-*.service'

# Restart individual service
ssh autobot@172.16.168.25 'sudo systemctl restart browser-playwright'
```

### Stop/Start Services

```bash
# Stop all
ssh autobot@172.16.168.25 'sudo systemctl stop browser-*.service'

# Start all
ssh autobot@172.16.168.25 'sudo systemctl start browser-vnc browser-vnc-websockify browser-playwright'
```

## Configuration

### Playwright Headed Mode

Configured via environment variables in `browser-playwright.service`:

```ini
Environment="HEADLESS=false"
Environment="DISPLAY=:1"
```

### VNC Server Settings

- **Display**: :1
- **Port**: 5901
- **Resolution**: 1920x1080
- **Depth**: 24-bit
- **Security**: None (internal network only)

### noVNC Settings

- **Port**: 6080
- **Web Root**: /usr/share/novnc
- **Proxy Target**: localhost:5901

## Frontend Integration

### Service Discovery Configuration

File: `autobot-user-frontend/src/config/ServiceDiscovery.js`

```javascript
vnc_playwright: {
  envVar: 'VITE_PLAYWRIGHT_VNC_URL',
  hostVar: 'VITE_PLAYWRIGHT_VNC_HOST',
  portVar: 'VITE_PLAYWRIGHT_VNC_PORT',
  port: '6080',
  protocol: 'http',
  fallbackHosts: [NetworkConstants.BROWSER_VM_IP, ...] // Browser VM first
},
```

### Browser Component

File: `autobot-user-frontend/src/components/PopoutChromiumBrowser.vue`

```javascript
// Loads VNC URL on mount
vncUrl.value = await appConfig.getVncUrl('playwright', {
  autoconnect: true,
  resize: 'scale'
})
```

## Access Points

### Direct VNC Access

- **noVNC Web**: http://172.16.168.25:6080/vnc.html
- **VNC Protocol**: vnc://172.16.168.25:5901

### Frontend Browser Tab

Navigate to Browser tab in AutoBot interface:
- VNC iframe automatically loads
- Real-time browser viewing
- Address bar for manual navigation
- Both user and agent can control browser

## Testing

### Verify Services

```bash
# Check all ports listening
ssh autobot@172.16.168.25 "ss -tuln | grep -E ':(5901|6080|3000)'"

# Should show:
# - Port 5901 (VNC)
# - Port 6080 (noVNC)
# - Port 3000 (Playwright API)
```

### Test VNC Connection

1. Open http://172.16.168.25:6080/vnc.html
2. Click "Connect"
3. Should see XFCE desktop

### Test Playwright Headed Mode

```bash
# Navigate to a page via API
curl -X POST http://172.16.168.25:3000/navigate \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# Check VNC - browser window should appear on desktop
```

### Test Frontend Integration

1. Open AutoBot frontend
2. Navigate to Browser tab
3. Enter URL in address bar
4. Click "Navigate"
5. Should see browser window in VNC iframe

## Collaborative Browsing

### User Actions

- Enter URL in address bar
- Click navigation buttons
- Observe agent browser activities in real-time

### Agent Actions

- Use Playwright MCP tools to control browser
- Navigate, click, fill forms
- All actions visible to user via VNC

### Real-time Synchronization

- Both user and agent see same browser instance
- Actions immediately visible to both parties
- Enables collaborative debugging and testing

## Troubleshooting

### VNC Connection Failed

```bash
# Check VNC server
ssh autobot@172.16.168.25 'ps aux | grep Xtigervnc'

# Restart if needed
ssh autobot@172.16.168.25 'sudo systemctl restart browser-vnc'
```

### websockify Not Working

```bash
# Check logs
ssh autobot@172.16.168.25 'sudo journalctl -u browser-vnc-websockify -n 50'

# Verify noVNC installed
ssh autobot@172.16.168.25 'dpkg -l | grep novnc'

# Install if missing
ssh autobot@172.16.168.25 'sudo apt-get install -y novnc'
```

### Playwright Still Headless

```bash
# Check environment variables
ssh autobot@172.16.168.25 'sudo systemctl show browser-playwright | grep Environment'

# Should show:
# Environment=HEADLESS=false DISPLAY=:1
```

### Browser Window Not Visible

```bash
# Check DISPLAY variable
ssh autobot@172.16.168.25 'echo $DISPLAY'

# Check X server
ssh autobot@172.16.168.25 'ps aux | grep Xtigervnc'

# Restart Playwright with correct DISPLAY
ssh autobot@172.16.168.25 'sudo systemctl restart browser-playwright'
```

## Maintenance

### Update Service Configuration

1. Edit service file locally in `scripts/infrastructure/`
2. Run deployment script: `./scripts/infrastructure/deploy_browser_vnc_services.sh`
3. Or manually copy and reload: `sudo systemctl daemon-reload`

### Monitor Resource Usage

```bash
# Check system resources
ssh autobot@172.16.168.25 'top -b -n 1 | head -20'

# Check service memory usage
ssh autobot@172.16.168.25 'systemctl status browser-playwright --no-pager | grep Memory'
```

## Security Notes

⚠️ **IMPORTANT**: This setup is for internal network use only

- VNC server runs without password (SecurityTypes None)
- Only accessible from AutoBot internal network (172.16.168.x)
- Do NOT expose VNC ports (5901, 6080) to public internet
- Consider VPN/SSH tunnel for remote access

## Future Improvements

- [ ] Add VNC password protection
- [ ] Implement session recording
- [ ] Add multiple browser profiles
- [ ] Browser tab isolation per chat session
- [ ] Performance optimizations for video streaming
- [ ] Clipboard integration between frontend and VNC
- [ ] Multi-user collaborative sessions

## Related Documentation

- [Infrastructure Deployment Guide](../developer/INFRASTRUCTURE_DEPLOYMENT.md)
- [Service Discovery Configuration](../developer/SERVICE_DISCOVERY.md)
- [Playwright Integration](../developer/PLAYWRIGHT_INTEGRATION.md)
- [Network Constants](../developer/NETWORK_CONSTANTS.md)

---

**Status**: ✅ Deployed and operational
**Last Updated**: 2025-11-14
**Maintainer**: AutoBot Infrastructure Team
