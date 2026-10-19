#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Remove AutoBot from this host (#2706, #18653). Run by `install.sh --uninstall`, or directly:
#   sudo bash /opt/autobot/code_source/scripts/uninstall.sh [--dry-run] [--yes] [--purge-data] [--purge-shared]
#
# Safety rules (#18653):
# - Nothing is removed without proof it is AutoBot's. An account only if the install record
#   says the installer created it, or it carries AutoBot's own admin marker; never by name.
#   install.sh's packages and apt sources only if the record says it added them. The rest
#   are files and units AutoBot's roles write, listed below -- each removed or KEPT with its
#   reason; repo_tests/uninstall_covers_role_components_18653_test.py fails when a role
#   deploys something this script neither removes nor keeps.
# - DATA stays unless --purge-data: AutoBot's databases, its state and backups, its
#   credentials and secrets, and the accounts it created (with their homes). With it,
#   PostgreSQL itself goes only when every cluster was listed and inspected and holds
#   nothing but AutoBot's databases and roles; anything else, or any doubt, keeps it.
# - SHARED software (grafana, prometheus, node-exporter, redis-stack, python3-psycopg2 and
#   their data) stays unless --purge-shared: there is no record of who installed it.
# - apt never removes more than was asked: if the simulated purge would take anything else
#   (reverse-dependents), the purge is skipped and named. No `apt-get autoremove`.
# - The plan is printed first; --dry-run stops there; without --yes the operator types
#   UNINSTALL, and a missing terminal refuses. A failed step warns and the rest still runs.
# - The log lives in /var/tmp, outside everything removed: deleting its own log directory
#   mid-run is what aborted the old uninstaller halfway.

set -euo pipefail

readonly COPY_PATTERN="/var/tmp/autobot-uninstall.*.sh"
# The script deletes the directory it lives in; run from a temporary copy instead.
if [[ "${AUTOBOT_UNINSTALL_COPY:-}" != "1" ]]; then
    copy="$(mktemp /var/tmp/autobot-uninstall.XXXXXX.sh)"
    cp "${BASH_SOURCE[0]}" "${copy}"
    AUTOBOT_UNINSTALL_COPY=1 exec bash "${copy}" "$@"
fi
# Remove the temp copy on every exit -- and only ever a temp copy, never the real script.
# shellcheck disable=SC2053  # COPY_PATTERN is a glob on purpose
trap '[[ "${BASH_SOURCE[0]}" == ${COPY_PATTERN} ]] && rm -f "${BASH_SOURCE[0]}"' EXIT

readonly AUTOBOT_BASE="/opt/autobot"
readonly INSTALL_RECORD="/etc/autobot/install-record"
readonly LOG_FILE="/var/tmp/autobot-uninstall-$(date +%Y%m%d-%H%M%S).log"
# The `comment:` AutoBot's playbooks give the admin account they create
# (enroll-local.yml, setup-backup-admin.yml).
readonly ADMIN_ACCOUNT="autobot_admin"
readonly ADMIN_MARKERS=("Emergency Admin User (fallback access)" "AutoBot Backup Admin (Emergency Access)")

# --- What AutoBot's Ansible roles deploy (checked by the #18653 guard) -----------------------
readonly UNIT_GLOBS=("autobot-*.service" "autobot-*.timer" "autobot-*.socket")
readonly UNITS=(
    slm.target slm-agent.service slm-admin-ui.service node_exporter.service prometheus.service
    loki.service promtail.service redis_exporter.service redisinsight.service
    vnc-server.service vnc-websockify.service redis-stack-server.service
)
# ollama: commonly installed and used outside AutoBot; its unit and models stay.
readonly KEPT_UNITS=(ollama.service)
readonly UNIT_DROPINS=(
    /etc/systemd/system/nginx.service.d/ssl-cert-check.conf
    /etc/systemd/system/logrotate.timer.d/autobot-hourly.conf
)
readonly SUDOERS=(
    90-autobot 90-autobot_admin autobot_admin autobot-nopasswd autobot-python-provision
    autobot-redis-service slm-agent
)
readonly APT_SOURCES=(grafana redis)
# docker, intel-openvino, deadsnakes: general-purpose sources other software relies on
# (deadsnakes is removed when install.sh's record says it added it).
readonly KEPT_APT_SOURCES=(docker intel-openvino deadsnakes)
# Code, configs and AutoBot-only files: removed on UNINSTALL.
# /opt/autobot holds code AND data. By default only children named in OPT_CODE are removed
# -- an ALLOW-list: anything else there (data, snapshots, a folder of the owner's) stays and
# is named as kept. --purge-data removes the whole tree. Every child the roles write is
# classified in OPT_DATA or OPT_CODE -- the #18653 guard fails on an unclassified one.
readonly OPT_DATA=(backups db-backups snapshots data models llm-models plugins .env config config.yaml certs nginx)
readonly OPT_CODE=(
    autobot-backend autobot-slm-backend autobot-user-backend backend frontend
    autobot-browser-worker autobot-frontend autobot-npu-worker
    autobot-db-stack autobot-tts-worker autobot-slm-frontend autobot-ai-stack autobot-slm-agent
    autobot-vue autobot-infrastructure autobot-plugins autobot_shared autobot_shared.egg-info
    code_source scripts venv src app slm slm-agent agent ai-stack infrastructure libs constraints
    logs cache requirements.txt venv_provenance.py .autobot-installed
)
# Data that lives INSIDE an OPT_CODE directory (relative to /opt/autobot): such a directory
# loses its code and keeps these sub-paths unless --purge-data. Secrets are never code: ANY
# `.env`, `.env.*` or `*.env` file inside a code dir is kept by rule (nested_data_in), listed or not.
# The #18653 guard fails on a data-like sub-path under a code dir that is not covered.
readonly OPT_NESTED_DATA=(
    autobot-backend/data autobot-backend/.env autobot-slm-backend/data autobot-slm-backend/.env
    autobot-db-stack/chromadb autobot-db-stack/.env autobot-npu-worker/.env
)
readonly PATHS=(
    /etc/slm-agent /var/log/autobot /opt/node_exporter
    /etc/dnsmasq.d/autobot.conf /etc/logrotate.d/autobot /etc/logrotate.d/redis-stack
    /etc/rsyslog.d/30-autobot.conf /etc/rsyslog.d/50-autobot.conf /etc/ssl/slm
    /var/www/slm-admin /var/www/autobot-slm /etc/nginx/sites-available/slm
    /etc/tmpfiles.d/autobot-slm-self-update.conf /tmp/.autobot_detected_ip
    /usr/local/bin/autobot-admin /usr/local/bin/autobot-time-sync /usr/local/bin/autobot-pg-backup.sh
    /usr/local/bin/check-time-sync.sh /var/lib/systemd/timers/stamp-autobot-pg-backup.timer
)
readonly PATH_GLOBS=(
    "/etc/nginx/sites-available/autobot-*" "/etc/nginx/sites-enabled/autobot-*"
    "/etc/nginx/snippets/autobot-*" "/etc/logrotate.d/autobot-*"
)
# Data, credentials and state: only with --purge-data.
readonly DATA_PATHS=(
    "${AUTOBOT_BASE}" /etc/autobot /var/lib/autobot /var/lib/slm /var/lib/slm-agent
    /var/backups/autobot /var/backups/autobot-apt-sources
    /root/autobot-credentials.txt /root/slm-credentials.txt
)
readonly DATABASES=(slm slm_users autobot_users)
readonly DB_ROLES=(slm_app)
# PostgreSQL itself: only with --purge-data AND when it holds nothing but AutoBot's.
readonly POSTGRES_PACKAGES=("postgresql-*" "postgresql-contrib-*" postgresql-common)
# The client stays even then (KEPT_PACKAGES): other workloads use psql/pg_dump. `postgresql-*`
# also matches postgresql-client-NN, so plan_packages drops this family from every plan (#18761).
readonly POSTGRES_CLIENT_RE='^postgresql-client($|-)'
# Removed only once EMPTY after pg_dropcluster: /var/lib/postgresql is the postgres user's
# home (dumps, .pgpass, unregistered clusters live there).
readonly POSTGRES_PATHS=(/var/lib/postgresql /etc/postgresql)
readonly POSTGRES_APT_SOURCES=(pgdg)
# Shared software with no install record: only with --purge-shared.
readonly SHARED_PACKAGES=(python3-psycopg2 grafana prometheus "prometheus-node-exporter*" redis-stack-server)
# Packages the roles install that NO uninstall removes: general-purpose software the host or
# its operator may rely on, so taking it away could break something that is not AutoBot. Each
# group states why. Removed instead: the install record's packages, SHARED_PACKAGES with
# --purge-shared, POSTGRES_PACKAGES when PostgreSQL holds only AutoBot. The #18653 guard fails
# on a package a role installs that is in none of these lists.
readonly KEPT_PACKAGES=(
    # base OS tools and package plumbing -- every admin and many services use them
    apt-transport-https ca-certificates cron curl dnsutils git gnupg gzip htop iftop iotop iputils-ping
    logrotate lsb-release lsof net-tools netcat-openbsd nethogs nmap openssh-server openssl rsync
    software-properties-common strace sudo systemd tar traceroute tree unzip vim wget xz-utils zstd
    # host services an operator may run for other workloads too
    chkrootkit chrony containerd.io dnsmasq docker-buildx-plugin docker-ce docker-ce-cli
    docker-compose-plugin duplicity fail2ban nginx ntp ntpdate rkhunter supervisor systemd-timesyncd
    ufw unattended-upgrades xorgxrdp xrdp
    # build toolchain and development headers -- other software on the host builds with them
    build-essential cmake ninja-build pkg-config portaudio19-dev python3-dev tk-dev zlib1g-dev "lib*-dev"
    # language runtimes and their distro libraries
    ansible nodejs npm python3 python3-opencv python3-pip python3-prometheus-client python3-redis
    python3-tk python3-venv
    # desktop, VNC and browser stack, with the runtime libraries browsers load
    chromium-browser dbus-x11 firefox fluxbox tightvncserver "tigervnc-*" ubuntu-desktop-minimal
    websockify x11-apps x11-utils x11vnc xauth xfce4 xfce4-goodies xfce4-terminal xterm xvfb
    "libasound2*" "libatk*" libcups2 libdbus-1-3 libdrm2 libgbm1 libnspr4 libnss3 libxcomposite1
    libxdamage1 libxfixes3 libxkbcommon0 libxrandr2
    # media, speech and numeric libraries -- general purpose
    espeak-ng espeak-ng-data ffmpeg libsndfile1 tesseract-ocr
    # hardware drivers and vendor runtimes -- removing them can break the GPU or NPU for everything
    intel-driver-compiler-npu intel-opencl-icd level-zero "openvino-*"
    # clients of the shared services, and third-party CLIs from their own apt sources
    claude-code gh postgresql-client redis-tools
)
readonly SHARED_PATHS=(/var/lib/grafana /etc/grafana /var/log/grafana /var/lib/prometheus /etc/prometheus /opt/prometheus)
# Never removed: nginx and the base packages install.sh needs (git, curl, openssh-server, ...),
# and the service accounts the roles create (no record tells them from pre-existing ones).

log() { echo -e "$*" | tee -a "${LOG_FILE}"; }

record_values() {  # every value recorded under key $1
    [[ -f "${INSTALL_RECORD}" ]] || return 0
    sed -n "s/^$1=//p" "${INSTALL_RECORD}"
}

existing() {  # the arguments (globs expanded) that exist on this host, one per line
    local item path
    for item in "$@"; do
        # shellcheck disable=SC2086  # glob expansion is the point
        for path in ${item}; do [[ -e "${path}" || -L "${path}" ]] && echo "${path}"; done
    done
    return 0
}

psql_on() {  # psql_on <port> <db> <sql>: one value per line, non-zero if PostgreSQL did not answer
    sudo -u postgres psql -p "$1" -d "$2" -Atc "$3" 2>/dev/null
}

cluster_is_autobots() {  # cluster_is_autobots <port>: holds nothing but AutoBot's databases and roles
    local port="$1" db role tables listing names=()
    local own_dbs=" postgres template0 template1 ${DATABASES[*]} " own_roles=" postgres ${DB_ROLES[*]} "
    listing="$(psql_on "${port}" postgres "SELECT datname FROM pg_database")" || return 1
    mapfile -t names <<< "${listing}"
    for db in "${names[@]}"; do [[ -z "${db}" || "${own_dbs}" == *" ${db} "* ]] || return 1; done
    for db in postgres template1; do  # the owner's tables can live in the default databases too
        tables="$(psql_on "${port}" "${db}" "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind IN ('r','p','v','m','S','f') AND n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%'")" || return 1
        [[ "${tables}" == "0" ]] || return 1
    done
    listing="$(psql_on "${port}" postgres "SELECT rolname FROM pg_roles WHERE rolname !~ '^pg_'")" || return 1
    mapfile -t names <<< "${listing}"
    for role in "${names[@]}"; do [[ -z "${role}" || "${own_roles}" == *" ${role} "* ]] || return 1; done
    return 0
}

postgres_holds_only_autobot() {
    # Only a FULL inspection removes anything: no pg_lsclusters, a failing one, no cluster
    # listed, a cluster that is not online, or one that does not answer all mean "keep".
    command -v pg_lsclusters &>/dev/null && command -v psql &>/dev/null || return 1
    local listing ver name port status _
    listing="$(pg_lsclusters --no-header 2>/dev/null)" || return 1
    [[ -n "${listing}" ]] || return 1
    while read -r ver name port status _; do
        [[ "${status}" == online* ]] || return 1
        cluster_is_autobots "${port}" || return 1
    done <<< "${listing}"
    POSTGRES_CLUSTERS="${listing}"  # exactly what was inspected; drop_clusters drops only these
    return 0
}

plan_units() {
    local unit
    for unit in "${UNITS[@]}"; do
        [[ -e "/etc/systemd/system/${unit}" ]] && echo "${unit}"
    done
    # No matching unit makes systemctl exit 1; that is an empty answer, not a failure.
    { systemctl list-unit-files --no-legend "${UNIT_GLOBS[@]}" 2>/dev/null || true; } | awk '{print $1}'
    return 0
}

plan_packages() {  # the installed packages this run would purge
    local pkg wanted=()
    mapfile -t wanted < <(record_values package)
    ${PURGE_SHARED} && wanted+=("${SHARED_PACKAGES[@]}")
    [[ "${POSTGRES_DECISION}" == "remove" ]] && wanted+=("${POSTGRES_PACKAGES[@]}")
    for pkg in "${wanted[@]}"; do
        # dpkg-query exits 1 for a package that is not known here: not installed, not a failure.
        { dpkg-query -W -f='${Package} ${Status}\n' "${pkg}" 2>/dev/null || true; } | awk '/ installed$/{print $1}'
    done | awk -v keep="${POSTGRES_CLIENT_RE}" '$0 !~ keep' | sort -u
}

plan_purge_extra() {  # what apt would remove beyond plan_packages (reverse-dependents)
    local pkgs
    mapfile -t pkgs < <(plan_packages)
    [[ ${#pkgs[@]} -gt 0 ]] || return 0
    local simulated
    if ! simulated="$(apt-get -s purge "${pkgs[@]}" 2>/dev/null)"; then
        echo "(apt-get could not simulate this purge)"  # unknown is not "nothing else": skip
        return 0
    fi
    awk '/^Purg /{print $2}' <<< "${simulated}" | sort -u | comm -23 - <(printf '%s\n' "${pkgs[@]}")
}

plan_apt_sources() {
    local name names=("${APT_SOURCES[@]}")
    mapfile -t -O "${#names[@]}" names < <(record_values apt_source)
    [[ "${POSTGRES_DECISION}" == "remove" ]] && names+=("${POSTGRES_APT_SOURCES[@]}")
    for name in "${names[@]}"; do
        existing "/etc/apt/sources.list.d/${name}*.list" "/etc/apt/sources.list.d/${name}*.sources" \
                 "/etc/apt/sources.list.d/ppa_${name}_*.list" "/etc/apt/sources.list.d/*${name}*.list.distUpgrade"
    done
    existing /usr/share/keyrings/grafana.gpg /usr/share/keyrings/grafana.key
    [[ "${POSTGRES_DECISION}" == "remove" ]] && existing /usr/share/keyrings/pgdg.asc
    record_values apt_source | grep -qx nodesource && existing /usr/share/keyrings/nodesource.gpg
    return 0
}

opt_children() {  # every entry directly under /opt/autobot, hidden ones included
    local child
    for child in "${AUTOBOT_BASE}"/* "${AUTOBOT_BASE}"/.[!.]*; do
        [[ -e "${child}" || -L "${child}" ]] && echo "${child}"
    done
    return 0
}

nested_data_in() {  # nested_data_in <code dir>: its kept data -- OPT_NESTED_DATA plus every .env
    local rel
    {
        for rel in "${OPT_NESTED_DATA[@]}"; do
            [[ "${rel%%/*}" == "${1##*/}" ]] && existing "${AUTOBOT_BASE}/${rel}"
        done
        [[ -d "$1" ]] && find "$1" \( -name '.env' -o -name '.env.*' -o -name '*.env' \) \( -type f -o -type l \) -print 2>/dev/null
    } | sort -u
    return 0
}

is_code_child() { [[ " ${OPT_CODE[*]} " == *" ${1##*/} "* ]]; }

plan_opt_code() {  # AutoBot code children removed WHOLE -- allow-list, never "the rest"
    ${PURGE_DATA} && return 0  # the whole tree goes with DATA_PATHS
    local child
    while read -r child; do
        [[ -n "${child}" ]] && is_code_child "${child}" && [[ -z "$(nested_data_in "${child}")" ]] && echo "${child}"
    done < <(opt_children)
    return 0
}

plan_opt_partial() {  # code children that hold data: their code goes, the data inside stays
    ${PURGE_DATA} && return 0
    local child
    while read -r child; do
        [[ -n "${child}" ]] && is_code_child "${child}" && [[ -n "$(nested_data_in "${child}")" ]] && echo "${child}"
    done < <(opt_children)
    return 0
}

remove_code_keeping_data() {  # remove_code_keeping_data <code dir>: everything but its nested data
    local dir="$1" path keep skip
    local keeps=()
    mapfile -t keeps < <(nested_data_in "${dir}")
    while IFS= read -r -d '' path; do
        skip=false
        for keep in "${keeps[@]}"; do
            # the kept path itself, anything inside it, and the directories leading to it stay
            if [[ "${path}" == "${keep}" || "${path}" == "${keep}/"* || "${keep}" == "${path}/"* ]]; then skip=true; break; fi
        done
        if ! ${skip}; then rm -rf -- "${path}" || log "  WARNING: could not remove ${path}"; fi
    done < <(find "${dir}" -mindepth 1 -depth -print0)
    for keep in "${keeps[@]}"; do log "  KEPT ${keep} (data inside ${dir##*/})"; done
    return 0
}

plan_opt_kept() {  # what a default uninstall leaves in /opt/autobot
    ${PURGE_DATA} && return 0
    local child
    while read -r child; do
        [[ -z "${child}" ]] && continue
        if is_code_child "${child}"; then nested_data_in "${child}"; else echo "${child}"; fi
    done < <(opt_children)
    return 0
}

plan_paths() {
    existing "${PATHS[@]}" "${PATH_GLOBS[@]}" "${UNIT_DROPINS[@]}"
    plan_opt_code
    ${PURGE_DATA} && existing "${DATA_PATHS[@]}"
    ${PURGE_SHARED} && existing "${SHARED_PATHS[@]}"
    return 0
}

plan_sudoers() {
    local name path
    for name in "${SUDOERS[@]}"; do existing "/etc/sudoers.d/${name}"; done
    record_values created_sudoers | while read -r path; do existing "${path}"; done
}

plan_users() {  # accounts AutoBot provably created -- never one found by name alone
    local user marker gecos
    for user in $(record_values created_user); do id "${user}" &>/dev/null && echo "${user}"; done
    if id "${ADMIN_ACCOUNT}" &>/dev/null; then
        gecos="$(getent passwd "${ADMIN_ACCOUNT}" | cut -d: -f5)"
        for marker in "${ADMIN_MARKERS[@]}"; do [[ "${gecos}" == "${marker}" ]] && echo "${ADMIN_ACCOUNT}"; done
    fi
    return 0
}

print_plan() {
    local extra
    extra="$(plan_purge_extra | tr '\n' ' ')"
    log "This removes, from $(hostname):"
    log "  units:        $(plan_units | tr '\n' ' ')"
    log "  packages:     $(plan_packages | tr '\n' ' ')"
    [[ -n "${extra// }" ]] && log "  !! apt would ALSO remove: ${extra}-- so the purge will be SKIPPED"
    log "  apt sources:  $(plan_apt_sources | tr '\n' ' ')"
    log "  sudoers:      $(plan_sudoers | tr '\n' ' ')"
    log "  paths:        $(plan_paths | tr '\n' ' ')"
    if ${PURGE_DATA}; then
        log "  databases:    ${DATABASES[*]} (role ${DB_ROLES[*]})"
        [[ -d "${AUTOBOT_BASE}" ]] && log "  ${AUTOBOT_BASE}: the WHOLE tree, including anything else in it: $(opt_children | tr '\n' ' ')"
        log "  accounts:     $(plan_users | tr '\n' ' ')"
        log "  PostgreSQL:   $([[ "${POSTGRES_DECISION}" == "remove" ]] && echo "holds only AutoBot's -- removed too" || echo "KEPT (holds data that is not AutoBot's, or could not be fully inspected)")"
    else
        log "  KEPT (data):  databases ${DATABASES[*]}, accounts $(plan_users | tr '\n' ' '), $(existing "${DATA_PATHS[@]:1}" | tr '\n' ' ')-- add --purge-data to remove"
        log "  KEPT in ${AUTOBOT_BASE} (data, or not AutoBot code): $(plan_opt_kept | tr '\n' ' ')"
        log "  code removed AROUND the data kept inside: $(plan_opt_partial | tr '\n' ' ')"
    fi
    ${PURGE_SHARED} || log "  KEPT (shared): ${SHARED_PACKAGES[*]} and their data -- add --purge-shared to remove"
    [[ -f "${INSTALL_RECORD}" ]] || log "  (no install record at ${INSTALL_RECORD}: no account, recorded package or recorded apt source is removed)"
    log "Never removed: general-purpose packages (KEPT_PACKAGES in this script), ${KEPT_UNITS[*]}, apt sources ${KEPT_APT_SOURCES[*]}, role service accounts."
}

confirm() {
    ${CONFIRM_YES} && return 0
    local fd answer=""
    # Read the terminal, not stdin, and REFUSE without one: proceeding unconfirmed would be
    # a destructive wipe nobody approved (#17929's fail-closed rule for this prompt).
    if ! { exec {fd}</dev/tty; } 2>/dev/null || ! IFS= read -r -p "Type 'UNINSTALL' to confirm: " answer <&"${fd}"; then
        log "No terminal available to confirm an uninstall. Re-run with --yes if you intend to uninstall non-interactively."
        exit 1
    fi
    exec {fd}<&-
    [[ "${answer}" == "UNINSTALL" ]] || { log "Uninstall cancelled."; exit 0; }
}

warn_on_fail() {  # warn_on_fail <what> <command...>: run it; a failure warns and the run goes on
    local what="$1"; shift
    "$@" >>"${LOG_FILE}" 2>&1 || log "  WARNING: ${what} failed; see ${LOG_FILE}"
}

remove_units() {
    local unit
    for unit in $(plan_units); do
        systemctl disable --now "${unit}" >>"${LOG_FILE}" 2>&1 || true  # a unit that is not running is not an error
        rm -f "/etc/systemd/system/${unit}" && log "  removed unit ${unit}"
    done
    warn_on_fail "removing slm.target.wants" rm -rf /etc/systemd/system/slm.target.wants
    warn_on_fail "removing dangling autobot-* unit links" find /etc/systemd/system -xtype l -name 'autobot-*' -delete
    warn_on_fail "systemctl daemon-reload" systemctl daemon-reload
}

drop_databases() {
    command -v psql &>/dev/null || { log "  PostgreSQL not installed -- no databases to drop"; return 0; }
    systemctl start postgresql >>"${LOG_FILE}" 2>&1 || true  # already gone with its unit is fine
    local db role
    for db in "${DATABASES[@]}"; do
        if sudo -u postgres dropdb --if-exists "${db}" >>"${LOG_FILE}" 2>&1; then log "  dropped database ${db}"
        else log "  WARNING: could not drop database ${db}; see ${LOG_FILE}"; fi
    done
    for role in "${DB_ROLES[@]}"; do
        if sudo -u postgres dropuser --if-exists "${role}" >>"${LOG_FILE}" 2>&1; then log "  dropped role ${role}"
        else log "  WARNING: could not drop role ${role}; see ${LOG_FILE}"; fi
    done
    return 0
}

drop_clusters() {  # the clusters inspected at decision time -- never one created since
    [[ "${POSTGRES_DECISION}" == "remove" ]] || return 0
    local ver name _ dir
    while read -r ver name _; do
        [[ -n "${ver}" ]] || continue
        if pg_dropcluster --stop "${ver}" "${name}" >>"${LOG_FILE}" 2>&1; then log "  dropped cluster ${ver}/${name}"
        else log "  WARNING: could not drop cluster ${ver}/${name}; see ${LOG_FILE}"; fi
    done <<< "${POSTGRES_CLUSTERS}"
    for dir in "${POSTGRES_PATHS[@]}"; do  # only empty directories go
        if [[ -d "${dir}" ]]; then
            find "${dir}" -depth -type d -empty -delete 2>>"${LOG_FILE}" || log "  WARNING: could not prune empty directories in ${dir}"
        fi
        [[ -e "${dir}" ]] && log "  kept ${dir} (not empty after dropping the clusters)"
    done
    return 0
}

purge_packages() {
    local pkgs extra
    mapfile -t pkgs < <(plan_packages)
    [[ ${#pkgs[@]} -gt 0 ]] || return 0
    extra="$(plan_purge_extra | tr '\n' ' ')"
    if [[ -n "${extra// }" ]]; then
        log "  WARNING: purge SKIPPED -- apt would also remove ${extra}(not AutoBot's). Kept: ${pkgs[*]}"
        return 0
    fi
    if env DEBIAN_FRONTEND=noninteractive apt-get purge -y -qq "${pkgs[@]}" >>"${LOG_FILE}" 2>&1; then
        log "  purged ${pkgs[*]}"
    else
        log "  WARNING: apt-get purge failed for ${pkgs[*]}; see ${LOG_FILE}"
    fi
}

remove_files() {
    local path paths
    mapfile -t paths < <(plan_apt_sources; plan_paths)
    for path in "${paths[@]}"; do
        if rm -rf -- "${path}"; then log "  removed ${path}"; else log "  WARNING: could not remove ${path}"; fi
    done
    mapfile -t paths < <(plan_opt_partial)
    for path in "${paths[@]}"; do remove_code_keeping_data "${path}"; done
    return 0
}

remove_sudoers() {
    local path paths
    mapfile -t paths < <(plan_sudoers)
    for path in "${paths[@]}"; do rm -f -- "${path}" && log "  removed ${path}"; done
    visudo -c >>"${LOG_FILE}" 2>&1 || log "  WARNING: visudo reports a problem; check /etc/sudoers.d"
    return 0
}

remove_users() {  # $1: the accounts, read before /etc/autobot (and its record) is gone
    local user
    for user in $1; do
        if userdel -r "${user}" >>"${LOG_FILE}" 2>&1; then log "  removed account ${user}"
        else log "  WARNING: could not remove account ${user} (running processes?)"; fi
    done
    return 0
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run)      DRY_RUN=true ;;
            --yes|-y)       CONFIRM_YES=true ;;
            --purge-data)   PURGE_DATA=true ;;
            --purge-shared) PURGE_SHARED=true ;;
            *) echo "Unknown option: $1 (use --dry-run, --yes, --purge-data, --purge-shared)" >&2; exit 2 ;;
        esac
        shift
    done
}

main() {
    DRY_RUN=false CONFIRM_YES=false PURGE_DATA=false PURGE_SHARED=false POSTGRES_DECISION=keep POSTGRES_CLUSTERS=""
    parse_args "$@"
    [[ ${EUID} -eq 0 ]] || { echo "Run as root (sudo)." >&2; exit 1; }
    # Decided ONCE, before anything changes: after a purge psql is gone and could not re-decide.
    if ${PURGE_DATA} && postgres_holds_only_autobot; then POSTGRES_DECISION=remove; fi
    print_plan
    ${DRY_RUN} && { log "Dry run: nothing was removed. Log: ${LOG_FILE}"; exit 0; }
    confirm
    local users=""
    ${PURGE_DATA} && users="$(plan_users)"
    remove_units
    ${PURGE_DATA} && drop_databases
    drop_clusters
    purge_packages
    remove_sudoers
    remove_users "${users}"
    remove_files
    log "AutoBot has been removed. Kept items are listed above. Log: ${LOG_FILE}"
}

main "$@"
