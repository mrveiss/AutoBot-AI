# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Values the SLM and every fleet node must agree on, defined once (#18094).

Each one used to be restated by every module that needed it: the install root in eight files,
the agent heartbeat interval in the agent and again in the SLM settings. A restated value is a
fork waiting to happen, so each now lives here and every reader imports it.

Deliberately **stdlib-only**, with no imports at all: the SLM agent on a fleet node, the SLM's
bootstrap paths and ``autobot_shared/security`` all read it, and none of them may pay for (or
fail on) ``ssot_config``.

``tools/lint/_env_fork_scan.py`` lists this module among its SSOT sources, so a module-level
constant elsewhere that restates one of these names is a finding; the Ansible-side copies are
held equal by ``repo_tests/defined_twice_18094_test.py``.
"""

#: Where a deployed fleet node keeps its install: the deploy *target*, the Python mirror of
#: Ansible's ``autobot.base_dir`` (inventory/group_vars/all.yml, #18880). A statement about the
#: fleet's layout, NOT an answer to "where is this process running" -- that is
#: ``autobot_shared.paths.install_base_dir``, which never guesses (#14544).
FLEET_INSTALL_ROOT = "/opt/autobot"

#: The SLM agent's code directory on a fleet node (#1121, #1129).
FLEET_AGENT_DIR = f"{FLEET_INSTALL_ROOT}/autobot-slm-agent"

#: Seconds between SLM agent heartbeats. The agent's ``--interval`` default and the SLM's
#: ``heartbeat_interval`` setting (``SLM_HEARTBEAT_INTERVAL``), which with
#: ``unhealthy_threshold`` decides when a silent node is marked unhealthy; Ansible's
#: ``slm_heartbeat_interval`` role default mirrors it.
DEFAULT_HEARTBEAT_INTERVAL = 30
