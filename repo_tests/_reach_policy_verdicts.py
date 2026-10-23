# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The allowance-verdict table, split out of `_reach_policy` at its 600-line ceiling (#12732).

The policy -- what each verdict and reason code means, and why the sets are closed -- stays in
:mod:`repo_tests._reach_policy`, which re-exports this table under the same name. Every
importer keeps reading ``_reach_policy.ALLOWANCE_VERDICTS``; only the rows moved.
"""

from __future__ import annotations

ABSOLUTE = "ABSOLUTE"
CONVERTIBLE = "CONVERTIBLE"

ALLOWANCE_VERDICTS: dict[str, tuple[str, str, str]] = {
    "chunk-identity-single-home-18142": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test Python under the backend and shared trees, a subset of tracked Python; the test share and "
        "the other trees grow at their own rate, so a share of all Python would sink with nothing wrong.",
    ),
    "shadowed-literal-routes": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Router modules the registries and main.py mount, a subset of tracked Python under two trees; "
        "the rest of those trees grows independently, so a share of all Python would sink with nothing wrong.",
    ),
    "brand-mark-announcer-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test .ts/.vue/.js source is a subset of tracked files under three roots; the test-file share drifts.",
    ),
    "migration-gate-test-import-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "One test directory's Python, against all tracked Python; the rest of the suite grows at its own rate.",
    ),
    "paths-filter-workflow-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Workflow files are a subset of tracked YAML; compose, ansible and filter files grow at "
        "their own rate, so a share of all YAML would sink with nothing wrong.",
    ),
    "deployment-mode-detector-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Python files under two of the tracked trees, a subset of all tracked Python; the other trees drift.",
    ),
    "egress-default-outbound-call-sites": (
        ABSOLUTE,
        "NOT_PATHS",
        "Call sites, not paths: one id per detected or declared outbound call in the egress sweep.",
    ),
    "egress-default-outbound-call-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Files making outbound HTTP calls are a small subset of tracked python; the other ~6000 "
        "files grow independently, so a share of them sinks with nothing wrong with the sweep.",
    ),
    "ansible-apt-repo-budget-override-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Ansible variable files are a subset of tracked YAML; workflow and compose YAML grow "
        "independently of the ansible tree, so a share of all YAML sinks with nothing wrong.",
    ),
    "ansible-inventory-shell-sweep": (
        ABSOLUTE,
        "FRACTION_IS_COARSER",
        "Measured, after an earlier verdict here said CONVERTIBLE with no blocker stated and a "
        "reviewer called that out: an independent suffix filter does count the same class and "
        "agrees with the sweep exactly. It still cannot convert, because at this population one "
        "step of a fraction is worth more files than the constant's own band -- 0.99 implies a "
        "floor BELOW the constant it would replace, which #17914 AC2 refuses, and 1.00 fires on "
        "a single index-versus-filesystem skew.",
    ),
    "audio-extension-allowlist": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked Python minus the canonical file and `repo_tests/` (#16724); tests grow at their "
        "own rate, so a share of all tracked Python sinks with nothing wrong with the sweep.",
    ),
    "blanket-skip-test-module-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Test modules against all tracked Python: tests grow faster than production code, so "
        "this share rises and falls on unrelated work.",
    ),
    "chromadb-bind-host-override-candidates": (
        ABSOLUTE,
        "FIXED_INVENTORY",
        "A handful of inventory and role-default files.",
    ),
    "chromadb-bind-launch-sites": (
        ABSOLUTE,
        "FIXED_INVENTORY",
        "Single-digit launch sites; the band is already near equality.",
    ),
    "chromadb-compose-files": (
        ABSOLUTE,
        "FIXED_INVENTORY",
        "Single-digit compose files; a fraction of any reference is noise at this size.",
    ),
    "jekyll-processed-docs": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Markdown under `docs/` carrying front matter -- the only files Jekyll renders through "
        "Liquid. All `docs/**/*.md` is the obvious reference and it is the wrong one: it is the "
        "`archives/` case named in this module's own header. Archived pages are added without "
        "front matter and never removed, so the processed share sinks with nothing wrong, and a "
        "fraction of the whole would fire on that drift rather than on a guard going blind.",
    ),
    "chat-history-async-calls-awaited": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test modules under `autobot-backend/api`, the same population and the same test "
        "drift as `chat-single-delete-implementation` (#18316).",
    ),
    "chat-single-delete-implementation": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test modules under `autobot-backend/api`; the api package's tests grow at their own "
        "rate, so a share of all its `.py` files would drift with nothing wrong (#18316).",
    ),
    "compat-module-needs-importer": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test backend modules whose docstring declares backward compatibility; a subset of the "
        "backend's `.py` files whose share drifts as facades are retired (#18552).",
    ),
    "chromadb-compose-port-sites": (ABSOLUTE, "NOT_PATHS", "Parsed `ports:` entries, not files."),
    "chromadb-compose-services": (ABSOLUTE, "NOT_PATHS", "Parsed compose services, not files."),
    "collectable-modules-inert-on-import": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Modules matching pytest's `python_files` patterns -- the same test-versus-production "
        "drift as `blanket-skip-test-module-sweep`.",
    ),
    "component-style-block-sweep": (
        ABSOLUTE,
        "NOT_PATHS",
        "`<style>` blocks within components, counted per block rather than per file.",
    ),
    "config-router-auth-coverage": (ABSOLUTE, "NOT_PATHS", "Routers listed in the config registries, not files."),
    "connector-redaction-sweep": (ABSOLUTE, "FIXED_INVENTORY", "A couple of dozen importable connector modules."),
    "detect-environment-env-files": (
        ABSOLUTE,
        "FIXED_INVENTORY",
        "The `.env*` files tracked at the repo root; a fixed, named set.",
    ),
    "direct-secrets-service-callers": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Production modules under two trees, against all tracked Python.",
    ),
    "docstring-restatement-scan": (
        ABSOLUTE,
        "NOT_PATHS",
        "Named public symbols, not files; nothing outside the sweep counts symbols.",
    ),
    "dpkg-ansible-registrations": (
        ABSOLUTE,
        "NOT_PATHS",
        "Ansible tasks registering a package-query result, not files.",
    ),
    "dpkg-list-call-sites": (ABSOLUTE, "NOT_PATHS", "Package-list invocations inside lines, not files."),
    "enum-hand-copy-census": (
        ABSOLUTE,
        "COMPLETION_GAP",
        "Its population is the tracked Python class, but it bounds `completed(parsed)` with the "
        "same declaration -- a file that will not parse is skipped, and one fraction cannot "
        "serve both bounds until that rate is measured and declared as `skips`.",
    ),
    "env-var-bare-cast": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "A filtered subset of tracked Python, against a Python class that grows elsewhere.",
    ),
    "excluded-tree-size-debt": (
        ABSOLUTE,
        "FIXED_INVENTORY",
        "Python inside the declared excluded trees -- a set the repository is trying to SHRINK, "
        "so a floor that rises with a reference would fight the work.",
    ),
    "fastapi-validation-handler": (ABSOLUTE, "SUBSET_DRIFTS", "Non-test Python, against all tracked Python."),
    "git-repo-root-call-site-files": (ABSOLUTE, "FIXED_INVENTORY", "Single-digit shell call sites."),
    "hardcoded-ui-literal-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Both frontends' `.vue` files, against all tracked `.vue`, which also includes the shared kit's and "
        "the excluded stories/tests.",
    ),
    "hardcoded-colour-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "One frontend tree's source, against all tracked `.vue`/`.ts`/`.js` including the other frontend.",
    ),
    "container-hardening-inline": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under two roots; the test-file share drifts.",
    ),
    "credential-field-name-only-callers": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked .py under thirteen declared trees; Python elsewhere (hidden dirs, root files) drifts alone.",
    ),
    "anti-pattern-type-emitters": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under two detector packages; the test-file share drifts.",
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
    "llc-actor-id-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under one root; the test-file share drifts.",
    ),
    "conftest-stubset-primitives": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "conftest.py files are a proper subset of tracked files under the pytest roots; no reference co-moves.",
    ),
    "root-resolver-depth-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "All tracked Python under seven roots, against all tracked Python in the repository.",
    ),
    "github-api-single-module": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under two roots; the test-file share drifts.",
    ),
    "architecture-family-definition-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under four roots; the test-file share drifts.",
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
    "hand-rolled-async-session-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Test-file .py under the two backend roots is a subset of tracked files; the non-test share drifts.",
    ),
    "hand-rolled-circuit-breaker-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under eight roots; the test-file share drifts.",
    ),
    "serving-predicate-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under four roots; the test-file share drifts.",
    ),
    "backoff-formula-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test .ts/.vue source is a subset of tracked files under three roots; the test-file share drifts.",
    ),
    "anthropic-message-split-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under one root; the test-file share drifts.",
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
    "knowledge-metadata-parse-canonical": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test knowledge_*.py route modules are a subset of tracked api files; the test-file share drifts.",
    ),
    "fact-read-authorization-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under three roots; the test-file share drifts.",
    ),
    "one-permission-gate-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under three roots; the test-file share drifts.",
    ),
    "env-file-family-18555-scan": (
        ABSOLUTE,
        "FIXED_INVENTORY",
        "The tracked env templates; a small, named set across four roots.",
    ),
    "ansible-concept-forks-17856-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Yaml, template and shell files are a subset of everything tracked under the ansible tree.",
    ),
    "concept-forks-17856-scan": (
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
    "model-tier-map-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under three roots; the test-file share drifts.",
    ),
    "embedding-model-render-sites": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked ansible yml/yaml files, of which only those naming a template that carries the variable are parsed.",
    ),
    "frontend-model-literal-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Frontend ts and vue source, excluding tests and generated types, against all tracked frontend files.",
    ),
    "tool-effect-table-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source under three roots, a subset of all tracked Python; the test-file share drifts.",
    ),
    "embedding-model-literal-sites": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Production python under two roots, a subset of all tracked Python; the test-file share drifts.",
    ),
    "chunker-private-hook-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked .py under three roots, a subset of all tracked Python; the test-file share drifts.",
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
    "gateway-adapter-package-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Python files under one gateway directory; tests and new adapters drift the count.",
    ),
    "provenance-accessor-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under autobot-backend; the test-file share drifts.",
    ),
    "audit-writer-single-source": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under three roots; the test-file share drifts.",
    ),
    "import-hermeticity": (
        ABSOLUTE,
        "NOT_PATHS",
        "Module records, not paths; the population is two declared trees minus tests.",
    ),
    "important-declaration-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Both frontends' components (shared with the raw-palette-class ratchet), against all tracked `.vue`, "
        "which also includes the shared kit's.",
    ),
    "infra-backend-import-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Python under the infrastructure tree, against all tracked Python; the backend grows independently.",
    ),
    "kb-admin-read-bypass": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Production Python under two trees, against all tracked Python.",
    ),
    "kb-content-redaction-chokepoint": (ABSOLUTE, "FIXED_INVENTORY", "Non-test files under one package."),
    "kb-read-visibility-production-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Production Python under three trees, against all tracked Python.",
    ),
    "model-revision-pinning-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Production Python under three trees, against all tracked Python.",
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
    "severity-enum-fork-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked Python under three roots against all tracked Python: the other roots (frontend "
        "tooling, SLM, tests, docs scripts) grow independently, so a share of the whole sinks "
        "with nothing wrong. The guard needs the roots reached, not a share of the repository.",
    ),
    "captcha-type-fork-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked Python under two roots against all tracked Python: the other roots grow independently, "
        "so a share of the whole sinks with nothing wrong. The guard needs the roots reached.",
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
    "doubled-api-prefix-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under two roots; the test-file share drifts.",
    ),
    "user-mode-default-carriers-18729": (
        ABSOLUTE,
        "FIXED_INVENTORY",
        "Compose files, container entrypoints and env templates: a small, named set.",
    ),
    "backend-migrations-resume-safe-18729": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Alembic revisions, growing.",
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
    "kb-construction-18122-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test Python under thirteen source roots, a subset of tracked Python; the test-file share drifts.",
    ),
    "slm-agent-single-definition-19040": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked Python, YAML and Jinja files, a subset of the tree; the other extensions grow at their own rate.",
    ),
}
