#!/bin/bash

# AutoBot VNC Headless Installation Script
# Sets up VNC server with noVNC web interface for headless servers
# Compatible with empty servers without existing desktop systems

set -e

VNC_SCRIPT_VERSION="1.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTOBOT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Default configuration
VNC_DISPLAY=":1"
VNC_PORT="5901"
NOVNC_PORT="6080"
SCREEN_WIDTH="1920"
SCREEN_HEIGHT="1080"
SCREEN_DEPTH="24"
VNC_PASSWORD=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[VNC-SETUP]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[VNC-SETUP]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[VNC-SETUP]${NC} $1"
}

log_error() {
    echo -e "${RED}[VNC-SETUP]${NC} $1"
}

show_usage() {
    cat << EOF
AutoBot VNC Headless Installation Script v${VNC_SCRIPT_VERSION}

Usage: $(basename "$0") [OPTIONS]

OPTIONS:
    --display DISPLAY       VNC display number (default: :1)
    --vnc-port PORT        VNC server port (default: 5901)
    --novnc-port PORT      noVNC web interface port (default: 6080)
    --width WIDTH          Screen width (default: 1920)
    --height HEIGHT        Screen height (default: 1080)
    --depth DEPTH          Color depth (default: 24)
    --password PASSWORD    VNC password (optional, will prompt if not provided)
    --no-password          Disable VNC authentication (NOT recommended)
    --help                 Show this help message

EXAMPLES:
    # Basic installation with default settings
    $(basename "$0")

    # Custom display and ports
    $(basename "$0") --display :2 --vnc-port 5902 --novnc-port 6081

    # Custom screen resolution
    $(basename "$0") --width 1600 --height 900

    # Install without password (insecure)
    $(basename "$0") --no-password

DESCRIPTION:
    This script sets up a complete VNC solution for headless servers:
    - Installs Xvfb (virtual X11 display)
    - Installs and configures TigerVNC server
    - Installs noVNC web interface with websockify
    - Creates systemd services for automatic startup
    - Configures proper security settings

    After installation, access the desktop via:
    - VNC client: localhost:${VNC_PORT}
    - Web browser: http://localhost:${NOVNC_PORT}/vnc.html

EOF
}

# Parse command line arguments
parse_args() {
    local no_password=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --display)
                VNC_DISPLAY="$2"
                shift 2
                ;;
            --vnc-port)
                VNC_PORT="$2"
                shift 2
                ;;
            --novnc-port)
                NOVNC_PORT="$2"
                shift 2
                ;;
            --width)
                SCREEN_WIDTH="$2"
                shift 2
                ;;
            --height)
                SCREEN_HEIGHT="$2"
                shift 2
                ;;
            --depth)
                SCREEN_DEPTH="$2"
                shift 2
                ;;
            --password)
                VNC_PASSWORD="$2"
                shift 2
                ;;
            --no-password)
                no_password=true
                shift
                ;;
            --help)
                show_usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done

    # Prompt for password if not provided and not disabled
    if [[ "$no_password" == "false" && -z "$VNC_PASSWORD" ]]; then
        echo -n "Enter VNC password (6-8 characters): "
        read -s VNC_PASSWORD
        echo

        if [[ ${#VNC_PASSWORD} -lt 6 || ${#VNC_PASSWORD} -gt 8 ]]; then
            log_error "VNC password must be 6-8 characters long"
            exit 1
        fi
    elif [[ "$no_password" == "true" ]]; then
        VNC_PASSWORD=""
        log_warn "VNC authentication disabled - this is insecure!"
    fi
}

# Check if running as root
check_privileges() {
    if [[ $EUID -eq 0 ]]; then
        log_warn "Running as root. This is not recommended for VNC setup."
        log_warn "Consider running as a regular user with sudo privileges."
        sleep 2
    fi
}

# Detect OS and package manager
detect_os() {
    if command -v apt-get &> /dev/null; then
        PACKAGE_MANAGER="apt"
        PKG_UPDATE="apt-get update"
        PKG_INSTALL="apt-get install -y"
    elif command -v yum &> /dev/null; then
        PACKAGE_MANAGER="yum"
        PKG_UPDATE="yum update -y"
        PKG_INSTALL="yum install -y"
    elif command -v dnf &> /dev/null; then
        PACKAGE_MANAGER="dnf"
        PKG_UPDATE="dnf update -y"
        PKG_INSTALL="dnf install -y"
    else
        log_error "Unsupported package manager. This script supports apt, yum, and dnf."
        exit 1
    fi

    log "Detected package manager: $PACKAGE_MANAGER"
}

# Install required packages
install_packages() {
    log "Installing required packages..."

    case $PACKAGE_MANAGER in
        apt)
            sudo $PKG_UPDATE
            sudo $PKG_INSTALL \
                xvfb \
                x11vnc \
                tigervnc-standalone-server \
                tigervnc-common \
                websockify \
                python3-websockify \
                supervisor \
                wget \
                curl \
                net-tools
            ;;
        yum|dnf)
            sudo $PKG_UPDATE
            sudo $PKG_INSTALL \
                xorg-x11-server-Xvfb \
                x11vnc \
                tigervnc-server \
                python3-websockify \
                supervisor \
                wget \
                curl \
                net-tools
            ;;
    esac

    log_success "Required packages installed"
}

# Install noVNC
install_novnc() {
    log "Installing noVNC web interface..."

    local novnc_dir="/opt/novnc"

    # Remove existing installation
    if [[ -d "$novnc_dir" ]]; then
        log "Removing existing noVNC installation..."
        sudo rm -rf "$novnc_dir"
    fi

    # Clone noVNC repository
    sudo git clone https://github.com/novnc/noVNC.git "$novnc_dir" || {
        log_error "Failed to clone noVNC repository"
        exit 1
    }

    # Set proper permissions
    sudo chown -R $USER:$USER "$novnc_dir"
    sudo chmod +x "$novnc_dir/utils/launch.sh"

    log_success "noVNC installed to $novnc_dir"
}

# Configure VNC server
configure_vnc() {
    log "Configuring VNC server..."

    # Create VNC directory
    mkdir -p ~/.vnc

    # Generate VNC config
    cat > ~/.vnc/config << EOF
## AutoBot VNC Configuration
geometry=${SCREEN_WIDTH}x${SCREEN_HEIGHT}
depth=${SCREEN_DEPTH}
desktop=AutoBot-Desktop
dpi=96
alwaysshared=true
nevershared=false
EOF

    # Set VNC password if provided
    if [[ -n "$VNC_PASSWORD" ]]; then
        echo "$VNC_PASSWORD" | vncpasswd -f > ~/.vnc/passwd
        chmod 600 ~/.vnc/passwd
        log "VNC password configured"
    else
        # Configure for no password (SecurityTypes=None)
        echo "SecurityTypes=None" >> ~/.vnc/config
        log_warn "VNC configured without password authentication"
    fi

    log_success "VNC server configured"
}

# Create Xvfb service
create_xvfb_service() {
    log "Creating Xvfb systemd service..."

    local display_num="${VNC_DISPLAY#:}"

    sudo tee /etc/systemd/system/xvfb@.service << EOF
[Unit]
Description=Xvfb Virtual Display %i
After=network.target
Wants=network.target

[Service]
Type=simple
User=$USER
Group=$USER
ExecStart=/usr/bin/Xvfb :%i -screen 0 ${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH} -ac -nolisten tcp -dpi 96
ExecStop=/bin/kill -TERM \$MAINPID
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    # Enable and start Xvfb service
    sudo systemctl daemon-reload
    sudo systemctl enable "xvfb@${display_num}.service"
    sudo systemctl start "xvfb@${display_num}.service"

    log_success "Xvfb service created and started"
}

# Create VNC service
create_vnc_service() {
    log "Creating TigerVNC systemd service..."

    local display_num="${VNC_DISPLAY#:}"

    sudo tee /etc/systemd/system/vncserver@.service << EOF
[Unit]
Description=TigerVNC Server %i
After=xvfb@%i.service
Requires=xvfb@%i.service
Wants=network.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=/home/$USER
ExecStartPre=-/bin/sh -c 'DISPLAY=:%i /usr/bin/vncserver -kill :%i || true'
ExecStart=/usr/bin/vncserver :%i -localhost no -SecurityTypes VncAuth -rfbport ${VNC_PORT}
ExecStop=/usr/bin/vncserver -kill :%i
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    # Enable and start VNC service
    sudo systemctl daemon-reload
    sudo systemctl enable "vncserver@${display_num}.service"
    sudo systemctl start "vncserver@${display_num}.service"

    log_success "VNC service created and started"
}

# Create noVNC service
create_novnc_service() {
    log "Creating noVNC systemd service..."

    sudo tee /etc/systemd/system/novnc.service << EOF
[Unit]
Description=noVNC Web Interface
After=vncserver@1.service
Requires=vncserver@1.service
Wants=network.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=/opt/novnc
ExecStart=/opt/novnc/utils/launch.sh --vnc localhost:${VNC_PORT} --listen ${NOVNC_PORT}
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    # Enable and start noVNC service
    sudo systemctl daemon-reload
    sudo systemctl enable novnc.service
    sudo systemctl start novnc.service

    log_success "noVNC service created and started"
}

# Create desktop environment startup script
create_desktop_startup() {
    log "Creating desktop environment startup script..."

    mkdir -p ~/.vnc

    cat > ~/.vnc/xstartup << 'EOF'
#!/bin/bash
# AutoBot VNC Desktop Startup Script

# Set up environment
export USER="$(whoami)"
export HOME="/home/$USER"

# Start a minimal window manager
if command -v xfce4-session &> /dev/null; then
    exec xfce4-session
elif command -v startlxde &> /dev/null; then
    exec startlxde
elif command -v mate-session &> /dev/null; then
    exec mate-session
elif command -v gnome-session &> /dev/null; then
    exec gnome-session
else
    # Fallback to basic X environment
    xsetroot -solid grey &
    if command -v xterm &> /dev/null; then
        xterm -geometry 120x40+10+10 &
    fi
    if command -v x-window-manager &> /dev/null; then
        exec x-window-manager
    else
        # Ultimate fallback
        exec /bin/bash
    fi
fi
EOF

    chmod +x ~/.vnc/xstartup

    log_success "Desktop startup script created"
}

# Verify installation
verify_installation() {
    log "Verifying VNC installation..."

    local display_num="${VNC_DISPLAY#:}"
    local errors=0

    # Check Xvfb service
    if ! systemctl is-active --quiet "xvfb@${display_num}.service"; then
        log_error "Xvfb service is not running"
        ((errors++))
    else
        log_success "Xvfb service is running"
    fi

    # Check VNC service
    if ! systemctl is-active --quiet "vncserver@${display_num}.service"; then
        log_error "VNC service is not running"
        ((errors++))
    else
        log_success "VNC service is running"
    fi

    # Check noVNC service
    if ! systemctl is-active --quiet novnc.service; then
        log_error "noVNC service is not running"
        ((errors++))
    else
        log_success "noVNC service is running"
    fi

    # Check VNC port
    if ! netstat -ln | grep -q ":${VNC_PORT} "; then
        log_error "VNC port $VNC_PORT is not listening"
        ((errors++))
    else
        log_success "VNC port $VNC_PORT is listening"
    fi

    # Check noVNC port
    if ! netstat -ln | grep -q ":${NOVNC_PORT} "; then
        log_error "noVNC port $NOVNC_PORT is not listening"
        ((errors++))
    else
        log_success "noVNC port $NOVNC_PORT is listening"
    fi

    return $errors
}

# Show connection information
show_connection_info() {
    local display_num="${VNC_DISPLAY#:}"

    cat << EOF

${GREEN}========================================${NC}
${GREEN}    AutoBot VNC Installation Complete   ${NC}
${GREEN}========================================${NC}

${BLUE}Connection Information:${NC}
  Display:        ${VNC_DISPLAY}
  VNC Port:       ${VNC_PORT}
  noVNC Port:     ${NOVNC_PORT}
  Screen Size:    ${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH}

${BLUE}Access Methods:${NC}
  VNC Client:     localhost:${VNC_PORT}
  Web Browser:    http://localhost:${NOVNC_PORT}/vnc.html

${BLUE}Service Management:${NC}
  Start Xvfb:     sudo systemctl start xvfb@${display_num}
  Start VNC:      sudo systemctl start vncserver@${display_num}
  Start noVNC:    sudo systemctl start novnc

  Stop all:       sudo systemctl stop novnc vncserver@${display_num} xvfb@${display_num}
  Status:         sudo systemctl status xvfb@${display_num} vncserver@${display_num} novnc

${BLUE}Troubleshooting:${NC}
  View logs:      journalctl -u xvfb@${display_num} -u vncserver@${display_num} -u novnc -f
  Test display:   DISPLAY=${VNC_DISPLAY} xterm

${YELLOW}Note:${NC} Services are configured to auto-start on boot.

EOF
}

# Main installation function
main() {
    log "Starting AutoBot VNC Headless Installation v${VNC_SCRIPT_VERSION}"

    parse_args "$@"
    check_privileges
    detect_os

    log "Configuration:"
    log "  Display: $VNC_DISPLAY"
    log "  VNC Port: $VNC_PORT"
    log "  noVNC Port: $NOVNC_PORT"
    log "  Resolution: ${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH}"
    log "  Password: $([ -n "$VNC_PASSWORD" ] && echo "Set" || echo "None")"

    echo -n "Continue with installation? [Y/n] "
    read -r confirm
    if [[ "$confirm" =~ ^[Nn] ]]; then
        log "Installation cancelled"
        exit 0
    fi

    install_packages
    install_novnc
    configure_vnc
    create_desktop_startup
    create_xvfb_service
    create_vnc_service
    create_novnc_service

    # Wait for services to start
    sleep 5

    if verify_installation; then
        log_success "VNC installation completed successfully!"
        show_connection_info
    else
        log_error "Installation completed with errors. Check service status:"
        log "  sudo systemctl status xvfb@1 vncserver@1 novnc"
        exit 1
    fi
}

# Run main function with all arguments
main "$@"
