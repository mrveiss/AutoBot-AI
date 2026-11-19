#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# The ONE shell reader of the browser worker's shipped-file list (#21852).
#
# The list lives in autobot-infrastructure/autobot-browser-worker/manifest.yml
# (`deploy.files`). Deploy scripts used to copy a hand-written list of the worker's
# modules; a module a list omitted made the worker die with MODULE_NOT_FOUND there.
#
#     source "$PROJECT_ROOT/scripts/lib/browser_worker_files.sh"
#     for f in $(browser_worker_files "$PROJECT_ROOT"); do cp "$PROJECT_ROOT/autobot-browser-worker/$f" ...; done
#
# Prints one file name per line. Refuses (non-zero, message on stderr) when the manifest is
# missing or lists nothing, so a broken read never ships an empty worker. Plain awk: a node's
# system python may not have PyYAML.

browser_worker_files() {
    local root="${1:?browser_worker_files: project root required}"
    local manifest="$root/autobot-infrastructure/autobot-browser-worker/manifest.yml"
    local files
    [ -f "$manifest" ] || {
        echo "browser_worker_files: $manifest not found" >&2
        return 1
    }
    files="$(awk '
        /^deploy:/ { in_deploy = 1; next }
        in_deploy && /^[^ #]/ { in_deploy = 0 }
        in_deploy && /^  files:/ { in_files = 1; next }
        in_files && /^    - / { sub(/^    - /, ""); sub(/[ \t]*(#.*)?$/, ""); print; next }
        in_files && /^[ \t]*(#.*)?$/ { next }
        in_files { in_files = 0 }
    ' "$manifest")"
    [ -n "$files" ] || {
        echo "browser_worker_files: deploy.files in $manifest lists nothing" >&2
        return 1
    }
    printf '%s\n' "$files"
}

# Executed directly: `browser_worker_files.sh [ROOT]`.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    browser_worker_files "${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
fi
