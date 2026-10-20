# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
# flake8: noqa: E501  -- the keys are `path::qualname::field::kind` and one line each
"""Frozen allowlist of the trust/validity readers that exist outside `knowledge/serving.py` (#18820).

Each key is `<repo path>::<enclosing qualname>::<field>::<kind>` (`<module>` outside any def/class,
`Class.method` for a method), so a new hand filter in a function of an already-listed file is a new key and
fails the guard. The value is the reason it is not a second serving predicate. The list may only SHRINK:
a new match fails the guard, and an entry whose reader left the tree (or stopped matching) fails it too
until the line is deleted. `FROZEN_TOTAL` caps the length so a stale-then-refilled list cannot grow quietly.

`READ` = a load of `.valid_to` / `.valid_until` / `.valid_from` / `.is_active` / `.verification_status`
(attribute, `x["f"]` or `x.get("f")`). `REJECT_CMP` / `REJECT_WHERE` have NO entries: today only
`knowledge/serving.py` compares a trust state to "rejected". Entries marked MIGRATE are serving-shaped
and should move onto the predicate; the rest are not facts or not a serving decision.
"""

from __future__ import annotations

_AGENT_RUNTIME = "is_active of a live agent-loop assertion, agent channel or terminal session; not a knowledge fact"
_CREDENTIAL = "is_active of a stored credential or API key (secrets store); not a knowledge fact"
_ACCOUNT = "is_active of a user, organization or person account; not a knowledge fact"
_CONFIG = "is_active of a share link, model record or project phase; not a knowledge fact"
_TRUST = (
    "reads verification_status for review queue, export or retention; not a serving decision "
    "(never compares to rejected)"
)
_ATOMIC = (
    "AtomicFact model: the extraction pipeline's own validity bookkeeping (invalidate, "
    "serialise, active_facts property); MIGRATE the active_facts view onto knowledge.serving if "
    "it gains a serving caller"
)
_TEMPORAL = (
    "temporal-invalidation job: ages facts and persists valid_until; it decides what to INVALIDATE, not what to serve"
)

_INVALIDATION_FLAG = (
    "stored is_active flag read by the temporal-invalidation job's fact loader (invalidation bookkeeping, "
    "not a serving decision: a future-dated or date-expired fact must still be loaded to be invalidated, #18820)"
)

ALLOWLIST: dict[str, str] = {
    "autobot-backend/agent_loop/belief_state.py::BeliefState.active_assertions::is_active::READ": _AGENT_RUNTIME,
    "autobot-backend/agent_loop/belief_state.py::BeliefState.get::is_active::READ": _AGENT_RUNTIME,
    "autobot-backend/agent_loop/loop.py::AgentLoop._maybe_use_cached_assertion::is_active::READ": _AGENT_RUNTIME,
    "autobot-backend/agent_loop/loop.py::AgentLoop._think_before_completion::is_active::READ": _AGENT_RUNTIME,
    "autobot-backend/agent_loop/types.py::Assertion.to_dict::is_active::READ": _AGENT_RUNTIME,
    "autobot-backend/api/agent_config.py::_get_agent_config_from_slm::is_active::READ": _CONFIG,
    "autobot-backend/api/chat_shared_links.py::_resolve_link::is_active::READ": _CONFIG,
    "autobot-backend/api/chat_shared_links.py::list_all_shared_links_admin::is_active::READ": _CONFIG,
    "autobot-backend/api/chat_shared_links.py::list_shared_links::is_active::READ": _CONFIG,
    "autobot-backend/api/coordination_issue_claims_credential.py::_revoke_previous::is_active::READ": _CREDENTIAL,
    "autobot-backend/api/knowledge_verification.py::_is_pending_review::verification_status::READ": _TRUST,
    "autobot-backend/api/phases.py::get_phases_status::is_active::READ": _CONFIG,
    "autobot-backend/api/project_state.py::get_all_phases::is_active::READ": _CONFIG,
    "autobot-backend/api/terminal.py::list_terminal_sessions::is_active::READ": _AGENT_RUNTIME,
    "autobot-backend/api/user_management/organizations.py::_org_to_response::is_active::READ": _ACCOUNT,
    "autobot-backend/api/user_management/users.py::_user_to_response::is_active::READ": _ACCOUNT,
    "autobot-backend/api/user_provider_credentials.py::create_or_update_credential::is_active::READ": _CREDENTIAL,
    "autobot-backend/api/user_provider_credentials.py::delete_credential::is_active::READ": _CREDENTIAL,
    "autobot-backend/api/user_provider_credentials.py::list_credentials::is_active::READ": _CREDENTIAL,
    "autobot-backend/benchmarks/benchmark_belief_state.py::_assertion_summary_tokens::is_active::READ": _AGENT_RUNTIME,
    "autobot-backend/knowledge/adapters/okf_adapter.py::_build_frontmatter::verification_status::READ": _TRUST,
    "autobot-backend/knowledge/facts.py::_fact_is_protected::verification_status::READ": _TRUST,
    "autobot-backend/llc/api/companies.py::_compose_human_nodes::is_active::READ": _ACCOUNT,
    "autobot-backend/llc/api/companies.py::list_members::is_active::READ": _ACCOUNT,
    "autobot-backend/llm_shared/run_credential_loader.py::load_user_provider_credentials::is_active::READ": _CREDENTIAL,
    "autobot-backend/models/atomic_fact.py::AtomicFact.__repr__::is_active::READ": _ATOMIC,
    "autobot-backend/models/atomic_fact.py::AtomicFact.__str__::is_active::READ": _ATOMIC,
    "autobot-backend/models/atomic_fact.py::AtomicFact.from_dict::is_active::READ": _ATOMIC,
    "autobot-backend/models/atomic_fact.py::AtomicFact.from_dict::valid_from::READ": _ATOMIC,
    "autobot-backend/models/atomic_fact.py::AtomicFact.from_dict::valid_until::READ": _ATOMIC,
    "autobot-backend/models/atomic_fact.py::AtomicFact.invalidate::valid_from::READ": _ATOMIC,
    "autobot-backend/models/atomic_fact.py::AtomicFact.should_invalidate::valid_from::READ": _ATOMIC,
    "autobot-backend/models/atomic_fact.py::AtomicFact.to_dict::is_active::READ": _ATOMIC,
    "autobot-backend/models/atomic_fact.py::AtomicFact.to_dict::valid_from::READ": _ATOMIC,
    "autobot-backend/models/atomic_fact.py::AtomicFact.to_dict::valid_until::READ": _ATOMIC,
    "autobot-backend/models/atomic_fact.py::AtomicFact.to_redis_mapping::is_active::READ": _ATOMIC,
    "autobot-backend/models/atomic_fact.py::AtomicFact.to_redis_mapping::valid_from::READ": _ATOMIC,
    "autobot-backend/models/atomic_fact.py::AtomicFact.with_resolved_entities::is_active::READ": _ATOMIC,
    "autobot-backend/models/atomic_fact.py::AtomicFact.with_resolved_entities::valid_from::READ": _ATOMIC,
    "autobot-backend/models/atomic_fact.py::AtomicFact.with_resolved_entities::valid_until::READ": _ATOMIC,
    "autobot-backend/models/atomic_fact.py::FactExtractionResult.active_facts::is_active::READ": _ATOMIC,
    "autobot-backend/models/chat_shared_link.py::ChatSharedLink.__repr__::is_active::READ": _CONFIG,
    "autobot-backend/models/ml_model.py::MLModel.__repr__::is_active::READ": _CONFIG,
    "autobot-backend/models/ml_model.py::MLModel.to_dict::is_active::READ": _CONFIG,
    "autobot-backend/project_state_manager.py::ProjectStateManager._build_phase_details::is_active::READ": _CONFIG,
    "autobot-backend/project_state_manager.py::ProjectStateManager._save_phase_info::is_active::READ": _CONFIG,
    "autobot-backend/project_state_manager.py::ProjectStateManager.generate_validation_report::is_active::READ": _CONFIG,
    "autobot-backend/project_state_manager.py::ProjectStateManager.get_fast_project_status::is_active::READ": _CONFIG,
    "autobot-backend/project_state_manager.py::ProjectStateManager.get_project_status::is_active::READ": _CONFIG,
    "autobot-backend/protocols/agent_channels.py::DirectCommunicationChannel.send::is_active::READ": _AGENT_RUNTIME,
    "autobot-backend/protocols/agent_channels.py::RedisCommunicationChannel._listen_for_messages::is_active::READ": _AGENT_RUNTIME,
    "autobot-backend/protocols/agent_communication.py::AgentCommunicationProtocol._finished::is_active::READ": _AGENT_RUNTIME,
    "autobot-backend/protocols/agent_communication.py::AgentCommunicationProtocol._heartbeat_loop::is_active::READ": _AGENT_RUNTIME,
    "autobot-backend/protocols/agent_communication.py::AgentCommunicationProtocol._process_incoming_messages::is_active::READ": _AGENT_RUNTIME,
    "autobot-backend/routers/model_management.py::list_models::is_active::READ": _CONFIG,
    "autobot-backend/services/credential_read.py::read_imported_credential_in_session::is_active::READ": _CREDENTIAL,
    "autobot-backend/services/credential_reconcile.py::_read_sqlite_state::is_active::READ": _CREDENTIAL,
    "autobot-backend/services/credential_reconcile.py::reconcile_connector_credentials::is_active::READ": _CREDENTIAL,
    "autobot-backend/services/credential_write.py::_find_by_marker::is_active::READ": _CREDENTIAL,
    "autobot-backend/services/fact_extraction_service.py::FactExtractionService._filter_and_deserialize_fact::is_active::READ": _INVALIDATION_FLAG,
    "autobot-backend/services/json_secrets_read.py::_find_by_marker::is_active::READ": _CREDENTIAL,
    "autobot-backend/services/llc_secrets_read.py::_find_by_marker::is_active::READ": _CREDENTIAL,
    "autobot-backend/services/provider_key_vault.py::_find_system_secret_id::is_active::READ": _CREDENTIAL,
    "autobot-backend/services/secrets_access_audit.py::_inactive_users::is_active::READ": _CREDENTIAL,
    "autobot-backend/services/secrets_coordinator.py::SecretsCoordinator._bearer_matches::is_active::READ": _CREDENTIAL,
    "autobot-backend/services/secrets_principal_resolver.py::resolve_principal_facts::is_active::READ": _CREDENTIAL,
    "autobot-backend/services/temporal_invalidation_service.py::InvalidationRule.matches_fact::valid_from::READ": _TEMPORAL,
    "autobot-backend/services/temporal_invalidation_service.py::TemporalInvalidationService._build_sample_facts_list::valid_from::READ": _TEMPORAL,
    "autobot-backend/services/temporal_invalidation_service.py::TemporalInvalidationService._prepare_fact_for_invalidation::valid_until::READ": _TEMPORAL,
    "autobot-backend/tools/terminal_tool.py::TerminalTool.get_user_command_history::is_active::READ": _AGENT_RUNTIME,
    "autobot_shared/user_management/login_eligibility.py::login_refusal::is_active::READ": _ACCOUNT,
    "autobot_shared/user_management/models/api_key.py::APIKey.is_valid::is_active::READ": _ACCOUNT,
    "autobot_shared/user_management/organization_service.py::OrganizationService.get_organization_stats::is_active::READ": _ACCOUNT,
    "autobot_shared/user_management/organization_service.py::OrganizationService.get_user_count::is_active::READ": _ACCOUNT,
    "autobot_shared/user_management/organization_service.py::OrganizationService.list_organizations::is_active::READ": _ACCOUNT,
    "autobot_shared/user_management/user_service.py::UserService._build_user_list_base_query::is_active::READ": _ACCOUNT,
}

FROZEN_TOTAL = 76
