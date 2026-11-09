#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# #18663: stamp the freshly registered local SLM node as synced by running the playbook's own
# mark-synced tasks -- the one implementation the fleet run uses, no second call to the endpoint.
# install.sh runs this AFTER register_local_node: the endpoint 404s on a node with no row.
# The install inventory's one host is `localhost`; the node id travels as slm_node_id, which
# Phase 6.5 uses for the URL. mark_synced_strict=true makes the play fail on anything but a 200.
# Exit 1 when the node was not stamped, so the caller can warn without undoing a finished install.
#
#   mark_local_node_synced.sh <code source dir> <node id> <ansible vars file> <log file>
set -euo pipefail

readonly INVENTORY="inventory/localhost.yml" INVENTORY_HOST="localhost"
code_source="${1:?code source dir}" node_id="${2:?node id}" vars_file="${3:?vars file}" log_file="${4:?log file}"
out="$(mktemp)"; trap 'rm -f "${out}"' EXIT
args=(-i "${INVENTORY}" playbooks/provision-fleet-roles.yml --tags mark-synced --skip-tags always
    --limit "${INVENTORY_HOST}" -e "slm_node_id=${node_id}" -e mark_synced_strict=true -e "target_host=${INVENTORY_HOST}")
rc=0
(cd "${code_source}/autobot-slm-backend/ansible" && ansible-playbook "${args[@]}" \
    -e "@${vars_file}") >"${out}" 2>&1 || rc=$?
cat "${out}" >> "${log_file}"
# The POST task's first result line: ok/changed means it ran; skipping or nothing means it did not.
post="$(awk '/^TASK \[Mark-synced \| POST/{f=1; next} /^TASK \[/{f=0} f && /^(ok|changed|skipping|fatal|failed):/{print $1; exit}' "${out}")"
if [[ ${rc} -ne 0 ]] || grep -qE "WARNING: (mark-synced|SLM login)" "${out}" \
    || ! grep -qE "^${INVENTORY_HOST} +: ok=[1-9]" "${out}" || [[ ${post} != ok: && ${post} != changed: ]]; then
    cause="$(grep -E "WARNING|fatal:|FAILED!|ERROR" "${out}" | tail -n 1 || true)"
    echo "mark synced failed for ${node_id} (ansible exit ${rc}, POST task: ${post:-not run}): ${cause:-no cause printed}" >&2
    # The vars file is removed when install.sh exits; the playbook then reads the admin password
    # from the root-readable secrets file, so the recovery command runs under sudo and needs no file.
    echo "rerun: cd ${code_source}/autobot-slm-backend/ansible && sudo ansible-playbook ${args[*]}" >&2
    exit 1
fi
echo "Local node ${node_id} marked synced"
