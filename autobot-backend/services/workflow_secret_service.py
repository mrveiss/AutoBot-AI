# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Workflow Secret Service

Provides workflow-scoped credential storage and ${secrets.NAME} resolution for
workflow step commands. Wraps the existing SecretsService — no duplicate
encryption logic.

Issue #2153 — Secret management for workflow credentials.
"""

import re
import sqlite3
from typing import Dict, FrozenSet, List, Mapping, NoReturn

from cryptography.fernet import InvalidToken

from autobot_shared.logging_manager import get_logger
from autobot_shared.secret_redaction import LOG_MASK
from autobot_shared.singleton_factory import lazy_singleton
from services.secrets_service import SecretsService, get_secrets_service

logger = get_logger(__name__)

# Pattern: ${secrets.SOME_KEY_NAME}
_SECRET_REF_RE = re.compile(r"\$\{secrets\.([A-Za-z0-9_\-\.]+)\}")

# Scope value stored in the secrets table for workflow-scoped secrets.
WORKFLOW_SCOPE = "workflow"

# Placeholder used in logs/responses in place of a resolved secret value.
REDACTED = LOG_MASK  # the one in-text mask (#19337)


#: What reading a secret can raise: opening or querying the secrets database (``sqlite3.Error``), its data
#: directory or key file (``OSError``), a stored row that does not parse (``ValueError``, which covers
#: ``json.JSONDecodeError`` and ``UnicodeDecodeError``) and a value its key cannot decrypt (``InvalidToken``).
#: Anything else is a defect, not an unreadable store, and propagates.
SECRET_STORE_ERRORS = (sqlite3.Error, OSError, ValueError, InvalidToken)


class StepSecrets:
    """The secret values injected into one workflow step: in memory, scoped to the step.

    Never logged, serialised or persisted -- ``repr`` and ``str`` show the names only, and
    pickling is refused. Only :meth:`WorkflowSecretService.redact_secrets` reads the values.
    """

    __slots__ = ("_injected",)

    def __init__(self, injected: Mapping[str, str] | None = None) -> None:
        self._injected: Dict[str, str] = {name: value for name, value in (injected or {}).items() if value}

    @property
    def names(self) -> FrozenSet[str]:
        """The names injected, which are not sensitive."""
        return frozenset(self._injected)

    def __bool__(self) -> bool:
        return bool(self._injected)

    def __repr__(self) -> str:
        return f"StepSecrets(names={sorted(self._injected)})"

    __str__ = __repr__

    def __reduce__(self) -> NoReturn:
        raise TypeError("StepSecrets holds live credential values and must not be serialised")

    def values_longest_first(self) -> List[str]:
        """Values to mask; the longest first, so one containing another is masked whole."""
        return sorted(self._injected.values(), key=len, reverse=True)


class WorkflowSecretService:
    """
    Workflow-scoped secret CRUD and ${secrets.NAME} resolution.

    All encryption is delegated to SecretsService (Fernet). This service adds:
    - Workflow-scoped create / list / delete / update
    - resolve_secrets(): substitutes ${secrets.NAME} patterns in command strings
    - redact_secrets(): masks exactly the values resolve_secrets() injected into the step

    Issue #2153.
    """

    def __init__(self, secrets_service: SecretsService | None = None) -> None:
        """Initialise service, lazily obtaining the SecretsService singleton."""
        self._secrets_service = secrets_service
        logger.info("WorkflowSecretService initialised")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _svc(self) -> SecretsService:
        """Lazy accessor for SecretsService singleton."""
        if self._secrets_service is None:
            self._secrets_service = get_secrets_service()
        return self._secrets_service

    def _build_chat_id(self, workflow_id: str | None) -> str | None:
        """
        Map workflow_id to the chat_id column used by SecretsService.

        SecretsService uses chat_id for sub-scope isolation; we store the
        workflow_id there when scope=workflow. (Issue #2153)
        """
        return workflow_id

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_secret(
        self,
        name: str,
        value: str,
        owner_id: str,
        secret_type: str = "api_key",  # nosec B107  # secret_type category, not a password
        workflow_id: str | None = None,
        description: str | None = None,
    ) -> Dict:
        """
        Store an encrypted workflow secret.

        Args:
            name: Identifier used in ${secrets.NAME} references.
            value: Plaintext credential value — encrypted before storage.
            owner_id: ID of the user creating the secret.
            secret_type: Category (api_key, token, password, etc.).
            workflow_id: If provided, the secret is scoped to that workflow.
            description: Optional human-readable description.

        Returns:
            Metadata dict (no value field — never returned after creation).

        Issue #2153.
        """
        result = self._svc.create_secret(
            name=name,
            secret_type=secret_type,
            value=value,
            scope=WORKFLOW_SCOPE,
            chat_id=self._build_chat_id(workflow_id),
            description=description,
            created_by=owner_id,
        )
        logger.info(
            "Workflow secret created: name=%s owner=%s workflow=%s",
            name,
            owner_id,
            workflow_id or "global",
        )
        return result

    def list_secrets(
        self,
        owner_id: str,
        workflow_id: str | None = None,
    ) -> List[Dict]:
        """
        Return secret metadata for the given owner (never includes values).

        Only secrets whose ``created_by`` column matches *owner_id* are
        returned — preventing cross-owner exposure.  (Issue #2321)

        Args:
            owner_id: Filter to secrets created by this user.
            workflow_id: If provided, only return secrets for that workflow.

        Returns:
            List of metadata dicts (name, id, secret_type, scope, created_at, …).

        Issue #2153, #2321.
        """
        rows = self._svc.list_secrets(
            scope=WORKFLOW_SCOPE,
            chat_id=self._build_chat_id(workflow_id),
        )
        # Filter by owner_id using the created_by field that SecretsService
        # returns in list results.  This is the authoritative ownership check
        # at this layer — not a hint. (Issue #2321)
        return [r for r in rows if r.get("created_by") == owner_id]

    def get_secret_value(self, name: str, owner_id: str) -> str | None:
        """
        Retrieve and decrypt a secret value by name.

        SECURITY: this result must NEVER be logged or returned in API responses.

        Args:
            name: Secret name.
            owner_id: Requesting user — used for audit trail only at this layer.

        Returns:
            Plaintext secret value, or None if not found.

        Issue #2153.
        """
        secret = self._svc.get_secret(
            name=name,
            scope=WORKFLOW_SCOPE,
            include_value=True,
            accessed_by=f"workflow_resolver:{owner_id}",
        )
        if secret is None:
            return None
        return secret.get("value")

    def update_secret(self, name: str, new_value: str, owner_id: str) -> bool:
        """
        Replace the encrypted value of an existing secret.

        Args:
            name: Secret name to update.
            new_value: New plaintext value — encrypted before storage.
            owner_id: Requesting user — used for audit trail.

        Returns:
            True if the secret was found and updated, False otherwise.

        Issue #2153.
        """
        existing = self._svc.get_secret(
            name=name,
            scope=WORKFLOW_SCOPE,
            include_value=False,
        )
        if existing is None:
            logger.warning("update_secret: secret not found name=%s owner=%s", name, owner_id)
            return False
        updated = self._svc.update_secret(
            secret_id=existing["id"],
            value=new_value,
            updated_by=owner_id,
        )
        if updated:
            logger.info("Workflow secret updated: name=%s owner=%s", name, owner_id)
        return updated

    def delete_secret(self, name: str, owner_id: str) -> bool:
        """
        Deactivate a workflow secret by name.

        Args:
            name: Secret name.
            owner_id: Requesting user — used for audit trail.

        Returns:
            True if deleted, False if not found.

        Issue #2153.
        """
        existing = self._svc.get_secret(
            name=name,
            scope=WORKFLOW_SCOPE,
            include_value=False,
        )
        if existing is None:
            return False
        deleted = self._svc.delete_secret(
            secret_id=existing["id"],
            deleted_by=owner_id,
        )
        if deleted:
            logger.info("Workflow secret deleted: name=%s owner=%s", name, owner_id)
        return deleted

    # ------------------------------------------------------------------
    # Secret resolution
    # ------------------------------------------------------------------

    def _collect_referenced_names(self, text: str) -> List[str]:
        """Return all unique secret names referenced in text. Issue #2153."""
        return list(dict.fromkeys(_SECRET_REF_RE.findall(text)))

    def resolve_secrets(self, text: str, owner_id: str) -> tuple[str, StepSecrets]:
        """
        Replace every ${secrets.NAME} token in *text* with its plaintext value.

        Tokens that reference an unknown or expired secret are left unchanged
        so that downstream execution fails visibly rather than silently.

        SECURITY: the resolved string contains live credential values -- it must
        NEVER be logged or stored.

        Args:
            text: Command string potentially containing ${secrets.NAME} tokens.
            owner_id: User on whose behalf resolution is performed.

        Returns:
            Tuple of (resolved_text, step_secrets). ``step_secrets`` holds the values
            that were injected, in memory and scoped to this step; pass it to
            :meth:`redact_secrets`, which masks exactly those values. A secret rotated
            or deleted after this call is still masked, because nothing is re-read.

        Issue #2153, #2321, #20868.
        """
        injected: Dict[str, str] = {}
        resolved = text
        for name in self._collect_referenced_names(text):
            value = self.get_secret_value(name, owner_id)
            if value is None:
                logger.warning(
                    "resolve_secrets: no secret found for name=%s owner=%s -- token left unresolved", name, owner_id
                )
                continue
            resolved = resolved.replace(f"${{secrets.{name}}}", value)
            injected[name] = value
        return resolved, StepSecrets(injected)

    def redact_secrets(self, text: str, secrets: StepSecrets) -> str:
        """
        Replace the values injected into one step with ***.

        The one redaction path for every caller (the step result, the executor result,
        the command policy): it masks exactly the values ``resolve_secrets`` returned
        for the step and never reads the secret store, so a secret rotated or deleted
        mid-step cannot leak its old value and another owner's secrets are never loaded.

        Issue #2153, #2321, #20868.
        """
        redacted = text
        for value in secrets.values_longest_first():
            redacted = redacted.replace(value, REDACTED)
        return redacted


# ---------------------------------------------------------------------------
# Thread-safe singleton
# ---------------------------------------------------------------------------

get_workflow_secret_service = lazy_singleton(WorkflowSecretService)
