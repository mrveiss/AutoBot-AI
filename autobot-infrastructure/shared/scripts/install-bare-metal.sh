#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Bare-Metal Single-Machine Installer (#2669)
#
# Installs all AutoBot services (backend, SLM, frontend) on a single machine
# using per-service Python venvs to avoid dependency conflicts.
#
# Usage:
#   sudo ./install-bare-metal.sh              # Interactive mode
#   sudo ./install-bare-metal.sh --unattended # Unattended with defaults
#   sudo ./install-bare-metal.sh --help       # Show help

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_VERSION="1.0.0"
INSTALL_DIR="/opt/autobot"
AUTOBOT_USER="autobot"
AUTOBOT_GROUP="autobot"

# Service ports — from network_constants.py SSOT
BACKEND_PORT=8001
SLM_PORT=8000
FRONTEND_PORT=5173
REDIS_PORT=6379
OLLAMA_PORT=11434
CHROMADB_PORT=8100

# Git source
DEFAULT_GIT_REPO="https://github.com/mrveiss/AutoBot-AI.git"
DEFAULT_BRANCH="Dev_new_gui"

# Python version
PYTHON_VERSION="3.14"
PYTHON_BIN="python${PYTHON_VERSION}"

# Runtime variables
UNATTENDED=false
GIT_REPO="${DEFAULT_GIT_REPO}"
GIT_BRANCH="${DEFAULT_BRANCH}"
INSTALL_OLLAMA=true
SKIP_REDIS=false
SKIP_CHROMADB=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# =============================================================================
# Helpers
# =============================================================================

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "\n${BLUE}==>${NC} $*"; }

die() { log_error "$*"; exit 1; }

check_root() {
    [[ $EUID -eq 0 ]] || die "This script must be run as root (sudo)."
}

# =============================================================================
# Argument Parsing
# =============================================================================

show_help() {
    cat <<'HELP'
AutoBot Bare-Metal Single-Machine Installer

Usage:
  sudo ./install-bare-metal.sh [OPTIONS]

Options:
  --unattended          Run with default values, no prompts
  --branch BRANCH       Git branch to install (default: Dev_new_gui)
  --repo URL            Git repository URL
  --no-ollama           Skip Ollama installation
  --skip-redis          Skip Redis installation (use existing)
  --skip-chromadb       Skip ChromaDB installation (use existing)
  --help                Show this help

Services installed:
  - autobot-backend     (port 8001) — main API server
  - autobot-slm         (port 8000) — SLM management backend
  - autobot-frontend    (port 5173) — Vue.js frontend (built to static)
  - nginx               (port 80/443) — reverse proxy
  - redis-server        (port 6379) — data store
  - ollama              (port 11434) — local LLM (optional)

Each Python service gets its own venv under /opt/autobot/<service>/venv
to avoid dependency conflicts between components.
HELP
    exit 0
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --unattended)  UNATTENDED=true; shift ;;
            --branch)      GIT_BRANCH="$2"; shift 2 ;;
            --repo)        GIT_REPO="$2"; shift 2 ;;
            --no-ollama)   INSTALL_OLLAMA=false; shift ;;
            --skip-redis)  SKIP_REDIS=true; shift ;;
            --skip-chromadb) SKIP_CHROMADB=true; shift ;;
            --help|-h)     show_help ;;
            *) die "Unknown option: $1. Use --help for usage." ;;
        esac
    done
}

# =============================================================================
# System Detection
# =============================================================================

detect_system() {
    log_step "Detecting system capabilities"

    # OS
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        log_info "OS: ${PRETTY_NAME:-${ID} ${VERSION_ID}}"
    fi

    # RAM
    TOTAL_RAM_MB=$(awk '/MemTotal/ {printf "%.0f", $2/1024}' /proc/meminfo)
    log_info "RAM: ${TOTAL_RAM_MB} MB"

    if [[ $TOTAL_RAM_MB -lt 4096 ]]; then
        log_warn "Less than 4 GB RAM — Ollama may not work well"
    fi

    # GPU detection
    GPU_DETECTED=false
    if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
        GPU_TYPE="nvidia"
        GPU_DETECTED=true
        GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
        log_info "GPU: ${GPU_NAME} (NVIDIA CUDA)"
    elif [[ -d /dev/dri ]] && command -v clinfo &>/dev/null; then
        GPU_TYPE="intel"
        GPU_DETECTED=true
        log_info "GPU: Intel (OpenCL/OpenVINO)"
    else
        GPU_TYPE="none"
        log_info "GPU: None detected — Ollama will use CPU"
    fi

    # WSL detection
    IS_WSL=false
    if grep -qi microsoft /proc/version 2>/dev/null; then
        IS_WSL=true
        log_info "Environment: WSL2"
    fi

    # Disk space
    AVAIL_GB=$(df -BG "${INSTALL_DIR%/*}" 2>/dev/null | awk 'NR==2{print $4}' | tr -d 'G')
    if [[ -n "$AVAIL_GB" ]] && [[ "$AVAIL_GB" -lt 10 ]]; then
        log_warn "Only ${AVAIL_GB}G disk space available — recommend at least 10G"
    fi
}

# =============================================================================
# Prerequisites
# =============================================================================

install_prerequisites() {
    log_step "Installing system prerequisites"

    apt-get update -qq

    # Core packages
    apt-get install -y -qq \
        software-properties-common \
        curl wget git \
        build-essential \
        nginx \
        jq

    # Python 3.14 via deadsnakes PPA
    if ! command -v "${PYTHON_BIN}" &>/dev/null; then
        log_info "Installing Python ${PYTHON_VERSION} from deadsnakes PPA"
        add-apt-repository -y ppa:deadsnakes/ppa
        apt-get update -qq
        apt-get install -y -qq \
            "${PYTHON_BIN}" \
            "${PYTHON_BIN}-venv" \
            "${PYTHON_BIN}-dev"
    else
        log_info "Python ${PYTHON_VERSION} already installed"
    fi

    # Node.js for frontend build
    if ! command -v node &>/dev/null; then
        log_info "Installing Node.js 20.x"
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
        apt-get install -y -qq nodejs
    fi

    # Redis
    if [[ "$SKIP_REDIS" == false ]]; then
        if ! command -v redis-server &>/dev/null; then
            log_info "Installing Redis"
            apt-get install -y -qq redis-server
        fi
        systemctl enable redis-server
        systemctl start redis-server
    fi
}

# =============================================================================
# Ollama Installation
# =============================================================================

install_ollama() {
    if [[ "$INSTALL_OLLAMA" == false ]]; then
        log_info "Skipping Ollama installation (--no-ollama)"
        return
    fi

    log_step "Installing Ollama"

    if command -v ollama &>/dev/null; then
        log_info "Ollama already installed: $(ollama --version 2>/dev/null || echo 'unknown')"
    else
        curl -fsSL https://ollama.com/install.sh | sh
    fi

    # Pull default models if GPU available or enough RAM
    if [[ "$GPU_DETECTED" == true ]] || [[ "$TOTAL_RAM_MB" -ge 16384 ]]; then
        log_info "Pulling default embedding model..."
        ollama pull nomic-embed-text:latest || log_warn "Failed to pull embedding model"
    else
        log_warn "Skipping model pull — insufficient resources (need GPU or 16GB+ RAM)"
        log_info "Pull models manually: ollama pull nomic-embed-text:latest"
    fi
}

# =============================================================================
# User & Directory Setup
# =============================================================================

setup_directories() {
    log_step "Creating autobot user and directories"

    # Create service user
    if ! id -u "${AUTOBOT_USER}" &>/dev/null; then
        useradd --system --create-home --shell /bin/bash "${AUTOBOT_USER}"
        log_info "Created user: ${AUTOBOT_USER}"
    fi

    # Directory structure
    mkdir -p \
        "${INSTALL_DIR}/code" \
        "${INSTALL_DIR}/backend/venv" \
        "${INSTALL_DIR}/slm/venv" \
        "${INSTALL_DIR}/frontend" \
        "${INSTALL_DIR}/data" \
        "${INSTALL_DIR}/logs"

    chown -R "${AUTOBOT_USER}:${AUTOBOT_GROUP}" "${INSTALL_DIR}"
}

# =============================================================================
# Code Checkout
# =============================================================================

checkout_code() {
    log_step "Cloning AutoBot repository"

    local code_dir="${INSTALL_DIR}/code"

    if [[ -d "${code_dir}/.git" ]]; then
        log_info "Repository exists — pulling latest"
        sudo -u "${AUTOBOT_USER}" git -C "${code_dir}" fetch origin
        sudo -u "${AUTOBOT_USER}" git -C "${code_dir}" checkout "${GIT_BRANCH}"
        sudo -u "${AUTOBOT_USER}" git -C "${code_dir}" pull --rebase origin "${GIT_BRANCH}"
    else
        sudo -u "${AUTOBOT_USER}" git clone \
            --branch "${GIT_BRANCH}" \
            --depth 1 \
            "${GIT_REPO}" "${code_dir}"
    fi
}

# =============================================================================
# Python Venv Setup (per-service isolation)
# =============================================================================

setup_venv() {
    local service_name="$1"
    local requirements_file="$2"
    local venv_dir="${INSTALL_DIR}/${service_name}/venv"

    log_info "Setting up venv: ${venv_dir}"

    # Create venv
    sudo -u "${AUTOBOT_USER}" "${PYTHON_BIN}" -m venv "${venv_dir}" --clear

    # Upgrade pip
    sudo -u "${AUTOBOT_USER}" "${venv_dir}/bin/pip" install --upgrade pip setuptools wheel -q

    # Install requirements
    sudo -u "${AUTOBOT_USER}" "${venv_dir}/bin/pip" install \
        -r "${requirements_file}" --prefer-binary -q

    log_info "Installed $(${venv_dir}/bin/pip list --format=columns 2>/dev/null | wc -l) packages for ${service_name}"
}

install_backend() {
    log_step "Installing autobot-backend (port ${BACKEND_PORT})"

    local code_dir="${INSTALL_DIR}/code"

    setup_venv "backend" "${code_dir}/autobot-backend/requirements.txt"
}

install_slm() {
    log_step "Installing autobot-slm (port ${SLM_PORT})"

    local code_dir="${INSTALL_DIR}/code"

    setup_venv "slm" "${code_dir}/autobot-slm-backend/requirements.txt"
}

install_chromadb() {
    if [[ "$SKIP_CHROMADB" == true ]]; then
        log_info "Skipping ChromaDB installation (--skip-chromadb)"
        return
    fi

    log_step "Installing ChromaDB (port ${CHROMADB_PORT})"

    local chromadb_dir="${INSTALL_DIR}/chromadb"
    local venv_dir="${chromadb_dir}/venv"
    local data_dir="${chromadb_dir}/data"

    # Directories
    mkdir -p "${chromadb_dir}" "${data_dir}"
    chown -R "${AUTOBOT_USER}:${AUTOBOT_GROUP}" "${chromadb_dir}"

    # Virtual environment + package
    sudo -u "${AUTOBOT_USER}" "${PYTHON_BIN}" -m venv "${venv_dir}" --clear
    sudo -u "${AUTOBOT_USER}" "${venv_dir}/bin/pip" install --upgrade pip -q
    sudo -u "${AUTOBOT_USER}" "${venv_dir}/bin/pip" install "chromadb>=0.5" -q
    log_info "ChromaDB installed: $(${venv_dir}/bin/chroma --version 2>/dev/null || echo 'unknown')"

    # Systemd unit
    cat > /etc/systemd/system/autobot-chromadb.service <<EOF
[Unit]
Description=AutoBot ChromaDB - Vector Database
Documentation=https://github.com/mrveiss/AutoBot-AI
After=network.target

[Service]
Type=simple
User=${AUTOBOT_USER}
Group=${AUTOBOT_GROUP}
WorkingDirectory=${chromadb_dir}
Environment="PYTHONUNBUFFERED=1"
Environment="ANONYMIZED_TELEMETRY=FALSE"
EnvironmentFile=-${INSTALL_DIR}/.env
ExecStart=${venv_dir}/bin/chroma run \\
    --host 127.0.0.1 \\
    --port ${CHROMADB_PORT} \\
    --path ${data_dir}
Restart=on-failure
RestartSec=10
TimeoutStartSec=30
TimeoutStopSec=30
MemoryMax=4G
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=${data_dir}
StandardOutput=journal
StandardError=journal
SyslogIdentifier=autobot-chromadb

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable autobot-chromadb
    log_info "Created and enabled systemd service: autobot-chromadb (port ${CHROMADB_PORT})"
}

# =============================================================================
# Frontend Build
# =============================================================================

build_frontend() {
    log_step "Building frontend"

    local frontend_dir="${INSTALL_DIR}/code/autobot-frontend"

    if [[ ! -d "${frontend_dir}" ]]; then
        log_warn "Frontend directory not found — skipping"
        return
    fi

    cd "${frontend_dir}"
    sudo -u "${AUTOBOT_USER}" npm ci --prefer-offline 2>/dev/null || \
        sudo -u "${AUTOBOT_USER}" npm install
    sudo -u "${AUTOBOT_USER}" npm run build

    # Copy built assets to serve directory
    if [[ -d "dist" ]]; then
        cp -r dist/* "${INSTALL_DIR}/frontend/"
        chown -R "${AUTOBOT_USER}:${AUTOBOT_GROUP}" "${INSTALL_DIR}/frontend/"
        log_info "Frontend built and deployed to ${INSTALL_DIR}/frontend/"
    else
        log_warn "Frontend build did not produce dist/ — check build output"
    fi
}

# =============================================================================
# Environment Configuration
# =============================================================================

generate_env() {
    log_step "Generating environment configuration"

    local env_file="${INSTALL_DIR}/.env"

    if [[ -f "${env_file}" ]]; then
        log_info "Environment file exists — preserving"
        return
    fi

    # Generate secret key
    local secret_key
    secret_key=$(${PYTHON_BIN} -c "import secrets; print(secrets.token_urlsafe(64))")

    cat > "${env_file}" <<EOF
# AutoBot Bare-Metal Configuration
# Generated by install-bare-metal.sh v${SCRIPT_VERSION}
# $(date -Iseconds)

# === Core ===
AUTOBOT_ENVIRONMENT=production
AUTOBOT_DEPLOYMENT_MODE=local
AUTOBOT_SECRET_KEY=${secret_key}

# === Backend (port ${BACKEND_PORT}) ===
AUTOBOT_BACKEND_HOST=127.0.0.1
AUTOBOT_BACKEND_PORT=${BACKEND_PORT}

# === SLM (port ${SLM_PORT}) ===
AUTOBOT_SLM_HOST=127.0.0.1
AUTOBOT_SLM_PORT=${SLM_PORT}

# === Redis ===
AUTOBOT_REDIS_HOST=127.0.0.1
AUTOBOT_REDIS_PORT=${REDIS_PORT}

# === Ollama ===
AUTOBOT_OLLAMA_HOST=127.0.0.1
AUTOBOT_OLLAMA_PORT=${OLLAMA_PORT}
AUTOBOT_OLLAMA_ENDPOINT=http://127.0.0.1:${OLLAMA_PORT}

# === ChromaDB ===
AUTOBOT_CHROMADB_HOST=127.0.0.1
AUTOBOT_CHROMADB_PORT=${CHROMADB_PORT}

# === LLM ===
AUTOBOT_LLM_PROVIDER=ollama
AUTOBOT_DEFAULT_LLM_MODEL=qwen3.5:9b
AUTOBOT_EMBEDDING_MODEL=nomic-embed-text:latest
EOF

    chown "${AUTOBOT_USER}:${AUTOBOT_GROUP}" "${env_file}"
    chmod 600 "${env_file}"
    log_info "Generated ${env_file}"
}

# =============================================================================
# Nginx Reverse Proxy
# =============================================================================

configure_nginx() {
    log_step "Configuring nginx reverse proxy"

    cat > /etc/nginx/sites-available/autobot <<EOF
# AutoBot Bare-Metal Reverse Proxy
# Generated by install-bare-metal.sh v${SCRIPT_VERSION}

upstream backend {
    server 127.0.0.1:${BACKEND_PORT};
}

upstream slm {
    server 127.0.0.1:${SLM_PORT};
}

server {
    listen 80 default_server;
    server_name _;

    # Frontend — static files
    root ${INSTALL_DIR}/frontend;
    index index.html;

    # Backend API
    location /api/ {
        proxy_pass http://backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
    }

    # Backend WebSocket
    location /ws/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 86400s;
    }

    # SLM API
    location /slm/ {
        proxy_pass http://slm/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
    }

    # SPA fallback — serve index.html for client-side routes
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF

    # Enable site
    ln -sfn /etc/nginx/sites-available/autobot /etc/nginx/sites-enabled/autobot

    # Remove default site if present
    rm -f /etc/nginx/sites-enabled/default

    # Test and reload
    nginx -t || die "Nginx configuration test failed"
    systemctl enable nginx
    systemctl reload nginx

    log_info "Nginx configured — http://localhost"
}

# =============================================================================
# Systemd Services
# =============================================================================

create_systemd_service() {
    local service_name="$1"
    local service_port="$2"
    local app_dir="$3"
    local venv_dir="$4"

    cat > "/etc/systemd/system/autobot-${service_name}.service" <<EOF
[Unit]
Description=AutoBot ${service_name}
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=simple
User=${AUTOBOT_USER}
Group=${AUTOBOT_GROUP}
WorkingDirectory=${app_dir}
Environment=PATH=${venv_dir}/bin:/usr/local/bin:/usr/bin
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${venv_dir}/bin/python -m uvicorn main:app \\
    --host 127.0.0.1 --port ${service_port} --workers 1
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=autobot-${service_name}

# Hardening
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=${INSTALL_DIR}
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable "autobot-${service_name}"
    log_info "Created systemd service: autobot-${service_name}"
}

setup_services() {
    log_step "Creating systemd services"

    local code_dir="${INSTALL_DIR}/code"

    create_systemd_service \
        "backend" "${BACKEND_PORT}" \
        "${code_dir}/autobot-backend" \
        "${INSTALL_DIR}/backend/venv"

    create_systemd_service \
        "slm" "${SLM_PORT}" \
        "${code_dir}/autobot-slm-backend" \
        "${INSTALL_DIR}/slm/venv"
}

# =============================================================================
# Resource Tuning
# =============================================================================

tune_resources() {
    log_step "Tuning resources based on available RAM (${TOTAL_RAM_MB} MB)"

    local workers=1

    if [[ $TOTAL_RAM_MB -ge 32768 ]]; then
        workers=4
        log_info "High-memory system — 4 workers per service"
    elif [[ $TOTAL_RAM_MB -ge 16384 ]]; then
        workers=2
        log_info "Standard system — 2 workers per service"
    else
        workers=1
        log_info "Low-memory system — 1 worker per service"
    fi

    # Update worker count in systemd services
    if [[ $workers -gt 1 ]]; then
        for service in backend slm; do
            sed -i "s/--workers 1/--workers ${workers}/" \
                "/etc/systemd/system/autobot-${service}.service"
        done
        systemctl daemon-reload
    fi
}

# =============================================================================
# Start Services
# =============================================================================

start_services() {
    log_step "Starting AutoBot services"

    if [[ "$SKIP_CHROMADB" == false ]]; then
        systemctl start autobot-chromadb
    fi
    systemctl start autobot-backend
    systemctl start autobot-slm

    # Wait for services
    sleep 3

    # Verify
    local all_ok=true
    local services_to_check=(autobot-backend autobot-slm)
    if [[ "$SKIP_CHROMADB" == false ]]; then
        services_to_check=(autobot-chromadb "${services_to_check[@]}")
    fi
    for service in "${services_to_check[@]}"; do
        if systemctl is-active --quiet "${service}"; then
            log_info "${service}: running"
        else
            log_error "${service}: FAILED"
            journalctl -u "${service}" -n 10 --no-pager
            all_ok=false
        fi
    done

    if [[ "$all_ok" == false ]]; then
        log_error "Some services failed to start — check logs above"
    fi
}

# =============================================================================
# Verification
# =============================================================================

verify_installation() {
    log_step "Verifying installation"

    local errors=0

    # Check backend health
    if curl -sf "http://127.0.0.1:${BACKEND_PORT}/api/system/health" >/dev/null 2>&1; then
        log_info "Backend health check: OK"
    else
        log_warn "Backend health check: FAILED (may still be starting)"
        ((errors++)) || true
    fi

    # Check SLM health
    if curl -sf "http://127.0.0.1:${SLM_PORT}/api/health" >/dev/null 2>&1; then
        log_info "SLM health check: OK"
    else
        log_warn "SLM health check: FAILED (may still be starting)"
        ((errors++)) || true
    fi

    # Check nginx
    if curl -sf "http://127.0.0.1/" >/dev/null 2>&1; then
        log_info "Nginx proxy: OK"
    else
        log_warn "Nginx proxy: FAILED"
        ((errors++)) || true
    fi

    # Check Redis
    if redis-cli ping 2>/dev/null | grep -q PONG; then
        log_info "Redis: OK"
    else
        log_warn "Redis: not responding"
        ((errors++)) || true
    fi

    # Check ChromaDB
    if [[ "$SKIP_CHROMADB" == false ]]; then
        if curl -sf "http://127.0.0.1:${CHROMADB_PORT}/api/v1/heartbeat" >/dev/null 2>&1; then
            log_info "ChromaDB: OK"
        else
            log_warn "ChromaDB: not responding (may still be starting)"
            ((errors++)) || true
        fi
    fi

    # Check Ollama
    if [[ "$INSTALL_OLLAMA" == true ]]; then
        if curl -sf "http://127.0.0.1:${OLLAMA_PORT}/api/tags" >/dev/null 2>&1; then
            log_info "Ollama: OK"
        else
            log_warn "Ollama: not responding"
            ((errors++)) || true
        fi
    fi

    return $errors
}

# =============================================================================
# Summary
# =============================================================================

print_summary() {
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  AutoBot Bare-Metal Installation Complete  ${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo "  Services:"
    echo "    Backend:   http://127.0.0.1:${BACKEND_PORT}"
    echo "    SLM:       http://127.0.0.1:${SLM_PORT}"
    echo "    Frontend:  http://127.0.0.1 (via nginx)"
    echo "    Redis:     127.0.0.1:${REDIS_PORT}"
    if [[ "$SKIP_CHROMADB" == false ]]; then
        echo "    ChromaDB:  http://127.0.0.1:${CHROMADB_PORT}"
    fi
    if [[ "$INSTALL_OLLAMA" == true ]]; then
        echo "    Ollama:    http://127.0.0.1:${OLLAMA_PORT}"
    fi
    echo ""
    echo "  Paths:"
    echo "    Code:      ${INSTALL_DIR}/code"
    echo "    Backend:   ${INSTALL_DIR}/backend/venv"
    echo "    SLM:       ${INSTALL_DIR}/slm/venv"
    echo "    Frontend:  ${INSTALL_DIR}/frontend"
    echo "    Env file:  ${INSTALL_DIR}/.env"
    echo "    Logs:      journalctl -u autobot-backend"
    echo ""
    echo "  Management:"
    echo "    sudo systemctl {start|stop|restart} autobot-backend"
    echo "    sudo systemctl {start|stop|restart} autobot-slm"
    echo "    sudo journalctl -u autobot-backend -f"
    echo "    sudo journalctl -u autobot-slm -f"
    echo ""

    if [[ "$GPU_DETECTED" == true ]]; then
        echo -e "  GPU: ${GREEN}${GPU_TYPE}${NC} detected — Ollama will use GPU acceleration"
    else
        echo -e "  GPU: ${YELLOW}None${NC} — Ollama will use CPU (slower inference)"
    fi
    echo ""
}

# =============================================================================
# Main
# =============================================================================

main() {
    parse_args "$@"
    check_root

    echo -e "${BLUE}AutoBot Bare-Metal Installer v${SCRIPT_VERSION}${NC}"
    echo ""

    detect_system
    install_prerequisites
    install_ollama
    setup_directories
    checkout_code
    install_backend
    install_slm
    install_chromadb
    build_frontend
    generate_env
    configure_nginx
    setup_services
    tune_resources
    start_services
    verify_installation || true
    print_summary
}

main "$@"
