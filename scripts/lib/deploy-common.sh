#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Logging and preflight helpers shared by the Ansible deployment wrappers
# (autobot-slm-backend/ansible/deploy-hybrid.sh, deploy-native.sh) (#18557).
#
# Both scripts carried byte-identical copies of these five functions. Source
# this file -- do not execute it -- after defining the variables below:
#
#     source "$(dirname "${BASH_SOURCE[0]}")/../../scripts/lib/deploy-common.sh"
#
# The caller owns (this file reads them, never sets them):
#   LOG_FILE        file `log` appends to
#   RED GREEN YELLOW BLUE NC   ANSI colour codes `log` prints with
#   INVENTORY_FILE  Ansible inventory checked by check_prerequisites / test_connectivity
#   PLAYBOOK_FILE   playbook checked by check_prerequisites

# Logging
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case "$level" in
        INFO)  echo -e "${BLUE}ℹ️ ${message}${NC}" | tee -a "$LOG_FILE" ;;
        WARN)  echo -e "${YELLOW}⚠️ ${message}${NC}" | tee -a "$LOG_FILE" ;;
        ERROR) echo -e "${RED}❌ ${message}${NC}" | tee -a "$LOG_FILE" ;;
        SUCCESS) echo -e "${GREEN}✅ ${message}${NC}" | tee -a "$LOG_FILE" ;;
        DEBUG) echo -e "${timestamp} [DEBUG] ${message}" >> "$LOG_FILE" ;;
    esac
}

error_exit() {
    log "ERROR" "$1"
    exit 1
}

success() {
    log "SUCCESS" "$1"
}

# Check prerequisites
check_prerequisites() {
    log "INFO" "Checking prerequisites..."

    if ! command -v ansible-playbook &> /dev/null; then
        error_exit "Ansible is not installed. Please install ansible first."
    fi

    if [[ ! -f "$INVENTORY_FILE" ]]; then
        error_exit "Inventory file not found: $INVENTORY_FILE"
    fi

    if [[ ! -f "$PLAYBOOK_FILE" ]]; then
        error_exit "Playbook file not found: $PLAYBOOK_FILE"
    fi

    success "Prerequisites checked"
}

# Test VM connectivity
test_connectivity() {
    log "INFO" "Testing connectivity to all VMs..."

    if ansible all -i "$INVENTORY_FILE" -m ping --ask-pass; then
        success "All VMs are accessible"
    else
        error_exit "Some VMs are not accessible. Please check network connectivity."
    fi
}
