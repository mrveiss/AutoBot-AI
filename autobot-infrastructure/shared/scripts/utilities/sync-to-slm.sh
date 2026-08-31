#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss

# SLM Management Plane Sync & Deploy Script (Issue #814)
#
# Phase 1: Rsync code to the SLM server (${AUTOBOT_SLM_HOST})
# Phase 2: Run Ansible playbook to configure services (certs, nginx, build, systemd)
#
# The SLM then handles distributing code to fleet nodes via its code-sync agents.
#
# Usage: ./sync-to-slm.sh [OPTIONS]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/../lib/ssot-config.sh" || {
    echo "FATAL: ${SCRIPT_DIR}/../lib/ssot-config.sh could not be sourced -- refusing to run on hardcoded config fallbacks (#14172)" >&2
    return 1 2>/dev/null || exit 1
}
# #14459: pure classify_db_update_result() -- no ssh/psql/rsync in this file.
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/../lib/db-update-classify.sh" || {
    echo "FATAL: ${SCRIPT_DIR}/../lib/db-update-classify.sh could not be sourced -- refusing to run without it (#14172)" >&2
    return 1 2>/dev/null || exit 1
}

# Configuration (from SSOT)
REMOTE_HOST="${AUTOBOT_SLM_HOST:-localhost}"
REMOTE_USER="${AUTOBOT_SSH_USER:-autobot}"
# #9956: SLM manager DB node_id is overridable — deployments may rename the
# node. Defaults to the inventory default (slm_server host in slm-nodes.yml).
SLM_NODE_ID="${AUTOBOT_SLM_NODE_ID:-00-SLM-Manager}"
# #14459: this value ends up embedded in a remote SSH command string that is
# parsed twice (once here, once by the remote shell). Constrain it to what a
# `nodes.node_id` value actually looks like (see models/database.py,
# VARCHAR(64)) before it ever reaches that string — same approach #14173 used
# for AUTOBOT_USER ahead of a sudoers heredoc.
if ! [[ "${SLM_NODE_ID}" =~ ^[A-Za-z0-9_-]{1,64}$ ]]; then
    echo "❌ Invalid AUTOBOT_SLM_NODE_ID: '${SLM_NODE_ID}' is not a valid node id" >&2
    exit 1
fi
SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"
SSH_OPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"

# Local paths
SLM_BACKEND_LOCAL="$PROJECT_ROOT/autobot-slm-backend"
SLM_FRONTEND_LOCAL="$PROJECT_ROOT/autobot-slm-frontend"
SHARED_LIB_LOCAL="$PROJECT_ROOT/autobot_shared"

# Ansible paths
ANSIBLE_DIR="$SLM_BACKEND_LOCAL/ansible"
ANSIBLE_INVENTORY="$ANSIBLE_DIR/inventory/slm-nodes.yml"
ANSIBLE_PLAYBOOK="$ANSIBLE_DIR/playbooks/deploy-slm-manager.yml"

# Remote paths (match systemd service and nginx config)
REMOTE_BASE="/opt/autobot"
SLM_BACKEND_REMOTE="$REMOTE_BASE/autobot-slm-backend"
SLM_FRONTEND_REMOTE="$REMOTE_BASE/autobot-slm-frontend"
SHARED_LIB_REMOTE="$REMOTE_BASE/autobot_shared"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

rsync_cmd() {
    if [ -f "$SSH_KEY" ]; then
        rsync -avz --delete -e "ssh -i $SSH_KEY $SSH_OPTS" "$@"
    else
        rsync -avz --delete -e "ssh $SSH_OPTS" "$@"
    fi
}

show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Syncs code to SLM server, then runs Ansible to configure services."
    echo ""
    echo "Options:"
    echo "  (none)       Sync files only (no Ansible)"
    echo "  --deploy     Sync + run full Ansible playbook (recommended)"
    echo "  --tags TAGS  Sync + run Ansible with specific tags"
    echo "               Tags: packages, tls, backend, frontend, nginx, service"
    echo "  --sync-only  Sync files only (same as no option)"
    echo "  --help       Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 --deploy                    # Full deploy (sync + ansible)"
    echo "  $0 --tags frontend,nginx       # Rebuild frontend + reload nginx"
    echo "  $0 --tags tls                  # Regenerate TLS certs only"
    echo "  $0 --tags backend,service      # Update backend + restart service"
}

# Parse options
ACTION="sync-only"
ANSIBLE_TAGS=""
case "${1:-}" in
    --help|-h) show_usage; exit 0 ;;
    --deploy) ACTION="deploy" ;;
    --tags)
        ACTION="deploy"
        ANSIBLE_TAGS="${2:-}"
        if [ -z "$ANSIBLE_TAGS" ]; then
            log_error "Missing tags argument. Usage: $0 --tags frontend,nginx"
            exit 1
        fi
        ;;
    --sync-only|"") ACTION="sync-only" ;;
    *)
        log_error "Unknown option: $1"
        show_usage
        exit 1
        ;;
esac

echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}     SLM Management Plane Deployment        ${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo "Target:     $REMOTE_USER@$REMOTE_HOST"
echo "Components: autobot-slm-backend, autobot-slm-frontend, autobot_shared"
echo "Remote:     $REMOTE_BASE/"
echo "Action:     $ACTION"
[ -n "$ANSIBLE_TAGS" ] && echo "Tags:       $ANSIBLE_TAGS"
echo ""

# ===== Phase 1: Rsync code =====

log_step "Checking connectivity to $REMOTE_HOST..."
if ! ping -c 1 -W 2 "$REMOTE_HOST" > /dev/null 2>&1; then
    log_error "Cannot reach $REMOTE_HOST"
    exit 1
fi
log_info "Host reachable"

# Sync autobot_shared (backend dependency)
echo ""
log_step "Syncing autobot_shared..."
rsync_cmd \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.git/' \
    "$SHARED_LIB_LOCAL/" \
    "$REMOTE_USER@$REMOTE_HOST:$SHARED_LIB_REMOTE/"
log_info "Shared lib synced"

# Sync SLM backend (exclude ansible dir - it stays local for running playbooks)
echo ""
log_step "Syncing autobot-slm-backend..."
rsync_cmd \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.git/' \
    --exclude '*.log' \
    --exclude 'venv/' \
    --exclude '.venv/' \
    --exclude '*.db' \
    --exclude '.env.local' \
    --exclude 'ansible/' \
    "$SLM_BACKEND_LOCAL/" \
    "$REMOTE_USER@$REMOTE_HOST:$SLM_BACKEND_REMOTE/"
log_info "Backend synced"

# Sync SLM frontend (source, not dist - Ansible will build)
echo ""
log_step "Syncing autobot-slm-frontend..."
rsync_cmd \
    --exclude 'node_modules/' \
    --exclude 'dist/' \
    --exclude '.git/' \
    --exclude '*.log' \
    "$SLM_FRONTEND_LOCAL/" \
    "$REMOTE_USER@$REMOTE_HOST:$SLM_FRONTEND_REMOTE/"
log_info "Frontend synced"

# ===== Update Database Version =====

# Get current commit hash (Issue #885)
echo ""
log_step "Updating SLM node version in database..."
CURRENT_COMMIT=$(git -C "$PROJECT_ROOT" log --oneline -1 --format='%h' 2>/dev/null || echo "unknown")

# #14459: code_version/code_status are the only view an operator has of what
# is running on a node without logging into it, so a failed or no-op UPDATE
# here must never look like success. Three outcomes are distinguished below
# (row updated / no row matched / command failed); the last two are always
# logged with log_error, naming the node id, because "the row is now wrong"
# is true in both cases.
#
# Deliberately NOT fatal: by this point rsync has already copied the code,
# and (on --deploy) Ansible still needs to run. Aborting the whole deploy
# over a status-table write would block a deploy that otherwise succeeded.
# Instead the failure is loud at the point it happens, repeated in the final
# summary, and the script's own exit code reflects it — so both an operator
# watching the output and anything scripting around this tool can tell the
# row is stale.
DB_UPDATE_FAILED=0

if [ "$CURRENT_COMMIT" != "unknown" ]; then
    # Note: sources /etc/autobot/db-credentials.env on the remote host for
    # postgres credentials.
    #
    # `psql -c` does NOT process psql-specific syntax: psql(1) requires a
    # -c argument to be "completely parsable by the server", so a :'var'
    # reference inside -c is a syntax error on the server, not a
    # client-side substitution (caught in review -- reproduced against a
    # scratch Postgres, every -c call failed before it could report a row
    # count). The SQL is instead sent over psql's STDIN, exactly like -f,
    # where :'var' interpolation actually runs client-side; ssh forwards
    # this command's stdin to the remote process since no pty is allocated.
    #
    # SLM_NODE_ID and CURRENT_COMMIT reach the remote host through a single
    # ssh command string, parsed TWICE — once by this shell building the
    # string, once by the remote shell executing it. Two independent
    # defenses, since either value could otherwise break out at either
    # layer:
    #   1. Both values are passed as psql variables (-v) and referenced in
    #      the SQL text (sent over stdin, below) with the quoting form
    #      :'var', never concatenated into the SQL string, so neither can
    #      break out of the SQL literal.
    #   2. The psql invocation is shell-escaped with `printf %q` before it
    #      is embedded in the ssh command string, so the remote shell sees
    #      exactly the intended tokens rather than a second round of
    #      word-splitting. SLM_NODE_ID is additionally validated above
    #      against a fixed character set.
    REMOTE_PSQL_CMD=(
        psql -h 127.0.0.1 -U slm_app -d slm
        -v "ON_ERROR_STOP=1"
        -v "node_id=${SLM_NODE_ID}"
        -v "commit=${CURRENT_COMMIT}"
    )
    REMOTE_PSQL_CMD_STR=$(printf '%q ' "${REMOTE_PSQL_CMD[@]}")

    set +e
    DB_UPDATE_OUTPUT=$(ssh ${SSH_KEY:+-i "$SSH_KEY"} $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" \
        "source /etc/autobot/db-credentials.env 2>/dev/null && PGPASSWORD=\$SLM_DB_PASSWORD $REMOTE_PSQL_CMD_STR" <<'REMOTE_SQL' 2>&1
UPDATE nodes SET code_version = :'commit', code_status = 'UP_TO_DATE', updated_at = NOW() WHERE node_id = :'node_id';
REMOTE_SQL
)
    DB_UPDATE_EXIT=$?
    set -e

    DB_UPDATE_RESULT=$(classify_db_update_result "$DB_UPDATE_EXIT" "$DB_UPDATE_OUTPUT")
    case "$DB_UPDATE_RESULT" in
        failed)
            log_error "Database update FAILED for node '$SLM_NODE_ID' (ssh/psql exit $DB_UPDATE_EXIT):"
            log_error "$DB_UPDATE_OUTPUT"
            log_error "code_version/code_status for '$SLM_NODE_ID' is now STALE — code is deployed but the row was not updated."
            DB_UPDATE_FAILED=1
            ;;
        no_match)
            log_error "Database update matched NO ROW for node_id '$SLM_NODE_ID' — the row is now STALE."
            log_error "Likely cause: the node was renamed (#9956) and AUTOBOT_SLM_NODE_ID no longer matches any row in 'nodes'."
            DB_UPDATE_FAILED=1
            ;;
        updated)
            log_info "Database updated: $SLM_NODE_ID → $CURRENT_COMMIT"
            ;;
    esac
else
    log_error "Could not determine current commit — code_version/code_status for '$SLM_NODE_ID' was NOT updated and is now STALE."
    DB_UPDATE_FAILED=1
fi

# ===== Phase 2: Run Ansible =====

if [ "$ACTION" = "deploy" ]; then
    echo ""
    echo -e "${BLUE}--------------------------------------------${NC}"
    echo -e "${BLUE}     Running Ansible Playbook               ${NC}"
    echo -e "${BLUE}--------------------------------------------${NC}"
    echo ""

    # Verify ansible-playbook is available locally
    if ! command -v ansible-playbook &> /dev/null; then
        log_error "ansible-playbook not found. Install: sudo apt install ansible"
        exit 1
    fi

    # Verify inventory and playbook exist
    if [ ! -f "$ANSIBLE_INVENTORY" ]; then
        log_error "Inventory not found: $ANSIBLE_INVENTORY"
        exit 1
    fi
    if [ ! -f "$ANSIBLE_PLAYBOOK" ]; then
        log_error "Playbook not found: $ANSIBLE_PLAYBOOK"
        exit 1
    fi

    # Build ansible command (run from ansible/ dir so ansible.cfg is picked up)
    # Per-user local tmp (#10006): a fixed shared /tmp path is created mode
    # 0700 by whichever user runs ansible first, locking out every other user.
    export ANSIBLE_LOCAL_TEMP="${HOME}/.ansible/tmp"

    ANSIBLE_CMD=(
        ansible-playbook
        -i "inventory/slm-nodes.yml"
        "playbooks/deploy-slm-manager.yml"
    )

    # Add SSH key if available
    if [ -f "$SSH_KEY" ]; then
        ANSIBLE_CMD+=(--private-key "$SSH_KEY")
    fi

    # Add tags if specified
    if [ -n "$ANSIBLE_TAGS" ]; then
        ANSIBLE_CMD+=(--tags "$ANSIBLE_TAGS")
        log_step "Running playbook with tags: $ANSIBLE_TAGS"
    else
        log_step "Running full playbook..."
    fi

    # Execute from ansible dir so ansible.cfg roles_path works
    (cd "$ANSIBLE_DIR" && "${ANSIBLE_CMD[@]}")

    echo ""
    log_info "Ansible playbook completed"
fi

# ===== Summary =====

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}           Sync Complete!                   ${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

if [ "$ACTION" = "sync-only" ]; then
    echo "Files synced. To configure services, run:"
    echo ""
    echo "  $0 --deploy                    # Full deploy"
    echo "  $0 --tags frontend,nginx       # Build frontend + nginx"
    echo "  $0 --tags tls                  # Generate TLS certs"
    echo "  $0 --tags backend,service      # Backend + restart"
else
    echo "Deployment complete. Useful commands:"
    echo ""
    echo "  View backend logs:"
    echo "    ssh $REMOTE_USER@$REMOTE_HOST 'journalctl -u autobot-slm-backend -f'"
    echo ""
    echo "  View nginx logs:"
    echo "    ssh $REMOTE_USER@$REMOTE_HOST 'tail -f /opt/autobot/logs/nginx-error.log'"
fi
echo ""

if [ "$DB_UPDATE_FAILED" -eq 1 ]; then
    log_error "Code was synced, but the SLM database status row for node '$SLM_NODE_ID' is STALE."
    log_error "code_version/code_status will not reflect this deploy until that row is corrected."
    exit 1
fi
