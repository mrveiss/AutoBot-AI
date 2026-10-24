# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The reach declarations that name no scope, and why that set only shrinks (#17914).

Split out of `_reach_policy.py`, which `ALLOWANCE_VERDICTS` keeps at the 600-line cap: every
new allowance-carrying declaration adds an entry there, so the two lists no longer share a file.
"""

from __future__ import annotations

#: Declarations whose `what=` names no scope, because their discovery does not return paths a
#: prefix can describe, or because the population genuinely is the whole tree (`_reach_scope`'s
#: docstring states why `roots=` is opt-in). Compared as a SET in both directions, so a
#: declaration that gains `roots=` must be removed here and a new declaration has to make the
#: decision rather than inherit silence. SHRINKS ONLY.
#:
#: An earlier version of this was a `len(...) <= MAX_UNSCOPED` ceiling whose own comment claimed
#: a set comparison. A comment claiming a stronger check than the code performs is worse than no
#: comment, and a reviewer caught it; the names are frozen here instead.
UNSCOPED = frozenset(
    {
        "ansible-apt-repo-budget-override-sweep",
        # Whole tree (#18940): every tracked test file, wherever a test lives; the population is
        # the test suite itself, so a roots= list would only go stale as tests move.
        "isolated-git-env",
        # #19076: items are (role, unit) pairs from one registry file, not paths -- no roots= to check.
        "role-registry-installed-units",
        # #19310: every tracked text file in the repository, so a runtime-dir literal written
        # anywhere is seen; no roots= list could name "wherever someone writes it".
        "system-knowledge-runtime-literal-scan",
        "ansible-inventory-shell-sweep",
        "audio-extension-allowlist",
        "blanket-skip-test-module-sweep",
        "chromadb-bind-host-override-candidates",
        "chromadb-bind-launch-sites",
        "chromadb-compose-port-sites",
        "chromadb-compose-services",
        "collectable-modules-inert-on-import",
        "component-style-block-sweep",
        "compose-files",
        "config-router-auth-coverage",
        "conflict-marker-scanned-files",
        "connector-redaction-sweep",
        "detect-environment-env-files",
        "docstring-restatement-scan",
        "dpkg-ansible-registrations",
        "dpkg-list-call-sites",
        "enum-hand-copy-census",
        "env-var-bare-cast",
        "excluded-tree-size-debt",
        "fastapi-validation-handler",
        "git-repo-root-call-site-files",
        "hardcoded-colour-scan",
        "hooks-path-override",
        "import-hermeticity",
        "important-declaration-sweep",
        "kb-content-redaction-chokepoint",
        "nginx-play-level-yml-sweep",
        "no-created-by-admin-literal",
        "nosec-b615-suppression-sweep",
        "npm-audit-workspace-coverage",
        "post-sync-branch-functions",
        "prompt-injection-detector-strict-mode",
        "redaction-concept-census",
        "redis-config-path-census",
        # Whole tree (#18999): walks the repo root and excludes by rule, so a new top-level
        # directory is swept with no edit; a roots= list would turn that into a red.
        "redis-keys-runtime-18999-scan",
        "reduced-motion-animate-call",
        "reduced-motion-animate-option",
        "reduced-motion-apex-animations",
        "reduced-motion-smooth-scroll",
        "response-model-secret-scan",
        "router-auth-coverage",
        "slm-agent-single-definition-19040",  # every tracked .py/.yml/.yaml/.j2: no prefix describes it (#19040)
        "slm-frontend-components",
        "slm-frontend-locale-keys",
        "slm-scripts-importing-services",
        "sqlalchemy-requirements-files",
        "tracked-key-material",
        "tts-address-env-name-sweep",
        "undefined-css-var-scan",
        "vnc-password-not-in-frontend-source",
        "websocket-subprotocol-echo",
        "workflow-job-parse-sweep",
        "workflow-rc-capture",
    }
)
