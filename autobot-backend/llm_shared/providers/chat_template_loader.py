# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Chat template loader for local LLM providers.

Moved from llm_providers/ as part of Phase 2 consolidation (MVA-178 / GH#7637).
"""

import os

from jinja2 import Environment, FileSystemLoader, select_autoescape

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton

logger = get_logger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "chat_templates")
SUPPORTED_TEMPLATES = {"chatml", "zephyr", "vicuna"}
DEFAULT_TEMPLATE = "chatml"

_get_env = lazy_singleton(
    lambda: Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape([]),
        keep_trailing_newline=True,
    )
)


def render_chat_template(messages: list, template_name: str = DEFAULT_TEMPLATE) -> str:
    """Render messages using the specified Jinja2 chat template.

    Only for local/self-hosted providers. OpenAI/Anthropic/Gemini format server-side.
    """
    if template_name not in SUPPORTED_TEMPLATES:
        logger.warning("Unknown chat template '%s', falling back to '%s'", template_name, DEFAULT_TEMPLATE)
        template_name = DEFAULT_TEMPLATE
    template = _get_env().get_template(f"{template_name}.j2")
    return template.render(messages=messages)
