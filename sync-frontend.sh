#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot Frontend Sync Script
# Builds Vue.js frontend and deploys to native VM

set -e  # Exit on any error

# #13149: the "Expected:" hint below named the deployed install rather than
# the tree this script actually runs in, sending anyone who hit it to the wrong
# directory. PROJECT_ROOT comes from the shared resolver.
# shellcheck source=scripts/lib/project_root.sh
source "$(dirname "${BASH_SOURCE[0]}")/scripts/lib/project_root.sh"

# Source SSOT configuration (#808)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=autobot-infrastructure/shared/scripts/lib/ssot-config.sh
source "${SCRIPT_DIR}/autobot-infrastructure/shared/scripts/lib/ssot-config.sh" || {
    echo "FATAL: ${SCRIPT_DIR}/autobot-infrastructure/shared/scripts/lib/ssot-config.sh could not be sourced -- refusing to run on hardcoded config fallbacks (#14172)" >&2
    return 1 2>/dev/null || exit 1
}

# Production-mode target: the SLM frontend host, addressed the same way every
# other script in this family does (AUTOBOT_FRONTEND_HOST/AUTOBOT_SSH_USER/
# AUTOBOT_SSH_KEY, exported by ssot-config.sh) rather than the ansible ad-hoc
# inventory this script used to depend on -- see the production branch below
# for why (#15659).
REMOTE_BASE="${AUTOBOT_BASE_DIR:-/opt/autobot}"
REMOTE_FRONTEND_DIR="${REMOTE_BASE}/autobot-slm-frontend"
SSH_TARGET="${AUTOBOT_SSH_USER}@${AUTOBOT_FRONTEND_HOST}"
SSH_KEY_OPTS=(-i "${AUTOBOT_SSH_KEY}" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔧 AutoBot Frontend Sync${NC}"
echo "=================================="

# Parse command line arguments
DEV_MODE=false
if [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]]; then
    echo -e "${BLUE}AutoBot Frontend Sync Script${NC}"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --dev         Development mode: Sync source files (fast, hot reload)"
    echo "  --restart     Production mode + restart frontend server"
    echo "  (no flags)    Production mode: Build and deploy"
    echo "  --help, -h    Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                # Production build and deploy"
    echo "  $0 --dev         # Development source sync (recommended for development)"
    echo "  $0 --restart     # Production build + server restart"
    exit 0
elif [[ "$1" == "--dev" ]]; then
    DEV_MODE=true
    echo -e "${YELLOW}🧪 Development mode: Syncing source files${NC}"
else
    echo -e "${BLUE}🏭 Production mode: Building and deploying${NC}"
fi

# Check if we're in the right directory
if [[ ! -f "autobot-slm-frontend/package.json" ]]; then
    echo -e "${RED}❌ Error: Must run from AutoBot root directory${NC}"
    echo "Current directory: $(pwd)"
    echo "Expected: ${PROJECT_ROOT}"
    exit 1
fi

# Show current git status for context
if git status &>/dev/null; then
    echo -e "${BLUE}Git status:${NC}"
    git status --porcelain | head -5
    echo ""
fi

if [[ "$DEV_MODE" == "true" ]]; then
    # Development mode: Sync source files
    echo -e "${YELLOW}📁 Syncing source files to frontend VM...${NC}"
    start_time=$(date +%s)

    if ./scripts/utilities/sync-to-vm.sh frontend autobot-slm-frontend/src/ "/home/${AUTOBOT_SSH_USER}/autobot-slm-frontend/src/"; then
        end_time=$(date +%s)
        sync_time=$((end_time - start_time))
        echo -e "${GREEN}✅ Source sync completed in ${sync_time}s${NC}"
    else
        echo -e "${RED}❌ Source sync failed${NC}"
        exit 1
    fi

    # Check if dependencies need repopulation
    echo -e "${YELLOW}🔍 Checking dependencies status...${NC}"
    if ssh -i "${AUTOBOT_SSH_KEY}" "${AUTOBOT_SSH_USER}@${AUTOBOT_FRONTEND_HOST}" "test -f /home/${AUTOBOT_SSH_USER}/autobot-slm-frontend/node_modules/.vite/deps/vue.js" 2>/dev/null; then
        echo -e "${GREEN}✅ Dependencies are current, skipping sync${NC}"
    else
        echo -e "${YELLOW}📦 Dependencies missing or outdated, syncing...${NC}"
        if ./scripts/utilities/sync-to-vm.sh frontend autobot-slm-frontend/node_modules/ "/home/${AUTOBOT_SSH_USER}/autobot-slm-frontend/node_modules/"; then
            echo -e "${GREEN}✅ Dependencies sync completed${NC}"
        else
            echo -e "${RED}❌ Dependencies sync failed${NC}"
            exit 1
        fi
    fi

    # Skip production deployment in dev mode
    echo -e "${GREEN}🎉 Development sync completed!${NC}"
    echo "=================================="
    echo -e "${BLUE}Summary:${NC}"
    echo "  • Mode: 🧪 Development source sync"
    echo "  • Target: Frontend VM (${AUTOBOT_FRONTEND_HOST:-localhost})"
    echo "  • Status: ✅ Source files synced"
    echo ""
    echo -e "${BLUE}Next steps:${NC}"
    echo "  • Frontend dev server will auto-reload changes"
    echo "  • Open browser: http://${AUTOBOT_FRONTEND_HOST:-localhost}:${AUTOBOT_FRONTEND_PORT:-5173}"
    echo "  • Check console for any errors"
    exit 0
else
    # Production mode: build AND publish on the SLM frontend host itself, by
    # installing and running the SAME helper bootstrap-slm.sh installs
    # (autobot-infrastructure/autobot-slm-frontend/templates/
    # build-publish-slm-frontend.sh) -- not a second copy of the build:slm /
    # atomic-flip idiom (#15650, #15689, #15659).
    #
    # This script used to build locally with a plain `npm run build` (the
    # wrong script, #9563/#9710/#10435) and publish by having
    # `ansible ... -i ansible/inventory/production.yml -m copy` push the
    # result straight into /var/www/html -- the unstaged shape #15557/#15610
    # replaced everywhere else, over an inventory path that was deleted from
    # this repository in 2026-02 (#781) and could not have resolved since.
    # The SLM frontend is not served from /var/www/html; nginx serves
    # `${REMOTE_FRONTEND_DIR}/current` (roles/slm_manager/templates and
    # autobot-infrastructure/autobot-slm-frontend/templates/autobot-slm.conf
    # agree on that path), so publishing is done the same way bootstrap does
    # it: directly over SSH to the host named by AUTOBOT_FRONTEND_HOST.
    echo -e "${YELLOW}🚀 Deploying frontend to ${SSH_TARGET}...${NC}"

    if ! ssh "${SSH_KEY_OPTS[@]}" "${SSH_TARGET}" "echo ok" > /dev/null 2>&1; then
        echo -e "${RED}❌ Error: cannot reach ${SSH_TARGET} over SSH${NC}"
        exit 1
    fi

    echo "  📤 Syncing source to ${SSH_TARGET}:${REMOTE_FRONTEND_DIR}..."
    if ! ssh "${SSH_KEY_OPTS[@]}" "${SSH_TARGET}" "mkdir -p ${REMOTE_FRONTEND_DIR}"; then
        echo -e "${RED}❌ Could not create ${REMOTE_FRONTEND_DIR} on ${SSH_TARGET}${NC}"
        exit 1
    fi
    if ! rsync -avz --delete \
        --exclude 'node_modules' --exclude 'dist' --exclude 'dist-*' \
        --exclude 'current' --exclude 'previous' --exclude '.git' \
        -e "ssh ${SSH_KEY_OPTS[*]}" \
        autobot-slm-frontend/ "${SSH_TARGET}:${REMOTE_FRONTEND_DIR}/" > /dev/null; then
        echo -e "${RED}❌ Source sync failed${NC}"
        exit 1
    fi
    echo -e "${GREEN}  ✅ Source synced${NC}"

    echo "  📄 Installing build+publish helper..."
    if ! ssh "${SSH_KEY_OPTS[@]}" "${SSH_TARGET}" \
        "cat > ${REMOTE_FRONTEND_DIR}/build-publish.sh && chmod +x ${REMOTE_FRONTEND_DIR}/build-publish.sh" \
        < autobot-infrastructure/autobot-slm-frontend/templates/build-publish-slm-frontend.sh; then
        echo -e "${RED}❌ Could not install the build+publish helper on ${SSH_TARGET}${NC}"
        exit 1
    fi

    echo "  🔧 Installing npm dependencies on remote..."
    if ! ssh "${SSH_KEY_OPTS[@]}" "${SSH_TARGET}" "cd ${REMOTE_FRONTEND_DIR} && npm install --silent"; then
        echo -e "${RED}❌ Remote npm install failed${NC}"
        exit 1
    fi

    echo "  🏗️  Building (build:slm) and publishing (atomic flip)..."
    if ! ssh "${SSH_KEY_OPTS[@]}" "${SSH_TARGET}" \
        "cd ${REMOTE_FRONTEND_DIR} && SLM_FRONTEND_RELEASE_KEEP=\"${SLM_FRONTEND_RELEASE_KEEP:-3}\" ./build-publish.sh"; then
        echo -e "${RED}❌ Build failed -- current was not touched, the previous bundle is still being served${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Frontend built and published${NC}"
fi

# Step 2: Test backend connectivity
echo -e "${YELLOW}🔍 Testing backend connectivity...${NC}"
if ssh "${SSH_KEY_OPTS[@]}" "${AUTOBOT_SSH_USER}@${AUTOBOT_BACKEND_HOST}" \
    "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:${AUTOBOT_BACKEND_PORT}/api/system/health" 2>/dev/null \
    | grep -q "200"; then
    echo -e "${GREEN}✅ Backend is healthy${NC}"
else
    echo -e "${YELLOW}⚠️  Warning: Backend may not be responding${NC}"
fi

# Optional: restart nginx. Never required after a publish -- an atomic
# symlink flip is visible to nginx on the very next request with no reload
# (#15610) -- but kept for the case where nginx itself, not the bundle,
# needs to pick up a change (e.g. a certificate refresh).
if [[ "$1" == "--restart" ]] || [[ "$1" == "-r" ]]; then
    echo -e "${YELLOW}  🔄 Restarting nginx on ${SSH_TARGET}...${NC}"
    if ssh "${SSH_KEY_OPTS[@]}" "${SSH_TARGET}" "sudo systemctl restart nginx" > /dev/null 2>&1; then
        echo -e "${GREEN}  ✅ nginx restarted${NC}"
    else
        echo -e "${YELLOW}  ⚠️  Warning: failed to restart nginx${NC}"
    fi
fi

# Step 3: Verify deployment
echo -e "${YELLOW}🔍 Verifying deployment...${NC}"
slm_url="https://${AUTOBOT_FRONTEND_HOST}/slm/"
if curl -sk -o /dev/null -w '%{http_code}' "${slm_url}" | grep -q "200"; then
    echo -e "${GREEN}  ✅ ${slm_url} is serving (self-signed cert, -k)${NC}"
else
    echo -e "${RED}  ❌ ${slm_url} is not responding${NC}"
fi

# Summary
echo ""
echo -e "${GREEN}🎉 Frontend sync completed!${NC}"
echo "=================================="
echo -e "${BLUE}Summary:${NC}"
echo "  • Target: ${SSH_TARGET}:${REMOTE_FRONTEND_DIR}"
echo "  • URL: ${slm_url}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "  • Open browser and test changes"
echo "  • Check browser console for errors"
echo "  • Use --restart flag to also restart nginx"
echo ""
echo -e "${BLUE}Usage examples:${NC}"
echo "  ./sync-frontend.sh           # Normal sync"
echo "  ./sync-frontend.sh --restart  # Sync + restart nginx"
