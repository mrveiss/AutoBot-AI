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
        # #19317: every tracked code/config/env/shell file outside docs -- the whole tree by suffix,
        # since a re-added default can land in any component; a roots= list would only shrink it.
        "tls-cert-dir-one-home-19317",
        # #19076: items are (role, unit) pairs from one registry file, not paths -- no roots= to check.
        "role-registry-installed-units",
        # #19413: every tracked file, so a ChromaDB heartbeat path written anywhere is seen.
        "chromadb-heartbeat-one-home-sweep",
        # #19318: every tracked code/config file by suffix (.py, .sh, .yml, .j2, .env*, Dockerfile*),
        # wherever a copy of the SLM admin password default could be written -- no prefix describes it.
        "slm-admin-password-one-home-sweep",
        # #19319: every tracked file repo-wide (minus vendored/build parts), wherever a copy of the
        # AUTOBOT_FEATURE_ROUTERS_STRICT default could be written -- no prefix describes it.
        "feature-routers-strict-one-home-19319",
        # #19310: every tracked text file in the repository, so a runtime-dir literal written
        # anywhere is seen; no roots= list could name "wherever someone writes it".
        "system-knowledge-runtime-literal-scan",
        # #19523: items are (ecosystem, directory) pairs from every tracked file name, at any
        # depth -- a new package root can appear anywhere, so no roots= list could name it.
        "dependabot-package-roots",
        "ansible-inventory-shell-sweep",
        "audio-extension-allowlist",
        "blanket-skip-test-module-sweep",
        # #19324: an extension filter (*.py, *.sh, *.yml, .env*, ...) over the whole tree, not a set of prefixes.
        "browser-port-single-home-scan",
        # #19279: requirements files live in every package directory; a glob, not a set of prefixes.
        "landing-page-declared-dependencies",
        "chromadb-bind-host-override-candidates",
        "chromadb-bind-launch-sites",
        "chromadb-compose-port-sites",
        "chromadb-compose-services",
        # #14908: items are export names parsed from the kit index, not paths.
        "kit-export-names-14908",
        # #19321/#19322: every tracked file outside docs and tests, wherever a copy could be
        # re-added; a roots= list would name the whole tree and go stale as it grows.
        "chromadb-port-one-home-scan",
        "slm-node-id-one-home-scan",
        "collectable-modules-inert-on-import",
        "component-style-block-sweep",
        "compose-files",
        "config-router-auth-coverage",
        "conflict-marker-scanned-files",
        "connector-redaction-sweep",
        # #19315: items are (path, line, var, value) assignments across the whole tree, not paths.
        "deployment-profile-writers-19315",
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
