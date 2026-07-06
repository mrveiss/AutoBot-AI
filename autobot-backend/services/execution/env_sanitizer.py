# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Task environment-variable sanitizer for execution backends (security).

Automated security review flagged ``claude_code_backend`` merging semi-untrusted
``task.env_vars`` into the subprocess environment behind an *incomplete denylist*.
An incomplete denylist lets a task inject language-runtime / loader / shell-startup
hijack variables (``NODE_OPTIONS``, ``BASH_ENV``, ``LD_PRELOAD``, ``GIT_SSH_COMMAND``,
``PERL5OPT`` ...) into the spawned process, yielding arbitrary code execution.

Trust model
-----------
* ``base_env`` is the backend's OWN, TRUSTED environment (``os.environ``): PATH,
  HOME, LANG, ANTHROPIC_* credentials, the language runtime. The subprocess
  legitimately needs it, so it is passed through untouched.
* ``task_env_vars`` is SEMI-UNTRUSTED (agent/task-generated). It is filtered with
  an *allowlist* — only the application's own ``AUTOBOT_*`` task vars may be
  contributed — plus a comprehensive *denylist* as defense-in-depth.

This is the single shared implementation used by every execution backend so the
policy can never drift between them.
"""

from __future__ import annotations

import re
from typing import Dict, Mapping

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Allowlist: only the application's own task variables may be contributed by a
# task. Verified against the codebase — no production caller sets non-``AUTOBOT_``
# execution-task env vars, so this does not over-restrict real usage.
_ALLOWED_TASK_ENV_RE = re.compile(r"^AUTOBOT_[A-Z0-9_]+$")

# Denylist (defense-in-depth): never contributable even if somehow allowlisted.
# Credentials + process loader / interpreter / shell-startup hijack vectors.
# Kept in sync with ``secure_command_executor._DANGEROUS_ENV_VARS``.
PROTECTED_ENV_KEYS = frozenset(
    {
        # Anthropic / Claude Code credentials and endpoints
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_API_URL",
        "CLAUDE_CODE_ENTRYPOINT",
        # Path / executable resolution
        "PATH",
        # Python interpreter hijack
        "PYTHONPATH",
        "PYTHONSTARTUP",
        # Node.js runtime hijack
        "NODE_OPTIONS",
        "NODE_PATH",
        # Perl runtime hijack
        "PERL5OPT",
        "PERL5LIB",
        # Ruby runtime hijack
        "RUBYOPT",
        "RUBYLIB",
        # Git subprocess hijack
        "GIT_SSH_COMMAND",
        "GIT_EXEC_PATH",
        # glibc / iconv loader hijack
        "GCONV_PATH",
        # Shell parsing / startup
        "IFS",
        "BASH_ENV",
        "ENV",
        "PROMPT_COMMAND",
    }
)

# Any variable whose name starts with one of these prefixes is a dynamic-loader
# hijack vector (there are many ``LD_*`` / ``DYLD_*`` variants beyond the common
# three) and is always protected.
_PROTECTED_ENV_PREFIXES = ("LD_", "DYLD_")


def is_protected_env_key(key: str) -> bool:
    """Return True if ``key`` is a credential / loader / shell-startup hijack var.

    Covers the explicit :data:`PROTECTED_ENV_KEYS` denylist and the ``LD_*`` /
    ``DYLD_*`` dynamic-loader prefix families.
    """
    return key in PROTECTED_ENV_KEYS or key.startswith(_PROTECTED_ENV_PREFIXES)


def safe_task_env(
    base_env: Mapping[str, str],
    task_env_vars: Mapping[str, str] | None,
) -> Dict[str, str]:
    """Merge trusted ``base_env`` with allowlisted, denylist-filtered task vars.

    Args:
        base_env: The backend's own trusted environment (``os.environ``). Passed
            through untouched — the subprocess needs PATH/HOME/credentials/runtime.
        task_env_vars: Semi-untrusted task-supplied variables.

    Returns:
        A new dict: ``base_env`` plus only those task vars that match the
        ``AUTOBOT_*`` allowlist AND are not on the protected denylist.
    """
    env: Dict[str, str] = dict(base_env)
    dropped: list[str] = []
    for key, value in (task_env_vars or {}).items():
        if is_protected_env_key(key) or not _ALLOWED_TASK_ENV_RE.match(key):
            dropped.append(key)
            continue
        env[key] = value
    if dropped:
        # Log dropped KEY names only — never their values.
        logger.warning(
            "Dropped %d task env var(s) not on the AUTOBOT_* allowlist: %s",
            len(dropped),
            ", ".join(sorted(dropped)),
        )
    return env
