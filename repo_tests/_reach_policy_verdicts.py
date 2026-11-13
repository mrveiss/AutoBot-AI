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

from repo_tests._reach_policy_verdicts_mid import MID
from repo_tests._reach_policy_verdicts_n_to_z import N_TO_Z

ABSOLUTE = "ABSOLUTE"
CONVERTIBLE = "CONVERTIBLE"

_A_TO_M: dict[str, tuple[str, str, str]] = {
    "edge-configs-proxying-api-20046": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Configs and generators that proxy a public /api location: a small set, so a share of any file count "
        "means nothing.",
    ),
    "ci-requirements-one-install-workflows": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Workflow files are a subset of tracked YAML (#20191); compose, ansible and filter files grow "
        "at their own rate, so a share of all YAML would sink with nothing wrong.",
    ),
    "windows-install-scripts-stage-constraints-19681": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "The Windows install scripts that call pip on the installed requirements: a small named set, "
        "so a share of any file count means nothing.",
    ),
    "role-source-paths-depth-proof-20509": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Ansible YAML under roles, a subset of tracked files that grows at its own rate.",
    ),
    "operational-docs-playbook-references-19611": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Playbook references in operational docs and scripts, not files: docs grow at their own rate, so a share "
        "of any file count would sink with nothing wrong.",
    ),
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
    "ceiling-table-sweep-19544": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked Python only, a subset of all tracked files; the non-Python share grows at its own rate, "
        "so a share of all tracked files would sink with nothing wrong.",
    ),
    "migration-gate-test-import-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "One test directory's Python, against all tracked Python; the rest of the suite grows at its own rate.",
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
    "docker-smoke-context-publishers": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Top-level .yml under .github/workflows, against all tracked workflow files; reusable-body share drifts.",
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
    "file-type-sets-one-home-19339": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test Python under autobot-backend, a subset of all tracked Python; the test-file share drifts.",
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
    "frontend-local-date-formatter-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Both GUIs' component, view and composable .ts/.vue, excluding tests, against all tracked frontend source.",
    ),
    "frontend-hand-rolled-file-save-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Both GUIs' .ts/.vue source, excluding tests, specs and stories, against all tracked frontend source.",
    ),
    "frontend-hand-built-relative-time-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Both GUIs' .ts/.vue source, excluding tests, generated types and locales, against all tracked frontend.",
    ),
    "frontend-hand-rolled-spinner-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Both GUIs' and the plugins' .vue/.css, excluding tests, against all tracked frontend source.",
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
    "kb-populate-doc-patterns": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test infrastructure Python, against all tracked .py under autobot-infrastructure; drifts.",
    ),
    "kb-wipe-never-invoked": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Every tracked file, so a caller of the KB setup script in any component is seen (#21048); files are "
        "added in every PR, so an exact floor would fail any new file.",
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
    "duplicate-type-names-ts-files-scanned-14908": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Every non-test .ts file under two app trees and the kit; no reference count co-moves with it.",
    ),
    "duplicate-util-filenames-scanned-14908": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test .ts/.js files under the two apps' src/utils; the test-file share and other trees drift on their own.",
    ),
    "frontend-url-served-by-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Non-test Python, shell, YAML, Jinja, env and unit files under six roots plus the root .env profiles, a "
        "subset of tracked files; the test share and the other extensions grow at their own rate.",
    ),
}

#: Rows live in three modules (600-line ceiling): this one, `_mid` and `_n_to_z`. One table, one name; a key
#: in two modules is refused by `reach_allowance_verdicts_17914_test`, because a dict merge would
#: otherwise let the later one silently replace the earlier.
ALLOWANCE_VERDICTS: dict[str, tuple[str, str, str]] = {**_A_TO_M, **MID, **N_TO_Z}
