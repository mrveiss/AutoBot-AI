# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Chat template loader for local LLM providers.

Moved from llm_providers/ as part of Phase 2 consolidation (MVA-178 / GH#7637).
"""

import os

from jinja2 import Environment, FileSystemLoader, select_autoescape

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "chat_templates")
SUPPORTED_TEMPLATES = {"chatml", "zephyr", "vicuna"}
DEFAULT_TEMPLATE = "chatml"

_env = None


def _get_env() -> Environment:
    global _env
    if _env is None:
        _env = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            autoescape=select_autoescape([]),
            keep_trailing_newline=True,
        )
    return _env


def render_chat_template(messages: list, template_name: str = DEFAULT_TEMPLATE) -> str:
    """Render messages using the specified Jinja2 chat template.

    Only for local/self-hosted providers. OpenAI/Anthropic/Gemini format server-side.
    """
    if template_name not in SUPPORTED_TEMPLATES:
        logger.warning("Unknown chat template '%s', falling back to '%s'", template_name, DEFAULT_TEMPLATE)
        template_name = DEFAULT_TEMPLATE
    template = _get_env().get_template(f"{template_name}.j2")
    return template.render(messages=messages)
