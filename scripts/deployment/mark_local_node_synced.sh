#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# #18663: stamp the freshly registered local SLM node as synced by running the playbook's own
# mark-synced tasks -- the one implementation the fleet run uses, no second call to the endpoint.
# install.sh runs this AFTER register_local_node: the endpoint 404s on a node with no row, and
# the playbook tolerates that 404. Exit 1 when the node was not stamped, so the caller can warn
# loudly without undoing a finished install.
#
#   mark_local_node_synced.sh <code source dir> <node id> <ansible vars file> <log file>
set -euo pipefail

code_source="${1:?code source dir}" node_id="${2:?node id}" vars_file="${3:?vars file}" log_file="${4:?log file}"
out="$(mktemp)"; trap 'rm -f "${out}"' EXIT
rc=0
(cd "${code_source}/autobot-slm-backend/ansible" && ansible-playbook \
    -i inventory/localhost.yml playbooks/provision-fleet-roles.yml \
    --tags mark-synced --skip-tags always --limit "${node_id}" \
    -e "@${vars_file}" -e "target_host=localhost") >"${out}" 2>&1 || rc=$?
cat "${out}" >> "${log_file}"
if [[ ${rc} -ne 0 ]] || grep -qE "WARNING: (mark-synced|SLM login)" "${out}"; then
    echo "mark synced failed for ${node_id} (ansible exit ${rc}); rerun: cd ${code_source}/autobot-slm-backend/ansible && ansible-playbook -i inventory/localhost.yml playbooks/provision-fleet-roles.yml --tags mark-synced --skip-tags always --limit ${node_id}" >&2
    exit 1
fi
echo "Local node ${node_id} marked synced"
