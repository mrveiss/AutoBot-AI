#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# #19736: pull the embedding model, then run the same kind check the Ansible pull sites run. A wrong
# kind stops the install; a failed pull or an unreachable model server is only a warning.
# Sourced by install-bare-metal.sh, which provides log_warn and log_error.
_ANSIBLE_DIR="$(dirname "${BASH_SOURCE[0]}")/../../../../autobot-slm-backend/ansible"

pull_embedding_model() {
    local model verdicts
    # The one home of the embedding role's model. No fallback: a second name here is the defect.
    model="$(grep -oP '^ollama_embedding_model:\s*"\K[^"]+' "${_ANSIBLE_DIR}/roles/agent_config/defaults/main.yml")"
    [[ -n "${model}" ]] || { log_error "No ollama_embedding_model in agent_config's defaults"; exit 1; }
    ollama pull "${model}" || log_warn "Failed to pull embedding model"
    if ! verdicts="$(MODEL_CLI=ollama EMBEDDING_MODEL="${model}" COMPLETION_MODELS="" sh "${_ANSIBLE_DIR}/_shared/files/check_model_kinds.sh")"; then
        log_warn "Could not check the kind of ${model}: ${verdicts}"
    elif grep -q '^WRONG-KIND ' <<<"${verdicts}"; then
        log_error "A model is the wrong kind for its role: ${verdicts}"
        exit 1
    fi
}
