# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Allowance-verdict rows split out of `_reach_policy_verdicts` a second time (#21206), when it again reached
its 600-line ceiling. `_reach_policy_verdicts.ALLOWANCE_VERDICTS` merges every part; nothing imports this
module directly except that one. New rows may go in any of the three modules, but a name must appear in
exactly one (`reach_allowance_verdicts_17914_test` fails on a repeat).
"""

from __future__ import annotations

ABSOLUTE = "ABSOLUTE"
CONVERTIBLE = "CONVERTIBLE"

MID: dict[str, tuple[str, str, str]] = {
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
    "icon-font-size-rule-vue-files": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "One frontend tree's `.vue` files, against all tracked `.vue` including the other frontend and the kit.",
    ),
    "primary-fill-white-label-files": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "One frontend tree's `.vue` and `.css` files, against all tracked ones incl. the other frontend and kit.",
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
    "ansible-files-scanned-for-slm-port": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Ansible YAML and templates are a subset of tracked files; other trees grow independently of it.",
    ),
    "ansible-apt-repo-budget-override-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Ansible variable files are a subset of tracked YAML; workflow and compose YAML grow "
        "independently of the ansible tree, so a share of all YAML sinks with nothing wrong.",
    ),
    "ansible-status-queries-check-mode-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Ansible YAML is a subset of all tracked YAML under the SLM backend; templates, scripts and "
        "docs beside it grow independently, so a share of the tree sinks with nothing wrong.",
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
    "autobot-has-no-pro-name": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Every tracked file minus changelogs and the guard itself (#19982); files are added in every PR, "
        "so an exact floor would fail any new file, and the changelog share grows at its own rate.",
    ),
    "autobot-has-no-pro-tier-in-user-text": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "The .vue components and locale JSON of two frontends (#19982), a subset of tracked files; "
        "every new component grows it, and the rest of the tree grows at its own rate.",
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
    "unconnected-code-modules": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Backend modules that could have a caller (no `__init__`, `__main__` script, migration or testkit); a subset "
        "of the backends' `.py` files whose share drifts as tests and migrations are added (#20512).",
    ),
    "unconnected-code-routes": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Backend files that declare a route decorator; a subset of the backends' `.py` files that drifts as "
        "non-router modules are added (#20512).",
    ),
    "unconnected-code-stores": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Files that push to a Redis queue or define a table; a small subset of the tracked tree that drifts "
        "with it (#20512).",
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
        "Both frontends' source (#17567), against all tracked `.vue`/`.ts`/`.js`, which includes the shared kit.",
    ),
}
