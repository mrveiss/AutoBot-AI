# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No tracked shell script assigns a literal Redis password (#16686).

The Redis credential is the one the SLM generates into ``slm-secrets.env``, which the
Ansible roles read through ``_shared/tasks/read_redis_password.yml`` (#16627). A literal
such as ``AUTOBOT_REDIS_PASSWORD=autobot123`` bypasses that source. Once the server
enforces a password (#16628), it either locks clients out or leaves a guessable
credential in place.

**Scope.** Every git-tracked ``*.sh`` file, including heredoc bodies, because the two
scripts #16686 found wrote their literal inside a ``cat > .env << EOF`` block. A line
counts when it assigns ``AUTOBOT_REDIS_PASSWORD=`` a value that neither starts with
``$`` (an expansion) nor is empty. It cannot see a password assembled from pieces,
written to another variable name, or kept in a non-``.sh`` script. Those are the
declared blind spots.

**Measured 2026-09-14:** 2 literal assignments on ``main``, in
``ansible/deploy-hybrid.sh:151`` and ``ansible/deploy-native.sh:175``, both removed by
#16686. The target population is the empty set.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

REPO_ROOT = repo_root()
_LITERAL = re.compile(r"""^\s*(?:export\s+)?AUTOBOT_REDIS_PASSWORD=(?!\$|["']\$|["']?["']?\s*$)\S""")


def literal_redis_passwords(text: str) -> list[int]:
    """1-based line numbers in *text* that assign a literal Redis password."""
    return [n for n, line in enumerate(text.splitlines(), 1) if _LITERAL.match(line)]


def test_no_shell_script_assigns_a_literal_redis_password():
    scripts = tracked_paths(REPO_ROOT, "*.sh")
    assert len(scripts) > 100, f"only {len(scripts)} tracked shell scripts -- did the enumeration break?"
    found = {
        rel: lines
        for rel in scripts
        if (lines := literal_redis_passwords((REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")))
    }
    assert not found, (
        "literal AUTOBOT_REDIS_PASSWORD in a shell script (#16686) -- read the SLM-generated secret "
        f"(slm-secrets.env, as _shared/tasks/read_redis_password.yml does) instead: {found}"
    )


def test_the_detector_fires_on_the_shapes_it_claims_to_see():
    """Known positives, the #16686 lines among them, and the forms that must pass."""
    assert literal_redis_passwords("AUTOBOT_REDIS_PASSWORD=autobot123") == [1]  # pragma: allowlist secret
    assert literal_redis_passwords("  export AUTOBOT_REDIS_PASSWORD='hunter2'") == [1]  # pragma: allowlist secret
    for allowed in (
        "AUTOBOT_REDIS_PASSWORD=${redis_password}",
        'AUTOBOT_REDIS_PASSWORD="$REDIS_PW"',
        "AUTOBOT_REDIS_PASSWORD=",
        'AUTOBOT_REDIS_PASSWORD=""',
        "# AUTOBOT_REDIS_PASSWORD=autobot123 was the old default",
    ):
        assert literal_redis_passwords(allowed) == [], allowed
