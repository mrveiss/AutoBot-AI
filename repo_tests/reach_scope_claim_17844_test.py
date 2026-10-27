# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A declaration's claimed population must match the one its discovery reaches (#17844).

`floor` is a number the framework verifies. `what=` was free text nobody verified, and both sit
in the same `declare()` call. That leaves a third coverage state nothing could see:

| state | caught by |
|---|---|
| no floor at all | `guard_reach_meta_test.test_no_new_tree_scanning_guard_lacks_a_floor` |
| floored below its reach | the floor assertion itself |
| floored correctly, over the WRONG population | nothing, until this |

Measured on #17844's base: 52 `what=` strings, 14 naming a root or scope, 38 bare population
nouns. Seven guards claimed some form of "production python files" across floors from 2555 to
3247 -- a 692-file spread fully explained by differing scan roots, and invisible because only
two of the seven said which roots.

The real-fixture case below is the one the issue asks for by name. A synthetic declaration
proves the rule can fire; it does not prove the rule fires on the shape that actually occurs,
and the shape that occurs is a guard whose discovery stopped reaching one of its own roots
while its floor went on being cleared by the others.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import repo_tests.ansible_concept_forks_17856_test as _ansible_forks_guard  # noqa: F401 -- registers its scope
import repo_tests.anti_pattern_type_emitted_18189_test as _anti_pattern_guard  # noqa: F401 -- registers its scope
import repo_tests.audit_writer_single_source_17225_test as _audit_writer_guard  # noqa: F401 -- registers its scope
import repo_tests.chat_history_async_calls_awaited_18316_test as _chat_async_guard  # noqa: F401 -- registers its scope
import repo_tests.chat_single_delete_implementation_18316_test as _chat_delete_guard  # noqa: F401 -- registers its scope
import repo_tests.chunker_private_embedding_hooks_18185_test as _chunker_hooks_guard  # noqa: F401 -- registers its scope
import repo_tests.compat_module_needs_importer_18552_test as _compat_importer_guard  # noqa: F401 -- registers its scope
import repo_tests.concept_forks_17856_test as _concept_forks_guard  # noqa: F401 -- registers its scope
import repo_tests.conftest_stubset_primitives_13596_test as _conftest_stubset_guard  # noqa: F401 -- registers its scope
import repo_tests.container_hardening_single_source_17267_test as _hardening_guard  # noqa: F401 -- registers its scope
import repo_tests.conversation_turn_single_store_18293_test as _conversation_turn_guard  # noqa: F401 -- registers its scope
import repo_tests.credential_field_name_only_17336_test as _credential_field_guard  # noqa: F401 -- registers its scope
import repo_tests.data_db_path_single_source_test as _data_db_guard  # noqa: F401 -- registers its scope
import repo_tests.docker_admin_seed_18729_test as _user_mode_guard  # noqa: F401 -- registers its scope
import repo_tests.egress_default_guard_17576_test as _egress_default_guard  # noqa: F401 -- registers its scope
import repo_tests.embedding_model_preserved_15502_test as _embedding_render_guard  # noqa: F401 -- registers its scope
import repo_tests.env_file_family_18555_test as _env_family_guard  # noqa: F401 -- registers its scope
import repo_tests.env_fork_guard_18094_test as _env_fork_guard  # noqa: F401 -- registers its scope
import repo_tests.github_api_single_module_15411_test as _github_api_guard  # noqa: F401 -- registers its scope
import repo_tests.infra_scripts_no_backend_imports_18288_test as _infra_backend_guard  # noqa: F401 -- registers its scope
import repo_tests.kb_read_visibility_guard_test as kb
import repo_tests.knowledge_metadata_parse_canonical_18220_test as _metadata_parse_guard  # noqa: F401 -- registers its scope
import repo_tests.migration_gate_filter_covers_what_its_tests_import_test as _migration_gate_guard  # noqa: F401 -- registers its scope
import repo_tests.model_tier_single_definition_15502_test as _model_tier_guard  # noqa: F401 -- registers its scope
import repo_tests.no_doubled_api_prefix_18722_test as _doubled_api_prefix_guard  # noqa: F401 -- registers its scope
import repo_tests.oauth_bundle_no_app_secret_13630_test as _oauth_bundle_guard  # noqa: F401 -- registers its scope
import repo_tests.one_actor_id_15754_test as _actor_id_guard  # noqa: F401 -- registers its scope
import repo_tests.one_anthropic_message_split_16815_test as _anthropic_split_guard  # noqa: F401 -- registers its scope
import repo_tests.one_backoff_formula_15402_test as _backoff_formula_guard  # noqa: F401 -- registers its scope
import repo_tests.one_bm25_formula_18183_test as _bm25_guard  # noqa: F401 -- registers its scope
import repo_tests.one_brand_mark_and_announcer_18240_test as _brand_mark_guard  # noqa: F401 -- registers its scope
import repo_tests.one_circuit_breaker_18554_test as _circuit_breaker_guard  # noqa: F401 -- registers its scope
import repo_tests.one_claim_model_18086_test as _claim_model_guard  # noqa: F401 -- registers its scope
import repo_tests.one_content_digest_15722_test as _content_digest_guard  # noqa: F401 -- registers its scope
import repo_tests.one_deployment_mode_detector_12771_test as _deployment_mode_guard  # noqa: F401 -- registers its scope
import repo_tests.one_fact_read_authorization_18184_test as _fact_read_guard  # noqa: F401 -- registers its scope
import repo_tests.one_gateway_adapter_package_15024_test as _gateway_adapter_guard  # noqa: F401 -- registers its scope
import repo_tests.one_hybrid_search_17599_test as _hybrid_search_guard  # noqa: F401 -- registers its scope
import repo_tests.one_internal_api_key_reader_17856_test as _internal_key_reader_guard  # noqa: F401 -- registers its scope
import repo_tests.one_paths_filter_job_15360_test as _paths_filter_guard  # noqa: F401 -- registers its scope
import repo_tests.one_permission_gate_18263_test as _permission_gate_guard  # noqa: F401 -- registers its scope
import repo_tests.one_playwright_server_18549_test as _playwright_server_guard  # noqa: F401 -- registers its scope
import repo_tests.one_semantic_chunker_14485_test as _semantic_chunker_guard  # noqa: F401 -- registers its scope
import repo_tests.one_serving_predicate_18820_test as _serving_predicate_guard  # noqa: F401 -- registers its scope
import repo_tests.one_session_ownership_validator_14016_test as _ownership_validator_guard  # noqa: F401 -- registers its scope
import repo_tests.one_session_scope_15068_test as _session_scope_guard  # noqa: F401 -- registers its scope
import repo_tests.one_ssh_restart_executor_18186_test as _ssh_restart_guard
import repo_tests.one_static_data_copy_18556_test as _static_data_guard  # noqa: F401 -- registers its scope
import repo_tests.one_sync_command_runner_18180_test as _sync_runner_guard  # noqa: F401 -- registers its scope
import repo_tests.opt_autobot_literal_ratchet_18880_test as _opt_autobot_guard  # noqa: F401 -- registers its scope
import repo_tests.optimization_taxonomies_13049_test as _taxonomy_guard  # noqa: F401 -- registers its scope
import repo_tests.pr_comment_upsert_12984_test as _pr_comment_guard  # noqa: F401 -- registers its scope
import repo_tests.provider_key_env_reads_route_through_vault_18094_test as _provider_key_env_guard  # noqa: F401 -- registers its scope
import repo_tests.redis_direct_constructor_18553_test as _redis_constructor_guard  # noqa: F401 -- registers its scope
import repo_tests.root_resolver_single_source_18101_test as _root_resolver_guard  # noqa: F401 -- registers its scope
import repo_tests.script_module_names_unique_14873_test as _script_names_guard  # noqa: F401 -- registers its scope
import repo_tests.shadowed_literal_routes_18720_test as _shadowed_routes_guard  # noqa: F401 -- registers its scope
import repo_tests.single_attribute_writer_18240_test as _attribute_writer_guard  # noqa: F401 -- registers its scope
import repo_tests.slm_backend_no_embedded_playbook_18606_test as _embedded_playbook_guard  # noqa: F401 -- registers its scope
from repo_tests._paths import repo_root
from repo_tests._reach import Reach, ReachScopeError, declare
from repo_tests._reach_scope import relative_paths, scope_complaint

_ROOT = repo_root()
_NEW_GUARD_MODULES = (_ssh_restart_guard,)  # importing a guard module is what registers its scope


def test_declare_renders_the_scope_from_the_data() -> None:
    """`what=` is derived, so the string cannot disagree with the tuple the check reads."""
    reach = declare(
        "self-check::rendered-scope",
        discover=lambda _root: ["a/x.py"],
        floor=1,
        what="production python files",
        roots=("a/", "b/"),
    )
    assert reach.what == "production python files under a/, b/"


def test_declare_refuses_a_scope_written_twice() -> None:
    """Longhand beside the data is the drift this replaces, not a belt-and-braces restatement."""
    with pytest.raises(ValueError, match="already spells a scope out longhand"):
        declare(
            "self-check::double-scope",
            discover=lambda _root: ["a/x.py"],
            floor=1,
            what="production python files under a/",
            roots=("a/",),
        )


def test_declare_refuses_an_empty_roots_tuple() -> None:
    with pytest.raises(ValueError, match="non-empty tuple of path prefixes"):
        declare("self-check::empty-roots", discover=lambda _root: [], floor=1, what="things", roots=())


def test_the_real_guard_passes_its_own_scope_check() -> None:
    """The negative control, and it has to come first: a check that fails everything is not a check.

    `kb-read-visibility-production-sweep` is the declaration #17844 names as the instance -- it
    claimed "production python files" unqualified over three scan roots. With the scope carried
    as data it must now PASS, or the mutation below would be meaningless.
    """
    kb.REACH.verify_scope(_ROOT)
    assert kb.REACH.what.endswith(", ".join(kb.SCAN_ROOTS)), "the rendered claim must name the roots it was built from"


def test_a_real_guard_whose_discovery_stops_reaching_a_root_fails() -> None:
    """The mutation, on the REAL fixture rather than a synthetic one (#17844 AC2).

    The guard's own `discover` is kept and its output narrowed to two of its three declared
    roots -- the shape a moved directory or an inverted filter produces. The floor is untouched
    and still cleared: 2,701 files minus the MCP tree is far above 2,555, so every count check
    in the suite stays green. Only the scope check notices.
    """
    narrowed, dropped = kb.SCAN_ROOTS[:-1], kb.SCAN_ROOTS[-1]

    def _narrowed(root: Path) -> list[str]:
        return [rel for rel in kb._production_files(root) if rel.startswith(narrowed)]

    mutant = Reach(
        name="self-check::kb-read-visibility-narrowed",
        discover=_narrowed,
        floor=kb.REACH.floor,
        what=kb.REACH.what,
        growth=kb.REACH.growth,
        roots=kb.SCAN_ROOTS,
    )

    assert len(mutant.population(_ROOT)) >= mutant.floor, "precondition: the mutant must still clear its floor"
    with pytest.raises(ReachScopeError) as caught:
        mutant.verify_scope(_ROOT)
    assert dropped in str(caught.value), "the failure must name the root the sweep stopped reaching"


def test_a_sweep_reaching_outside_its_declared_scope_fails() -> None:
    """The mirror: a scope narrower than the sweep under-reports what the guard covers."""
    reach = Reach(
        name="self-check::under-claimed-scope",
        discover=lambda _root: ["a/x.py", "elsewhere/y.py"],
        floor=1,
        what="things under a/",
        roots=("a/",),
    )
    with pytest.raises(ReachScopeError, match="outside every declared root"):
        reach.verify_scope(_ROOT)


def test_a_declaration_whose_items_are_not_paths_is_refused_rather_than_passed() -> None:
    """`roots=` on a sweep returning parsed objects would be a claim nothing can check."""
    assert relative_paths([("a.yml", "job"), 3], _ROOT) is None
    complaint = scope_complaint("synthetic", "things", ("a/",), None)
    assert "not paths" in complaint


def test_the_scope_check_is_satisfiable() -> None:
    """Positive control for the primitive itself, independent of any live guard."""
    assert scope_complaint("synthetic", "things under a/, b/", ("a/", "b/"), ["a/x.py", "b/y.py"]) == ""


def test_a_declared_scope_that_the_sweep_does_not_reach_is_refused() -> None:
    """The synthetic control for `verify_scope`: it must be able to fail.

    The real-fixture mutation above is the one #17844 asks for; this is the cheap half that
    keeps `reach_declarations_test`'s parametrised sweep from passing vacuously if
    `verify_scope` ever became a no-op.
    """
    overclaiming = Reach(
        name="self-check::overclaiming-scope",
        discover=lambda _root: ["autobot-backend/api/x.py"],
        floor=1,
        what="production python files under autobot-backend/, autobot-slm-backend/",
        roots=("autobot-backend/", "autobot-slm-backend/"),
    )
    with pytest.raises(ReachScopeError, match="found NOTHING under"):
        overclaiming.verify_scope(_ROOT)


#: What each scoped declaration claims, written out BY HAND rather than read from the constant
#: the guard walks (#17844, review). Every call site passes `roots=SCAN_ROOTS` or the local
#: equivalent, so narrowing that constant narrows the claim with it and `verify_scope` stays
#: green over the smaller population -- which is the very mutation #17844's AC2 describes.
#: This is the independent second derivation that closes it: narrow a guard's roots constant
#: and this goes red, because the expectation does not move with it.
#:
#: Compared as a SET in both directions. Adding a scoped declaration means adding a line here,
#: and that is the point -- the scope is a decision, so it is written twice on purpose.
_DECLARED_SCOPES = {
    "kit-shadow-ts-files-scanned-14908": ("autobot-frontend/src", "autobot-slm-frontend/src"),
    "v-html-sanitiser-sinks": (
        "autobot-frontend/src",
        "autobot-slm-frontend/src",
        "libs/autobot-ui/src",
        "libs/autobot-ui/index.ts",
    ),
    "audit-writer-single-source": ("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    "container-hardening-inline": ("autobot-backend", "autobot_shared"),
    "brand-mark-announcer-scan": ("libs/autobot-ui", "autobot-frontend/src", "autobot-slm-frontend/src"),
    "one-content-digest-scan": ("autobot-backend", "autobot_shared"),
    "audit-action-vocabulary": ("autobot-backend", "autobot_shared", "autobot-slm-backend"),
    "hand-rolled-redis-pipeline-scan": ("autobot-backend", "autobot-slm-backend"),
    "one-internal-api-key-reader-scan": ("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    "provider-key-env-read-scan": ("autobot-backend", "autobot_shared", "plugins"),
    "semantic-chunker-fork-scan": ("autobot-backend", "autobot_shared"),
    "migration-gate-test-import-sweep": ("autobot-backend/tests/migrations",),
    "paths-filter-workflow-sweep": (".github/workflows",),
    "workflow-visible-name-sweep": (".github/workflows",),
    "anti-pattern-type-emitters": ("autobot-backend/code_analysis", "autobot-backend/code_intelligence"),
    "compat-module-needs-importer": ("autobot-backend",),
    "chat-history-async-calls-awaited": ("autobot-backend/api",),
    "chat-single-delete-implementation": ("autobot-backend/api",),
    "ai-line-single-policy": ("autobot-backend", "autobot_shared"),
    "no-literal-secret-default": ("autobot-slm-backend", "autobot-backend", "autobot_shared"),
    "hardcoded-ui-literal-scan": ("autobot-frontend/src/", "autobot-slm-frontend/src/"),
    "shadowed-literal-routes": ("autobot-backend", "autobot-slm-backend"),
    "conversation-turn-single-store": ("autobot-backend", "autobot_shared", "autobot-infrastructure"),
    "credential-field-name-only-callers": (
        "autobot-backend",
        "autobot-slm-backend",
        "autobot_shared",
        "plugins",
        "scripts",
        "pipeline-scripts",
        "tools",
        "repo_tests",
        "autobot-infrastructure",
        "autobot-npu-worker",
        "autobot-tts-worker",
        "autobot-browser-worker",
        "libs",
    ),
    "chunker-private-hook-scan": ("autobot-backend", "autobot-infrastructure", "autobot_shared"),
    "chunk-identity-single-home-18142": ("autobot-backend/", "autobot_shared/"),
    "provenance-accessor-scan": ("autobot-backend",),
    "embedding-model-literal-sites": (
        "autobot-backend",
        "autobot_shared",
        "autobot-infrastructure/shared/scripts/populate_kb_chromadb.py",
        "autobot-infrastructure/shared/tools/index_documentation.py",
    ),
    "single-attribute-writer-scan": ("autobot-frontend/src",),
    "torch-pair-literals": (
        ".github",
        "docker",
        "autobot-infrastructure",
        "autobot-slm-backend/ansible",
        "scripts",
        "install.sh",
    ),
    "tool-effect-table-scan": ("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    "deployment-mode-detector-scan": ("autobot-backend/", "autobot-infrastructure/"),
    "egress-default-outbound-call-sites": (
        "autobot-",
        "autobot_shared/",
        "debug/",
        "plugins/",
        "scripts/",
        "pipeline-scripts/",
    ),
    "egress-default-outbound-call-sweep": (
        "autobot-",
        "autobot_shared/",
        "debug/",
        "plugins/",
        "scripts/",
        "pipeline-scripts/",
    ),
    "ansible-concept-forks-17856-scan": ("autobot-slm-backend/ansible",),
    "defined-twice-18094-scan": (
        "autobot-backend",
        "autobot-slm-backend",
        "autobot_shared",
        "autobot-infrastructure",
        "autobot-npu-worker",
        "scripts",
    ),
    "env-fallback-read-sites-18094": (
        "autobot-backend",
        "autobot-slm-backend",
        "autobot_shared",
        "autobot-infrastructure",
        "autobot-npu-worker",
        "scripts",
    ),
    "env-file-family-18555-scan": (".env", "autobot-frontend/", "autobot-slm-backend/", "docker/"),
    "user-mode-default-carriers-18729": (
        ".env",
        "autobot-frontend/",
        "autobot-slm-backend/",
        "docker-compose",
        "docker/",
    ),
    "backend-migrations-resume-safe-18729": ("autobot-backend/migrations/versions",),
    "opt-autobot-literal-ratchet-18880": ("autobot-slm-backend/ansible",),
    "concept-forks-17856-scan": ("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    "gateway-adapter-package-scan": ("autobot-backend/services/gateway",),
    "architecture-family-definition-scan": (
        "autobot-backend",
        "autobot-npu-worker",
        "autobot-slm-backend",
        "autobot_shared",
    ),
    "optimization-taxonomy-scan": ("autobot-backend/llm_shared/optimization",),
    "github-api-single-module": ("pipeline-scripts", "scripts"),
    "conftest-stubset-primitives": (
        "autobot-backend",
        "autobot-infrastructure",
        "autobot-npu-worker",
        "autobot-slm-backend",
        "repo_tests",
    ),
    "root-resolver-depth-scan": (
        "autobot-backend",
        "autobot-slm-backend",
        "autobot_shared",
        "pipeline-scripts",
        "repo_tests",
        "scripts",
        "tools",
    ),
    "llc-actor-id-scan": ("autobot-backend/llc",),
    "generated-type-redeclarations": ("autobot-frontend/src",),
    "severity-order-copies": ("autobot-backend", "autobot-slm-backend", "autobot_shared", "pipeline-scripts"),
    "llc-sigterm-grace-copies": ("autobot-backend/llc",),
    "frontend-http-transports": ("autobot-frontend/src", "autobot-slm-frontend/src"),
    "search-mode-copies": ("autobot-backend",),
    "redaction-placeholder-literals": ("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    "one-system-knowledge-template-tree": ("autobot-backend",),
    "one-static-data-copy-scan": (
        "autobot-backend",
        "autobot-slm-backend",
        "autobot-infrastructure",
        "autobot-monitoring",
    ),
    "hand-rolled-async-session-scan": (
        "autobot-backend",
        "autobot-slm-backend",
    ),
    "hand-rolled-circuit-breaker-scan": (
        "autobot-backend",
        "autobot-slm-backend",
        "autobot_shared",
        "autobot-npu-worker",
        "autobot-tts-worker",
        "autobot-browser-worker",
        "plugins",
        "libs",
    ),
    "serving-predicate-scan": ("autobot-backend", "autobot_shared", "plugins", "libs"),
    "anthropic-message-split-scan": ("autobot-backend/llm_shared/providers",),
    "backoff-formula-scan": ("libs/autobot-ui", "autobot-frontend/src", "autobot-slm-frontend/src"),
    "doubled-api-prefix-scan": ("autobot-backend/api", "autobot-slm-backend/api"),
    "script-module-name-scan": ("autobot-infrastructure/shared/scripts",),
    "post-commit-seed-scan": ("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    "redis-direct-constructor-scan": (
        "autobot-backend",
        "autobot-slm-backend",
        "autobot_shared",
        "autobot-infrastructure",
        "autobot-npu-worker",
        "autobot-tts-worker",
        "autobot-browser-worker",
        "scripts",
        "pipeline-scripts",
        "tools",
        "plugins",
        "libs",
        "debug",
    ),
    "slm-backend-embedded-playbook-scan": ("autobot-slm-backend",),
    "slm-node-enum-members-exist": ("autobot-slm-backend",),
    "one-playwright-server-scan": (
        "autobot-browser-worker",
        "autobot-infrastructure",
        "autobot-frontend",
    ),
    "fact-read-authorization-scan": ("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    "one-permission-gate-scan": ("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    "infra-backend-import-scan": ("autobot-infrastructure",),
    "captcha-type-fork-scan": ("autobot-backend", "autobot_shared"),
    "severity-enum-fork-scan": ("autobot-backend", "autobot_shared", "autobot-infrastructure"),
    "session-ownership-validator-scan": ("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    "knowledge-metadata-parse-canonical": ("autobot-backend/api",),
    "monitoring-version-literals": ("docker-compose.yml", "autobot-infrastructure", "autobot-slm-backend/ansible"),
    "model-tier-map-scan": ("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    "embedding-model-render-sites": ("autobot-slm-backend/ansible",),
    "frontend-model-literal-scan": ("autobot-frontend/src",),
    "one-bm25-formula": ("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    "one-hybrid-search": ("autobot-backend", "autobot_shared"),
    "shared-authority-callers-scan": ("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    "one-doc-indexer": (
        "autobot-backend",
        "autobot-slm-backend",
        "autobot_shared",
        "autobot-infrastructure",
        "tools",
        "scripts",
    ),
    "pr-comment-upsert-sweep": (".github/workflows", "scripts", "tools", "pipeline-scripts", "autobot_shared"),
    "sync-command-result-mapping-scan": ("autobot-backend",),
    "one-claim-model-scan": ("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    "direct-secrets-service-callers": ("autobot-backend", "autobot_shared"),
    "data-db-path-production-python": ("autobot-backend", "autobot_shared"),
    "jekyll-processed-docs": ("docs",),
    "kb-admin-read-bypass": ("autobot-backend/", "autobot_shared/"),
    "kb-construction-18122-scan": (
        "autobot-backend/",
        "autobot-infrastructure/",
        "autobot-slm-backend/",
        "autobot_shared/",
        "autobot-npu-worker/",
        "autobot-tts-worker/",
        "autobot-browser-worker/",
        "tools/",
        "scripts/",
        "pipeline-scripts/",
        "plugins/",
        "libs/",
        "debug/",
    ),
    "kb-read-visibility-production-sweep": (
        "autobot-backend/",
        "autobot_shared/",
        "autobot-infrastructure/shared/mcp/",
    ),
    "model-revision-pinning-sweep": ("autobot-backend", "autobot_shared", "autobot-slm-backend"),
    "oauth-bundle-app-secret-scan": ("autobot-backend", "autobot_shared"),
    "one-claim-registry": (
        "autobot-backend",
        "autobot_shared",
        "autobot-slm-backend",
        "scripts",
        "pipeline-scripts",
    ),
    "store-fact-chokepoint": ("autobot-backend/", "autobot_shared/"),
    "ssh-restart-executor-scan": ("autobot-slm-backend",),
}


def test_every_scoped_declaration_claims_the_roots_recorded_here() -> None:
    """A guard's roots constant cannot be narrowed without this failing.

    `verify_scope` holds the sweep to `roots`; it cannot hold `roots` to anything, because the
    call sites alias the same constant the discovery walks. Without this pin, deleting a tree
    from `SCAN_ROOTS` shrinks the sweep AND the claim together and every check in the suite
    stays green over two thirds of the population -- the exact state #17844 was filed about.
    """
    import repo_tests.direct_secrets_service_callers_17773_test  # noqa: F401, PLC0415
    import repo_tests.docs_liquid_tags_are_defined_17930_test  # noqa: F401, PLC0415
    import repo_tests.kb_admin_read_bypass_guard_test  # noqa: F401, PLC0415
    import repo_tests.model_revision_pinning_enforced_17804_test  # noqa: F401, PLC0415
    import repo_tests.one_claim_registry_16653_test  # noqa: F401, PLC0415

    # Every guard module, not a hand-kept list: importing reach_declarations_test runs its
    # _import_every_guard(), so this check sees the same REGISTRY alone as in a full run. A
    # hand list drifted (#18295 train fixups recorded scopes whose modules it never imported),
    # and the test then failed only when run alone -- i.e. in every pre-push.
    import repo_tests.reach_declarations_test  # noqa: F401, PLC0415
    import repo_tests.store_fact_chokepoint_guard_test  # noqa: F401, PLC0415
    from repo_tests._reach import REGISTRY

    live = {
        name: reach.roots for name, reach in REGISTRY.items() if reach.roots and not name.startswith("self-check::")
    }
    assert live == _DECLARED_SCOPES, (
        "declared scopes disagree with the hand-written record. Narrowed or widened: "
        + repr(
            {
                n: (live.get(n), _DECLARED_SCOPES.get(n))
                for n in set(live) ^ set(_DECLARED_SCOPES) | {n for n in live if live[n] != _DECLARED_SCOPES.get(n)}
            }
        )
        + "\nA root removed from a guard's own constant shrinks the sweep and the claim "
        "together, which nothing else here can see. Change both, in one diff, on purpose."
    )
