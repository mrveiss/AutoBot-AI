# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The record of glob declarations the python path filter does not cover (#15900).

Split out of ``glob_declared_reads_15900_test.py`` when that file reached the
600-line ceiling (#5060). The seam is data from assertions: this module holds
the record and nothing else, and the guard that enforces it imports from here.

The split is the fix rather than a larger ceiling, and it also removes a
recurring conflict: this is a registry every branch appends to, so appends now
land in a small data file instead of colliding inside a long test.

The shrink-only rule travels with the data and is restated below, because a
reader who lands here from an append will not have seen the guard's docstring.
"""

from __future__ import annotations

#: Glob declarations whose tree the python filter does NOT cover, with the guard
#: that declares each and why it is accepted for now.
#:
#: THIS ONLY SHRINKS. An entry leaves when the filter covers its tree, or when a
#: cheaper route runs that guard on its own trigger. Never add one to make a new
#: uncovered dependency pass — that is the decision this record exists to keep
#: visible rather than to rubber-stamp.
GLOB_DECLARED_UNCOVERED: dict[str, tuple[set[str], str]] = {
    "*.conf": (
        {"repo_tests/slm_frontend_atomic_publish_15610_test.py"},
        "root-relative `*.conf` sweep; the matching files live outside the python filter's trees",
    ),
    "*.conf.j2": (
        {"repo_tests/slm_frontend_atomic_publish_15610_test.py"},
        "root-relative `*.conf.j2` sweep; the matching files live outside the python filter's trees",
    ),
    "*.j2": (
        {
            "repo_tests/nginx_internal_api_key_auth_gate_test.py",
            "repo_tests/slm_frontend_publish_contract_test.py",
        },
        "root-relative `*.j2` sweep; the matching files live outside the python filter's trees",
    ),
    "*.md": (
        {
            "repo_tests/doc_sync_hook_resolves_indexer_15845_test.py",
            "repo_tests/documented_playbook_invocations_test.py",
            "repo_tests/sdk_docs_paths_test.py",
        },
        "root-relative `*.md` sweep; the matching files live outside the python filter's trees",
    ),
    "*.promtool-test.yml": (
        {"repo_tests/promtool_rules_test.py"},
        "root-relative `*.promtool-test.yml` sweep; the matching files live outside the python filter's trees",
    ),
    "*.service": (
        {"repo_tests/chromadb_bind_not_hardcoded_15317_test.py"},
        "root-relative `*.service` sweep; the matching files live outside the python filter's trees",
    ),
    "*.service.j2": (
        {"repo_tests/chromadb_bind_not_hardcoded_15317_test.py"},
        "root-relative `*.service.j2` sweep; the matching files live outside the python filter's trees",
    ),
    "*.sh": (
        {
            "repo_tests/ansible_inventory_path_exists_test.py",
            "repo_tests/chromadb_bind_not_hardcoded_15317_test.py",
            "repo_tests/deployment_script_scan.py",
            "repo_tests/embedded_python_dependency_declared_test.py",
            "repo_tests/git_merge_rejects_pull_only_flags_15938_test.py",
            "repo_tests/git_repo_root_calls_are_guarded_17418_test.py",
            "repo_tests/hook_decision_exit_codes_15956_test.py",
            "repo_tests/hooks_path_override_15961_test.py",
            "repo_tests/one_git_enumeration_15926_test.py",
            "repo_tests/python_filter_covers_tested_shell_wrappers_test.py",
            "repo_tests/redis_password_literal_guard_test.py",
            "repo_tests/shell_lib_test.py",
            "repo_tests/slm_frontend_publish_contract_test.py",
            "repo_tests/slm_frontend_shell_publish_test.py",
        },
        "root-relative `*.sh` sweep; the matching files live outside the python filter's trees",
    ),
    "*.ts": (
        {"repo_tests/slm_frontend_calls_reach_served_routes_test.py"},
        "root-relative `*.ts` sweep; the matching files live outside the python filter's trees",
    ),
    "*.vue": (
        {
            "repo_tests/hardcoded_colour_ratchet_17560_test.py",
            "repo_tests/slm_frontend_bare_ui_literals_test.py",
            "repo_tests/slm_frontend_calls_reach_served_routes_test.py",
        },
        "root-relative `*.vue` sweep; the matching files live outside the python filter's trees",
    ),
    "*.yaml": (
        {
            "repo_tests/generate_service_keys_export_dir_16348_test.py",
            "repo_tests/git_merge_rejects_pull_only_flags_15938_test.py",
            "repo_tests/hook_suites_run_in_ci_test.py",
            "repo_tests/hooks_path_override_15961_test.py",
            "repo_tests/infra_libs_test_wiring_guard_15051_test.py",
            "repo_tests/slm_frontend_publish_contract_test.py",
        },
        "root-relative `*.yaml` sweep; the matching files live outside the python filter's trees",
    ),
    "*.yml": (
        {
            "repo_tests/access_control_enforcement_provisioning_test.py",
            "repo_tests/ansible_code_source_delegation_17243_test.py",
            "repo_tests/ansible_generated_manifest_paths_17331_test.py",
            "repo_tests/ansible_inventory_mapping_renders_anywhere_test.py",
            "repo_tests/ansible_manifest_resolution.py",
            "repo_tests/ansible_pip_isolation_test.py",
            "repo_tests/ansible_pip_venv_creation_test.py",
            "repo_tests/ansible_python_interpreter_binary_scope_16750_test.py",
            "repo_tests/ansible_shared_tasks_code_source_dir_default_16750_test.py",
            "repo_tests/documented_playbook_invocations_test.py",
            "repo_tests/frontend_duplicate_typecheck_compile_guard_test.py",
            "repo_tests/git_merge_rejects_pull_only_flags_15938_test.py",
            "repo_tests/hook_suites_run_in_ci_test.py",
            "repo_tests/hooks_path_override_15961_test.py",
            "repo_tests/infra_libs_test_wiring_guard_15051_test.py",
            "repo_tests/job_name_names_what_it_runs_test.py",
            "repo_tests/nginx_sites_enabled_link_enforced_16979_test.py",
            "repo_tests/pip_relative_editable_needs_chdir_test.py",
            "repo_tests/python_interpreter_role_rename_test.py",
            "repo_tests/required_context_complements_test.py",
            "repo_tests/slm_frontend_publish_contract_test.py",
            "repo_tests/sync_deletions_ansible_wiring_16310_test.py",
            "repo_tests/test_agent_venv_isolation_14278.py",
            "repo_tests/test_ci_import_smoke_paths_14252.py",
            "repo_tests/test_deploy_constraint_rewrite_14272.py",
            "repo_tests/workflow_action_version_regression_test.py",
            "repo_tests/workflow_closed_reference_guard_test.py",
            "repo_tests/workflow_concurrency_guard_test.py",
        },
        "root-relative `*.yml` sweep; the matching files live outside the python filter's trees",
    ),
    "*_test.sh": (
        {"repo_tests/shell_lib_test.py"},
        "root-relative `*_test.sh` sweep; the matching files live outside the python filter's trees",
    ),
    "*package.json": (
        {
            "repo_tests/npm_audit_covers_its_workspaces_test.py",
            "repo_tests/npm_test_scripts_run_in_ci_test.py",
        },
        "root-relative `*package.json` sweep; the matching files live outside the python filter's trees",
    ),
    "*package-lock.json": (
        {"repo_tests/npm_audit_covers_its_workspaces_test.py"},
        "root-relative `*package-lock.json` sweep (#16131): a lockfile is what makes a workspace "
        "auditable, and they live outside the python filter's trees",
    ),
    "*requirements*.txt": (
        {"repo_tests/declared_distributions_test.py", "repo_tests/dependabot_requirements_coverage_test.py"},
        "root-relative `*requirements*.txt` sweep; the matching files live outside the python filter's trees",
    ),
    ".github/actions/**": (
        {"repo_tests/code_quality_guard_reach_test.py"},
        "CI metadata tree; covering it runs twelve shards on almost every pull request (#15900)",
    ),
    ".github/actions/*/action.yml": (
        {"repo_tests/python_version_declaration_drift_test.py"},
        "CI metadata tree; covering it runs twelve shards on almost every pull request (#15900)",
    ),
    ".github/workflows/*.yaml": (
        {
            "repo_tests/python_version_declaration_drift_test.py",
            "repo_tests/workflow_rc_capture_test.py",
        },
        "CI metadata tree; covering it runs twelve shards on almost every pull request (#15900)",
    ),
    ".github/workflows/*.yml": (
        {
            "repo_tests/comment_line_number_citations_test.py",
            "repo_tests/python_version_declaration_drift_test.py",
            "repo_tests/workflow_rc_capture_test.py",
        },
        "CI metadata tree; covering it runs twelve shards on almost every pull request (#15900)",
    ),
    "autobot-frontend/src/*.js": (
        {"repo_tests/vnc_password_not_in_frontend_source_16299_test.py"},
        "sweeps the whole frontend source tree for a leaked VNC password env-var reference "
        "(#16299); `autobot-frontend/` is outside the python filter's trees",
    ),
    "autobot-frontend/src/*.ts": (
        {"repo_tests/vnc_password_not_in_frontend_source_16299_test.py"},
        "sweeps the whole frontend source tree for a leaked VNC password env-var reference "
        "(#16299); `autobot-frontend/` is outside the python filter's trees",
    ),
    "autobot-frontend/src/*.vue": (
        {"repo_tests/vnc_password_not_in_frontend_source_16299_test.py"},
        "sweeps the whole frontend source tree for a leaked VNC password env-var reference "
        "(#16299); `autobot-frontend/` is outside the python filter's trees",
    ),
    "autobot-frontend/src/i18n/locales/*.json": (
        {"repo_tests/locale_html_entity_leak_test.py"},
        "scans every main-frontend locale file for an HTML entity leaking through "
        "{{ $t(...) }} (#17152); `autobot-frontend/src/i18n/` is outside the python filter's "
        "trees",
    ),
    # `autobot-slm-frontend/src/locales/*.json` DRAINED (#17174): that PR widened
    # .github/filters/python-paths.yml to cover `autobot-slm-frontend/src/locales/**`
    # (for an unrelated secrets-baseline fix in the same tree), so the
    # locale_html_entity_leak_test.py sweep over this specific path is no longer
    # uncovered -- confirmed by reading the filter file directly, not assumed from
    # the guard's own failure message alone.
    "docker/*.yml": (
        {"repo_tests/chromadb_bind_not_hardcoded_15317_test.py"},
        "sweeps compose files for a hardcoded ChromaDB bind address (#15317); `docker/` is "
        "outside the python filter's trees",
    ),
    "libs/autobot-sdk-ts/src/resources/*.ts": (
        {"repo_tests/sdk_ts_request_contract_test.py"},
        "reads the TS SDK's own resource-method source to check it against the backend's routes (#15528, "
        "#16495); `libs/` is outside the python filter's trees",
    ),
    "scripts/lib/*.sh": (
        {"repo_tests/comment_line_number_citations_test.py"},
        "tree `scripts/` is outside the python filter; the per-tree trade #15900 declines to make wholesale",
    ),
}
