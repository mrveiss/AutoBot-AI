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

from repo_tests._reach_policy_verdicts_n_to_z import N_TO_Z

ABSOLUTE = "ABSOLUTE"
CONVERTIBLE = "CONVERTIBLE"

_A_TO_M: dict[str, tuple[str, str, str]] = {
    "chunk-identity-single-home-18142": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test Python under the backend and shared trees, a subset of tracked Python; the test share and "
        "the other trees grow at their own rate, so a share of all Python would sink with nothing wrong.",
    ),
    "browser-port-single-home-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked code, config and env files by extension, minus docs/ and changelog/; the Markdown and "
        "asset share grows at its own rate, so a share of all tracked files would sink with nothing wrong.",
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
    "defined-twice-18094-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Production Python under six sweep roots, test files excluded: a subset of tracked files that drifts.",
    ),
    "env-fallback-read-sites-18094": (
        ABSOLUTE,
        "NOT_PATHS",
        "Call sites, not paths: one id per literal-fallback env read in the sweep roots, a subset of tracked Python.",
    ),
    "dead-icon-selector-vue-files": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "One frontend tree's `.vue` files, against all tracked `.vue` including the other frontend and the kit.",
    ),
    "deployment-mode-detector-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Python files under two of the tracked trees, a subset of all tracked Python; the other trees drift.",
    ),
    "deployment-profile-writers-19315": (
        ABSOLUTE,
        "NOT_PATHS",
        "Assignment lines, not paths: one item per literal AUTOBOT_ENVIRONMENT/DEPLOYMENT_MODE/DEBUG write.",
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
    "chromadb-port-one-home-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked files outside docs and tests, a subset of the tree; docs and tests grow at their own rate.",
    ),
    "compose-files": (
        ABSOLUTE,
        "FIXED_INVENTORY",
        "Single-digit compose files at any depth; a fraction of any reference is noise at this size.",
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
    "compose-nodes-restated-default": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test SLM, infrastructure and docker files plus the root compose file; drifts.",
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
    "cache-never-in-repo": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test modules of both backends and autobot_shared, against all tracked .py under them; "
        "the test-file share drifts.",
    ),
    "generated-type-redeclarations": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "The main GUI's non-test .ts/.vue, against all tracked frontend source; the test-file share drifts.",
    ),
    "llc-sigterm-grace-copies": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test LLC modules, against all tracked .py under autobot-backend/llc; the test-file share drifts.",
    ),
    "frontend-http-transports": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Both GUIs' non-test .ts/.js/.vue under src, against all tracked frontend source; the test-file share drifts.",
    ),
    "feature-routers-strict-one-home-19319": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "All tracked files minus vendored/build parts, against the whole tracked tree; the skipped share drifts.",
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
    "monitoring-version-literals": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Compose, infrastructure and Ansible files (yml/yaml/ini/sh), against all tracked files there; drifts.",
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
    "ansible-credentials-never-logged": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked ansible yml/yaml files; every one is parsed, but only task lists carry http tasks to judge.",
    ),
    "frontend-local-formatter-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Both GUIs' component, view and composable .ts/.vue, excluding tests, against all tracked frontend source.",
    ),
    "frontend-model-literal-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Frontend ts and vue source, excluding tests and generated types, against all tracked frontend files.",
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
    "gateway-adapter-package-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Python files under one gateway directory; tests and new adapters drift the count.",
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
    "captcha-type-fork-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked Python under two roots against all tracked Python: the other roots grow independently, "
        "so a share of the whole sinks with nothing wrong. The guard needs the roots reached.",
    ),
    "doubled-api-prefix-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test source is a subset of tracked .py under two roots; the test-file share drifts.",
    ),
    "backend-migrations-resume-safe-18729": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Alembic revisions, growing.",
    ),
    "kb-construction-18122-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test Python under thirteen source roots, a subset of tracked Python; the test-file share drifts.",
    ),
    "disaster-recovery-deployed-units": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Ansible role task files, a subset of tracked YAML; workflows and inventories grow on their own.",
    ),
    "landing-page-declared-dependencies": (
        ABSOLUTE,
        "FIXED_INVENTORY",
        "The requirements files and the root pyproject.toml: a small, deliberately enumerable set.",
    ),
    "kit-export-names-14908": (ABSOLUTE, "NOT_PATHS", "Names parsed out of the kit's index, not files."),
    "kit-shadow-ts-files-scanned-14908": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "The scanned .ts files are every non-test file under two app trees; no reference count co-moves with it.",
    ),
}

#: Rows whose name sorts n-z live in the sibling module (600-line ceiling); one table, one name.
ALLOWANCE_VERDICTS: dict[str, tuple[str, str, str]] = {**_A_TO_M, **N_TO_Z}
