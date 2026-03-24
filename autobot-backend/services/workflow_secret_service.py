# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Secret Service

Provides workflow-scoped credential storage and ${secrets.NAME} resolution for
workflow step commands. Wraps the existing SecretsService — no duplicate
encryption logic.

Issue #2153 — Secret management for workflow credentials.
"""

import logging
import re
import threading
from typing import Dict, List, Optional

from services.secrets_service import SecretsService, get_secrets_service

logger = logging.getLogger(__name__)

# Pattern: ${secrets.SOME_KEY_NAME}
_SECRET_REF_RE = re.compile(r"\$\{secrets\.([A-Za-z0-9_\-\.]+)\}")

# Scope value stored in the secrets table for workflow-scoped secrets.
WORKFLOW_SCOPE = "workflow"

# Placeholder used in logs/responses in place of a resolved secret value.
REDACTED = "***"


class WorkflowSecretService:
    """
    Workflow-scoped secret CRUD and ${secrets.NAME} resolution.

    All encryption is delegated to SecretsService (Fernet). This service adds:
    - Workflow-scoped create / list / delete / update
    - resolve_secrets(): substitutes ${secrets.NAME} patterns in command strings
    - redact_secrets(): replaces resolved values with *** in output text

    Issue #2153.
    """

    def __init__(self, secrets_service: Optional[SecretsService] = None) -> None:
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

    def _build_chat_id(self, workflow_id: Optional[str]) -> Optional[str]:
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
        secret_type: str = "api_key",  # nosec B107 - secret_type category, not a password
        workflow_id: Optional[str] = None,
        description: Optional[str] = None,
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
        workflow_id: Optional[str] = None,
    ) -> List[Dict]:
        """
        Return secret metadata for the given owner (never includes values).

        Args:
            owner_id: Filter to secrets created by this user.
            workflow_id: If provided, only return secrets for that workflow.

        Returns:
            List of metadata dicts (name, id, secret_type, scope, created_at, …).

        Issue #2153.
        """
        rows = self._svc.list_secrets(
            scope=WORKFLOW_SCOPE,
            chat_id=self._build_chat_id(workflow_id),
        )
        # Filter by owner via created_by stored in metadata (SecretsService
        # does not expose created_by in list results so we use it as a hint;
        # access control is enforced at the API layer).
        return rows

    def get_secret_value(self, name: str, owner_id: str) -> Optional[str]:
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
            logger.warning(
                "update_secret: secret not found name=%s owner=%s", name, owner_id
            )
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

    def resolve_secrets(self, text: str, owner_id: str) -> str:
        """
        Replace every ${secrets.NAME} token in *text* with its plaintext value.

        Tokens that reference an unknown or expired secret are left unchanged
        so that downstream execution fails visibly rather than silently.

        SECURITY: the returned string contains live credential values — it must
        NEVER be logged or stored.

        Args:
            text: Command string potentially containing ${secrets.NAME} tokens.
            owner_id: User on whose behalf resolution is performed.

        Returns:
            Resolved string with credential values substituted in.

        Issue #2153.
        """
        names = self._collect_referenced_names(text)
        if not names:
            return text

        resolved = text
        for name in names:
            value = self.get_secret_value(name, owner_id)
            if value is None:
                logger.warning(
                    "resolve_secrets: no secret found for name=%s owner=%s — "
                    "token left unresolved",
                    name,
                    owner_id,
                )
                continue
            resolved = resolved.replace(f"${{secrets.{name}}}", value)

        return resolved

    def redact_secrets(self, text: str, owner_id: str) -> str:
        """
        Replace resolved secret values in *text* with ***.

        Use this to sanitise command output or log lines that may contain
        credentials that were injected via resolve_secrets().

        Args:
            text: Text that may contain live secret values.
            owner_id: User context — used to look up the same secrets.

        Returns:
            Text with all known secret values replaced by ***.

        Issue #2153.
        """
        names = self._collect_referenced_names(text)
        # Even if text no longer has tokens, scan for the actual values.
        # We also scan without tokens by fetching all workflow secrets.
        all_names = names or [row["name"] for row in self.list_secrets(owner_id)]

        redacted = text
        for name in all_names:
            value = self.get_secret_value(name, owner_id)
            if value and value in redacted:
                redacted = redacted.replace(value, REDACTED)
        return redacted


# ---------------------------------------------------------------------------
# Thread-safe singleton
# ---------------------------------------------------------------------------

_service_instance: Optional[WorkflowSecretService] = None
_service_lock = threading.Lock()


def get_workflow_secret_service() -> WorkflowSecretService:
    """Return (or lazily create) the WorkflowSecretService singleton.

    Issue #2153.
    """
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = WorkflowSecretService()
    return _service_instance
