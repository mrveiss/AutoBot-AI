# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""AutoBot TTS Worker - Pocket TTS text-to-speech service.

Deploys to: 172.16.168.22 (NPU VM) on port 8082

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
