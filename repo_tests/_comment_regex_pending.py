# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Files whose regex strips or reads a comment construct, pending migration (#21569).

Measured with the guard's own detector over the tree it sweeps: **40 files** (plus
`tools/lint/_comment_syntax.py`, the canonical exemption). **This list only ever shrinks.**

Not every entry is a source scanner. Some are format parsers where a trailing `#` is part of the
format (`env_file_family_18555_test`, `service_units_set_logs_dir_20894_test`), one reads comments
as data (`check_spdx_header`), and one strips Jinja comments (`tts_model_config_names_what_runs_19734_test`);
the same argument as in the guard's own list applies: an entry leaving here must be argued.
`<!--`: `tools/lint/_comment_syntax.py` already has `strip_html_comments` and
`strip_html_and_block_comments`; the `<!--` entries below should adopt them.
"""

PENDING_REGEX_STRIPPERS = frozenset(
    {
        "pipeline-scripts/issue_structure.py",
        "pipeline-scripts/landing_notes.py",
        "repo_tests/_filter_entries.py",
        "repo_tests/_hardcoded_colour_detect.py",
        "repo_tests/_unconnected_clients.py",
        "repo_tests/_unconnected_mounts.py",
        "repo_tests/ambient_git_vars_mirror_test.py",
        "repo_tests/analytics_page_open_reads_only_20491_test.py",
        "repo_tests/compat_module_needs_importer_18552_test.py",
        "repo_tests/compose_nodes_one_home_19323_test.py",
        "repo_tests/dead_icon_selector_ratchet_19491_test.py",
        "repo_tests/embedding_model_one_resolver_19377_test.py",
        "repo_tests/env_file_family_18555_test.py",
        "repo_tests/frontend_api_contract_ratchet_test.py",
        "repo_tests/frontend_api_timeout_ssot_17856_test.py",
        "repo_tests/frontend_hand_built_relative_time_19606_test.py",
        "repo_tests/frontend_hand_rolled_file_save_ratchet_20770_test.py",
        "repo_tests/frontend_local_date_formatter_ratchet_19905_test.py",
        "repo_tests/frontend_local_formatter_ratchet_19680_test.py",
        "repo_tests/frontend_reduced_motion_guard_test.py",
        "repo_tests/frontend_single_api_client_12363_test.py",
        "repo_tests/hook_interpreter_resolver_21163_test.py",
        "repo_tests/icon_rule_sets_font_size_only_19875_test.py",
        "repo_tests/internal_paths_denied_at_edge_20046_test.py",
        "repo_tests/kit_export_shadow_ratchet_14908_test.py",
        "repo_tests/kit_loading_ratchet_19906_test.py",
        "repo_tests/model_tier_single_definition_15502_test.py",
        "repo_tests/monitoring_versions_one_home_19329_test.py",
        "repo_tests/primary_fill_label_reads_text_on_primary_20425_test.py",
        "repo_tests/redis_unit_is_the_stack_unit_16071_test.py",
        "repo_tests/service_port_homes_test.py",
        "repo_tests/service_units_set_logs_dir_20894_test.py",
        "repo_tests/slm_frontend_i18n_parity_test.py",
        "repo_tests/slm_raw_setinterval_ratchet_19482_test.py",
        "repo_tests/torch_pair_one_home_19330_test.py",
        "repo_tests/tts_model_config_names_what_runs_19734_test.py",
        "repo_tests/v_html_sanitiser_guard_19118_test.py",
        "repo_tests/workflow_rc_capture_test.py",
        "tools/lint/check_code_quality_guard_reach.py",
        "tools/lint/check_spdx_header.py",
    }
)
