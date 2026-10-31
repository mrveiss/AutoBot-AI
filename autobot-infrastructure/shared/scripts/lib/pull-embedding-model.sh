#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# #19736: pull the embedding model, then run the same kind check the Ansible pull sites run. A wrong
# kind stops the install; a failed pull or an unreachable model server is only a warning.
# Sourced by install-bare-metal.sh, which provides log_warn and log_error.
_KIND_CHECK="$(dirname "${BASH_SOURCE[0]}")/../../../../autobot-slm-backend/ansible/_shared/files/check_model_kinds.sh"

pull_embedding_model() {
    local verdicts
    ollama pull "$1" || log_warn "Failed to pull embedding model"
    if ! verdicts="$(MODEL_CLI=ollama EMBEDDING_MODEL="$1" COMPLETION_MODELS="" sh "${_KIND_CHECK}")"; then
        log_warn "Could not check the kind of $1: ${verdicts}"
    elif grep -q '^WRONG-KIND ' <<<"${verdicts}"; then
        log_error "A model is the wrong kind for its role: ${verdicts}"
        exit 1
    fi
}
