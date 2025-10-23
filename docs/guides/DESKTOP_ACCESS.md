# AutoBot Desktop Access via VNC

AutoBot now supports full desktop access through VNC, allowing you to access your Kali Linux desktop remotely via a web browser.

## 🚀 Quick Start

### Launch with Desktop Access
```bash
./run_agent_unified.sh --dev --desktop
```

This will:
- ✅ Start AutoBot frontend on http://localhost:5173
- ✅ Start VNC server with XFCE4 desktop on display :1
- ✅ Start noVNC web client on http://localhost:6080  
- ✅ Auto-open both in browser tabs
- ✅ Use password `autobot` for VNC connection

### Access URLs
- **AutoBot Frontend**: http://localhost:5173
- **Desktop Access**: http://localhost:6080/vnc.html?autoconnect=true&password=autobot
- **Manual Connection**: http://localhost:6080/vnc.html (enter password: `autobot`)

## 🔧 Features

### Smart Browser Management
- **Reuse existing browser** instances instead of launching new ones
- **Auto-open tabs** for both frontend and desktop access
- **Clean shutdown** - closes all opened browsers on Ctrl+C

### Desktop Integration  
- **Full XFCE4 desktop** with all installed applications
- **1920x1080 resolution** with 24-bit color depth
- **Auto-connect** with pre-configured password
- **Optimal settings** for remote scaling and quality

### Process Management
- **Tracked PIDs** for all launched processes
- **Graceful shutdown** with SIGTERM → SIGKILL escalation  
- **Clean cleanup** removes all VNC and browser processes

## 📋 Requirements

**Auto-installed:**
- `websockify` (Python package for VNC-to-WebSocket bridge)
- `noVNC` (HTML5 VNC client, downloaded from GitHub)

**Pre-installed:**
- ✅ `tigervnc-standalone-server` 
- ✅ `python3`
- ✅ `git`
- ✅ `xfce4-session`

## 🎛️ Usage Examples

### Development with Desktop Access
```bash
./run_agent_unified.sh --dev --desktop
# Opens both frontend and desktop in browser
```

### Production with Desktop Access  
```bash
./run_agent_unified.sh --desktop
# Desktop access only, no dev tools
```

### No Auto Browser (Manual Access)
```bash
./run_agent_unified.sh --dev --desktop --no-browser
# Setup VNC but don't auto-open browsers
```

### Clean Shutdown
```bash
# Press Ctrl+C in the terminal
# Automatically stops: Backend, VNC Server, noVNC, Browsers
```

## 🔐 Security

- **Default Password**: `autobot` (stored in `~/.vnc/passwd`)
- **Local Access Only**: VNC server binds to localhost
- **Session Isolation**: Each VNC session runs on separate display (:1)

## 🛠️ Manual Setup (Advanced)

If you need to customize the VNC setup:

```bash
# 1. Create custom VNC password
vncpasswd

# 2. Custom VNC startup script  
nano ~/.vnc/xstartup

# 3. Start VNC with custom settings
vncserver :2 -geometry 1440x900 -depth 16

# 4. Start websockify bridge
cd ~/.novnc
python3 -m websockify 6081 localhost:5902

# 5. Access via browser
open http://localhost:6081/vnc.html
```

## 🎯 Integration

The desktop access integrates seamlessly with AutoBot's existing browser management:

1. **First run**: Launches new browser with two tabs (frontend + desktop)
2. **Subsequent runs**: Opens new tabs in existing browser
3. **Process tracking**: All browser PIDs tracked for clean shutdown
4. **Unified cleanup**: Single Ctrl+C stops everything

This provides a complete development environment where you can:
- Monitor AutoBot frontend with DevTools
- Access full Kali desktop for tool usage
- All within the same browser session
- Clean shutdown with single key combination

Perfect for penetration testing workflows where you need both AutoBot's interface and access to Kali's security tools!