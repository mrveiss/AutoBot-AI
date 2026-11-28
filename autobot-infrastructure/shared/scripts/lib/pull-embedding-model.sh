#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# #19736: pull the embedding model, then run the same kind check the Ansible pull sites run: the script's
# exit code decides, for both (#19886). Only an unreachable model server is a warning here.
# Sourced by install-bare-metal.sh before its `cd /`, which provides log_warn and log_error. Paths are
# absolute for that reason, and a checkout without the Ansible tree stops the install here (set -e).
_BARE_METAL_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_ANSIBLE_DIR="$(cd "${_BARE_METAL_LIB_DIR}/../../../../autobot-slm-backend/ansible" && pwd)"

# The one home of the embedding role's model. No fallback: a second name here is the defect.
embedding_model_name() {
    grep -oP '^ollama_embedding_model:\s*["\x27]?\K[^"\x27\s#]+' "${_ANSIBLE_DIR}/roles/agent_config/defaults/main.yml"
}

pull_embedding_model() {
    local model verdicts
    model="$(embedding_model_name)"
    [[ -n "${model}" ]] || { log_error "No ollama_embedding_model in agent_config's defaults"; exit 1; }
    ollama pull "${model}" || log_warn "Failed to pull embedding model"
    local rc=0
    verdicts="$(MODEL_CLI=ollama EMBEDDING_MODEL="${model}" COMPLETION_MODELS="" sh "${_ANSIBLE_DIR}/_shared/files/check_model_kinds.sh")" || rc=$?
    if [[ "${rc}" == 2 ]]; then
        log_error "A model cannot be shown to do its role's job: ${verdicts}"
        exit 1
    elif [[ "${rc}" != 0 ]]; then
        log_warn "Could not check the kind of ${model}: ${verdicts}"
    fi
}
