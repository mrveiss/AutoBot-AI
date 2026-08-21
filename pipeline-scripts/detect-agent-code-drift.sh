#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Detect drift between canonical source files and their Ansible-deployed
# copies under ansible/roles/*/files/.
# Used by: .github/workflows/code-quality.yml (required check "code-quality")
# Reference: Issue #1629, #14584, #14538, umbrella #13916
#
# Two pairs are tracked, both found by tracing `copy: src:` entries in
# ansible/roles/*/tasks/*.yml back to a source that also exists elsewhere in
# the tree:
#
#   1. autobot-slm-backend/slm/agent/ (canonical) mirrors to
#      autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent/. Only the
#      production *.py modules are actually deployed by
#      roles/slm_agent/tasks/main.yml -- the *_test.py files in the mirror
#      are not deployed, they exist so CI can run the test suite against the
#      exact bytes the role ships (#14538, #14576), so they must ALSO stay
#      byte-identical. This is the pair #14584 was filed for: the mirror
#      copy of health_collector_state_change_test.py silently drifted and
#      failed 2 tests on base, misread as shard flakiness for a full CI
#      cycle, because this script used to blanket-`--exclude='*_test.py'`
#      instead of naming the one deliberate exception below.
#      health_collector_probe_test.py IS that one deliberate exception --
#      its own docstring says it is canonical-tree-only -- and stays absent
#      from the mirror on purpose.
#
#   2. autobot-backend/{config/permission_rules.yaml,static/error_messages.yaml}
#      (canonical) mirror to the matching basenames under
#      autobot-slm-backend/ansible/roles/backend/files/, deployed by
#      roles/backend/tasks/main.yml.
#
# They MUST stay byte-identical. This fails loudly on: content drift (naming
# both paths and a unified diff), either side of a pair going missing, and
# resolving zero pairs -- an empty result must never read as a clean one.

set -euo pipefail

PAIRS_COMPARED=0

# compare_dir_pair <label> <canonical_dir> <mirror_dir> [exclude ...]
# Recursively diffs canonical_dir against mirror_dir. `exclude` names are
# passed straight to `diff --exclude` for files deliberately not mirrored.
compare_dir_pair() {
    local label="$1" canonical="$2" mirror="$3"
    shift 3
    if [ ! -d "$canonical" ]; then
        echo "ERROR: $label -- canonical directory not found: $canonical"
        exit 1
    fi
    if [ ! -d "$mirror" ]; then
        echo "ERROR: $label -- mirror directory not found: $mirror"
        exit 1
    fi
    local diff_args=(-r "$canonical" "$mirror" --exclude='__pycache__' --exclude='*.pyc')
    local exclude
    for exclude in "$@"; do
        diff_args+=(--exclude="$exclude")
    done
    local diff_out
    diff_out=$(diff "${diff_args[@]}" 2>&1) || true
    if [ -n "$diff_out" ]; then
        echo "DRIFT DETECTED ($label):"
        echo "  canonical: $canonical"
        echo "  mirror:    $mirror"
        echo "$diff_out"
        echo ""
        echo "Fix: copy the canonical file(s) over the mirror, e.g."
        echo "  cp $canonical/<file> $mirror/<file>"
        exit 1
    fi
    # Every file actually present in the mirror is a validated pair -- the
    # deliberate exceptions above never appear there.
    local count
    count=$(find "$mirror" -type f ! -path '*/__pycache__/*' ! -name '*.pyc' | wc -l)
    PAIRS_COMPARED=$((PAIRS_COMPARED + count))
}

# compare_file_pair <label> <canonical_file> <mirror_file>
compare_file_pair() {
    local label="$1" canonical="$2" mirror="$3"
    if [ ! -f "$canonical" ]; then
        echo "ERROR: $label -- canonical file not found: $canonical"
        exit 1
    fi
    if [ ! -f "$mirror" ]; then
        echo "ERROR: $label -- mirror file MISSING: $mirror (canonical exists at $canonical)"
        exit 1
    fi
    local diff_out
    if ! diff_out=$(diff -u "$canonical" "$mirror" 2>&1); then
        echo "DRIFT DETECTED ($label):"
        echo "  canonical: $canonical"
        echo "  mirror:    $mirror"
        echo "$diff_out"
        exit 1
    fi
    PAIRS_COMPARED=$((PAIRS_COMPARED + 1))
}

compare_dir_pair "slm_agent" \
    "autobot-slm-backend/slm/agent" \
    "autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent" \
    "health_collector_probe_test.py"

compare_file_pair "backend permission_rules.yaml" \
    "autobot-backend/config/permission_rules.yaml" \
    "autobot-slm-backend/ansible/roles/backend/files/permission_rules.yaml"

compare_file_pair "backend error_messages.yaml" \
    "autobot-backend/static/error_messages.yaml" \
    "autobot-slm-backend/ansible/roles/backend/files/error_messages.yaml"

if [ "$PAIRS_COMPARED" -eq 0 ]; then
    echo "ERROR: resolved zero canonical/mirror file pairs -- refusing to report clean on an empty result"
    exit 1
fi

echo "OK -- $PAIRS_COMPARED canonical/mirror file pair(s) byte-identical"
exit 0
