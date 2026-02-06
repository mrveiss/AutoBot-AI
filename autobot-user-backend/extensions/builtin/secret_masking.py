# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Secret Masking Extension for security.

Issue #658: Built-in extension that masks sensitive information
in responses before they are displayed to users.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from src.extensions.base import Extension, HookContext

logger = logging.getLogger(__name__)


class SecretMaskingExtension(Extension):
    """
    Extension that masks secrets in responses.

    Issue #658: This built-in extension provides security by masking
    sensitive information (API keys, passwords, tokens) before responses
    are sent to users.

    Attributes:
        name: "secret_masking"
        priority: 90 (runs near the end, before response is sent)
        patterns: List of regex patterns to detect secrets
        mask_char: Character used for masking (default '*')
        show_chars: Number of characters to show at start/end

    Usage:
        manager.register(SecretMaskingExtension())

        # Or with custom patterns
        ext = SecretMaskingExtension()
        ext.add_pattern(r'my-custom-secret-\\w+', 'Custom Secret')
        manager.register(ext)
    """

    name = "secret_masking"
    priority = 90  # Run near the end, before logging

    # Default patterns for common secrets
    DEFAULT_PATTERNS: List[Dict[str, Any]] = [
        {
            "name": "API Key (generic)",
            "pattern": r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"]?([a-zA-Z0-9_-]{20,})['\"]?",
            "group": 2,
        },
        {
            "name": "AWS Access Key",
            "pattern": r"AKIA[0-9A-Z]{16}",
            "group": 0,
        },
        {
            "name": "AWS Secret Key",
            "pattern": (
                r"(?i)(aws[_-]?secret[_-]?access[_-]?key|secret[_-]?key)"
                r"\s*[:=]\s*['\"]?([a-zA-Z0-9/+=]{40})['\"]?"
            ),
            "group": 2,
        },
        {
            "name": "Bearer Token",
            "pattern": r"(?i)bearer\s+([a-zA-Z0-9_-]{20,})",
            "group": 1,
        },
        {
            "name": "Password (generic)",
            "pattern": r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?([^\s'\"]{8,})['\"]?",
            "group": 2,
        },
        {
            "name": "Private Key Header",
            "pattern": r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
            "group": 0,
        },
        {
            "name": "GitHub Token",
            "pattern": r"gh[pousr]_[A-Za-z0-9_]{36,}",
            "group": 0,
        },
        {
            "name": "Slack Token",
            "pattern": r"xox[baprs]-[0-9A-Za-z-]{10,}",
            "group": 0,
        },
        {
            "name": "JWT Token",
            "pattern": r"eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*",
            "group": 0,
        },
        {
            "name": "Generic Secret",
            "pattern": r"(?i)(secret|token|credential)\s*[:=]\s*['\"]?([a-zA-Z0-9_-]{16,})['\"]?",
            "group": 2,
        },
        {
            "name": "OpenAI API Key",
            "pattern": r"sk-[a-zA-Z0-9]{48}",
            "group": 0,
        },
        {
            "name": "Anthropic API Key",
            "pattern": r"sk-ant-[a-zA-Z0-9-]{32,}",
            "group": 0,
        },
    ]

    def __init__(self):
        """Initialize secret masking extension."""
        self.patterns: List[Dict[str, Any]] = []
        self.compiled_patterns: List[tuple] = []
        self.mask_char = "*"
        self.show_chars = 4  # Show first/last N chars
        self.mask_count = 0  # Track number of masks applied

        # Load default patterns
        for pattern_config in self.DEFAULT_PATTERNS:
            self.add_pattern(
                pattern_config["pattern"],
                pattern_config["name"],
                pattern_config.get("group", 0),
            )

    def add_pattern(
        self,
        pattern: str,
        name: str,
        group: int = 0,
    ) -> bool:
        """
        Add a pattern to detect secrets.

        Args:
            pattern: Regex pattern string
            name: Human-readable name for logging
            group: Regex group to mask (0 = whole match)

        Returns:
            True if pattern added successfully
        """
        try:
            compiled = re.compile(pattern)
            self.patterns.append(
                {
                    "name": name,
                    "pattern": pattern,
                    "group": group,
                }
            )
            self.compiled_patterns.append((compiled, name, group))
            return True
        except re.error as e:
            logger.error(
                "[Issue #658] Invalid regex pattern '%s': %s",
                name,
                str(e),
            )
            return False

    def mask_secret(self, secret: str) -> str:
        """
        Mask a secret string.

        Shows first and last N characters with masked middle.

        Args:
            secret: The secret to mask

        Returns:
            Masked string
        """
        if len(secret) <= self.show_chars * 2:
            # Too short to show any chars - mask entirely
            return self.mask_char * len(secret)

        start = secret[: self.show_chars]
        end = secret[-self.show_chars :]
        middle_len = len(secret) - (self.show_chars * 2)

        return f"{start}{self.mask_char * middle_len}{end}"

    def mask_secrets(self, text: str) -> str:
        """
        Mask all detected secrets in text.

        Args:
            text: Text potentially containing secrets

        Returns:
            Text with secrets masked
        """
        masked_text = text
        masks_applied = 0

        for compiled_pattern, name, group in self.compiled_patterns:
            try:
                matches = list(compiled_pattern.finditer(masked_text))
                # Process in reverse to maintain correct positions
                for match in reversed(matches):
                    if group == 0:
                        secret = match.group(0)
                        start, end = match.start(), match.end()
                    else:
                        try:
                            secret = match.group(group)
                            start = match.start(group)
                            end = match.end(group)
                        except IndexError:
                            continue

                    masked = self.mask_secret(secret)
                    masked_text = masked_text[:start] + masked + masked_text[end:]
                    masks_applied += 1

                    logger.debug(
                        "[Issue #658] Masked %s: %s -> %s",
                        name,
                        secret[:4] + "...",
                        masked[:8] + "...",
                    )
            except Exception as e:
                logger.error(
                    "[Issue #658] Error applying pattern '%s': %s",
                    name,
                    str(e),
                )

        if masks_applied > 0:
            self.mask_count += masks_applied
            logger.info(
                "[Issue #658] Masked %d secret(s) in response",
                masks_applied,
            )

        return masked_text

    async def on_before_response_send(self, ctx: HookContext) -> Optional[str]:
        """
        Mask secrets before sending response.

        Args:
            ctx: Hook context with response in data

        Returns:
            Masked response or None if no changes
        """
        response = ctx.get("response", "")
        if not response:
            return None

        masked = self.mask_secrets(response)
        if masked != response:
            ctx.set("response", masked)
            return masked

        return None

    async def on_after_llm_response(self, ctx: HookContext) -> Optional[str]:
        """
        Mask secrets in LLM responses.

        Args:
            ctx: Hook context with response in data

        Returns:
            Masked response or None if no changes
        """
        response = ctx.get("response", "")
        if not response:
            return None

        masked = self.mask_secrets(response)
        if masked != response:
            return masked

        return None

    async def on_after_tool_execute(self, ctx: HookContext) -> Optional[str]:
        """
        Mask secrets in tool results.

        Args:
            ctx: Hook context with result in data

        Returns:
            Masked result or None if no changes
        """
        result = ctx.get("result", "")
        if not result or not isinstance(result, str):
            return None

        masked = self.mask_secrets(result)
        if masked != result:
            return masked

        return None

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about secret masking.

        Returns:
            Dictionary with masking stats
        """
        return {
            "pattern_count": len(self.patterns),
            "total_masks_applied": self.mask_count,
            "patterns": [p["name"] for p in self.patterns],
        }
