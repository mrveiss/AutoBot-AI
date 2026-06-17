#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
# #9956: Default SLM manager node_id. Must match the host/slm_node_id written
# into the generated localhost inventory (generate_inventory) — that inventory
# is the canonical definition; this constant mirrors it for the API
# registration calls so the value is not duplicated as scattered literals.
readonly SLM_NODE_ID="00-SLM-Manager"
readonly DEFAULT_REPO="https://github.com/mrveiss/AutoBot-AI.git"
readonly DEFAULT_BRANCH="Dev_new_gui"
readonly REQUIRED_DISK_MB=5120
readonly REQUIRED_MEM_MB=2048

# Runtime flags
UNATTENDED=false
REINSTALL=false
UNINSTALL=false
VALIDATE=false
CONFIRM_YES=false
ROTATE_SECRETS=false  # #7075: --rotate-secrets opts in to replacing existing SLM_ADMIN_PASSWORD
GIT_BRANCH="${DEFAULT_BRANCH}"
ADMIN_PASSWORD=""
OVERRIDE_IP=""  # --ip= override for multi-interface hosts (#2832)

# Critical service directories that must be present for a valid deployment (#4130)
readonly CRITICAL_DIRS=(
    "autobot-slm-backend"
    "autobot-slm-frontend"
    "autobot_shared"
    "autobot-infrastructure"
)

# Phase tracking
TOTAL_PHASES=7
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

# add_ppa_if_missing: prefer device-shipped PPA; only add if not already configured (#7144)
#   $1 = ppa spec for apt-add-repository, e.g. "ppa:ansible/ansible"
#   $2 = match string to grep across /etc/apt/sources.list.d/ — typically
#        "<owner>/<name>" (matches both ppa.launchpadcontent.net and the
#        deb822 URIs field). E.g. "ansible/ansible".
#   $3 = friendly description for log lines, e.g. "Ansible".
#
# DGX Spark and similar AI workstation images ship with several PPAs already
# configured (deb822 .sources format with inline GPG key). Re-adding via
# apt-add-repository creates a legacy .list duplicate with mismatched
# Signed-By → apt-get update aborts with E:Conflicting values set for option
# Signed-By. This helper preserves the device-shipped repo and removes any
# stale legacy duplicate left from prior install attempts.
add_ppa_if_missing() {
    local ppa="$1"
    local match="$2"
    local desc="$3"

    if grep -rqsE "${match}" /etc/apt/sources.list.d/ 2>/dev/null; then
        success "  ${desc} PPA already configured (preserving device-shipped repo)"
        # Sweep stale legacy .list duplicates left by prior apt-add-repository runs
        local owner_repo="${ppa#ppa:}"             # ansible/ansible
        local owner="${owner_repo%/*}"             # ansible
        local repo="${owner_repo#*/}"              # ansible
        local stale_list="/etc/apt/sources.list.d/ppa_${owner}_${repo}_*.list"
        # shellcheck disable=SC2086
        for f in ${stale_list}; do
            if [[ -f "${f}" ]] && [[ -f "${f%.list}.sources" ]] || \
               compgen -G "/etc/apt/sources.list.d/${owner}-*-${repo}-*.sources" >/dev/null; then
                rm -f "${f}"
                log "  Removed stale duplicate ${f}"
            fi
        done
        return 0
    fi

    run_ok "Adding ${desc} PPA" \
        apt-add-repository -y "${ppa}"
}

# =============================================================================
# Network Interface Detection (#2832)
# =============================================================================

detect_local_ip() {
    # If OVERRIDE_IP is set, use it directly
    if [[ -n "${OVERRIDE_IP:-}" ]]; then
        echo "${OVERRIDE_IP}"
        return
    fi

    # Cache to a file so the result persists across $() subshell boundaries
    # (#3010). Shell variables set inside $() are lost when the subshell exits,
    # so every $(detect_local_ip) call would re-run the interactive prompt and
    # garble any curl command that interpolates the result.
    # On reinstall, always clear the cache so the interface prompt re-runs
    # and the user can select the correct interface (#3194).
    local cache_file="/tmp/.autobot_detected_ip"
    if [[ "${REINSTALL}" == true ]]; then
        rm -f "${cache_file}"
    fi
    if [[ -f "${cache_file}" ]]; then
        cat "${cache_file}"
        return
    fi

    # Gather all interfaces with IPv4 addresses (exclude loopback)
    local -a ifaces=()
    local -a ips=()
    while IFS= read -r line; do
        local iface ip
        iface=$(echo "$line" | awk '{print $1}')
        ip=$(echo "$line" | awk '{print $2}' | cut -d/ -f1)
        [[ "$ip" == 127.* ]] && continue
        ifaces+=("$iface")
        ips+=("$ip")
    done < <(ip -4 -o addr show | awk '{print $2, $4}')

    local detected_ip=""
    if [[ ${#ips[@]} -eq 0 ]]; then
        fatal "No network interfaces with IPv4 addresses found"
    elif [[ ${#ips[@]} -eq 1 ]]; then
        detected_ip="${ips[0]}"
    elif [[ -n "${AUTOBOT_INSTALL_INTERFACE:-}" ]]; then
        # #7057: env-var override picks the interface by name (e.g. eth2)
        # so the script runs without an interactive prompt
        for i in "${!ifaces[@]}"; do
            if [[ "${ifaces[$i]}" == "${AUTOBOT_INSTALL_INTERFACE}" ]]; then
                detected_ip="${ips[$i]}"
                success "Using ${ifaces[$i]}: ${detected_ip} (AUTOBOT_INSTALL_INTERFACE)" >&2
                break
            fi
        done
        if [[ -z "${detected_ip}" ]]; then
            fatal "AUTOBOT_INSTALL_INTERFACE='${AUTOBOT_INSTALL_INTERFACE}' not found among detected interfaces: ${ifaces[*]}"
        fi
    else
        # Multiple interfaces — ask user to select
        echo -e "\n${YELLOW}  Multiple network interfaces detected:${NC}" >&2
        for i in "${!ifaces[@]}"; do
            echo -e "    ${CYAN}[$((i+1))]${NC} ${ifaces[$i]}: ${ips[$i]}" >&2
        done
        echo -ne "\n  ${YELLOW}Select interface for AutoBot [1-${#ips[@]}]:${NC} " >&2
        local choice
        read -r choice
        choice=$((choice - 1))
        if [[ $choice -lt 0 || $choice -ge ${#ips[@]} ]]; then
            fatal "Invalid selection"
        fi
        detected_ip="${ips[$choice]}"
        success "Using ${ifaces[$choice]}: ${detected_ip}" >&2
    fi

    echo "${detected_ip}" > "${cache_file}"
    echo "${detected_ip}"
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
  --uninstall           Completely remove AutoBot and all dependencies (#2706)
  --validate            Verify installation integrity (check required service distributions)
  --yes                 Skip confirmation prompts (use with --uninstall)
  --branch=BRANCH       Git branch to install (default: ${DEFAULT_BRANCH})
  --admin-pass=PASS     SLM admin password (auto-generated if not set)
  --ip=IP               Override auto-detected IP address (#2832)
  --rotate-secrets      Replace existing SLM_ADMIN_PASSWORD on reinstall (#7075).
                        By default reinstall PRESERVES the wizard-set password
                        and ignores --admin-pass= / AUTOBOT_SLM_ADMIN_PASSWORD.
  --help                Show this help message

Environment overrides (skip the corresponding interactive prompt; #7057):
  AUTOBOT_INSTALL_BRANCH=<branch>     same as --branch=
  AUTOBOT_SLM_ADMIN_PASSWORD=<pass>   same as --admin-pass=
  AUTOBOT_INSTALL_INTERFACE=<iface>   pick an interface by name (eth2, eth0, ...)
                                      instead of the menu prompt
  OVERRIDE_IP=<ip>                    skip detection entirely and use this IP

Examples:
  sudo $0                                    # Interactive install
  sudo $0 --unattended                       # Default unattended install
  sudo $0 --unattended --admin-pass=MyPass   # Unattended with custom password
  sudo $0 --reinstall                        # Reinstall over existing
  sudo $0 --uninstall                        # Full uninstall (with confirmation)
  sudo $0 --uninstall --yes                  # Full uninstall (no prompt)
  sudo AUTOBOT_INSTALL_INTERFACE=eth2 \\
       AUTOBOT_INSTALL_BRANCH=Dev_new_gui \\
       AUTOBOT_SLM_ADMIN_PASSWORD=secret \\
       $0 --reinstall                        # Fully scripted reinstall (#7057)

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

    # pidof fails on WSL2 (can't resolve /proc/1/exe), use ps fallback
    if ! pidof systemd &>/dev/null && [[ "$(ps -p 1 -o comm= 2>/dev/null)" != "systemd" ]]; then
        fatal "systemd is required. On WSL2: add [boot] systemd=true to /etc/wsl.conf and restart WSL"
    fi
    success "systemd is running"

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
            git curl wget openssl jq rsync sshpass openssh-server \
            nginx \
            software-properties-common apt-transport-https \
            ca-certificates gnupg build-essential \
            libpq-dev

    if ! locale -a 2>/dev/null | grep -qi 'en_US\.utf-\?8'; then
        run_ok "Generating en_US.UTF-8 locale" \
            locale-gen en_US.UTF-8
    fi

    # Issue #2705: Python 3.12 required by autobot_shared
    if ! command -v python3.12 &>/dev/null; then
        add_ppa_if_missing "ppa:deadsnakes/ppa" "deadsnakes/ppa" "deadsnakes (Python 3.12)"
        run_ok "Updating package lists (Python 3.12)" \
            apt-get update -qq
        run_ok "Installing Python 3.12" \
            env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
                python3.12 python3.12-venv python3.12-dev
    else
        success "  Python 3.12 already installed ($(python3.12 --version))"
    fi

    if ! command -v ansible-playbook &>/dev/null; then
        add_ppa_if_missing "ppa:ansible/ansible" "ansible/ansible" "Ansible"
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
            /etc/autobot \
            /etc/autobot/ssh

    chown -R autobot:autobot "${AUTOBOT_BASE}"
    success "  Directory ownership set"

    local ssh_key="/home/autobot/.ssh/autobot_key"
    if [[ ! -f "${ssh_key}" ]]; then
        run_ok "Generating SSH key pair for fleet management" \
            sudo -u autobot bash -c "mkdir -p /home/autobot/.ssh && ssh-keygen -t ed25519 -f ${ssh_key} -N '' -C 'autobot@slm'"
    else
        success "  SSH key pair already exists"
    fi

    # Issue #2828: Copy SSH key to shared location for Ansible (#3268: must be
    # autobot:autobot 0600 — SSH client refuses group-readable private keys).
    if [[ -f "${ssh_key}" ]]; then
        cp "${ssh_key}" /etc/autobot/ssh/autobot_key
        cp "${ssh_key}.pub" /etc/autobot/ssh/autobot_key.pub
        chown autobot:autobot /etc/autobot/ssh/autobot_key /etc/autobot/ssh/autobot_key.pub
        chmod 0600 /etc/autobot/ssh/autobot_key
        chmod 0644 /etc/autobot/ssh/autobot_key.pub
        success "  SSH key published to /etc/autobot/ssh/"
    fi
}

# =============================================================================
# Phase 3: Code Deployment
# =============================================================================

code_deployment() {
    phase "Code Deployment"

    if [[ -d "${CODE_SOURCE}/.git" ]]; then
        info "Updating existing repository..."

        # Remove stale git lock files left by prior crashed processes (exit 128 guard)
        local _lock _lf
        for _lock in index config HEAD; do
            _lf="${CODE_SOURCE}/.git/${_lock}.lock"
            if [[ -f "${_lf}" ]]; then
                warn "Removing stale git lock: ${_lf}"
                rm -f "${_lf}"
            fi
        done

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

    # Copy code from code_source to service directories where Ansible expects them
    info "Distributing code to service directories..."
    local missing_dirs=()
    for dir in "${CRITICAL_DIRS[@]}"; do
        if [[ -d "${CODE_SOURCE}/${dir}" ]]; then
            run_ok "Copying ${dir} to ${AUTOBOT_BASE}/${dir}" \
                sudo -u autobot rsync -a --delete "${CODE_SOURCE}/${dir}/" "${AUTOBOT_BASE}/${dir}/"
            if [[ ! -d "${AUTOBOT_BASE}/${dir}" ]]; then
                fatal "Distribution of ${dir} failed — destination directory not created"
            fi
        else
            warn "${dir} not found in code source"
            missing_dirs+=("${dir}")
        fi
    done

    if [[ ${#missing_dirs[@]} -gt 0 ]]; then
        fatal "Required service directories missing from code source: ${missing_dirs[*]}. Cannot proceed with deployment."
    fi

    success "All required service directories distributed successfully"
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
    # The installer sets up the SLM control plane only. User-facing components
    # (backend, frontend, AI stack, browser, etc.) are deployed from the SLM
    # instance via the deployment wizard, where the user selects target nodes.
    cat > "${inventory}" << 'INVENTORY'
# AutoBot SLM-Manager inventory (Issue #1294, #7162)
all:
  vars:
    # #7162: network_subnet/network_gateway/slm_host MUST be defined here so
    # firewall rules in group_vars/slm.yml resolve. Match slm-nodes.yml's
    # lookup-with-fallback pattern: env first, then secrets file, then default.
    slm_host: "{{ lookup('env', 'SLM_HOST') | default(lookup('pipe', 'grep -oP \"SLM_HOST=\\K.*\" /etc/autobot/slm-secrets.env 2>/dev/null || echo 127.0.0.1'), true) }}"
    network_subnet: "{{ lookup('env', 'NETWORK_SUBNET') or lookup('pipe', 'grep -oP \"NETWORK_SUBNET=\\K.*\" /etc/autobot/slm-secrets.env 2>/dev/null') or '0.0.0.0/0' }}"
    network_gateway: "{{ lookup('env', 'NETWORK_GATEWAY') or lookup('pipe', 'grep -oP \"NETWORK_GATEWAY=\\K.*\" /etc/autobot/slm-secrets.env 2>/dev/null') or '0.0.0.0' }}"
  hosts:
    00-SLM-Manager:
      ansible_connection: local
      ansible_host: 127.0.0.1
      ansible_python_interpreter: /usr/bin/python3
      slm_node_id: "00-SLM-Manager"
      node_role: "slm-manager"
      node_roles: []
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
        local secret_key encryption_key local_ip network_subnet network_gateway
        secret_key=$(openssl rand -hex 32)
        encryption_key=$(openssl rand -hex 32)
        # Issue #2758: detect the machine's primary outbound IP so that
        # SLM_EXTERNAL_URL is set correctly and not left to the Python fallback.
        local_ip="$(detect_local_ip)"
        # Detect subnet and gateway from the selected interface so Ansible
        # firewall rules use the correct network range for any installation.
        local cidr
        cidr=$(ip -4 addr show | awk '/inet / {print $2}' | grep "^${local_ip%.*}" | head -1)
        if [[ -n "$cidr" ]]; then
            network_subnet=$(python3 -c "import ipaddress; print(str(ipaddress.ip_interface('$cidr').network))" 2>/dev/null)
        fi
        network_gateway=$(ip route | awk '/^default/ {print $3}' | head -1)
        [[ -z "$network_subnet" ]] && network_subnet="${local_ip%.*}.0/24"
        [[ -z "$network_gateway" ]] && network_gateway="${local_ip%.*}.1"
        cat > "${SECRETS_FILE}" << EOF
SLM_SECRET_KEY=${secret_key}
SLM_ENCRYPTION_KEY=${encryption_key}
SLM_ADMIN_PASSWORD=${ADMIN_PASSWORD}
SLM_EXTERNAL_URL=https://${local_ip}
SLM_HOST=${local_ip}
NETWORK_SUBNET=${network_subnet}
NETWORK_GATEWAY=${network_gateway}
EOF
        chown root:autobot "${SECRETS_FILE}"
        chmod 640 "${SECRETS_FILE}"
        success "  Secrets written to ${SECRETS_FILE}"
    else
        ADMIN_PASSWORD=$(grep -oP 'SLM_ADMIN_PASSWORD=\K.*' "${SECRETS_FILE}" 2>/dev/null || echo "${ADMIN_PASSWORD}")
        # Refresh IP/network fields even when preserving static secrets (#3266).
        # Stale IPs remain when the machine's address changes between installs.
        info "  Refreshing IP/network fields in preserved secrets file..."
        local local_ip network_subnet network_gateway cidr
        local_ip="$(detect_local_ip)"
        cidr=$(ip -4 addr show | awk '/inet / {print $2}' | grep "^${local_ip%.*}" | head -1)
        if [[ -n "$cidr" ]]; then
            network_subnet=$(python3 -c "import ipaddress; print(str(ipaddress.ip_interface('$cidr').network))" 2>/dev/null)
        fi
        network_gateway=$(ip route | awk '/^default/ {print $3}' | head -1)
        [[ -z "$network_subnet" ]] && network_subnet="${local_ip%.*}.0/24"
        [[ -z "$network_gateway" ]] && network_gateway="${local_ip%.*}.1"
        # Upsert each key: replace the line if it exists, append if missing.
        # Plain sed s/// silently does nothing when the key is absent — which
        # causes SLM_HOST / NETWORK_* to stay missing on secrets files written
        # before those keys were introduced (#3194).
        _upsert_secrets_key() {
            local key="$1" value="$2" file="$3"
            if grep -q "^${key}=" "${file}"; then
                sed -i "s|^${key}=.*|${key}=${value}|" "${file}"
            else
                echo "${key}=${value}" >> "${file}"
            fi
        }
        _upsert_secrets_key "SLM_EXTERNAL_URL" "https://${local_ip}" "${SECRETS_FILE}"
        _upsert_secrets_key "SLM_HOST"         "${local_ip}"          "${SECRETS_FILE}"
        _upsert_secrets_key "NETWORK_SUBNET"   "${network_subnet}"    "${SECRETS_FILE}"
        _upsert_secrets_key "NETWORK_GATEWAY"  "${network_gateway}"   "${SECRETS_FILE}"
        success "  Secrets file preserved (IP/network fields updated to ${local_ip})"
    fi

    # Ensure ansible tmp dirs are owned by autobot user (#3298).
    # When install.sh runs ansible as root during bootstrap, these dirs get
    # created as root-owned. Later ansible runs (and become operations) need
    # write access as the autobot user, causing permission denied errors.
    # NOTE (#10006): local_tmp is per-user (~/.ansible/tmp) and no longer
    # pre-created here — a fixed /tmp/ansible_local_tmp locked out every
    # user except whoever created it first.
    mkdir -p /tmp/ansible_fact_cache /tmp/ansible-retry /tmp/.ansible-cp
    chown autobot:autobot /tmp/ansible_fact_cache /tmp/ansible-retry /tmp/.ansible-cp

    info "Running Ansible deployment (this may take several minutes)..."
    # #6600: keep `provision` so backend role applies to the SLM manager node in
    # single-host mode. Skip only `seed` — fleet seeding requires SLM DB
    # rows that don't exist yet on a fresh install.
    log "  Playbook: deploy-slm-manager.yml --skip-tags seed"
    info "  Live progress below — full output also in ${LOG_FILE}"
    echo

    cd "${ansible_dir}"
    set +o pipefail
    ansible-playbook \
        -i "${inventory}" \
        playbooks/deploy-slm-manager.yml \
        --skip-tags "seed" \
        -e "slm_admin_password=${ADMIN_PASSWORD}" \
        -e "target_host=localhost" \
        2>&1 | tee -a "${LOG_FILE}" | \
        grep --line-buffered -E \
            "^(PLAY \[|TASK \[|ok: \[|changed: \[|failed: \[|skipping: \[|fatal:|PLAY RECAP|[A-Za-z0-9_-].*: ok=)"
    _ansible_exit=${PIPESTATUS[0]}
    set -o pipefail

    echo
    if [[ ${_ansible_exit} -eq 0 ]]; then
        success "Ansible deployment completed"
    else
        error "Ansible deployment failed (exit ${_ansible_exit})"
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
# Phase 6: Register Local Node (#2717)
# =============================================================================

register_local_node() {
    phase "Register Local Node"

    local api_url="https://127.0.0.1"

    # Wait for HTTPS to be ready before registering (#2830)
    # After Ansible deployment, nginx may still be loading TLS certificates
    # or the reverse-proxy upstream may not be connected yet.
    info "Waiting for HTTPS endpoint to be ready..."
    local max_wait=60
    local waited=0
    while ! curl -sk --max-time 3 "${api_url}/api/health" >/dev/null 2>&1; do
        sleep 2
        waited=$((waited + 2))
        if [[ ${waited} -ge ${max_wait} ]]; then
            warn "HTTPS not ready after ${max_wait}s — skipping node registration"
            warn "Register manually once services are up: SLM UI > Fleet > Add Node"
            return
        fi
        log "  Waiting for HTTPS (${waited}s / ${max_wait}s)..."
    done
    success "HTTPS endpoint is ready"

    local local_ip
    local_ip="$(detect_local_ip)"
    local hostname_val
    hostname_val=$(hostname)

    # Authenticate
    info "Authenticating with SLM API..."
    local token
    token=$(curl -sfk --max-time 10 \
        -X POST "${api_url}/api/auth/login" \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"admin\",\"password\":\"${ADMIN_PASSWORD}\"}" \
        2>/dev/null | jq -r '.access_token // empty')

    if [[ -z "${token}" ]]; then
        warn "Could not authenticate with SLM API — skipping node registration"
        warn "Register manually: SLM UI > Fleet > Add Node"
        return
    fi
    success "Authenticated with SLM API"

    # Register this node with all single-host roles
    info "Registering local node (${local_ip})..."
    local http_code
    http_code=$(curl -sfk --max-time 10 -o /dev/null -w "%{http_code}" \
        -X POST "${api_url}/api/nodes" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${token}" \
        -d "{
            \"hostname\": \"${hostname_val}\",
            \"ip_address\": \"${local_ip}\",
            \"node_id\": \"${SLM_NODE_ID}\",
            \"roles\": [
                \"slm-backend\",
                \"slm-frontend\",
                \"slm-database\",
                \"slm-monitoring\"
            ],
            \"ssh_user\": \"autobot\",
            \"ssh_port\": 22,
            \"auth_method\": \"key\",
            \"import_existing\": true,
            \"auto_enroll\": false
        }" 2>/dev/null)

    case "${http_code}" in
        201) success "Local node registered (${hostname_val} / ${local_ip})" ;;
        400) success "Local node already registered" ;;
        *)   warn "Node registration returned HTTP ${http_code} — register manually via SLM UI"
             return ;;
    esac

    # Auto-assign SLM Manager as code source (#2755)
    info "Assigning code source to SLM Manager..."
    local cs_code
    cs_code=$(curl -sfk --max-time 10 -o /dev/null -w "%{http_code}" \
        -X POST "${api_url}/api/code-source/assign" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${token}" \
        -d "{
            \"node_id\": \"${SLM_NODE_ID}\",
            \"repo_path\": \"${CODE_SOURCE}\",
            \"branch\": \"${GIT_BRANCH}\"
        }" 2>/dev/null)

    case "${cs_code}" in
        200) success "Code source assigned: ${CODE_SOURCE} (branch: ${GIT_BRANCH})" ;;
        *)   warn "Code source assignment returned HTTP ${cs_code} — assign manually via SLM UI > Code Sync" ;;
    esac
}

# =============================================================================
# Phase 7: Finalize
# =============================================================================

finalize() {
    phase "Finalize"

    echo "$(date -Iseconds) version=${SCRIPT_VERSION} branch=${GIT_BRANCH}" > "${INSTALL_MARKER}"
    chown autobot:autobot "${INSTALL_MARKER}"
    success "Install marker written"

    local creds_file="/root/autobot-credentials.txt"
    local server_ip
    server_ip="$(detect_local_ip)"
    cat > "${creds_file}" << EOF
AutoBot SLM Credentials
=======================
Generated: $(date)
Server:    ${server_ip}

SLM URL:   https://${server_ip}/slm/
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
    echo -e "  ${BLUE}SLM URL:${NC}         https://${server_ip}/slm/"
    echo -e "  ${BLUE}Admin Username:${NC}  admin"
    echo -e "  ${BLUE}Admin Password:${NC}  ${ADMIN_PASSWORD}"
    echo
    echo -e "  ${YELLOW}Note:${NC} Using self-signed certificate — browser will show a warning."
    echo
    echo -e "  ${CYAN}Next Steps:${NC}"
    echo "    1. Open https://${server_ip}/slm/ in your browser"
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

    # Clean up IP detection cache file (#3010)
    rm -f /tmp/.autobot_detected_ip 2>/dev/null || true
}

# =============================================================================
# Interactive Prompts
# =============================================================================

prompt_config() {
    # #7057: env-var overrides skip the corresponding interactive prompt
    # so the script can run from CI / cron / runbooks without a TTY.
    #   AUTOBOT_INSTALL_BRANCH=<branch>     skips the branch prompt
    #   AUTOBOT_SLM_ADMIN_PASSWORD=<pass>   skips the password prompt
    #   (interface override is in detect_local_ip via AUTOBOT_INSTALL_INTERFACE)
    if [[ -n "${AUTOBOT_INSTALL_BRANCH:-}" ]]; then
        GIT_BRANCH="${AUTOBOT_INSTALL_BRANCH}"
    fi
    if [[ -n "${AUTOBOT_SLM_ADMIN_PASSWORD:-}" ]]; then
        ADMIN_PASSWORD="${AUTOBOT_SLM_ADMIN_PASSWORD}"
    fi

    # #7075: preserve existing admin password on reinstall.
    # The install wizard is the source of truth for SLM_ADMIN_PASSWORD;
    # silently rotating it on every reinstall is a footgun (operator
    # discovers locked-out admins after the fact). Only rotate if:
    #   - secrets file does not exist yet (truly first install), OR
    #   - --rotate-secrets flag explicitly passed by user
    local secrets_file="/etc/autobot/slm-secrets.env"
    if [[ -f "${secrets_file}" ]] && [[ "${ROTATE_SECRETS:-false}" != true ]]; then
        local existing_pass
        existing_pass=$(grep -E '^SLM_ADMIN_PASSWORD=' "${secrets_file}" 2>/dev/null | cut -d'=' -f2- || true)
        if [[ -n "${existing_pass}" ]]; then
            if [[ -n "${ADMIN_PASSWORD}" && "${ADMIN_PASSWORD}" != "${existing_pass}" ]]; then
                warn "AUTOBOT_SLM_ADMIN_PASSWORD env-var ignored — existing wizard-set password preserved."
                warn "  To rotate: rerun with --rotate-secrets (warns + replaces) or edit ${secrets_file} manually."
            fi
            ADMIN_PASSWORD="${existing_pass}"
            info "Preserving existing SLM_ADMIN_PASSWORD from ${secrets_file}"
        fi
    fi

    if ${UNATTENDED}; then
        GIT_BRANCH="${GIT_BRANCH:-${DEFAULT_BRANCH}}"
        if [[ -z "${ADMIN_PASSWORD}" ]]; then
            ADMIN_PASSWORD=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 20)
        fi
        return
    fi

    echo -e "${YELLOW}Configuration:${NC}"
    echo

    if [[ -z "${GIT_BRANCH}" ]]; then
        echo -e "  ${CYAN}[1/2]${NC} Git branch to install:"
        read -rp "  [${DEFAULT_BRANCH}] > " input
        GIT_BRANCH="${input:-${DEFAULT_BRANCH}}"
    fi

    if [[ -z "${ADMIN_PASSWORD}" ]]; then
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
    fi
    echo
}

# =============================================================================
# Distribution Validation (#4130)
# =============================================================================

validate_distributions() {
    # Verify all critical service directories are present in AUTOBOT_BASE.
    # Called standalone via --validate or at the end of code_deployment().
    info "Validating required service distributions..."
    local failed=()
    for dir in "${CRITICAL_DIRS[@]}"; do
        if [[ -d "${AUTOBOT_BASE}/${dir}" ]]; then
            success "  ${dir}: present"
        else
            error "  ${dir}: MISSING at ${AUTOBOT_BASE}/${dir}"
            failed+=("${dir}")
        fi
    done

    if [[ ${#failed[@]} -gt 0 ]]; then
        fatal "Installation integrity check failed — missing: ${failed[*]}"
    fi
    success "All required service distributions are present"
}

# =============================================================================
# Argument Parsing
# =============================================================================

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --unattended)     UNATTENDED=true;        shift ;;
            --reinstall)      REINSTALL=true;          shift ;;
            --uninstall)      UNINSTALL=true;          shift ;;
            --validate)       VALIDATE=true;           shift ;;
            --yes|-y)         CONFIRM_YES=true;        shift ;;
            --branch=*)       GIT_BRANCH="${1#*=}";    shift ;;
            --admin-pass=*)   ADMIN_PASSWORD="${1#*=}"; shift ;;
            --ip=*)           OVERRIDE_IP="${1#*=}";    shift ;;
            --rotate-secrets) ROTATE_SECRETS=true;     shift ;;
            --help|-h)        print_usage; exit 0 ;;
            *)                fatal "Unknown option: $1 (use --help for usage)" ;;
        esac
    done
}

# =============================================================================
# Uninstall (#2706)
# =============================================================================

uninstall() {
    print_banner
    _log_init
    log "AutoBot Uninstaller started"

    if [[ $EUID -ne 0 ]]; then
        fatal "This script must be run as root (use sudo)"
    fi

    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}  WARNING: Full AutoBot Uninstall${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo
    echo "  This will permanently remove:"
    echo "    - All AutoBot services and data"
    echo "    - PostgreSQL server and all databases"
    echo "    - Node.js, Grafana, Ansible"
    echo "    - APT repositories added by the installer"
    echo "    - The 'autobot' system user"
    echo "    - Directories: /opt/autobot, /etc/autobot, /var/lib/slm, /var/log/autobot"
    echo

    if ! ${CONFIRM_YES}; then
        echo -e "  ${YELLOW}Type 'UNINSTALL' to confirm:${NC}"
        read -rp "  > " confirmation
        if [[ "${confirmation}" != "UNINSTALL" ]]; then
            info "Uninstall cancelled."
            exit 0
        fi
        echo
    fi

    info "Starting full uninstall..."

    # ---- Phase 1: Stop and disable services ----
    info "Stopping services..."
    # Stop all autobot-* units first (covers playwright, browser-worker, tts, npu, etc.)
    # before removing their unit files — otherwise processes survive with no unit file.
    while IFS= read -r unit; do
        [[ -z "$unit" ]] && continue
        svc="${unit%.service}"
        systemctl stop "${svc}" >> "${LOG_FILE}" 2>&1 && success "  Stopped ${svc}" || true
        systemctl disable "${svc}" >> "${LOG_FILE}" 2>&1 || true
    done < <(systemctl list-units --all --no-legend 'autobot-*' 2>/dev/null | grep -oP 'autobot-\S+\.service')

    local services=(nginx grafana-server postgresql)
    for svc in "${services[@]}"; do
        if systemctl is-active --quiet "${svc}" 2>/dev/null; then
            systemctl stop "${svc}" >> "${LOG_FILE}" 2>&1 && success "  Stopped ${svc}" || warn "  Failed to stop ${svc}"
        fi
        if systemctl is-enabled --quiet "${svc}" 2>/dev/null; then
            systemctl disable "${svc}" >> "${LOG_FILE}" 2>&1 || true
        fi
    done

    # Remove AutoBot systemd unit files
    for unit_file in /etc/systemd/system/autobot-*.service; do
        if [[ -f "${unit_file}" ]]; then
            rm -f "${unit_file}"
            log "  Removed ${unit_file}"
        fi
    done
    systemctl daemon-reload >> "${LOG_FILE}" 2>&1 || true

    # ---- Phase 2: Drop PostgreSQL databases and user ----
    info "Removing PostgreSQL databases..."
    if command -v psql &>/dev/null; then
        systemctl start postgresql >> "${LOG_FILE}" 2>&1 || true
        sleep 2
        local dbs=(slm slm_users autobot_users)
        for db in "${dbs[@]}"; do
            if sudo -u postgres psql -lqt 2>/dev/null | cut -d\| -f1 | grep -qw "${db}"; then
                sudo -u postgres dropdb "${db}" >> "${LOG_FILE}" 2>&1 && success "  Dropped database: ${db}" || warn "  Failed to drop: ${db}"
            fi
        done
        if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='slm_app'" 2>/dev/null | grep -q 1; then
            sudo -u postgres dropuser slm_app >> "${LOG_FILE}" 2>&1 && success "  Dropped user: slm_app" || warn "  Failed to drop user: slm_app"
        fi
        systemctl stop postgresql >> "${LOG_FILE}" 2>&1 || true
    else
        warn "  PostgreSQL not installed — skipping database cleanup"
    fi

    # ---- Phase 3: Remove APT packages ----
    info "Removing installed packages..."
    local pg_version
    pg_version=$(pg_lsclusters 2>/dev/null | awk 'NR==2{print $1}' || echo "16")

    # Drop the PostgreSQL cluster before purging
    if command -v pg_dropcluster &>/dev/null; then
        pg_dropcluster --stop "${pg_version}" main >> "${LOG_FILE}" 2>&1 || true
    fi

    local packages=(
        "postgresql-${pg_version}"
        "postgresql-client-${pg_version}"
        "postgresql-contrib-${pg_version}"
        python3-psycopg2
        grafana
        ansible
        nodejs
    )
    for pkg in "${packages[@]}"; do
        if dpkg -l "${pkg}" &>/dev/null 2>&1; then
            env DEBIAN_FRONTEND=noninteractive apt-get purge -y -qq "${pkg}" >> "${LOG_FILE}" 2>&1 \
                && success "  Purged ${pkg}" || warn "  Failed to purge ${pkg}"
        fi
    done

    # Purge remaining PostgreSQL and Grafana config
    env DEBIAN_FRONTEND=noninteractive apt-get purge -y -qq 'postgresql-common' >> "${LOG_FILE}" 2>&1 || true
    env DEBIAN_FRONTEND=noninteractive apt-get autoremove -y -qq >> "${LOG_FILE}" 2>&1 || true

    # ---- Phase 4: Remove APT repositories ----
    info "Removing APT repositories..."
    local repo_files=(
        /etc/apt/sources.list.d/pgdg.list
        /etc/apt/sources.list.d/pgdg.sources
        /etc/apt/sources.list.d/deadsnakes-*.list
        /etc/apt/sources.list.d/deadsnakes-*.sources
        /etc/apt/sources.list.d/nodesource.list
        /etc/apt/sources.list.d/nodesource.sources
        /etc/apt/sources.list.d/grafana.list
        /etc/apt/sources.list.d/grafana.sources
        /etc/apt/sources.list.d/ansible-*.list
        /etc/apt/sources.list.d/ansible-*.sources
    )
    for pattern in "${repo_files[@]}"; do
        # shellcheck disable=SC2086
        for f in ${pattern}; do
            if [[ -f "${f}" ]]; then
                rm -f "${f}"
                log "  Removed ${f}"
            fi
        done
    done

    # Remove signing keys
    rm -f /usr/share/keyrings/pgdg.asc /usr/share/keyrings/grafana.gpg \
          /usr/share/keyrings/nodesource.gpg 2>/dev/null || true
    success "  APT repositories cleaned"

    # ---- Phase 5: Remove directories and files ----
    info "Removing AutoBot directories and files..."
    local dirs=(
        /opt/autobot
        /var/lib/slm
        /var/log/autobot
        /etc/autobot
        /var/lib/postgresql
        /etc/postgresql
        /var/lib/grafana
        /etc/grafana
    )
    for dir in "${dirs[@]}"; do
        if [[ -d "${dir}" ]]; then
            rm -rf "${dir}"
            success "  Removed ${dir}"
        fi
    done

    # Remove credential and config files
    rm -f /root/autobot-credentials.txt 2>/dev/null || true
    rm -f /etc/sudoers.d/autobot 2>/dev/null || true
    rm -f /tmp/.autobot_detected_ip 2>/dev/null || true

    # Remove nginx site config (but leave nginx installed)
    rm -f /etc/nginx/sites-available/autobot-slm 2>/dev/null || true
    rm -f /etc/nginx/sites-enabled/autobot-slm 2>/dev/null || true
    rm -f /etc/systemd/system/nginx.service.d/ssl-cert-check.conf 2>/dev/null || true

    # ---- Phase 6: Remove autobot user ----
    info "Removing autobot user..."
    if id "autobot" &>/dev/null; then
        userdel -r autobot >> "${LOG_FILE}" 2>&1 && success "  Removed user: autobot" || warn "  Failed to remove user (may have running processes)"
    fi
    if getent group autobot &>/dev/null; then
        groupdel autobot >> "${LOG_FILE}" 2>&1 || true
    fi

    # ---- Done ----
    echo
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  AutoBot has been completely uninstalled.${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo
    echo -e "  ${CYAN}Removed:${NC} services, databases, packages, repos, user, data"
    echo -e "  ${CYAN}Log:${NC}     ${LOG_FILE}"
    echo
    echo -e "  ${YELLOW}Note:${NC} nginx was left installed but AutoBot site config was removed."
    echo -e "  To remove nginx too: ${BLUE}sudo apt purge nginx${NC}"
    echo
}

# =============================================================================
# Main
# =============================================================================

main() {
    parse_args "$@"

    if ${UNINSTALL}; then
        uninstall
        exit 0
    fi

    if ${VALIDATE}; then
        _log_init
        validate_distributions
        exit 0
    fi

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
    register_local_node
    finalize
}

main "$@"
