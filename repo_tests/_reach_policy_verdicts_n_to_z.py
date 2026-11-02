# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Allowance-verdict rows whose declaration name sorts n-z, split out of `_reach_policy_verdicts` at its
600-line ceiling. `_reach_policy_verdicts.ALLOWANCE_VERDICTS` merges both halves; nothing imports this
module directly except that one.
"""

from __future__ import annotations

ABSOLUTE = "ABSOLUTE"
CONVERTIBLE = "CONVERTIBLE"

N_TO_Z: dict[str, tuple[str, str, str]] = {
    "no_partial_key_mask_18221.sources": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test Python under three of the source trees (#18221); no tracked count moves with that "
        "subset, because the test share and the other trees grow at their own rate.",
    ),
    "node-major-literals": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Workflow, Ansible and install-script files (yml/yaml/sh/j2), against all tracked files there; drifts.",
    ),
    "severity-order-copies": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test .py under the backends, shared and pipeline-scripts, against all tracked .py; test share drifts.",
    ),
    "search-mode-copies": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test backend modules, against all tracked .py under autobot-backend; the test-file share drifts.",
    ),
    "redaction-placeholder-literals": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test .py under both backends and autobot_shared, against all tracked .py; the test share drifts.",
    ),
    "shadowed-literal-routes": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Router modules the registries and main.py mount, a subset of tracked Python under two trees; "
        "the rest of those trees grows independently, so a share of all Python would sink with nothing wrong.",
    ),
    "paths-filter-workflow-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Workflow files are a subset of tracked YAML; compose, ansible and filter files grow at "
        "their own rate, so a share of all YAML would sink with nothing wrong.",
    ),
    "provider-key-env-read-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under three roots; the test-file share drifts.",
    ),
    "one-internal-api-key-reader-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under three roots; the test-file share drifts.",
    ),
    "one-content-digest-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under two roots; the test-file share drifts.",
    ),
    "one-doc-indexer": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under six roots; the test-file share drifts.",
    ),
    "root-resolver-depth-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "All tracked Python under seven roots, against all tracked Python in the repository.",
    ),
    "optimization-taxonomy-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source of one package directory, against all tracked Python under it.",
    ),
    "single-attribute-writer-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test .ts/.vue/.js source is a subset of tracked files under the user frontend; test share drifts.",
    ),
    "one-playwright-server-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked .js under three roots is a subset of those trees; the unrelated-script share drifts.",
    ),
    "one-system-knowledge-template-tree": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Template-schema YAML is a subset of all tracked YAML (whole repo); unrelated YAML drifts (#19310).",
    ),
    "one-static-data-copy-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Guarded-basename files are a subset of all tracked files (whole repo); same-named unrelated files drift.",
    ),
    "redis-direct-constructor-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test .py/.sh under the scan roots is a subset of tracked files; the test-file share drifts.",
    ),
    "serving-predicate-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under four roots; the test-file share drifts.",
    ),
    "script-module-name-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked scripts (.py, .sh, .bash, .js) under one scripts root, a subset of all tracked files; "
        "the count drifts as scripts are added.",
    ),
    "post-commit-seed-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under three roots; the test-file share drifts.",
    ),
    "slm-backend-embedded-playbook-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under one root; the test-file share drifts.",
    ),
    "one-permission-gate-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under three roots; the test-file share drifts.",
    ),
    "session-ownership-validator-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under three roots; the test-file share drifts.",
    ),
    "oauth-bundle-app-secret-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under two roots; the test-file share drifts.",
    ),
    "torch-pair-literals": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Workflow, docker, infrastructure, Ansible and script files, against all tracked files there; drifts.",
    ),
    "tool-effect-table-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source under three roots, a subset of all tracked Python; the test-file share drifts.",
    ),
    "one-bm25-formula": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under three roots; the test-file share drifts.",
    ),
    "one-hybrid-search": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under two roots; the test-file share drifts.",
    ),
    "semantic-chunker-fork-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under two roots; the test-file share drifts.",
    ),
    "ssh-restart-executor-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under one root; the test-file share drifts.",
    ),
    "shared-authority-callers-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under three roots; the test-file share drifts.",
    ),
    "one-claim-model-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under three roots; the test-file share drifts.",
    ),
    "sync-command-result-mapping-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under one root; the test-file share drifts.",
    ),
    "pr-comment-upsert-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Workflow YAML and non-test python under five roots; each root grows and shrinks independently.",
    ),
    "provenance-accessor-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under autobot-backend; the test-file share drifts.",
    ),
    "nginx-play-level-yml-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "`*.yml` under the ansible tree, against all tracked YAML.",
    ),
    "no-created-by-admin-literal": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Backend Python with tests excluded, against all tracked Python.",
    ),
    "npm-audit-workspace-coverage": (ABSOLUTE, "FIXED_INVENTORY", "Workspaces, not files; a named, single-digit set."),
    "one-claim-registry": (ABSOLUTE, "SUBSET_DRIFTS", "Python under five named trees, against all tracked Python."),
    "post-sync-branch-functions": (ABSOLUTE, "NOT_PATHS", "Functions inside one module, not files."),
    "prompt-injection-detector-strict-mode": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "A production Python subset, against all tracked Python.",
    ),
    "redaction-concept-census": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked production Python, against all tracked Python including tests.",
    ),
    "response-model-secret-scan": (ABSOLUTE, "SUBSET_DRIFTS", "Backend Python modules, against all tracked Python."),
    "router-auth-coverage": (ABSOLUTE, "NOT_PATHS", "Routers registered in `core_routers.py`, not files."),
    "slm-frontend-components": (ABSOLUTE, "SUBSET_DRIFTS", "One frontend's components, against all tracked `.vue`."),
    "slm-node-id-one-home-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked files outside docs and tests, a subset of the tree; docs and tests grow at their own rate.",
    ),
    "severity-enum-fork-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked Python under three roots against all tracked Python: the other roots (frontend "
        "tooling, SLM, tests, docs scripts) grow independently, so a share of the whole sinks "
        "with nothing wrong. The guard needs the roots reached, not a share of the repository.",
    ),
    "slm-frontend-locale-keys": (
        ABSOLUTE,
        "NOT_PATHS",
        "Message keys inside one JSON file; the only count of them is this sweep.",
    ),
    "slm-scripts-importing-services": (
        ABSOLUTE,
        "FIXED_INVENTORY",
        "A single-digit set the guard exists to keep at zero-or-few.",
    ),
    "sqlalchemy-requirements-files": (ABSOLUTE, "FIXED_INVENTORY", "Single-digit requirements files."),
    "store-fact-chokepoint": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Production Python under two trees, against all tracked Python.",
    ),
    "tracked-key-material": (
        CONVERTIBLE,
        "REFERENCE_EXISTS",
        "Its population IS the tracked tree, the same shape `conflict-marker-scanned-files` "
        "already adopted. Held back on an OWNER question rather than a measurement: the file "
        "carries a recorded ruling that its floor is deliberately absolute and mid-window, and "
        "converting it would reverse that ruling from outside the file.",
    ),
    "undefined-css-var-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "One frontend tree's source, against all tracked frontend source.",
    ),
    "v-html-sanitiser-sinks": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Both frontends' and the kit's non-test `.vue`/`.ts`, against all tracked frontend source; "
        "the test-file share drifts.",
    ),
    "vnc-password-not-in-frontend-source": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "One frontend tree's source, against all tracked frontend source.",
    ),
    "websocket-subprotocol-echo": (
        ABSOLUTE,
        "FIXED_INVENTORY",
        "A couple of dozen backend modules that authenticate a WebSocket.",
    ),
    "workflow-job-parse-sweep": (ABSOLUTE, "NOT_PATHS", "Parsed workflow jobs, not files."),
    "workflow-rc-capture": (ABSOLUTE, "NOT_PATHS", "`run:` blocks under an errexit shell, not files."),
    "workflow-visible-name-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Workflow files are a subset of tracked YAML; compose, ansible and filter files grow at "
        "their own rate, so a share of all YAML would sink with nothing wrong.",
    ),
    "user-mode-default-carriers-18729": (
        ABSOLUTE,
        "FIXED_INVENTORY",
        "Compose files, container entrypoints and env templates: a small, named set.",
    ),
    "opt-autobot-literal-ratchet-18880": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Every tracked file under the ansible tree; grows with roles and playbooks.",
    ),
    "redis-keys-runtime-18999-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Runtime Python outside test, tooling and top-level docs/data/logs trees, a subset of tracked "
        "Python; the excluded share drifts independently.",
    ),
    "slm-agent-single-definition-19040": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked Python, YAML and Jinja files, a subset of the tree; the other extensions grow at their own rate.",
    ),
    "service-port-homes-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test Python and nine text extensions under seven roots, plus .env.example, a subset of tracked "
        "files; the test "
        "share and the other extensions grow at their own rate.",
    ),
    "ssot-rehardcode-scan-19730": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test Python under the backends and shared, a subset of tracked Python; the test share and "
        "the other trees grow at their own rate, so a share of all Python would sink with nothing wrong.",
    ),
    "user-mode-values-sweep-19437": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Docs and deployment files by extension, minus the history trees; the code share of the tree grows "
        "at its own rate, so a share of all tracked files would sink with nothing wrong.",
    ),
    "browser-service-routes-scan-19490": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked Python under five code roots, a subset of tracked Python; the other trees grow at their "
        "own rate, so a share of all Python would sink with nothing wrong.",
    ),
}
