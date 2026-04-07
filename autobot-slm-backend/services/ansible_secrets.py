# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Ansible secrets mapping shared between setup_wizard and playbook_executor.

Single source of truth for the SLM secret key -> Ansible variable name
mapping (#3519).  Any caller that needs to inject stored secrets as Ansible
extra_vars should import _SECRET_TO_ANSIBLE_VAR from here.
"""

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
