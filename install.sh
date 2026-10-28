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

# Re-exec under bash; must precede `set -o pipefail`, which dash rejects when
# started as `sh install.sh`. POSIX here -- dash reads it (#17875).
if [ -z "${BASH_VERSION:-}" ]; then
    [ -r "$0" ] && [ "$0" != "sh" ] && exec bash "$0" "$@"
    echo "AutoBot installer requires bash.  Run:  sudo bash install.sh" >&2
    exit 1
fi

set -euo pipefail; umask 022  # #19503: the root-run code tree must not take a loose caller umask (world-writable)

# =============================================================================
# Constants
# =============================================================================

readonly SCRIPT_VERSION="1.0.0"
readonly LOG_DIR="/var/log/autobot"
readonly LOG_FILE="${LOG_DIR}/install-$(date +%Y%m%d-%H%M%S).log"
readonly AUTOBOT_BASE="/opt/autobot"
readonly INSTALL_MARKER="${AUTOBOT_BASE}/.autobot-installed"
readonly CODE_SOURCE="${AUTOBOT_BASE}/code_source"
readonly SECRETS_FILE="/etc/autobot/slm-secrets.env"
# #18653: what this installer itself created -- read by scripts/uninstall.sh, which removes an
# account, package or apt source only if it is recorded here, never a pre-existing one.
readonly INSTALL_RECORD="/etc/autobot/install-record"
# The service account that owns ${AUTOBOT_BASE} and runs the AutoBot units, and the
# account the SLM later reaches this node as (PathConfig.ssh_user, AUTOBOT_SSH_USER).
# Named once here because this script runs before the repository, and so before
# ssot-config.sh, exists on the host.
readonly AUTOBOT_USER="autobot"
readonly AUTOBOT_HOME="/home/${AUTOBOT_USER}"
# #9956: Default SLM manager node_id. Must match the host/slm_node_id written
# into the generated localhost inventory (generate_inventory) — that inventory
# is the canonical definition; this constant mirrors it for the API
# registration calls so the value is not duplicated as scattered literals.
readonly SLM_NODE_ID="00-SLM-Manager"
# External hosts the install reaches, each named once. The connectivity pre-flight
# probes these same hosts, so it checks exactly what the install goes on to use.
readonly REPO_HOST="github.com"
readonly REPO_SLUG="mrveiss/AutoBot-AI"
readonly DEFAULT_REPO="https://${REPO_HOST}/${REPO_SLUG}.git"
readonly NODESOURCE_HOST="deb.nodesource.com"
# #19239: each pinned to its source of truth by a repo test -- autobot-frontend/package.json
# engines.node, the slm_manager role's slm_backend_port -- since the installer runs before the code exists.
readonly NODE_MIN_VERSION="22.22.2" SLM_BACKEND_PORT="8000"
readonly IP_CACHE_FILE="/run/autobot-install-ip"  # root-only, unlike /tmp, which any user can plant a file in
readonly DEFAULT_BRANCH="main" PINNED_COMMIT=""  # a release build pins both: tag and its commit (#18666)
# #18586: where this script was started from, resolved before any cd; empty under `curl | bash`
SCRIPT_DIR=""
[[ -f "${BASH_SOURCE[0]:-}" ]] && SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly REQUIRED_DISK_MB=5120
readonly REQUIRED_MEM_MB=1536   # SLM control plane only (#17875): postgres + slm-backend + nginx
readonly PROC_VERSION_FILE="/proc/version"  # #18583: WSL detection reads this

# Runtime flags
UNATTENDED=false
REINSTALL=false
UNINSTALL=false
VALIDATE=false
CONFIRM_YES=false
ROTATE_SECRETS=false  # #7075: --rotate-secrets opts in to replacing existing SLM_ADMIN_PASSWORD
INSTALL_TMP="" ADMIN_PASSWORD_GENERATED=false ADMIN_PASSWORD_PRESERVED=false  # #19236: private temp dir; print the password only if generated. PRESERVED: a reinstall kept the stored one
GIT_BRANCH=""  # empty until --branch=, AUTOBOT_INSTALL_BRANCH, unattended or the prompt sets it -- a default here made the prompt unreachable (#7060, #19403)
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

record_install() {  # record_install <key> <value>, once (#18653)
    mkdir -p "$(dirname "${INSTALL_RECORD}")"
    grep -qxF "$1=$2" "${INSTALL_RECORD}" 2>/dev/null || echo "$1=$2" >> "${INSTALL_RECORD}"
}
pkg_installed() { dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q 'ok installed'; }
apt_install_recorded() {  # <desc> <pkg>...: install; record only packages absent BEFORE (#18727)
    local desc="$1" p new=(); shift
    for p in "$@"; do pkg_installed "${p}" || new+=("${p}"); done
    run_ok "${desc}" env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@" || return
    for p in "${new[@]}"; do record_install package "${p}"; done
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
    record_install apt_source "${match%%/*}"
}

# =============================================================================
# Network Interface Detection (#2832)
# =============================================================================

# #17642: a firewall source, so given (NETWORK_SUBNET/NETWORK_GATEWAY) or detected, never guessed
detect_network() {
    local cidr
    network_subnet="${NETWORK_SUBNET:-}" network_gateway="${NETWORK_GATEWAY:-}"
    cidr=$(ip -4 addr show | awk -v ip="${local_ip}/" '$1 == "inet" && index($2, ip) == 1 {print $2; exit}')
    if [[ -z "${network_subnet}" && -n "${cidr}" ]]; then
        network_subnet=$(python3 -c "import ipaddress; print(ipaddress.ip_interface('${cidr}').network)") || network_subnet=""
    fi
    if [[ -z "${network_gateway}" ]]; then
        network_gateway=$(ip route | awk '/^default/ {print $3}' | head -1)
    fi
    python3 -c 'import ipaddress, sys; ipaddress.ip_network(sys.argv[1]); ipaddress.ip_address(sys.argv[2])' "${network_subnet}" "${network_gateway}" 2>/dev/null \
        || fatal "No usable network for ${local_ip} (subnet '${network_subnet}', gateway '${network_gateway}'). Re-run with NETWORK_SUBNET=<cidr> NETWORK_GATEWAY=<ip> (INSTALL.md)."
}

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
    local cache_file="${IP_CACHE_FILE}" cached=""
    [[ "${REINSTALL}" == true ]] && rm -f "${cache_file}"
    [[ -f "${cache_file}" ]] && cached="$(head -n1 "${cache_file}")"
    # #19239: reuse a cached address only while it is still assigned to an interface here.
    if [[ -n "${cached}" ]] && ip -4 -o addr show | awk '{print $4}' | cut -d/ -f1 | grep -qxF "${cached}"; then
        echo "${cached}"; return
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
        local choice=""  # /dev/tty, never stdin: under curl | bash stdin is the script itself (#17929)
        prompt_from_tty choice "  Select interface for AutoBot [1-${#ips[@]}]: " || fatal "No terminal to choose an interface: rerun with AUTOBOT_INSTALL_INTERFACE=<name> (one of: ${ifaces[*]})."
        [[ "${choice}" =~ ^[0-9]+$ ]] || fatal "Invalid selection"; choice=$((choice - 1))
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

Installs AutoBot SLM (Service Lifecycle Manager) on a blank Ubuntu 22.04+ host.
After installation, use the SLM web UI setup wizard to add fleet nodes.

Options:
  --unattended          Run without prompts, use all defaults
  --reinstall           Force reinstall over existing installation
  --uninstall           Remove AutoBot: shows the plan, then asks (#2706, #18653)
  --validate            Verify installation integrity (check required service distributions)
  --yes                 Skip confirmation prompts (use with --uninstall)
  --branch=BRANCH       Git branch to install (default: ${DEFAULT_BRANCH})
  --admin-pass-file=F   read the SLM admin password from file F (mode 600 or tighter, auto-generated if not set)
  --ip=IP               Override auto-detected IP address (#2832)
  --rotate-secrets      Replace existing SLM_ADMIN_PASSWORD on reinstall (#7075).
                        By default reinstall PRESERVES the wizard-set password
                        and ignores --admin-pass-file= / SLM_ADMIN_PASSWORD.
  --help                Show this help message

Environment overrides (skip the corresponding interactive prompt; #7057):
  AUTOBOT_INSTALL_BRANCH=<branch>     same as --branch=
  SLM_ADMIN_PASSWORD=<pass>           the admin password itself (not a file path);
                                      AUTOBOT_SLM_ADMIN_PASSWORD is a deprecated alias (#19318)
  AUTOBOT_INSTALL_INTERFACE=<iface>   pick an interface by name (eth2, eth0, ...)
                                      instead of the menu prompt
  OVERRIDE_IP=<ip>                    skip detection entirely and use this IP

Examples:
  sudo $0                                    # Interactive install
  sudo $0 --unattended                       # Default unattended install
  sudo $0 --unattended --admin-pass-file=/root/pw   # Unattended with custom password
  sudo $0 --reinstall                        # Reinstall over existing
  sudo $0 --uninstall                        # Full uninstall (with confirmation)
  sudo $0 --uninstall --yes                  # Full uninstall (no prompt)
  sudo AUTOBOT_INSTALL_INTERFACE=eth2 \\
       AUTOBOT_INSTALL_BRANCH=${DEFAULT_BRANCH} \\
       SLM_ADMIN_PASSWORD='<pass>' \\
       $0 --reinstall                        # Fully scripted reinstall (#7057)

Post-Install:
  1. Open https://<server-ip>/slm/ in a browser
  2. Log in with the admin credentials shown at the end
  3. Follow the Setup Wizard to add and configure fleet nodes

EOF
}

# #18583: name the requirement and the way out for this host — not a WSL2-only hint for all
systemd_missing_hint() {
    local fix="Use an Ubuntu 22.04+ VM or bare-metal host booted with systemd; in a container or a host without systemd, use the Docker path in INSTALL.md instead."
    grep -qi microsoft "${PROC_VERSION_FILE}" 2>/dev/null && fix="On WSL2 (WSL1 cannot run systemd): add [boot] systemd=true to /etc/wsl.conf and restart WSL."
    echo "systemd must be running as PID 1 (see Requirements in INSTALL.md). ${fix}"
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
        fatal "$(systemd_missing_hint)"
    fi
    success "systemd is running"

    # #19235: Ubuntu 22.04+ only -- Python 3.14 and Ansible come from Launchpad PPAs, which Debian lacks.
    local os_id="" os_version="" os_name
    os_id=$(. /etc/os-release 2>/dev/null && echo "${ID:-}") || true; os_version=$(. /etc/os-release 2>/dev/null && echo "${VERSION_ID:-}") || true
    [[ "${os_id}" == ubuntu && "$(printf '%s\n' 22.04 "${os_version}" | sort -V | head -1)" == 22.04 ]] || fatal "This installer supports Ubuntu 22.04 or newer (found: ${os_id:-unknown} ${os_version}). On other systems use the Docker path in INSTALL.md."
    os_name=$(. /etc/os-release 2>/dev/null && echo "${NAME} ${VERSION_ID}")
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
        fatal "Insufficient memory: ${total_mem_mb}MB total, ${REQUIRED_MEM_MB}MB required for the SLM node"
    fi
    success "Memory: ${total_mem_mb}MB total"

    if ! curl -sf --max-time 5 "https://${REPO_HOST}" > /dev/null 2>&1; then
        if ! curl -sf --max-time 5 "https://${NODESOURCE_HOST}" > /dev/null 2>&1; then
            fatal "No internet connectivity (cannot reach ${REPO_HOST} or ${NODESOURCE_HOST})"
        fi
    fi
    success "Internet connectivity OK"

    # openssl is needed BEFORE system_setup installs it: prompt_config runs first
    # and generate_admin_password shells out to it. Checked here so a missing one
    # fails with a name, not as another silent set -e abort mid-prompt (#17929).
    for cmd in curl apt-get openssl; do
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

    # Issue #2705: Python 3.14 required by autobot_shared
    if ! command -v python3.14 &>/dev/null; then
        add_ppa_if_missing "ppa:deadsnakes/ppa" "deadsnakes/ppa" "deadsnakes (Python 3.14)"
        run_ok "Updating package lists (Python 3.14)" \
            apt-get update -qq
        apt_install_recorded "Installing Python 3.14" python3.14 python3.14-venv python3.14-dev
    else
        success "  Python 3.14 already installed ($(python3.14 --version))"
    fi

    if ! command -v ansible-playbook &>/dev/null; then
        add_ppa_if_missing "ppa:ansible/ansible" "ansible/ansible" "Ansible"
        run_ok "Updating package lists (Ansible)" \
            apt-get update -qq
        apt_install_recorded "Installing Ansible" ansible
    else
        success "  Ansible already installed ($(ansible --version | head -1))"
    fi

    if ! command -v node &>/dev/null; then
        run_ok "Adding NodeSource repository" \
            bash -c "curl -fsSL https://${NODESOURCE_HOST}/setup_${NODE_MIN_VERSION%%.*}.x | bash -"
        apt_install_recorded "Installing Node.js" nodejs; record_install apt_source nodesource
    elif [[ "$(printf '%s\n' "${NODE_MIN_VERSION}" "$(node --version | tr -d v)" | sort -V | head -1)" != "${NODE_MIN_VERSION}" ]]; then
        fatal "Node.js $(node --version) is installed, but AutoBot needs ${NODE_MIN_VERSION} or newer. Upgrade or remove it, then rerun this installer."
    else
        success "  Node.js already installed ($(node --version))"
    fi

    if ! id "${AUTOBOT_USER}" &>/dev/null; then
        run_ok "Creating ${AUTOBOT_USER} user" \
            useradd -r -m -s /bin/bash -d "${AUTOBOT_HOME}" "${AUTOBOT_USER}"
        echo "${AUTOBOT_USER} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/autobot
        chmod 0440 /etc/sudoers.d/autobot
        record_install created_user "${AUTOBOT_USER}"; record_install created_sudoers /etc/sudoers.d/autobot
        success "  Passwordless sudo configured"
    else
        success "  User '${AUTOBOT_USER}' already exists"
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

    chown -R "${AUTOBOT_USER}:${AUTOBOT_USER}" "${AUTOBOT_BASE}"
    success "  Directory ownership set"

    local ssh_key="${AUTOBOT_HOME}/.ssh/autobot_key"
    if [[ ! -f "${ssh_key}" ]]; then
        run_ok "Generating SSH key pair for fleet management" \
            sudo -u "${AUTOBOT_USER}" bash -c "mkdir -p ${AUTOBOT_HOME}/.ssh && ssh-keygen -t ed25519 -f ${ssh_key} -N '' -C 'autobot@slm'"
    elif [[ ! -f "${ssh_key}.pub" ]]; then
        # DERIVE, never regenerate: enrolled nodes trust this key (#17875).
        run_ok "Recovering the public key from the existing private key" \
            sudo -u "${AUTOBOT_USER}" bash -c "ssh-keygen -y -f ${ssh_key} > ${ssh_key}.pub && chmod 0644 ${ssh_key}.pub"
    else
        success "  SSH key pair already exists"
    fi

    # Issue #2828: Copy SSH key to shared location for Ansible (#3268: must be
    # autobot:autobot 0600 — SSH client refuses group-readable private keys).
    if [[ -f "${ssh_key}" && -f "${ssh_key}.pub" ]]; then
        cp "${ssh_key}" /etc/autobot/ssh/autobot_key
        cp "${ssh_key}.pub" /etc/autobot/ssh/autobot_key.pub
        chown "${AUTOBOT_USER}:${AUTOBOT_USER}" /etc/autobot/ssh/autobot_key /etc/autobot/ssh/autobot_key.pub
        chmod 0600 /etc/autobot/ssh/autobot_key
        chmod 0644 /etc/autobot/ssh/autobot_key.pub
        success "  SSH key published to /etc/autobot/ssh/"
    fi
}

# =============================================================================
# Phase 3: Code Deployment
# =============================================================================

# #18586: ./install.sh run from a clone installs ${DEFAULT_REPO} at ${GIT_BRANCH}, not the commit
# on disk — say so before cloning. install.sh sits at the repo root, so SCRIPT_DIR is the checkout;
# an inherited GIT_DIR is dropped, and safe.directory covers sudo running as root in a user's clone.
report_local_checkout() {
    local sha
    [[ -n "${SCRIPT_DIR}" && "${SCRIPT_DIR}" != "${CODE_SOURCE}" ]] && command -v git &>/dev/null || return 0
    sha="$(env -u GIT_DIR -u GIT_WORK_TREE git -c safe.directory="${SCRIPT_DIR}" -C "${SCRIPT_DIR}" rev-parse --short HEAD 2>/dev/null)" || return 0
    warn "Run from a local checkout (${SCRIPT_DIR} @ ${sha}): this installs ${DEFAULT_REPO} branch ${GIT_BRANCH}, not that checkout."
    warn "Pass --branch=<name> to install another pushed branch; local unpushed commits are not installed."
}

code_deployment() {
    phase "Code Deployment"
    report_local_checkout

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
            sudo -u "${AUTOBOT_USER}" git -C "${CODE_SOURCE}" fetch --tags origin
        run_ok "Checking out ${GIT_BRANCH}" \
            sudo -u "${AUTOBOT_USER}" git -C "${CODE_SOURCE}" checkout "${GIT_BRANCH}"
        run_ok "Pulling latest changes" \
            sudo -u "${AUTOBOT_USER}" sh -c 'git -C "$1" symbolic-ref -q HEAD >/dev/null || exit 0; git -C "$1" pull origin "$2"' _ "${CODE_SOURCE}" "${GIT_BRANCH}"  # a release tag is already exact (#18666)
    else
        run_ok "Cloning AutoBot repository (branch: ${GIT_BRANCH})" \
            sudo -u "${AUTOBOT_USER}" git clone -b "${GIT_BRANCH}" "${DEFAULT_REPO}" "${CODE_SOURCE}"
    fi

    local installed_sha  # #18586: record exactly what was installed
    installed_sha="$(sudo -u "${AUTOBOT_USER}" git -C "${CODE_SOURCE}" rev-parse HEAD)"; [[ -z "${PINNED_COMMIT}" || "${GIT_BRANCH}" != "${DEFAULT_BRANCH}" || "${installed_sha}" == "${PINNED_COMMIT}" ]] || fatal "${GIT_BRANCH} checked out ${installed_sha}, but this signed installer was built for ${PINNED_COMMIT}; the tag moved -- refusing (#18666)"
    success "Installing ${DEFAULT_REPO} branch ${GIT_BRANCH} @ ${installed_sha}"

    # Copy code from code_source to service directories where Ansible expects them
    info "Distributing code to service directories..."
    local missing_dirs=()
    for dir in "${CRITICAL_DIRS[@]}"; do
        if [[ -d "${CODE_SOURCE}/${dir}" ]]; then
            run_ok "Copying ${dir} to ${AUTOBOT_BASE}/${dir}" \
                sudo -u "${AUTOBOT_USER}" rsync -a --delete "${CODE_SOURCE}/${dir}/" "${AUTOBOT_BASE}/${dir}/"
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
    # lookup pattern: env first, then secrets file, never an open-range default (#17642).
    slm_host: "{{ lookup('env', 'SLM_HOST') | default(lookup('pipe', 'grep -oP \"SLM_HOST=\\K.*\" /etc/autobot/slm-secrets.env 2>/dev/null || echo 127.0.0.1'), true) }}"
    network_subnet: "{{ (lookup('env', 'NETWORK_SUBNET') | trim) or (lookup('pipe', 'grep -oP \"NETWORK_SUBNET=\\K.*\" /etc/autobot/slm-secrets.env 2>/dev/null || true') | trim) or undef(hint='network_subnet is unset: set NETWORK_SUBNET in the environment or in /etc/autobot/slm-secrets.env. It is a firewall source, so it never falls back to an open range (#17642)') }}"
    network_gateway: "{{ (lookup('env', 'NETWORK_GATEWAY') | trim) or (lookup('pipe', 'grep -oP \"NETWORK_GATEWAY=\\K.*\" /etc/autobot/slm-secrets.env 2>/dev/null || true') | trim) or undef(hint='network_gateway is unset: set NETWORK_GATEWAY in the environment or in /etc/autobot/slm-secrets.env (#17642)') }}"
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
        ADMIN_PASSWORD=$(generate_admin_password); ADMIN_PASSWORD_GENERATED=true
    fi

    if [[ ! -f "${SECRETS_FILE}" ]] || [[ "${REINSTALL}" == true ]]; then
        info "Writing secrets file..."
        local secret_key encryption_key hmac_api_key_secret local_ip network_subnet network_gateway
        secret_key=$(openssl rand -hex 32) encryption_key=$(openssl rand -hex 32) hmac_api_key_secret=$(grep -oP '^SLM_HMAC_API_KEY_SECRET=\K.+' "${SECRETS_FILE}" 2>/dev/null | head -1 || true); hmac_api_key_secret=${hmac_api_key_secret:-$(openssl rand -hex 32)}  # #16299, #19120: a reinstall keeps an existing pepper
        # Issue #2758: detect the machine's primary outbound IP so that
        # SLM_EXTERNAL_URL is set correctly and not left to the Python fallback.
        local_ip="$(detect_local_ip)"
        detect_network
        (umask 077; cat > "${SECRETS_FILE}") << EOF  # created 0600, never briefly world-readable under the tree's 022
SLM_SECRET_KEY=${secret_key}
SLM_ENCRYPTION_KEY=${encryption_key}
SLM_HMAC_API_KEY_SECRET=${hmac_api_key_secret}
SLM_ADMIN_PASSWORD=${ADMIN_PASSWORD}
SLM_EXTERNAL_URL=https://${local_ip}
SLM_HOST=${local_ip}
NETWORK_SUBNET=${network_subnet}
NETWORK_GATEWAY=${network_gateway}
EOF
        chown "root:${AUTOBOT_USER}" "${SECRETS_FILE}"
        chmod 640 "${SECRETS_FILE}"
        success "  Secrets written to ${SECRETS_FILE}"
    else
        ADMIN_PASSWORD=$(grep -oP 'SLM_ADMIN_PASSWORD=\K.*' "${SECRETS_FILE}" 2>/dev/null || echo "${ADMIN_PASSWORD}")
        # Refresh IP/network fields even when preserving static secrets (#3266).
        # Stale IPs remain when the machine's address changes between installs.
        info "  Refreshing IP/network fields in preserved secrets file..."
        local local_ip network_subnet network_gateway
        local_ip="$(detect_local_ip)"
        detect_network
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
    chown "${AUTOBOT_USER}:${AUTOBOT_USER}" /tmp/ansible_fact_cache /tmp/ansible-retry /tmp/.ansible-cp

    info "Running Ansible deployment (this may take several minutes)..."
    # #6600: keep `provision` so backend role applies to the SLM manager node in
    # single-host mode. Skip only `seed` — fleet seeding requires SLM DB
    # rows that don't exist yet on a fresh install.
    log "  Playbook: deploy-slm-manager.yml --skip-tags seed"
    info "  Live progress below — full output also in ${LOG_FILE}"
    echo

    cd "${ansible_dir}"
    local vars_file="${INSTALL_TMP}/ansible-vars.json"  # #19236: never argv; the EXIT trap removes INSTALL_TMP
    (umask 077 && PW="${ADMIN_PASSWORD}" jq -n '{slm_admin_password: env.PW}' > "${vars_file}"); set +o pipefail
    ansible-playbook \
        -i "${inventory}" \
        playbooks/deploy-slm-manager.yml \
        --skip-tags "seed" \
        -e "@${vars_file}" \
        -e "target_host=localhost" \
        2>&1 | tee -a "${LOG_FILE}" | \
        { grep --line-buffered -E \
            "^(PLAY \[|TASK \[|ok: \[|changed: \[|failed: \[|skipping: \[|fatal:|PLAY RECAP|[A-Za-z0-9_-].*: ok=)" || true; }
    _ansible_exit=${PIPESTATUS[0]}  # #19493: `|| true` -- a no-match grep exit killed the run here, silently, under set -e
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
        if curl -sf --max-time 3 http://127.0.0.1:${SLM_BACKEND_PORT}/api/health > /dev/null 2>&1; then
            success "SLM backend health check passed"
            break
        fi
        attempt=$((attempt + 1))
        log "  Waiting for SLM backend (attempt ${attempt}/${max_attempts})..."
        sleep 5
    done

    # #19234: a failed required step stops the install -- no marker, so a plain rerun retries it.
    [[ ${attempt} -lt ${max_attempts} ]] || fatal "Step 'SLM backend health' failed: no answer within 7 minutes. Check: journalctl -u autobot-slm-backend -n 50, then rerun this installer."
    wait_for_https || fatal "Step 'HTTPS endpoint' failed: https://127.0.0.1/api/health did not answer within 60s. Check: nginx -t; journalctl -u nginx -n 50, then rerun this installer."
    success "HTTPS endpoint accessible"
}

wait_for_https() {  # 0 once https://127.0.0.1/api/health answers, 1 after 60s (#2830, #19234)
    local waited=0
    until curl -sfk --max-time 3 https://127.0.0.1/api/health >/dev/null 2>&1; do
        [[ ${waited} -ge 60 ]] && return 1
        sleep 2; waited=$((waited + 2))
    done
}

# =============================================================================
# Phase 6: Register Local Node (#2717)
# =============================================================================

register_local_node() {
    phase "Register Local Node"

    local api_url="https://127.0.0.1"

    # nginx may still be loading TLS certificates after the Ansible deploy (#2830).
    info "Waiting for HTTPS endpoint to be ready..."
    wait_for_https || fatal "Step 'node registration' failed: HTTPS is not answering. Check: journalctl -u nginx -n 50, then rerun this installer."
    success "HTTPS endpoint is ready"

    local local_ip
    local_ip="$(detect_local_ip)"
    local hostname_val
    hostname_val=$(hostname)

    # Authenticate
    info "Authenticating with SLM API..."
    local token
    # #15825: `|| true` is what makes the handler below reachable. Under
    # `set -euo pipefail` a failed assignment aborts the script, so on any auth
    # failure the installer died here and the two warn lines -- which read as
    # careful handling -- could never run. `-f` is kept deliberately: on a 401
    # we want no body to parse, not an error page fed to jq.
    token=$(PW="${ADMIN_PASSWORD}" jq -n '{username: "admin", password: env.PW}' | curl -sfk --max-time 10 \
        -X POST "${api_url}/api/auth/login" -H "Content-Type: application/json" --data @- \
        2>/dev/null | jq -r '.access_token // empty') || true  # #19236: the body goes on stdin, never argv

    [[ -n "${token}" ]] || fatal "Step 'admin login' failed: the SLM API refused the admin credentials. Check /etc/autobot/slm-secrets.env and journalctl -u autobot-slm-backend -n 50, then rerun this installer."
    success "Authenticated with SLM API"

    # Register this node with all single-host roles
    info "Registering local node (${local_ip})..."
    local http_code
    # #15825: NO -f here. `-f` makes curl exit 22 on any HTTP >= 400, so the
    # assignment failed under `set -e` and the `400)` arm below -- "already
    # registered", an expected outcome on re-run -- was unreachable, as was the
    # catch-all warn. Asking for %{http_code} and also asking curl to fail on
    # the codes you are branching on are contradictory intents.
    # A transport failure (DNS, refused, timeout) exits non-zero with no HTTP
    # response at all, and under `set -euo pipefail` that aborts the assignment
    # just as `-f` did -- the same dead end one layer down. `|| true` keeps the
    # script alive and `${var:-000}` gives the wildcard arm below something to
    # report, so "could not reach the API" surfaces as a manual-action warning
    # rather than a silent exit.
    http_code=$(curl -sk --max-time 10 -o /dev/null -w "%{http_code}" \
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
            \"ssh_user\": \"${AUTOBOT_USER}\",
            \"ssh_port\": 22,
            \"auth_method\": \"key\",
            \"import_existing\": true,
            \"auto_enroll\": false
        }" 2>/dev/null) || true

    case "${http_code:-000}" in
        201) success "Local node registered (${hostname_val} / ${local_ip})" ;;
        400) success "Local node already registered" ;;
        *)   fatal "Step 'node registration' failed: the SLM API returned HTTP ${http_code:-000}. Check journalctl -u autobot-slm-backend -n 50, then rerun this installer." ;;
    esac

    # Auto-assign SLM Manager as code source (#2755)
    info "Assigning code source to SLM Manager..."
    local cs_code
    # #15825: same as above -- capturing the status code means not using -f,
    # and a transport failure must reach the wildcard arm rather than abort.
    cs_code=$(curl -sk --max-time 10 -o /dev/null -w "%{http_code}" \
        -X POST "${api_url}/api/code-source/assign" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${token}" \
        -d "{
            \"node_id\": \"${SLM_NODE_ID}\",
            \"repo_path\": \"${CODE_SOURCE}\",
            \"branch\": \"${GIT_BRANCH}\"
        }" 2>/dev/null) || true

    case "${cs_code:-000}" in
        200) success "Code source assigned: ${CODE_SOURCE} (branch: ${GIT_BRANCH})" ;;
        *)   warn "Optional step 'code source' returned HTTP ${cs_code:-000} — assign it in SLM UI > Code Sync" ;;
    esac
}

# =============================================================================
# Phase 7: Finalize
# =============================================================================

finalize() {
    phase "Finalize"

    echo "$(date -Iseconds) version=${SCRIPT_VERSION} branch=${GIT_BRANCH}" > "${INSTALL_MARKER}"
    chown "${AUTOBOT_USER}:${AUTOBOT_USER}" "${INSTALL_MARKER}"
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
    if ${ADMIN_PASSWORD_GENERATED}; then echo -e "  ${BLUE}Admin Password:${NC}  ${ADMIN_PASSWORD}"; else echo -e "  ${BLUE}Admin Password:${NC}  $(${ADMIN_PASSWORD_PRESERVED} && echo "the existing password, kept from the previous install (see ${creds_file})" || echo "the one you supplied")"; fi
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
    rm -f "${IP_CACHE_FILE}" 2>/dev/null || true
}

# =============================================================================
# Interactive Prompts
# =============================================================================

# `curl | sudo bash` leaves stdin pointing at the PIPE CARRYING THIS SCRIPT, so a
# bare `read` gets EOF, returns 1, and `set -euo pipefail` aborts with no message
# (#17929). /dev/tty reaches the real terminal whatever stdin is. Returns non-zero
# when there is no terminal at all, so the CALLER decides what that means --
# `|| true` on the read would have continued with an empty password.
# Usage: prompt_from_tty <varname> <prompt> [--silent]
prompt_from_tty() {
    local __var="$1" __prompt="$2" __silent="${3:-}" __value="" __fd
    # Probed by OPENING, not `[[ -r /dev/tty ]]`: under setsid or in a container
    # the node is readable by mode and open() still returns ENXIO -- and the mode
    # check leaks bash's own "No such device or address" to the operator.
    if ! { exec {__fd}</dev/tty; } 2>/dev/null; then return 1; fi
    if [[ "${__silent}" == "--silent" ]]; then
        IFS= read -rs -p "${__prompt}" __value <&"${__fd}" || { exec {__fd}<&-; return 1; }
    else
        IFS= read -r -p "${__prompt}" __value <&"${__fd}" || { exec {__fd}<&-; return 1; }
    fi
    exec {__fd}<&-
    printf -v "${__var}" '%s' "${__value}"
}

# One generator, so the interactive-blank and no-terminal paths cannot drift.
generate_admin_password() {
    openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 20
}

prompt_config() {
    # #7057: env-var overrides skip the corresponding interactive prompt
    # so the script can run from CI / cron / runbooks without a TTY.
    #   AUTOBOT_INSTALL_BRANCH=<branch>     skips the branch prompt
    #   SLM_ADMIN_PASSWORD=<pass>   skips the password prompt (AUTOBOT_SLM_ADMIN_PASSWORD: deprecated alias, #19318)
    #   (interface override is in detect_local_ip via AUTOBOT_INSTALL_INTERFACE)
    if [[ -n "${AUTOBOT_INSTALL_BRANCH:-}" ]]; then
        GIT_BRANCH="${AUTOBOT_INSTALL_BRANCH}"
    fi
    ADMIN_PASSWORD="${SLM_ADMIN_PASSWORD:-${AUTOBOT_SLM_ADMIN_PASSWORD:-${ADMIN_PASSWORD}}}"
    if [[ -n "${AUTOBOT_SLM_ADMIN_PASSWORD:-}" && -z "${SLM_ADMIN_PASSWORD:-}" ]]; then warn "AUTOBOT_SLM_ADMIN_PASSWORD is deprecated: set SLM_ADMIN_PASSWORD (#19318)"; fi

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
                warn "SLM_ADMIN_PASSWORD env-var ignored — existing wizard-set password preserved."
                warn "  To rotate: rerun with --rotate-secrets (warns + replaces) or edit ${secrets_file} manually."
            fi
            ADMIN_PASSWORD="${existing_pass}"; ADMIN_PASSWORD_PRESERVED=true
            info "Preserving existing SLM_ADMIN_PASSWORD from ${secrets_file}"
        fi
    fi

    if ${UNATTENDED}; then
        GIT_BRANCH="${GIT_BRANCH:-${DEFAULT_BRANCH}}"
        if [[ -z "${ADMIN_PASSWORD}" ]]; then
            ADMIN_PASSWORD=$(generate_admin_password); ADMIN_PASSWORD_GENERATED=true
        fi
        return
    fi

    echo -e "${YELLOW}Configuration:${NC}"
    echo

    if [[ -z "${GIT_BRANCH}" ]]; then
        echo -e "  ${CYAN}[1/2]${NC} Git branch to install:"
        input=""
        prompt_from_tty input "  [${DEFAULT_BRANCH}] > " || info "  No terminal — using ${DEFAULT_BRANCH}"
        GIT_BRANCH="${input:-${DEFAULT_BRANCH}}"
    fi

    if [[ -z "${ADMIN_PASSWORD}" ]]; then
        echo
        echo -e "  ${CYAN}[2/2]${NC} SLM admin password:"
        input=""
        if prompt_from_tty input "  (leave blank to auto-generate) > " --silent; then
            echo
        else
            warn "  No terminal available to read a password — auto-generating one."
        fi
        if [[ -n "${input}" ]]; then
            ADMIN_PASSWORD="${input}"
        else
            ADMIN_PASSWORD=$(generate_admin_password); ADMIN_PASSWORD_GENERATED=true
            info "  Password auto-generated; it is printed at the end of this run."
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

read_admin_pass_file() {  # owner-only and non-empty, or refuse (#19236)
    [[ -r "$1" ]] || arg_error "Cannot read $1"
    [[ "$(stat -c %a "$1")" =~ ^[0-7]00$ ]] || arg_error "$1 is readable by group or others; chmod 600 it first"
    ADMIN_PASSWORD="$(head -n1 "$1")"; [[ -n "${ADMIN_PASSWORD}" ]] || arg_error "$1 is empty"
}
arg_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 2; }  # parse_args runs before _log_init: no log yet
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --unattended)     UNATTENDED=true;        shift ;;
            --reinstall)      REINSTALL=true;          shift ;;
            --uninstall)      UNINSTALL=true;          shift ;;
            --validate)       VALIDATE=true;           shift ;;
            --yes|-y)         CONFIRM_YES=true;        shift ;;
            --branch=*)       GIT_BRANCH="${1#*=}";    shift ;;
            --admin-pass-file=*) read_admin_pass_file "${1#*=}"; shift ;;
            --admin-pass=*)   arg_error "--admin-pass= puts the password on the command line, readable by every local user (#19236). Use --admin-pass-file=PATH, AUTOBOT_SLM_ADMIN_PASSWORD, or the prompt." ;;
            --ip=*)           OVERRIDE_IP="${1#*=}";    shift ;;
            --rotate-secrets) ROTATE_SECRETS=true;     shift ;;
            --help|-h)        print_usage; exit 0 ;;
            *)                arg_error "Unknown option: $1 (use --help for usage)" ;;
        esac
    done
}

# =============================================================================
# Uninstall (#2706)
# =============================================================================

uninstall() {
    # #18653: the uninstaller is its own script, installed with the code. It removes only
    # what the install record and AutoBot's own roles account for, shows the plan, and asks.
    local script="${CODE_SOURCE}/scripts/uninstall.sh"
    [[ $EUID -eq 0 ]] || fatal "This script must be run as root (use sudo)"
    if [[ ! -f "${script}" ]]; then
        echo "No installed AutoBot at ${CODE_SOURCE}: its uninstaller (scripts/uninstall.sh) lives there." >&2
        echo "See 'Uninstalling' in INSTALL.md for a partial install." >&2
        exit 1
    fi
    if ${CONFIRM_YES}; then exec bash "${script}" --yes; fi
    exec bash "${script}"
}

# =============================================================================
# Main
# =============================================================================

main() {
    parse_args "$@"; cd /  # the service user cannot read the caller's cwd, and git aborts in it (#19403)

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
    # #19236: one owner-only temp dir for the run, removed however it ends -- exit, fatal, Ctrl-C.
    INSTALL_TMP="$(umask 077 && mktemp -d)"; trap 'rm -rf "${INSTALL_TMP:-}"' EXIT; trap 'exit 130' INT TERM
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
