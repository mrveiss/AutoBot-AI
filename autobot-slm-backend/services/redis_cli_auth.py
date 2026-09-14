# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Authenticated ``redis-cli`` over SSH for the SLM's replication and backup (#16627).

The credential comes from its canonical source -- the SLM-generated secret, surfaced
through ``autobot_shared.ssot_config`` -- not from grepping a node's config file,
which ``roles/redis`` never renders (#16625). It is sent as ``--user <name>`` with the
secret on the SSH session's stdin: the remote shell reads it into ``REDISCLI_AUTH``,
so it never appears in the argv of ``ssh`` on this host or of ``redis-cli`` on the
node, where any local user could read it from the process list.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass

from autobot_shared.ssot_config import config as ssot_config

#: Remote shell prefix: read one stdin line into the env var redis-cli authenticates with.
_STDIN_TO_REDISCLI_ENV = "IFS= read -r REDISCLI_AUTH && export REDISCLI_AUTH && "


@dataclass(frozen=True)
class RedisCliAuth:
    """How one SSH session runs authenticated ``redis-cli`` commands."""

    user_flag: str
    stdin: bytes | None

    def remote(self, *redis_args: str) -> str:
        """The remote shell command running ``redis-cli <args>`` for each of *redis_args*."""
        prefix = _STDIN_TO_REDISCLI_ENV if self.stdin else ""
        return prefix + " && ".join(f"redis-cli {self.user_flag}{args}" for args in redis_args)


def redis_cli_auth(secret: str | None = None) -> RedisCliAuth:
    """Auth for *secret*, or for the canonical one when omitted; none when there is none.

    The username is the canonical ACL user, ``default`` when unset: ``AUTH default``
    with the secret succeeds while the server is nopass and still once it enforces
    that same secret, whereas the one-argument form is refused by a nopass server.
    """
    secret = ssot_config.redis.password if secret is None else secret
    if not secret:
        return RedisCliAuth(user_flag="", stdin=None)
    username = ssot_config.redis.username or "default"
    return RedisCliAuth(user_flag=f"--user {shlex.quote(username)} ", stdin=f"{secret}\n".encode())
