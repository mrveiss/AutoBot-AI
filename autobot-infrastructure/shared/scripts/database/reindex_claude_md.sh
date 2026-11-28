#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# CLAUDE.md Vector Database Re-indexing Script
# Proposes the deletion of outdated CLAUDE.md chunks (an admin approves it), then re-indexes the current version.
# Location: autobot-infrastructure/shared/scripts/database/reindex_claude_md.sh
#
#   reindex_claude_md.sh              list the chunks a deletion would remove; delete nothing
#   reindex_claude_md.sh --request    raise the approval proposal; delete nothing until an admin approves it
#   reindex_claude_md.sh --reindex    after the approval ran: index the current CLAUDE.md
#
# This script deletes nothing itself (#21383, #17038); the backend deletes after approval.

set -e  # Exit on error

# #13149: the shared helper resolves the root from this file's own location; AUTOBOT_PROJECT_ROOT overrides.
# shellcheck source=scripts/lib/project_root.sh
source "$(dirname "${BASH_SOURCE[0]}")/../../../../scripts/lib/project_root.sh"

if [ ! -d "${PROJECT_ROOT}/autobot-backend" ]; then
    echo "ERROR: backend package root not found at ${PROJECT_ROOT}/autobot-backend;" >&2
    echo "       nothing was requested or re-indexed (#14867)." >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PROJECT_ROOT
export PYTHONPATH="${PROJECT_ROOT}/autobot-backend:${PROJECT_ROOT}:${PYTHONPATH:-}"

echo "=== CLAUDE.md Vector Database Re-indexing ==="
exec python3 "${SCRIPT_DIR}/../claude_md_reindex_cli.py" "$@"
