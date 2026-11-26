# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The management-plane SSH identity, bound once for every settings model that reads it (#21925).

``AUTOBOT_SSH_KEY`` and ``AUTOBOT_SSH_USER`` were bound by two fields each: ``PathConfig`` (the
management scripts) and ``TLSConfig`` (the PKI code). One variable set two attributes, and an
operator could not tell which a service read. Both models now inherit the pair from here, so the
alias is declared by exactly one field (``repo_tests/env_planes_agree_on_defaults_17419_test.py``).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from autobot_shared.paths import project_root

DEFAULT_SSH_USER = "autobot"


def _default_management_ssh_key() -> str:
    return str(Path.home() / ".ssh" / "autobot_key")


class SSHIdentitySettings(BaseSettings):
    """Fields shared by ``PathConfig`` and ``TLSConfig``; each subclass reads them as its own attribute."""

    model_config = SettingsConfigDict(env_file=str(project_root() / ".env"), env_file_encoding="utf-8", extra="ignore")

    # Management-plane SSH key (#14173), DISTINCT from ``PathConfig.ssh_key_path`` (the service
    # account's key under /etc/autobot/ssh, #12429). ``setup-ssh-keys.sh`` generates this one under
    # the operator's own $HOME, and ~24 scripts read AUTOBOT_SSH_KEY with a $HOME-relative fallback,
    # so it must not collapse onto the /etc default. The PKI code reads it as ``ssh_key_path``.
    management_ssh_key_path: str = Field(
        default_factory=_default_management_ssh_key,
        alias="AUTOBOT_SSH_KEY",
        description="Path to the management-plane SSH key for VM access",
    )

    # The 'autobot' operational account (ansible.cfg remote_user, inventory ansible_user).
    ssh_user: str = Field(default=DEFAULT_SSH_USER, alias="AUTOBOT_SSH_USER", description="SSH user for VM access")
