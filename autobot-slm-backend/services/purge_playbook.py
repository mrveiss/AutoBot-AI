# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The playbook blue/green writes to purge a released role's services.

Its own module because `services/blue_green.py` sits at a grandfathered size
ceiling (#14236), and a grandfathered file may not grow. The #16071 fix needed
seven lines there -- `redis-stack-server` in the service map, plus the reason
it had been missing -- and no comment length would have fitted. New material
moves to a new module; the same answer `service_status.py` got for the same
reason.

The template is data, not logic: `blue_green.py` writes it verbatim
(`path.write_text`), substituting nothing. Keeping it beside the code that
writes it bought nothing that an import does not.
"""

PURGE_PLAYBOOK_TEMPLATE = """# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Role Purge Playbook - Clean slate for role release
---
- name: Purge Roles from Node
  hosts: all
  become: true
  gather_facts: false

  vars:
    purge_roles: ""
    role_service_map:
      slm-agent:
        - slm-agent
        - autobot-agent
      redis:
        # #16071: redis-stack-server is what roles/redis installs and the only
        # one of these three that exists on a provisioned node. Without it the
        # purge stopped two absent units, left Redis Stack serving data on a
        # node that had released the role, and reported success -- the loop
        # below carries ignore_errors, so a wrong unit name and a right one
        # were indistinguishable in the output.
        - redis-stack-server
        - redis-server
        - redis
      backend:
        - autobot-backend
        - autobot
      frontend:
        - autobot-frontend
      npu-worker:
        - autobot-npu-worker
      browser-automation:
        - playwright-server
        - browser-automation
      monitoring:
        - prometheus
        - grafana-server
        - node_exporter
      ai-stack:
        - autobot-ai-stack
      llm:
        - ollama

    role_data_dirs:
      redis:
        - /var/lib/redis
        - /etc/redis
      backend:
        - /opt/autobot/backend
        - /var/log/autobot
      frontend:
        - /opt/autobot/frontend
      monitoring:
        - /var/lib/prometheus
        - /var/lib/grafana
        - /etc/prometheus
        - /etc/grafana

  tasks:
    - name: Parse purge roles
      ansible.builtin.set_fact:
        role_list: "{{ purge_roles.split(',') | map('trim') | list }}"

    - name: Stop and disable services for each role
      ansible.builtin.systemd:
        name: "{{ item.1 }}"
        state: stopped
        enabled: false
      loop: "{{ role_list | product(role_service_map[item] | default([])) | list }}"
      when: item.0 in role_service_map
      ignore_errors: true
      loop_control:
        label: "{{ item.1 | default(item) }}"

    - name: Remove service files
      ansible.builtin.file:
        path: "/etc/systemd/system/{{ item.1 }}.service"
        state: absent
      loop: "{{ role_list | product(role_service_map[item] | default([])) | list }}"
      when: item.0 in role_service_map
      ignore_errors: true
      loop_control:
        label: "{{ item.1 | default(item) }}"

    - name: Remove role data directories
      ansible.builtin.file:
        path: "{{ item.1 }}"
        state: absent
      loop: "{{ role_list | product(role_data_dirs[item] | default([])) | list }}"
      when: item.0 in role_data_dirs
      ignore_errors: true
      loop_control:
        label: "{{ item.1 | default(item) }}"

    - name: Reload systemd daemon
      ansible.builtin.systemd:
        daemon_reload: true

    - name: Display purge summary
      ansible.builtin.debug:
        msg: "Purged roles: {{ role_list | join(', ') }}"
"""
