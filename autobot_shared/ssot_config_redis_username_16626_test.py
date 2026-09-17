# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SSOT Redis ACL username (#16626): optional, and carried in the auth URL when set.

Redis 7 rejects the password-only ``AUTH <password>`` while the default user is
``nopass`` and accepts ``AUTH <username> <password>`` (#13568). The URL builder
is what Celery's broker and result backend use, so its userinfo is pinned here
in both states. With no username the userinfo is ``:<password>``, exactly as
before.

``_env_file=None`` is pydantic-settings' init-only keyword that skips any
``.env`` on disk. mypy cannot see it on the generated settings signatures,
hence the ``call-arg`` ignores.
"""

import os
from unittest.mock import patch

from autobot_shared.ssot_config import AutoBotConfig, RedisConfig


def _userinfo(url: str) -> str:
    return url.split("://", 1)[1].split("@", 1)[0]


def test_username_is_unset_by_default() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert RedisConfig(_env_file=None).username is None  # type: ignore[call-arg]


def test_username_reads_autobot_redis_username() -> None:
    with patch.dict(os.environ, {"AUTOBOT_REDIS_USERNAME": "default"}, clear=True):
        assert RedisConfig(_env_file=None).username == "default"  # type: ignore[call-arg]


def test_auth_url_without_username_keeps_the_password_only_form() -> None:
    env = {"AUTOBOT_REDIS_PASSWORD": "secret123"}  # pragma: allowlist secret
    with patch.dict(os.environ, env, clear=True):
        url = AutoBotConfig(_env_file=None).redis_url_with_auth  # type: ignore[call-arg]
    assert url.startswith("redis://")
    assert _userinfo(url) == ":secret123"


def test_auth_url_carries_the_username() -> None:
    env = {"AUTOBOT_REDIS_PASSWORD": "secret123", "AUTOBOT_REDIS_USERNAME": "default"}  # pragma: allowlist secret
    with patch.dict(os.environ, env, clear=True):
        url = AutoBotConfig(_env_file=None).redis_url_with_auth  # type: ignore[call-arg]
    assert _userinfo(url) == "default:secret123"


def test_auth_url_encodes_both_credentials() -> None:
    """Celery used to encode the password itself; the shared builder now does it for every caller."""
    env = {"AUTOBOT_REDIS_PASSWORD": "p@ss/w+rd", "AUTOBOT_REDIS_USERNAME": "svc user"}  # pragma: allowlist secret
    with patch.dict(os.environ, env, clear=True):
        url = AutoBotConfig(_env_file=None).redis_url_with_auth  # type: ignore[call-arg]
    assert _userinfo(url) == "svc%20user:p%40ss%2Fw%2Brd"


def test_no_password_means_no_userinfo_even_with_a_username() -> None:
    with patch.dict(os.environ, {"AUTOBOT_REDIS_USERNAME": "default"}, clear=True):
        config = AutoBotConfig(_env_file=None)  # type: ignore[call-arg]
    assert "@" not in config.redis_url_with_auth
    assert config.get_redis_url_for_db(14).endswith("/14")
