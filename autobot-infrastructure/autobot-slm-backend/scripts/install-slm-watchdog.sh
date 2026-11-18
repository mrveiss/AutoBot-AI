#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# #20620: install the SLM watchdog on a bootstrapped host. The slm_manager role's templates and
# defaults are the one definition, rendered here because bootstrap runs before Ansible does.
# Sourced by bootstrap-slm.sh, which provides PROJECT_ROOT and remote_exec_sudo.

_slm_role_default() {
    sed -n "s/^$1: *//p" "${PROJECT_ROOT}/autobot-slm-backend/ansible/roles/slm_manager/defaults/main.yml" | head -1
}

render_slm_watchdog_file() {
    local var script=()
    script+=(-e 's/{{ ansible_managed }}/Installed by bootstrap-slm.sh/')
    for var in slm_backend_service slm_backend_host slm_backend_port slm_watchdog_interval \
        slm_watchdog_health_timeout slm_watchdog_max_health_failures slm_self_update_unit_prefix \
        slm_watchdog_max_update_ticks; do
        script+=(-e "s/{{ ${var} }}/$(_slm_role_default "$var")/")
    done
    sed "${script[@]}" "${PROJECT_ROOT}/autobot-slm-backend/ansible/roles/slm_manager/templates/$1.j2"
}

install_slm_watchdog() {
    render_slm_watchdog_file autobot-slm-watchdog.sh |
        remote_exec_sudo "cat > /usr/local/sbin/autobot-slm-watchdog && chmod 755 /usr/local/sbin/autobot-slm-watchdog"
    local unit
    for unit in autobot-slm-watchdog.service autobot-slm-watchdog.timer; do
        render_slm_watchdog_file "$unit" | remote_exec_sudo "cat > /etc/systemd/system/${unit}"
    done
    remote_exec_sudo "systemctl daemon-reload && systemctl enable --now autobot-slm-watchdog.timer"
}
