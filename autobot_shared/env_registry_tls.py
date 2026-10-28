# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""TLS and network AUTOBOT_* environment variable registrations.

Moved out of ``env_registry.py``, which sits at its grandfathered file-size ceiling
(#14236), to make room for the import lines every split module needs there. Imported
by ``env_registry`` itself, so registration happens whenever it loads.
"""

from __future__ import annotations

#: The ONE default for ``AUTOBOT_TLS_CERT_DIR`` (#19317): the PKI certificate TREE the CA host
#: generates and distributes from (``ca/``, ``main-host/``, ``<vm>/``), relative to the project root
#: unless absolute. Homed here, not in ``ssot_tls``, because the registry must import without
#: pydantic (the env-forks and env-vars-documented hooks run on a bare interpreter); ``ssot_tls``
#: and every Python reader import it. The Ansible, shell and env-file copies that cannot are pinned
#: to it by ``repo_tests/tls_cert_dir_one_home_19317_test.py``. Defined above the registry import
#: so ``ssot_tls`` can read it even while ``env_registry`` is still loading this module.
DEFAULT_TLS_CERT_DIR = "certs"

#: The ONE default for ``AUTOBOT_TLS_REMOTE_CERT_DIR`` (#19317): the FLAT directory a fleet node
#: serves from (``server-cert.pem``, ``server-key.pem``, ``ca-cert.pem``). Same home, same pin.
DEFAULT_TLS_REMOTE_CERT_DIR = "/etc/autobot/certs"

from autobot_shared.env_registry import EnvVarSpec, register_env_var  # noqa: E402 -- constants first, see above

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TLS_CA_PATH",
        type=str,
        default=None,
        description="Path to the CA certificate file for TLS verification.",
        component="tls",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TLS_CERT_DIR",
        type=str,
        default=DEFAULT_TLS_CERT_DIR,
        description=(
            "PKI certificate tree on the CA host (ca/, main-host/, <vm>/); relative to the project "
            "root unless absolute. A node's installed certs are AUTOBOT_TLS_REMOTE_CERT_DIR (#19317)."
        ),
        component="tls",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TLS_REMOTE_CERT_DIR",
        type=str,
        default=DEFAULT_TLS_REMOTE_CERT_DIR,
        description=(
            "Flat directory a fleet node serves TLS from (server-cert.pem, server-key.pem, ca-cert.pem) (#19317)."
        ),
        component="tls",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TLS_CERT_PATH",
        type=str,
        default=None,
        description="Path to the TLS client/server certificate file.",
        component="tls",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TLS_KEY_PATH",
        type=str,
        default=None,
        description="Path to the TLS private key file.",
        component="tls",
    )
)


# --- network (moved from env_registry.py, #18765) ---

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TRUSTED_PROXIES",
        type=str,
        default="",
        description=(
            "Comma-separated list of trusted reverse-proxy IP addresses or CIDR ranges "
            "for X-Forwarded-For header trust."
        ),
        component="network",
    )
)
