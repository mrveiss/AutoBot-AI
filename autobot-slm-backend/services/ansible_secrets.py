# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Ansible secrets mapping shared between setup_wizard and playbook_executor.

Single source of truth for the SLM secret key -> Ansible variable name
mapping (#3519).  Any caller that needs to inject stored secrets as Ansible
extra_vars should import _SECRET_TO_ANSIBLE_VAR and fetch_deploy_secrets
from here.
"""

import logging

logger = logging.getLogger(__name__)

# Maps SLM secrets-store keys to the Ansible extra_var names they become
# when injected into a playbook run.
#
# "hf_token"               -> tts_hf_token  (HuggingFace token for TTS worker)
# "autobot_internal_api_key" -> autobot_internal_api_key
#     Internal API key shared between SLM backend and main backend (#1779,
#     #3512).  Stored via the SLM secrets UI; injected as an Ansible extra_var
#     and rendered into slm-secrets.env and backend.env.
_SECRET_TO_ANSIBLE_VAR: dict[str, str] = {
    "hf_token": "tts_hf_token",
    "autobot_internal_api_key": "autobot_internal_api_key",
}


async def fetch_deploy_secrets() -> dict[str, str]:
    """Read stored SLM secrets and return them as Ansible extra_vars (#3519, #3778).

    Single source of truth used by setup_wizard, playbook_executor, and
    infrastructure — any deploy path that needs to inject stored secrets as
    Ansible extra_vars should call this function.

    Returns an empty dict and logs a warning if the DB is unavailable — the
    deploy is allowed to proceed rather than being blocked by a secret-fetch
    failure.
    """
    from sqlalchemy import select

    from models.database import SystemSecret
    from services.database import db_service
    from services.encryption import decrypt_data

    extra: dict[str, str] = {}
    try:
        async with db_service.session() as session:
            result = await session.execute(
                select(SystemSecret).where(SystemSecret.key.in_(list(_SECRET_TO_ANSIBLE_VAR.keys())))
            )
            for secret in result.scalars().all():
                ansible_var = _SECRET_TO_ANSIBLE_VAR.get(secret.key)
                if not ansible_var:
                    continue
                value = decrypt_data(secret.encrypted_value)
                if value:
                    extra[ansible_var] = value
    except Exception:
        logger.warning(
            "fetch_deploy_secrets: could not load SLM secrets — " "deploy will proceed without them (#3519)",
            exc_info=True,
        )
    return extra
