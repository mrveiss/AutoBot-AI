# Windows NPU Worker - Network Information Display Feature

## Overview

Enhanced the Windows NPU Worker to automatically display comprehensive network connection information on startup and provide a dedicated GUI panel for easy backend integration.

## Implementation Date

October 4, 2025

## Components Added

### 1. Network Information Utility Module

**File:** `gui/utils/network_info.py`

**Features:**
- Detects all network interfaces with IP addresses
- Filters out loopback and invalid interfaces
- Identifies primary interface for backend connectivity
- Platform detection (Windows version, NPU availability)
- ASCII box formatter for console output
- Backend registration configuration generator

**Functions:**
- `get_network_interfaces()` - Returns list of all network interfaces with IPs
- `get_primary_ip()` - Identifies primary IP for backend connectivity
- `get_platform_info()` - Detects OS, NPU hardware, and system details
- `format_connection_info_box()` - Creates ASCII box display
- `get_registration_config()` - Generates backend config snippet

### 2. Console Startup Display

**File:** `app/npu_worker.py`

**Enhancement:** Added `_display_network_info()` method

**Displays on startup:**
```
╔═══════════════════════════════════════════════════════╗
║        AutoBot NPU Worker - Connection Info          ║
╠═══════════════════════════════════════════════════════╣
║ Worker ID:    npu-worker-windows-001                 ║
║ Platform:     Windows 11 (NPU Detected)              ║
║ Port:         8082                                   ║
║                                                       ║
║ Network Interfaces:                                  ║
║   • Ethernet         (eth0): 192.168.1.100 ★         ║
║   • Wi-Fi            (wlan0): 172.16.168.20          ║
║   • WSL Bridge       (vEthernet): 172.16.168.1       ║
║                                                       ║
║ Add to Backend Settings:                             ║
║   URL: http://172.16.168.20:8082                     ║
║                                                       ║
║ Health Check: http://172.16.168.20:8082/health       ║
╚═══════════════════════════════════════════════════════╝
```

**Key Features:**
- Primary interface marked with ★ symbol
- All network interfaces listed with type and name
- Direct registration URL for backend configuration
- Health check endpoint for validation
- Non-blocking startup (continues on error)
- Comprehensive logging of network configuration

### 3. GUI Connection Info Widget

**File:** `gui/widgets/connection_info.py`

**Features:**
- Dedicated "Connection Info" tab in main window
- Worker ID display with copy button
- Platform information (OS, NPU status)
- Network interfaces list with formatting
- Registration URL with copy button
- Health check URL with copy button
- Backend configuration snippet with copy button
- Refresh button to update network info
- Copy-to-clipboard for all key information

**Sections:**
1. **Worker Information**
   - Worker ID (selectable, with copy button)
   - Port number

2. **Platform Information**
   - System (Windows version)
   - NPU Status (detected/not detected with color coding)

3. **Network Interfaces**
   - All interfaces with IP addresses
   - Interface type and name
   - Primary interface marked with ★
   - Copy all network info button

4. **Backend Registration**
   - Registration URL with copy button
   - Health check URL with copy button
   - Complete YAML configuration snippet
   - Copy configuration button

### 4. Main Window Integration

**File:** `gui/windows/main_window.py`

**Changes:**
- Added "Connection Info" tab between Dashboard and Logs
- Auto-updates worker ID and port when metrics received
- Enhanced About dialog with network information
- Shows up to 3 network interfaces in About dialog
- Displays primary IP in About dialog

## Dependencies Added

**Both `requirements.txt` and `requirements-gui.txt`:**
- `netifaces>=0.11.0` - Cross-platform network interface detection

**Fallback Support:**
- If `netifaces` not available, uses `socket` module fallback
- Gracefully handles missing dependencies
- Non-critical errors don't block worker startup

## Usage

### Console Mode (Service)

When starting the NPU worker service:
```bash
python app/npu_worker.py
```

Network information is automatically displayed in console as ASCII box before "Worker initialized" message.

### GUI Mode

1. Launch GUI application
2. Navigate to "Connection Info" tab
3. View all network interfaces and configuration
4. Click copy buttons to copy URLs or configuration to clipboard
5. Use "Refresh Network Info" button to update display

### Backend Integration

**From Console Output:**
1. Start NPU worker
2. Copy registration URL from ASCII box
3. Add to backend NPU worker configuration

**From GUI:**
1. Open "Connection Info" tab
2. Click "Copy Configuration" button
3. Paste into backend `config.yaml` or settings file

**Example Configuration to Add:**
```yaml
# Windows NPU Worker Configuration
# Add this to your backend NPU worker settings

windows_npu_worker:
  enabled: true
  url: http://172.16.168.20:8082
  health_check_interval: 60
  timeout: 30
```

## Network Detection Logic

### Interface Priority

Interfaces are sorted by:
1. Primary interfaces first (★ marked)
2. Alphabetically by interface name

### Primary Interface Detection

An interface is marked as primary if:
- IP is in `192.168.x.x` range (common home/office networks)
- IP is in `172.16.x.x` range (AutoBot VM network)

### Interface Type Detection

Automatically identifies:
- **Ethernet** - Physical wired connections
- **Wi-Fi** - Wireless connections
- **WSL Bridge** - Windows Subsystem for Linux network
- **Docker Bridge** - Docker container networks
- **Virtual** - VMware/VirtualBox adapters
- **Network** - Generic network interfaces

### Fallback Detection

If `netifaces` library unavailable:
1. Uses `socket.gethostname()` to get all IPs
2. Attempts connection to `8.8.8.8` to determine primary interface
3. Filters out loopback addresses (`127.x.x.x`)

## Platform Information

Detects and displays:
- Operating System (Windows, Linux, etc.)
- OS Release (Windows 11, Windows 10, etc.)
- NPU Hardware Availability (via OpenVINO detection)
- NPU Device List (specific NPU devices found)

## Error Handling

- Network detection errors are non-blocking
- Logs warnings if network info unavailable
- Shows "No network interfaces detected" if detection fails
- Worker continues initialization on network info errors
- GUI gracefully handles missing network information

## Testing

### Test Console Display
```bash
python app/npu_worker.py
```
Verify ASCII box appears with:
- Worker ID
- Network interfaces
- Registration URLs

### Test GUI Display
```bash
python gui/main.py
```
1. Navigate to "Connection Info" tab
2. Verify all fields populated
3. Test copy buttons
4. Test refresh button

### Test Without netifaces
```bash
pip uninstall netifaces -y
python app/npu_worker.py
```
Verify fallback detection works

### Test Network Changes
1. Connect/disconnect network interfaces
2. Click "Refresh Network Info" in GUI
3. Verify updated interface list

## Files Modified

1. **Created:**
   - `gui/utils/network_info.py` (332 lines)
   - `gui/widgets/connection_info.py` (282 lines)
   - `NETWORK_INFO_FEATURE.md` (this file)

2. **Modified:**
   - `app/npu_worker.py` - Added network info display
   - `gui/windows/main_window.py` - Added Connection Info tab
   - `requirements.txt` - Added netifaces dependency
   - `requirements-gui.txt` - Added netifaces dependency

## Benefits

1. **Easy Backend Integration**
   - Clear registration URLs provided
   - Copy-to-clipboard functionality
   - Ready-to-use configuration snippets

2. **Network Troubleshooting**
   - See all network interfaces at a glance
   - Identify primary interface for connectivity
   - Verify NPU worker is accessible on network

3. **Multi-Interface Support**
   - Works with Ethernet, Wi-Fi, WSL, Docker bridges
   - Handles multiple IPs on same machine
   - Identifies best interface for backend connectivity

4. **User-Friendly**
   - GUI panel for easy access
   - Copy buttons for all important information
   - Clear visual indicators for primary interface

5. **Production Ready**
   - Non-blocking startup
   - Graceful error handling
   - Fallback detection methods
   - Cross-platform compatible

## Future Enhancements

Potential improvements:
- Auto-register with backend on startup
- Test connectivity to backend from GUI
- QR code generation for easy mobile access
- Network performance testing
- Interface monitoring and alerts
