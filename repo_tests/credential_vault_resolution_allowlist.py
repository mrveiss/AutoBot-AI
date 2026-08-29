# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Data module for ``repo_tests/credential_vault_resolution_guard_test.py``'s ``ALLOWLIST``.

Split out from the guard itself (#15278) so the guard's own detection logic stays
well under the 600-line file-size limit ``check_python_file_size.py`` enforces on
everything else, mirroring how ``scripts/python_file_size_known_large.py`` was split
from ``scripts/check_python_file_size.py`` for the identical reason (#14547).

Every entry is keyed ``(repo-relative file, ssot_config field name) -> reason``, one
of three classifications:

* ``AUTH_BOOTSTRAP`` -- the credential gates the vault/DB itself, or is the
  platform's own internal-auth token, so vaulting it would be a confused-deputy
  cycle. Genuinely irreducible: not ratcheted.
* ``NOT_A_READ`` -- the regex's only match here is prose (a comment or docstring),
  not a real read. Not ratcheted; currently empty because #15280 taught the scanner
  to strip prose before matching, so this class no longer arises there, but the
  classification stays available for a shape that slips past that.
* ``TRACKED_GAP #NNNN`` -- a real gap, same defect class as #15267/#15268, not yet
  migrated through the vault seam. Tracked in #15276, and its live count is
  ratcheted -- see ``repo_tests/credential_vault_resolution_ratchet_test.py`` --
  because unlike the other two, this class is debt, not a durable classification.

No credential values appear anywhere in this table -- only field names and
source-code file paths, neither of which is a secret.
"""

from __future__ import annotations

_AUTH_BOOTSTRAP = "AUTH_BOOTSTRAP"  # gates the vault/DB itself; vaulting it is circular
_NOT_A_READ = "NOT_A_READ"  # the regex's only match here is prose, not code
_TRACKED = "TRACKED_GAP"  # a real gap, same defect class, named issue tracks its fix

#: ``(repo-relative file, ssot_config field name) -> reason``. No credential values
#: appear anywhere in this table -- only field names and source-code file paths.
ALLOWLIST: dict[tuple[str, str], str] = {
    # --- auth-bootstrap: internal/platform authentication, not a third-party
    # --- provider credential. Same classification IRREDUCIBLE_KEYS documents for
    # --- autobot_internal_api_key in autobot-slm-backend/services/system_secrets_vault.py.
    ("autobot-backend/agents/base_agent.py", "mcp_token"): f"{_AUTH_BOOTSTRAP}: internal MCP server shared secret",
    ("autobot-backend/mcp/autobot_server.py", "mcp_token"): f"{_AUTH_BOOTSTRAP}: internal MCP server shared secret",
    ("autobot-backend/services/execution/claude_code_backend.py", "mcp_token"): (
        f"{_AUTH_BOOTSTRAP}: internal MCP server shared secret"
    ),
    ("autobot-backend/auth_middleware.py", "jwt_secret"): (
        f"{_AUTH_BOOTSTRAP}: platform user-session signing key"
    ),
    ("autobot-backend/services/slm_client.py", "jwt_secret"): (
        f"{_AUTH_BOOTSTRAP}: platform user-session signing key, reused to mint SLM service JWTs"
    ),
    ("autobot-backend/services/run_jwt.py", "run_jwt_secret"): f"{_AUTH_BOOTSTRAP}: run-worker JWT signing key",
    ("autobot-backend/services/mcp_isolated_runtime.py", "run_jwt_secret"): (
        f"{_AUTH_BOOTSTRAP}: run-worker JWT signing key"
    ),
    ("autobot-backend/middleware/service_auth_enforcement.py", "service_auth_override_token"): (
        f"{_AUTH_BOOTSTRAP}: internal service-to-service auth override"
    ),
    ("autobot-backend/orchestration/dag_executor.py", "slm_auth_token"): (
        f"{_AUTH_BOOTSTRAP}: internal backend-to-SLM service auth token"
    ),
    ("autobot-backend/services/command_extraction_service.py", "slm_auth_token"): (
        f"{_AUTH_BOOTSTRAP}: internal backend-to-SLM service auth token"
    ),
    ("autobot-backend/user_management/config.py", "postgres_password"): (
        f"{_AUTH_BOOTSTRAP}: the vault's own Postgres backing store cannot gate itself"
    ),
    ("autobot-backend/auth_middleware.py", "internal_api_key"): (
        f"{_AUTH_BOOTSTRAP}: the exact confused-deputy example "
        "autobot-slm-backend/services/system_secrets_vault.py documents for this same credential"
    ),
    ("autobot-backend/initialization/lifespan.py", "slm_auth_token"): (
        f"{_AUTH_BOOTSTRAP}: internal backend-to-SLM service auth token, same as the two siblings above"
    ),
    ("autobot-backend/user_management/services/seed.py", "admin_password"): (
        f"{_AUTH_BOOTSTRAP}: bootstrap admin-account creation, read before any auth subsystem exists"
    ),
    ("autobot_shared/security/password_weakness.py", "admin_password"): (
        f"{_AUTH_BOOTSTRAP}: same bootstrap admin password as seed.py, checked for weakness"
    ),
    # --- auth-bootstrap: internal data-layer service credentials (Redis/ChromaDB),
    # --- same class as the Postgres password above -- the app's own storage
    # --- layer must be reachable before anything, including the vault, can start.
    ("autobot-backend/api/npu_workers.py", "password"): f"{_AUTH_BOOTSTRAP}: Redis connection password",
    ("autobot-backend/celery_app.py", "password"): f"{_AUTH_BOOTSTRAP}: Redis connection password",
    ("autobot-backend/config/__init__.py", "password"): f"{_AUTH_BOOTSTRAP}: Redis connection password",
    ("autobot-backend/config/defaults.py", "password"): f"{_AUTH_BOOTSTRAP}: Redis connection password",
    ("autobot-backend/config/service_config.py", "password"): f"{_AUTH_BOOTSTRAP}: Redis connection password",
    ("autobot-backend/knowledge/base.py", "password"): f"{_AUTH_BOOTSTRAP}: Redis connection password",
    ("autobot-backend/utils/async_chromadb_client.py", "chromadb_auth_token"): (
        f"{_AUTH_BOOTSTRAP}: internal ChromaDB data-layer service credential"
    ),
    ("autobot-backend/utils/chromadb_auth.py", "chromadb_auth_token"): (
        f"{_AUTH_BOOTSTRAP}: internal ChromaDB data-layer service credential"
    ),
    ("autobot-backend/utils/chromadb_client.py", "chromadb_auth_token"): (
        f"{_AUTH_BOOTSTRAP}: internal ChromaDB data-layer service credential"
    ),
    # --- tracked gap: third-party/service credentials, same defect class as
    # --- #15267/#15268, not yet migrated. See #15276.
    ("autobot-backend/llm_shared/adapters/anthropic_adapter.py", "anthropic_api_key"): (
        f"{_TRACKED} #15276: AdapterRegistry connectivity-test path"
    ),
    ("autobot-backend/llm_shared/adapters/groq_adapter.py", "groq_api_key"): (
        f"{_TRACKED} #15276: AdapterRegistry connectivity-test path"
    ),
    ("autobot-backend/llm_shared/adapters/openai_adapter.py", "openai_api_key"): (
        f"{_TRACKED} #15276: AdapterRegistry connectivity-test path"
    ),
    ("autobot-backend/llm_shared/providers/anthropic.py", "anthropic_api_key"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/groq.py", "groq_api_key"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/openai.py", "openai_api_key"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/mistral.py", "mistral_api_key"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/custom_openai.py", "custom_openai_api_key"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/openrouter.py", "openrouter_api_key"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/huggingface.py", "hf_token"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/huggingface.py", "huggingface_api_token"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/nous_portal.py", "hf_token"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/nous_portal.py", "huggingface_api_token"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/nous_portal.py", "nous_api_key"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/services/execution/claude_code_backend.py", "anthropic_api_key"): (
        f"{_TRACKED} #15276: execution backend reads the key directly rather than via the registry"
    ),
    ("autobot-backend/services/provider_health/providers.py", "anthropic_api_key"): (
        f"{_TRACKED} #15276: health-check probe reads config directly rather than via the registry"
    ),
    ("autobot-backend/services/provider_health/providers.py", "openai_api_key"): (
        f"{_TRACKED} #15276: health-check probe reads config directly rather than via the registry"
    ),
    ("autobot-backend/services/provider_health/providers.py", "google_api_key"): (
        f"{_TRACKED} #15276: health-check probe reads config directly rather than via the registry"
    ),
    ("autobot-backend/agent_loop/slack_hook.py", "slack_bot_token"): f"{_TRACKED} #15276: Slack bot token",
    ("autobot-backend/security/threat_intelligence.py", "virustotal_api_key"): (
        f"{_TRACKED} #15276: threat-intel API key"
    ),
    ("autobot-backend/security/threat_intelligence.py", "urlvoid_api_key"): (
        f"{_TRACKED} #15276: threat-intel API key"
    ),
    ("autobot-backend/services/notification_service.py", "smtp_password"): f"{_TRACKED} #15276: SMTP credential",
    ("autobot-backend/initialization/lifespan.py", "anthropic_api_key"): (
        f"{_TRACKED} #15276: AdapterRegistry gating check (adapter-listing only, not the LLM-call routing path)"
    ),
    ("autobot-backend/initialization/lifespan.py", "groq_api_key"): (
        f"{_TRACKED} #15276: AdapterRegistry gating check (adapter-listing only, not the LLM-call routing path)"
    ),
    ("autobot-backend/initialization/lifespan.py", "openai_api_key"): (
        f"{_TRACKED} #15276: AdapterRegistry gating check (adapter-listing only, not the LLM-call routing path)"
    ),
    ("autobot-backend/integrations/capability_registry.py", "slack_bot_token"): (
        f"{_TRACKED} #15276: the third CredentialGatedRegistry sibling (see "
        "autobot_shared/credential_gated_registry.py's own docstring) never migrated"
    ),
    ("autobot-backend/integrations/capability_registry.py", "discord_bot_token"): (
        f"{_TRACKED} #15276: the third CredentialGatedRegistry sibling (see "
        "autobot_shared/credential_gated_registry.py's own docstring) never migrated"
    ),
    ("autobot-backend/knowledge/base.py", "anthropic_api_key"): (
        f"{_TRACKED} #15276: LlamaIndex LLM configuration reads the key directly"
    ),
    ("autobot-backend/knowledge/base.py", "openai_api_key"): (
        f"{_TRACKED} #15276: LlamaIndex LLM/embedding configuration reads the key directly"
    ),
}
