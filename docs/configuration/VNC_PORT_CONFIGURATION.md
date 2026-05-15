# VNC Port Configuration Guide

AutoBot uses VNC for browser automation and desktop viewing capabilities. This document explains how VNC ports are configured to avoid conflicts between host and container environments.

## Port Usage Overview

### Default Ports
- **Host VNC**: `5900` (Standard VNC port, often used by Kali Linux desktop)
- **Container VNC**: `5901` (Avoids conflict with host VNC)
- **NoVNC Web Interface**: `6080` (Web-based VNC viewer)
- **Playwright API**: `3000` (Browser automation API)

### Environment Variables

| Variable | Purpose | Default | Container | Host |
|----------|---------|---------|-----------|------|
| `AUTOBOT_VNC_DISPLAY_PORT` | Host VNC display port | `5900` | `5900` | `5900` |
| `AUTOBOT_VNC_CONTAINER_PORT` | Container VNC port | `5901` | `5901` | `5901` |
| `AUTOBOT_PLAYWRIGHT_VNC_URL` | NoVNC web interface | `http://localhost:6080/vnc.html` | Same | Same |
| `AUTOBOT_PLAYWRIGHT_API_URL` | Playwright API endpoint | `http://localhost:3000` | Same | Same |

## Intelligent Port Selection

AutoBot automatically detects the appropriate VNC port based on the environment:

### Detection Logic
1. **Container Detection**: Checks for `/.dockerenv` file or `DOCKER_CONTAINER` environment variable
2. **Port Availability**: Tests if port 5900 is already in use
3. **Smart Selection**:
   - If in container → use `VNC_CONTAINER_PORT` (5901)
   - If port 5900 is busy (host VNC active) → use `VNC_CONTAINER_PORT` (5901)
   - Otherwise → use `VNC_DISPLAY_PORT` (5900)

### Usage in Code
```python
from src.config import get_vnc_direct_url, get_vnc_display_port

# Get intelligent VNC connection URL
vnc_url = get_vnc_direct_url()  # Returns vnc://localhost:5900 or vnc://localhost:5901

# Get the selected port number
port = get_vnc_display_port()  # Returns 5900 or 5901
```

## Common Scenarios

### Scenario 1: Kali Host with Desktop VNC
- **Host VNC**: Running on port 5900 (Kali desktop)
- **AutoBot**: Detects port 5900 busy → uses port 5901
- **Result**: `vnc://localhost:5901`

### Scenario 2: Docker Container Deployment
- **Environment**: Container detected via `/.dockerenv`
- **AutoBot**: Uses container port 5901 to avoid host conflicts
- **Result**: `vnc://localhost:5901` (mapped from container)

### Scenario 3: Clean Host Installation
- **Host VNC**: Not running (port 5900 free)
- **AutoBot**: Uses standard port 5900
- **Result**: `vnc://localhost:5900`

### Scenario 4: Custom Port Configuration
```bash
# Override default ports
export AUTOBOT_VNC_DISPLAY_PORT=5902
export AUTOBOT_VNC_CONTAINER_PORT=5903
```

## Browser Integration

### NoVNC Web Access
- **URL**: http://localhost:6080/vnc.html
- **Features**: Browser-based VNC viewer
- **Auto-connect**: `?autoconnect=true&resize=scale`

### Direct VNC Client
- **URL**: `vnc://localhost:{port}` (determined automatically)
- **Clients**: VNC Viewer, TightVNC, RealVNC
- **Protocol**: Standard VNC over TCP

## Troubleshooting

### Port Conflicts
```bash
# Check what's using port 5900
sudo netstat -tlnp | grep :5900

# Check what's using port 5901
sudo netstat -tlnp | grep :5901

# Test AutoBot's port detection
python3 -c "from src.config import get_vnc_display_port; print(f'Selected VNC port: {get_vnc_display_port()}')"
```

### Connection Issues
1. **VNC Service Not Running**: Start the appropriate VNC service
2. **Firewall Blocking**: Allow VNC ports through firewall
3. **Wrong Port**: Check which port AutoBot selected
4. **Container Mapping**: Verify Docker port mappings match configuration

### Docker Port Mapping
```yaml
# docker-compose.yml
services:
  autobot:
    ports:
      - "5901:5901"    # VNC port (container internal)
      - "6080:6080"    # NoVNC web interface
      - "3000:3000"    # Playwright API
```

## Security Considerations

### Network Access
- **Local Only**: Default configuration binds to localhost
- **Remote Access**: Set `AUTOBOT_VNC_HOST=0.0.0.0` to allow remote connections
- **Authentication**: Configure VNC password for security

### Container Isolation
- **Port Mapping**: Container ports are isolated from host
- **Process Isolation**: VNC processes run in container namespace
- **Resource Limits**: Docker resource constraints apply

## Configuration Examples

### Development Environment
```bash
# .env file for development
AUTOBOT_VNC_DISPLAY_PORT=5900
AUTOBOT_VNC_CONTAINER_PORT=5901
AUTOBOT_PLAYWRIGHT_VNC_URL=http://localhost:6080/vnc.html
AUTOBOT_PLAYWRIGHT_API_URL=http://localhost:3000
```

### Production Deployment
```bash
# .env file for production
AUTOBOT_VNC_DISPLAY_PORT=15900
AUTOBOT_VNC_CONTAINER_PORT=15901
AUTOBOT_PLAYWRIGHT_VNC_URL=http://production-host:16080/vnc.html
AUTOBOT_PLAYWRIGHT_API_URL=http://production-host:13000
```

### Multi-Instance Setup
```bash
# Instance 1
AUTOBOT_VNC_DISPLAY_PORT=5900
AUTOBOT_VNC_CONTAINER_PORT=5901

# Instance 2
AUTOBOT_VNC_DISPLAY_PORT=5902
AUTOBOT_VNC_CONTAINER_PORT=5903
```

This intelligent port configuration ensures AutoBot works seamlessly in both host and container environments while avoiding common VNC port conflicts.
