# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AutoBot TTS Worker - Pocket TTS text-to-speech service.

Deploys to the NPU node on port 8083 (#3431: 8082 is WSL2/Hyper-V reserved on
that host class, which is why the port moved -- see #3464 for the incident).
The authoritative value is ``tts_port`` in
``autobot-slm-backend/ansible/roles/tts-worker/defaults/main.yml``; this file is
a signpost and must not become a second place to read a port from (#17782).

The actual service implementation is in the Ansible template:
  autobot-slm-backend/ansible/roles/tts-worker/templates/tts-worker.py.j2

That template is deployed to /opt/autobot/autobot-tts-worker/tts-worker.py
on the target node, with environment variables injected from the Ansible role.
"""

import logging

logger = logging.getLogger(__name__)


def main():
    """TTS worker entry point (local stub)."""
    logger.info("TTS Worker starting...")


if __name__ == "__main__":
    main()
