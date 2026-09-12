# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A vault-backed credential template pre-fills the exact runtime key name (#16427).

``SecretsManager.vue``'s ``useTemplate()`` sets ``secretForm.name = template.name``,
and that value becomes ``POST /api/secrets/``'s ``request.name`` — the argument
``services.provider_key_vault.capture_provider_key`` matches verbatim against
``VAULT_RESOLVED_CREDENTIAL_NAMES`` before mirroring it into the System vault
(``api/secrets.py``'s ``_mirror_llm_provider_key``). A template whose ``name`` is a
display label instead of the exact key (``"OpenAI"`` instead of
``"OPENAI_API_KEY"``) silently loses the capture: the legacy secret is written, the
vault mirror never fires, and ``llm_shared.provider_registry`` can't resolve it at
runtime -- write-only, exactly the defect class #16427 fixes.

Checked against the real registries in ``provider_key_vault.py`` via ``ast``
(no import: that module pulls in sqlalchemy/autobot_shared/models.secret, heavy
for a name-parity check), so a rename on either side breaks this test, not just
a second copy of the same three strings.
"""

from __future__ import annotations

import ast
import re

from repo_tests._paths import repo_root

_REPO_ROOT = repo_root()
_VAULT_MODULE = _REPO_ROOT / "autobot-backend" / "services" / "provider_key_vault.py"
_SECRETS_MANAGER_VUE = _REPO_ROOT / "autobot-frontend" / "src" / "components" / "security" / "SecretsManager.vue"

_REGISTRY_NAMES = (
    "LLM_PROVIDER_KEY_NAMES",
    "SEARCH_PROVIDER_KEY_NAMES",
    "SERVICE_CREDENTIAL_KEY_NAMES",
)

# Every `credentialTemplates` entry whose secret is meant to reach a
# provider_key_vault-mirrored consumer, and the exact key it must pre-fill.
# The remaining templates (aws, github, postgres, redis, ssh, server) have no
# member in any provider_key_vault registry -- free-form names, out of scope.
_EXPECTED_VAULT_BACKED_NAMES = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "slack": "SLACK_BOT_TOKEN",
}


def _live_vault_registry() -> frozenset[str]:
    tree = ast.parse(_VAULT_MODULE.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        # Each is `NAME: frozenset[str] = frozenset({...})` -- an AnnAssign,
        # not a bare Assign, because of the type annotation.
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        if node.target.id not in _REGISTRY_NAMES:
            continue
        call = node.value
        assert isinstance(call, ast.Call), f"{node.target.id} is not a frozenset({{...}}) call"
        (literal,) = call.args
        names.update(ast.literal_eval(literal))
    return frozenset(names)


def _template_names() -> dict[str, str]:
    """Parse ``id: '...', name: '...'`` pairs out of the ``credentialTemplates`` array."""
    source = _SECRETS_MANAGER_VUE.read_text(encoding="utf-8")
    array_match = re.search(
        r"const credentialTemplates = computed<CredentialTemplate\[\]>\(\(\) => \[(.*?)\n\]\);",
        source,
        re.DOTALL,
    )
    assert array_match, "credentialTemplates computed array not found in SecretsManager.vue"
    body = array_match.group(1)
    return dict(re.findall(r"\{ id: '([\w-]+)', name: '([^']+)'", body))


def test_vault_backed_templates_prefill_the_exact_registry_key() -> None:
    templates = _template_names()
    for template_id, expected_name in _EXPECTED_VAULT_BACKED_NAMES.items():
        assert templates.get(template_id) == expected_name, (
            f"credentialTemplates['{template_id}'].name must be '{expected_name}' "
            "to reach its provider_key_vault-mirrored consumer"
        )


def test_expected_names_are_still_live_registry_members() -> None:
    registry = _live_vault_registry()
    for template_id, expected_name in _EXPECTED_VAULT_BACKED_NAMES.items():
        assert expected_name in registry, (
            f"'{expected_name}' (credentialTemplates['{template_id}']) is no longer in "
            "provider_key_vault's VAULT_RESOLVED_CREDENTIAL_NAMES -- update the template "
            "or this pin"
        )
