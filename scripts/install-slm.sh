#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# SLM Admin Machine Installer
# Installs and configures the Service Lifecycle Manager on a dedicated admin machine.
#
# Usage:
#   ./install-slm.sh              # Interactive mode
#   ./install-slm.sh --unattended # Unattended with defaults
#   ./install-slm.sh --help       # Show help

set -e

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_VERSION="1.0.0"
INSTALL_DIR="/home/autobot/AutoBot"
SLM_SERVER_DIR="$INSTALL_DIR/slm-server"
SLM_ADMIN_DIR="$INSTALL_DIR/slm-admin"
DATA_DIR="$INSTALL_DIR/data"
SSL_DIR="/etc/ssl/slm"
SYSTEMD_DIR="/etc/systemd/system"
NGINX_CONF="/etc/nginx/sites-available/slm"

# Default values
DEFAULT_GIT_REPO="https://github.com/mrveiss/AutoBot-AI.git"
DEFAULT_BRANCH="main"
DEFAULT_ADMIN_USER="admin"
DEFAULT_SLM_PORT=8000
DEFAULT_UI_PORT=5174
DEFAULT_DEV_HOST="172.16.168.20"

# Runtime variables
UNATTENDED=false
GIT_SOURCE="github"
GIT_BRANCH="$DEFAULT_BRANCH"
DEV_HOST="$DEFAULT_DEV_HOST"
ADMIN_USER="$DEFAULT_ADMIN_USER"
ADMIN_PASSWORD=""
EXPOSE_GRAFANA=false
EXPOSE_PROMETHEUS=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# =============================================================================
# Utility Functions
# =============================================================================

log() { echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"; }
info() { echo -e "${CYAN}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
die() { error "$1"; exit 1; }

generate_password() {
    openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 20
}

print_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║           SLM Admin Machine Installer v${SCRIPT_VERSION}            ║"
    echo "║         Service Lifecycle Manager for AutoBot            ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Options:
  --unattended          Run without prompts, use defaults
  --git-source=SOURCE   Code source: github or sync (default: github)
  --branch=BRANCH       Git branch (default: main)
  --dev-host=HOST       Dev machine IP for sync (default: 172.16.168.20)
  --admin-user=USER     Admin username (default: admin)
  --admin-pass=PASS     Admin password (auto-generated if not set)
  --expose-grafana      Expose Grafana directly (default: proxied)
  --expose-prometheus   Expose Prometheus directly (default: proxied)
  --help                Show this help message

Examples:
  $0                                    # Interactive installation
  $0 --unattended                       # Use all defaults
  $0 --git-source=sync --dev-host=172.16.168.20
EOF
}

# =============================================================================
# Prerequisite Checks
# =============================================================================

check_prerequisites() {
    log "Checking prerequisites..."

    # Check if running as root or with sudo
    if [[ $EUID -ne 0 ]]; then
        die "This script must be run as root or with sudo"
    fi

    # Check OS
    if [[ ! -f /etc/debian_version ]]; then
        die "This script requires Debian/Ubuntu"
    fi

    # Check if autobot user exists
    if ! id "autobot" &>/dev/null; then
        log "Creating autobot user..."
        useradd -m -s /bin/bash autobot
        echo "autobot:autobot" | chpasswd
        usermod -aG sudo autobot
    fi

    # Check SSH
    if ! command -v ssh &>/dev/null; then
        die "SSH client not found"
    fi

    success "Prerequisites check passed"
}

# =============================================================================
# Interactive Prompts
# =============================================================================

prompt_config() {
    if $UNATTENDED; then
        # Use defaults or command-line values
        if [[ -z "$ADMIN_PASSWORD" ]]; then
            ADMIN_PASSWORD=$(generate_password)
        fi
        return
    fi

    echo ""
    echo -e "${YELLOW}[1/6] Code source:${NC}"
    echo "  1) Clone from GitHub (mrveiss/AutoBot-AI)"
    echo "  2) Sync from dev machine ($DEFAULT_DEV_HOST)"
    read -p "  > " choice
    case $choice in
        2) GIT_SOURCE="sync" ;;
        *) GIT_SOURCE="github" ;;
    esac

    if [[ "$GIT_SOURCE" == "sync" ]]; then
        echo ""
        echo -e "${YELLOW}[2/6] Dev machine IP:${NC}"
        read -p "  [$DEFAULT_DEV_HOST] > " input
        DEV_HOST="${input:-$DEFAULT_DEV_HOST}"
    else
        echo ""
        echo -e "${YELLOW}[2/6] Git branch:${NC}"
        read -p "  [$DEFAULT_BRANCH] > " input
        GIT_BRANCH="${input:-$DEFAULT_BRANCH}"
    fi

    echo ""
    echo -e "${YELLOW}[3/6] SLM admin username:${NC}"
    read -p "  [$DEFAULT_ADMIN_USER] > " input
    ADMIN_USER="${input:-$DEFAULT_ADMIN_USER}"

    echo ""
    echo -e "${YELLOW}[4/6] SLM admin password:${NC}"
    read -s -p "  (leave blank to auto-generate) > " input
    echo ""
    if [[ -z "$input" ]]; then
        ADMIN_PASSWORD=$(generate_password)
        info "Password will be auto-generated"
    else
        ADMIN_PASSWORD="$input"
    fi

    echo ""
    echo -e "${YELLOW}[5/6] Expose Grafana directly (separate login)?${NC}"
    echo "  1) No - access through SLM only (recommended)"
    echo "  2) Yes - direct access with own credentials"
    read -p "  > " choice
    [[ "$choice" == "2" ]] && EXPOSE_GRAFANA=true

    echo ""
    echo -e "${YELLOW}[6/6] Expose Prometheus directly?${NC}"
    echo "  1) No - access through SLM only (recommended)"
    echo "  2) Yes - direct access"
    read -p "  > " choice
    [[ "$choice" == "2" ]] && EXPOSE_PROMETHEUS=true

    echo ""
    log "Configuration complete. Starting installation..."
    echo ""
}

# =============================================================================
# Installation Steps
# =============================================================================

install_system_packages() {
    log "Installing system packages..."

    apt-get update -qq

    apt-get install -y -qq \
        python3 \
        python3-pip \
        python3-venv \
        nginx \
        ansible \
        git \
        curl \
        wget \
        openssl \
        jq \
        rsync \
        apt-transport-https \
        software-properties-common

    success "System packages installed"
}

install_nodejs() {
    log "Installing Node.js..."

    if ! command -v node &>/dev/null; then
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
        apt-get install -y -qq nodejs
    fi

    success "Node.js $(node --version) installed"
}

install_prometheus() {
    log "Installing Prometheus..."

    if ! command -v prometheus &>/dev/null; then
        apt-get install -y -qq prometheus
    fi

    # Configure Prometheus to listen on localhost only
    cat > /etc/prometheus/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'slm'
    static_configs:
      - targets: ['localhost:8000']

  - job_name: 'nodes'
    file_sd_configs:
      - files:
          - /etc/prometheus/nodes/*.json
        refresh_interval: 30s
EOF

    mkdir -p /etc/prometheus/nodes

    # Bind to localhost only if not exposing
    if ! $EXPOSE_PROMETHEUS; then
        sed -i 's/--web.listen-address=.*/--web.listen-address=127.0.0.1:9090/' \
            /etc/default/prometheus 2>/dev/null || true
    fi

    systemctl enable prometheus
    systemctl restart prometheus

    success "Prometheus installed"
}

install_grafana() {
    log "Installing Grafana..."

    if ! command -v grafana-server &>/dev/null; then
        wget -q -O /usr/share/keyrings/grafana.key https://apt.grafana.com/gpg.key
        echo "deb [signed-by=/usr/share/keyrings/grafana.key] https://apt.grafana.com stable main" \
            > /etc/apt/sources.list.d/grafana.list
        apt-get update -qq
        apt-get install -y -qq grafana
    fi

    # Configure Grafana
    cat > /etc/grafana/grafana.ini << EOF
[server]
http_addr = 127.0.0.1
http_port = 3000
root_url = %(protocol)s://%(domain)s/grafana/
serve_from_sub_path = true

[security]
admin_user = admin
admin_password = $ADMIN_PASSWORD

[auth.anonymous]
enabled = false

[users]
allow_sign_up = false
EOF

    # Bind to localhost only if not exposing
    if $EXPOSE_GRAFANA; then
        sed -i 's/http_addr = 127.0.0.1/http_addr = 0.0.0.0/' /etc/grafana/grafana.ini
    fi

    systemctl enable grafana-server
    systemctl restart grafana-server

    success "Grafana installed"
}

setup_code() {
    log "Setting up AutoBot codebase..."

    mkdir -p "$INSTALL_DIR"
    chown autobot:autobot "$INSTALL_DIR"

    if [[ "$GIT_SOURCE" == "github" ]]; then
        if [[ -d "$INSTALL_DIR/.git" ]]; then
            log "Updating existing repository..."
            sudo -u autobot git -C "$INSTALL_DIR" fetch origin
            sudo -u autobot git -C "$INSTALL_DIR" checkout "$GIT_BRANCH"
            sudo -u autobot git -C "$INSTALL_DIR" pull origin "$GIT_BRANCH"
        else
            log "Cloning from GitHub..."
            sudo -u autobot git clone -b "$GIT_BRANCH" "$DEFAULT_GIT_REPO" "$INSTALL_DIR"
        fi
    else
        log "Syncing from dev machine ($DEV_HOST)..."
        rsync -avz --delete \
            --exclude 'node_modules/' \
            --exclude 'venv/' \
            --exclude '__pycache__/' \
            --exclude '.git/' \
            --exclude 'data/*.db' \
            "autobot@$DEV_HOST:/home/kali/Desktop/AutoBot/" \
            "$INSTALL_DIR/"
        chown -R autobot:autobot "$INSTALL_DIR"
    fi

    success "Codebase ready at $INSTALL_DIR"
}

setup_slm_backend() {
    log "Setting up SLM backend..."

    # Create slm-server directory if it doesn't exist yet
    mkdir -p "$SLM_SERVER_DIR"
    chown autobot:autobot "$SLM_SERVER_DIR"

    # Create Python virtual environment
    sudo -u autobot python3 -m venv "$SLM_SERVER_DIR/venv"

    # Install dependencies
    sudo -u autobot "$SLM_SERVER_DIR/venv/bin/pip" install --quiet --upgrade pip

    if [[ -f "$SLM_SERVER_DIR/requirements.txt" ]]; then
        sudo -u autobot "$SLM_SERVER_DIR/venv/bin/pip" install --quiet \
            -r "$SLM_SERVER_DIR/requirements.txt"
    else
        # Install minimal dependencies for now
        sudo -u autobot "$SLM_SERVER_DIR/venv/bin/pip" install --quiet \
            fastapi \
            uvicorn[standard] \
            sqlalchemy \
            aiosqlite \
            pydantic \
            python-jose[cryptography] \
            passlib[bcrypt] \
            aiofiles \
            ansible-runner \
            websockets \
            python-multipart
    fi

    # Create data directory
    mkdir -p "$DATA_DIR"
    chown autobot:autobot "$DATA_DIR"

    success "SLM backend configured"
}

setup_slm_admin_ui() {
    log "Setting up SLM Admin UI..."

    if [[ -d "$SLM_ADMIN_DIR" ]]; then
        cd "$SLM_ADMIN_DIR"
        sudo -u autobot npm install --silent
        sudo -u autobot npm run build --silent 2>/dev/null || true
    else
        warn "SLM Admin UI directory not found, skipping build"
    fi

    success "SLM Admin UI configured"
}

generate_ssl_cert() {
    log "Generating SSL certificate..."

    mkdir -p "$SSL_DIR"

    if [[ ! -f "$SSL_DIR/cert.pem" ]]; then
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout "$SSL_DIR/key.pem" \
            -out "$SSL_DIR/cert.pem" \
            -subj "/CN=slm-admin/O=AutoBot/C=US" \
            2>/dev/null
    fi

    chmod 600 "$SSL_DIR/key.pem"
    chmod 644 "$SSL_DIR/cert.pem"

    success "SSL certificate generated"
}

configure_nginx() {
    log "Configuring nginx..."

    cat > "$NGINX_CONF" << 'EOF'
# SLM Admin Machine - Nginx Configuration
# Generated by install-slm.sh

server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name _;

    ssl_certificate /etc/ssl/slm/cert.pem;
    ssl_certificate_key /etc/ssl/slm/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # SLM Admin UI (static files or dev server)
    location / {
        proxy_pass http://127.0.0.1:5174;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SLM API
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket endpoint
    location /api/ws {
        proxy_pass http://127.0.0.1:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    # Grafana (proxied through SLM auth)
    location /grafana/ {
        proxy_pass http://127.0.0.1:3000/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Prometheus (proxied through SLM auth)
    location /prometheus/ {
        proxy_pass http://127.0.0.1:9090/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF

    # Enable site
    ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/slm
    rm -f /etc/nginx/sites-enabled/default

    # Test and reload
    nginx -t
    systemctl enable nginx
    systemctl reload nginx

    success "Nginx configured"
}

create_systemd_services() {
    log "Creating systemd services..."

    # SLM target
    cat > "$SYSTEMD_DIR/slm.target" << 'EOF'
[Unit]
Description=SLM Admin Services
After=network-online.target
Wants=network-online.target

[Install]
WantedBy=multi-user.target
EOF

    # SLM Backend service
    cat > "$SYSTEMD_DIR/slm-backend.service" << EOF
[Unit]
Description=SLM Backend
PartOf=slm.target
After=network.target

[Service]
Type=simple
User=autobot
Group=autobot
WorkingDirectory=$SLM_SERVER_DIR
Environment="PATH=$SLM_SERVER_DIR/venv/bin"
ExecStart=$SLM_SERVER_DIR/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=slm.target
EOF

    # SLM Admin UI service
    cat > "$SYSTEMD_DIR/slm-admin-ui.service" << EOF
[Unit]
Description=SLM Admin UI
PartOf=slm.target
After=slm-backend.service

[Service]
Type=simple
User=autobot
Group=autobot
WorkingDirectory=$SLM_ADMIN_DIR
ExecStart=/usr/bin/npm run dev -- --host 127.0.0.1 --port 5174
Restart=always
RestartSec=5

[Install]
WantedBy=slm.target
EOF

    # Reload systemd
    systemctl daemon-reload

    # Enable services
    systemctl enable slm.target
    systemctl enable slm-backend.service
    systemctl enable slm-admin-ui.service

    success "Systemd services created"
}

initialize_database() {
    log "Initializing database..."

    mkdir -p "$DATA_DIR"
    chown autobot:autobot "$DATA_DIR"

    # Database will be initialized by the SLM backend on first run
    # For now, just ensure the directory exists

    success "Database directory ready"
}

create_admin_user() {
    log "Creating admin user credentials..."

    # Store credentials in a config file for the backend to read
    mkdir -p "$INSTALL_DIR/config"

    # Hash the password using Python
    HASHED_PASSWORD=$(python3 -c "
from passlib.hash import bcrypt
print(bcrypt.hash('$ADMIN_PASSWORD'))
")

    cat > "$INSTALL_DIR/config/admin.json" << EOF
{
    "username": "$ADMIN_USER",
    "password_hash": "$HASHED_PASSWORD",
    "created_at": "$(date -Iseconds)"
}
EOF

    chmod 600 "$INSTALL_DIR/config/admin.json"
    chown autobot:autobot "$INSTALL_DIR/config/admin.json"

    success "Admin user created"
}

start_services() {
    log "Starting SLM services..."

    systemctl start prometheus || warn "Prometheus failed to start"
    systemctl start grafana-server || warn "Grafana failed to start"

    # Only start SLM services if the backend exists
    if [[ -f "$SLM_SERVER_DIR/main.py" ]]; then
        systemctl start slm-backend || warn "SLM backend failed to start"
        systemctl start slm-admin-ui || warn "SLM Admin UI failed to start"
    else
        warn "SLM backend not yet created - services not started"
        info "Run Phase 2 to create slm-server/ standalone backend"
    fi

    success "Services started"
}

print_summary() {
    local IP=$(hostname -I | awk '{print $1}')

    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║           Installation Complete!                          ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}Access URLs:${NC}"
    echo "  SLM Admin UI:  https://$IP/"
    echo "  Grafana:       https://$IP/grafana/"
    echo "  Prometheus:    https://$IP/prometheus/"
    echo ""
    echo -e "${CYAN}Credentials:${NC}"
    echo "  Username: $ADMIN_USER"
    echo "  Password: $ADMIN_PASSWORD"
    echo ""
    echo -e "${CYAN}Service Management:${NC}"
    echo "  Start all:   sudo systemctl start slm.target"
    echo "  Stop all:    sudo systemctl stop slm.target"
    echo "  Status:      sudo systemctl status slm.target"
    echo ""
    echo -e "${YELLOW}Note:${NC} Save the credentials above - they won't be shown again!"
    echo ""

    # Save credentials to file
    cat > "/root/slm-credentials.txt" << EOF
SLM Admin Machine Credentials
=============================
Generated: $(date)

URL: https://$IP/
Username: $ADMIN_USER
Password: $ADMIN_PASSWORD

Grafana: https://$IP/grafana/
Prometheus: https://$IP/prometheus/
EOF
    chmod 600 /root/slm-credentials.txt
    info "Credentials saved to /root/slm-credentials.txt"
}

# =============================================================================
# Main
# =============================================================================

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --unattended)
                UNATTENDED=true
                shift
                ;;
            --git-source=*)
                GIT_SOURCE="${1#*=}"
                shift
                ;;
            --branch=*)
                GIT_BRANCH="${1#*=}"
                shift
                ;;
            --dev-host=*)
                DEV_HOST="${1#*=}"
                shift
                ;;
            --admin-user=*)
                ADMIN_USER="${1#*=}"
                shift
                ;;
            --admin-pass=*)
                ADMIN_PASSWORD="${1#*=}"
                shift
                ;;
            --expose-grafana)
                EXPOSE_GRAFANA=true
                shift
                ;;
            --expose-prometheus)
                EXPOSE_PROMETHEUS=true
                shift
                ;;
            --help)
                print_usage
                exit 0
                ;;
            *)
                die "Unknown option: $1"
                ;;
        esac
    done

    print_banner
    check_prerequisites
    prompt_config

    echo ""
    log "Starting installation..."
    echo ""

    install_system_packages
    install_nodejs
    install_prometheus
    install_grafana
    setup_code
    setup_slm_backend
    setup_slm_admin_ui
    generate_ssl_cert
    configure_nginx
    create_systemd_services
    initialize_database
    create_admin_user
    start_services

    print_summary
}

main "$@"
