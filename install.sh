#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# AutoBot Install Script (Issue #1294)
# Virtualmin-style single installer that deploys SLM and all dependencies.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/mrveiss/AutoBot-AI/main/install.sh | bash
#   # OR after cloning:
#   sudo ./install.sh
#   sudo ./install.sh --unattended
#   sudo ./install.sh --reinstall
#   sudo ./install.sh --help

set -euo pipefail

# =============================================================================
# Constants
# =============================================================================

readonly SCRIPT_VERSION="1.0.0"
readonly INSTALL_MARKER="/opt/autobot/.autobot-installed"
readonly LOG_DIR="/var/log/autobot"
readonly LOG_FILE="${LOG_DIR}/install-$(date +%Y%m%d-%H%M%S).log"
readonly AUTOBOT_BASE="/opt/autobot"
readonly CODE_SOURCE="${AUTOBOT_BASE}/code_source"
readonly SECRETS_FILE="/etc/autobot/slm-secrets.env"
readonly DEFAULT_REPO="https://github.com/mrveiss/AutoBot-AI.git"
readonly DEFAULT_BRANCH="Dev_new_gui"
readonly REQUIRED_DISK_MB=5120
readonly REQUIRED_MEM_MB=2048

# Runtime flags
UNATTENDED=false
REINSTALL=false
GIT_BRANCH="${DEFAULT_BRANCH}"
ADMIN_PASSWORD=""

# Phase tracking
TOTAL_PHASES=6
CURRENT_PHASE=0

# Colors
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly PURPLE='\033[0;35m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'

# =============================================================================
# Logging
# =============================================================================

_log_init() {
    mkdir -p "${LOG_DIR}"
    if [[ -f "${LOG_FILE}" ]]; then
        mv "${LOG_FILE}" "${LOG_FILE}.$(date +%s)"
    fi
    touch "${LOG_FILE}"
}

log()     { echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $*" | tee -a "${LOG_FILE}"; }
info()    { echo -e "${CYAN}[INFO]${NC} $*" | tee -a "${LOG_FILE}"; }
success() { echo -e "${GREEN}[OK]${NC} $*" | tee -a "${LOG_FILE}"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*" | tee -a "${LOG_FILE}"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" | tee -a "${LOG_FILE}" >&2; }
fatal()   { error "$*"; error "Installation failed. See ${LOG_FILE} for details."; exit 1; }

# Virtualmin-style run_ok: execute with description, log output, fail on error
run_ok() {
    local desc="$1"
    shift
    log "  ${desc}..."
    if "$@" >> "${LOG_FILE}" 2>&1; then
        success "  ${desc}"
        return 0
    else
        local code=$?
        error "  FAILED: ${desc} (exit ${code})"
        error "  Command: $*"
        error "  See ${LOG_FILE} for details"
        return $code
    fi
}

# =============================================================================
# Phase Progress
# =============================================================================

phase() {
    CURRENT_PHASE=$((CURRENT_PHASE + 1))
    echo
    echo -e "${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${PURPLE}  [${CURRENT_PHASE}/${TOTAL_PHASES}] $*${NC}"
    echo -e "${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo
}

# =============================================================================
# Banner & Usage
# =============================================================================

print_banner() {
    echo -e "${CYAN}"
    cat << 'BANNER'
     _         _        ____        _
    / \  _   _| |_ ___ | __ )  ___ | |_
   / _ \| | | | __/ _ \|  _ \ / _ \| __|
  / ___ \ |_| | || (_) | |_) | (_) | |_
 /_/   \_\__,_|\__\___/|____/ \___/ \__|

BANNER
    echo -e "  AutoBot Installer v${SCRIPT_VERSION}"
    echo -e "  Service Lifecycle Manager${NC}"
    echo
}

print_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Installs AutoBot SLM (Service Lifecycle Manager) on a blank Debian/Ubuntu host.
After installation, use the SLM web UI setup wizard to add fleet nodes.

Options:
  --unattended          Run without prompts, use all defaults
  --reinstall           Force reinstall over existing installation
  --branch=BRANCH       Git branch to install (default: ${DEFAULT_BRANCH})
  --admin-pass=PASS     SLM admin password (auto-generated if not set)
  --help                Show this help message

Examples:
  sudo $0                                    # Interactive install
  sudo $0 --unattended                       # Default unattended install
  sudo $0 --unattended --admin-pass=MyPass   # Unattended with custom password
  sudo $0 --reinstall                        # Reinstall over existing

Post-Install:
  1. Open https://<server-ip> in a browser
  2. Log in with the admin credentials shown at the end
  3. Follow the Setup Wizard to add and configure fleet nodes

EOF
}

# =============================================================================
# Phase 1: Pre-flight Checks
# =============================================================================

preflight_checks() {
    phase "Pre-flight Checks"

    if [[ $EUID -ne 0 ]]; then
        fatal "This script must be run as root (use sudo)"
    fi
    success "Running as root"

    if [[ ! -f /etc/debian_version ]]; then
        fatal "This script requires Debian or Ubuntu"
    fi
    local os_name
    os_name=$(. /etc/os-release 2>/dev/null && echo "${NAME} ${VERSION_ID}" || cat /etc/debian_version)
    success "OS: ${os_name}"

    if [[ -f "${INSTALL_MARKER}" ]] && [[ "${REINSTALL}" != true ]]; then
        local installed_at
        installed_at=$(cat "${INSTALL_MARKER}")
        warn "AutoBot already installed (${installed_at})"
        warn "Use --reinstall to force reinstall"
        exit 100
    fi

    local available_mb
    available_mb=$(df -m /opt 2>/dev/null | awk 'NR==2{print $4}')
    if [[ -z "${available_mb}" ]]; then
        available_mb=$(df -m / | awk 'NR==2{print $4}')
    fi
    if [[ "${available_mb}" -lt "${REQUIRED_DISK_MB}" ]]; then
        fatal "Insufficient disk space: ${available_mb}MB available, ${REQUIRED_DISK_MB}MB required"
    fi
    success "Disk space: ${available_mb}MB available"

    local total_mem_mb
    total_mem_mb=$(free -m | awk '/^Mem:/{print $2}')
    if [[ "${total_mem_mb}" -lt "${REQUIRED_MEM_MB}" ]]; then
        fatal "Insufficient memory: ${total_mem_mb}MB available, ${REQUIRED_MEM_MB}MB required"
    fi
    success "Memory: ${total_mem_mb}MB total"

    if ! curl -sf --max-time 5 https://github.com > /dev/null 2>&1; then
        if ! curl -sf --max-time 5 https://deb.nodesource.com > /dev/null 2>&1; then
            fatal "No internet connectivity (cannot reach github.com or deb.nodesource.com)"
        fi
    fi
    success "Internet connectivity OK"

    for cmd in curl apt-get; do
        if ! command -v "${cmd}" &>/dev/null; then
            fatal "Required command not found: ${cmd}"
        fi
    done
    success "Required commands available"
}

# =============================================================================
# Phase 2: System Setup
# =============================================================================

system_setup() {
    phase "System Setup"

    run_ok "Updating package lists" \
        apt-get update -qq

    run_ok "Installing base packages" \
        env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
            -o Dpkg::Options::="--force-confold" \
            python3 python3-pip python3-venv \
            git curl wget openssl jq rsync sshpass \
            nginx \
            software-properties-common apt-transport-https \
            ca-certificates gnupg build-essential \
            libpq-dev

    if ! command -v ansible-playbook &>/dev/null; then
        run_ok "Adding Ansible PPA" \
            apt-add-repository -y ppa:ansible/ansible
        run_ok "Updating package lists (Ansible)" \
            apt-get update -qq
        run_ok "Installing Ansible" \
            env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ansible
    else
        success "  Ansible already installed ($(ansible --version | head -1))"
    fi

    if ! command -v node &>/dev/null; then
        run_ok "Adding NodeSource repository" \
            bash -c 'curl -fsSL https://deb.nodesource.com/setup_20.x | bash -'
        run_ok "Installing Node.js" \
            env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nodejs
    else
        success "  Node.js already installed ($(node --version))"
    fi

    if ! id "autobot" &>/dev/null; then
        run_ok "Creating autobot user" \
            useradd -r -m -s /bin/bash -d /home/autobot autobot
        echo "autobot ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/autobot
        chmod 0440 /etc/sudoers.d/autobot
        success "  Passwordless sudo configured"
    else
        success "  User 'autobot' already exists"
    fi

    run_ok "Creating directory structure" \
        mkdir -p \
            "${AUTOBOT_BASE}" \
            "${AUTOBOT_BASE}/logs" \
            "${AUTOBOT_BASE}/certs" \
            "${AUTOBOT_BASE}/nginx/certs" \
            "${AUTOBOT_BASE}/cache" \
            "${LOG_DIR}" \
            /etc/autobot

    chown -R autobot:autobot "${AUTOBOT_BASE}"
    success "  Directory ownership set"

    local ssh_key="/home/autobot/.ssh/autobot_key"
    if [[ ! -f "${ssh_key}" ]]; then
        run_ok "Generating SSH key pair for fleet management" \
            sudo -u autobot bash -c "mkdir -p /home/autobot/.ssh && ssh-keygen -t ed25519 -f ${ssh_key} -N '' -C 'autobot@slm'"
    else
        success "  SSH key pair already exists"
    fi
}

# =============================================================================
# Phase 3: Code Deployment
# =============================================================================

code_deployment() {
    phase "Code Deployment"

    if [[ -d "${CODE_SOURCE}/.git" ]]; then
        info "Updating existing repository..."
        run_ok "Fetching latest code" \
            sudo -u autobot git -C "${CODE_SOURCE}" fetch origin
        run_ok "Checking out ${GIT_BRANCH}" \
            sudo -u autobot git -C "${CODE_SOURCE}" checkout "${GIT_BRANCH}"
        run_ok "Pulling latest changes" \
            sudo -u autobot git -C "${CODE_SOURCE}" pull origin "${GIT_BRANCH}"
    else
        run_ok "Cloning AutoBot repository (branch: ${GIT_BRANCH})" \
            sudo -u autobot git clone -b "${GIT_BRANCH}" "${DEFAULT_REPO}" "${CODE_SOURCE}"
    fi

    if [[ ! -L "${CODE_SOURCE}/autobot_shared" ]]; then
        run_ok "Creating autobot_shared symlink" \
            sudo -u autobot ln -sf autobot-shared "${CODE_SOURCE}/autobot_shared"
    fi

    # Copy code from code_source to service directories where Ansible expects them
    info "Distributing code to service directories..."
    local dirs_to_copy=(
        "autobot-slm-backend"
        "autobot-slm-frontend"
        "autobot-shared"
        "autobot-infrastructure"
    )
    for dir in "${dirs_to_copy[@]}"; do
        if [[ -d "${CODE_SOURCE}/${dir}" ]]; then
            run_ok "Copying ${dir} to ${AUTOBOT_BASE}/${dir}" \
                sudo -u autobot rsync -a --delete "${CODE_SOURCE}/${dir}/" "${AUTOBOT_BASE}/${dir}/"
        else
            warn "${dir} not found in code source — skipping"
        fi
    done

    # Ensure autobot_shared symlink exists in backend dir
    if [[ ! -L "${AUTOBOT_BASE}/autobot-slm-backend/autobot_shared" ]]; then
        run_ok "Creating autobot_shared symlink in backend" \
            sudo -u autobot ln -sf ../autobot-shared "${AUTOBOT_BASE}/autobot-slm-backend/autobot_shared"
    fi

    success "Codebase ready at ${CODE_SOURCE}"
}

# =============================================================================
# Phase 4: Ansible Deployment
# =============================================================================

ansible_deployment() {
    phase "Ansible Deployment (SLM Stack)"

    local ansible_dir="${CODE_SOURCE}/autobot-slm-backend/ansible"
    local inventory="${ansible_dir}/inventory/localhost.yml"

    info "Generating localhost inventory..."
    cat > "${inventory}" << 'INVENTORY'
# AutoBot localhost inventory for self-deploy (Issue #1294)
all:
  hosts:
    00-SLM-Manager:
      ansible_connection: local
      ansible_host: 127.0.0.1
      ansible_python_interpreter: /usr/bin/python3
      slm_node_id: "00-SLM-Manager"
      node_role: "slm-manager"
  children:
    slm_server:
      hosts:
        00-SLM-Manager:
INVENTORY
    success "  Localhost inventory generated"

    if [[ -z "${ADMIN_PASSWORD}" ]]; then
        ADMIN_PASSWORD=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 20)
    fi

    if [[ ! -f "${SECRETS_FILE}" ]] || [[ "${REINSTALL}" == true ]]; then
        info "Writing secrets file..."
        local secret_key encryption_key
        secret_key=$(openssl rand -hex 32)
        encryption_key=$(openssl rand -hex 32)
        cat > "${SECRETS_FILE}" << EOF
SLM_SECRET_KEY=${secret_key}
SLM_ENCRYPTION_KEY=${encryption_key}
SLM_ADMIN_PASSWORD=${ADMIN_PASSWORD}
EOF
        chmod 600 "${SECRETS_FILE}"
        success "  Secrets written to ${SECRETS_FILE}"
    else
        ADMIN_PASSWORD=$(grep -oP 'SLM_ADMIN_PASSWORD=\K.*' "${SECRETS_FILE}" 2>/dev/null || echo "${ADMIN_PASSWORD}")
        success "  Secrets file already exists (preserved)"
    fi

    info "Running Ansible deployment (this may take several minutes)..."
    log "  Playbook: deploy-slm-manager.yml --skip-tags seed,provision"

    cd "${ansible_dir}"
    if ansible-playbook \
        -i "${inventory}" \
        playbooks/deploy-slm-manager.yml \
        --skip-tags "seed,provision" \
        -e "slm_admin_password=${ADMIN_PASSWORD}" \
        -e "target_host=localhost" \
        >> "${LOG_FILE}" 2>&1; then
        success "Ansible deployment completed"
    else
        error "Ansible deployment failed"
        error "Check ${LOG_FILE} for details"
        error "Re-run: cd ${ansible_dir} && ansible-playbook -i ${inventory} playbooks/deploy-slm-manager.yml --skip-tags seed,provision"
        exit 1
    fi
}

# =============================================================================
# Phase 5: Service Verification
# =============================================================================

service_verification() {
    phase "Service Verification"

    if systemctl is-active --quiet postgresql; then
        success "PostgreSQL is running"
    else
        warn "PostgreSQL not running — attempting start"
        systemctl start postgresql || fatal "Cannot start PostgreSQL"
    fi

    if systemctl is-active --quiet autobot-slm-backend; then
        success "SLM backend service is running"
    else
        warn "SLM backend not running — attempting start"
        systemctl start autobot-slm-backend || fatal "Cannot start SLM backend"
    fi

    if systemctl is-active --quiet nginx; then
        success "nginx is running"
    else
        warn "nginx not running — attempting start"
        nginx -t >> "${LOG_FILE}" 2>&1 || fatal "nginx config test failed"
        systemctl start nginx || fatal "Cannot start nginx"
    fi

    info "Waiting for SLM backend to be ready (up to ~7 minutes)..."
    local max_attempts=80
    local attempt=0
    while [[ ${attempt} -lt ${max_attempts} ]]; do
        if curl -sf --max-time 3 http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
            success "SLM backend health check passed"
            break
        fi
        attempt=$((attempt + 1))
        log "  Waiting for SLM backend (attempt ${attempt}/${max_attempts})..."
        sleep 5
    done

    if [[ ${attempt} -ge ${max_attempts} ]]; then
        warn "SLM backend did not respond within 7 minutes"
        warn "Check: journalctl -u autobot-slm-backend -n 50"
    fi

    if curl -sfk --max-time 3 https://127.0.0.1/api/health > /dev/null 2>&1; then
        success "HTTPS endpoint accessible"
    else
        warn "HTTPS endpoint not responding (nginx may need time)"
    fi
}

# =============================================================================
# Phase 6: Finalize
# =============================================================================

finalize() {
    phase "Finalize"

    echo "$(date -Iseconds) version=${SCRIPT_VERSION} branch=${GIT_BRANCH}" > "${INSTALL_MARKER}"
    chown autobot:autobot "${INSTALL_MARKER}"
    success "Install marker written"

    local creds_file="/root/autobot-credentials.txt"
    local server_ip
    server_ip=$(hostname -I | awk '{print $1}')
    cat > "${creds_file}" << EOF
AutoBot SLM Credentials
=======================
Generated: $(date)
Server:    ${server_ip}

SLM URL:   https://${server_ip}/
Username:  admin
Password:  ${ADMIN_PASSWORD}

Secrets:   ${SECRETS_FILE}
Logs:      ${LOG_FILE}
Code:      ${CODE_SOURCE}
EOF
    chmod 600 "${creds_file}"
    success "Credentials saved to ${creds_file}"

    echo
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  AutoBot SLM Installation Complete!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo
    echo -e "  ${BLUE}SLM URL:${NC}         https://${server_ip}/"
    echo -e "  ${BLUE}Admin Username:${NC}  admin"
    echo -e "  ${BLUE}Admin Password:${NC}  ${ADMIN_PASSWORD}"
    echo
    echo -e "  ${YELLOW}Note:${NC} Using self-signed certificate — browser will show a warning."
    echo
    echo -e "  ${CYAN}Next Steps:${NC}"
    echo "    1. Open https://${server_ip}/ in your browser"
    echo "    2. Accept the self-signed certificate warning"
    echo "    3. Log in with the admin credentials above"
    echo "    4. Follow the Setup Wizard to add and configure fleet nodes"
    echo
    echo -e "  ${CYAN}Service Management:${NC}"
    echo "    Status:   systemctl status autobot-slm-backend"
    echo "    Restart:  systemctl restart autobot-slm-backend"
    echo "    Logs:     journalctl -u autobot-slm-backend -f"
    echo
    echo -e "  ${CYAN}Reinstall:${NC}  sudo ${CODE_SOURCE}/install.sh --reinstall"
    echo
    echo -e "  Credentials saved to: ${creds_file}"
    echo -e "  Install log: ${LOG_FILE}"
    echo
}

# =============================================================================
# Interactive Prompts
# =============================================================================

prompt_config() {
    if ${UNATTENDED}; then
        if [[ -z "${ADMIN_PASSWORD}" ]]; then
            ADMIN_PASSWORD=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 20)
        fi
        return
    fi

    echo -e "${YELLOW}Configuration:${NC}"
    echo

    echo -e "  ${CYAN}[1/2]${NC} Git branch to install:"
    read -rp "  [${DEFAULT_BRANCH}] > " input
    GIT_BRANCH="${input:-${DEFAULT_BRANCH}}"

    echo
    echo -e "  ${CYAN}[2/2]${NC} SLM admin password:"
    read -rsp "  (leave blank to auto-generate) > " input
    echo
    if [[ -n "${input}" ]]; then
        ADMIN_PASSWORD="${input}"
    else
        ADMIN_PASSWORD=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 20)
        info "  Password will be auto-generated"
    fi
    echo
}

# =============================================================================
# Argument Parsing
# =============================================================================

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --unattended)     UNATTENDED=true;        shift ;;
            --reinstall)      REINSTALL=true;          shift ;;
            --branch=*)       GIT_BRANCH="${1#*=}";    shift ;;
            --admin-pass=*)   ADMIN_PASSWORD="${1#*=}"; shift ;;
            --help|-h)        print_usage; exit 0 ;;
            *)                fatal "Unknown option: $1 (use --help for usage)" ;;
        esac
    done
}

# =============================================================================
# Main
# =============================================================================

main() {
    parse_args "$@"
    _log_init
    print_banner
    log "AutoBot Installer v${SCRIPT_VERSION}"
    log "Log file: ${LOG_FILE}"

    preflight_checks
    prompt_config
    system_setup
    code_deployment
    ansible_deployment
    service_verification
    finalize
}

main "$@"
