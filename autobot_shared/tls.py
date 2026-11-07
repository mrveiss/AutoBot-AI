# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Canonical SSL/TLS context factory for internal service-to-service connections.

Issue #6702: consolidates 4+ duplicate ssl.create_default_context() call sites
(slm_client.py, dag_executor.py, celery_app.py, notification_service.py) into
one function with a documented trust hierarchy.
"""

import os
import ssl
from pathlib import Path
from typing import Optional

from autobot_shared.logging_manager import get_logger

# #14039: acquired lazily, never at module scope. This module is imported by
# autobot-slm-backend, whose conftest stubs the config LoggingManager reads --
# constructing a rotating handler at import time then compares a MagicMock to an
# int and every SLM shard fails at collection. A logger bound at import in a
# low-level shared module is a constraint here, not a style choice.

# Canonical minimum TLS version for every AutoBot SSL context (#12285).
# CodeQL py/insecure-protocol: pinning this rejects the broken TLSv1/TLSv1_1
# protocols that ssl.create_default_context() is reported to still permit.
MIN_TLS_VERSION: ssl.TLSVersion = ssl.TLSVersion.TLSv1_2

# Hosts treated as loopback for TLS trust decisions (#6654).
_LOOPBACK_HOSTS: frozenset = frozenset({"127.0.0.1", "localhost", "::1", "ip6-localhost"})

_loopback_permissive_warned: bool = False


def _is_loopback_target(target_url: Optional[str]) -> bool:
    """Return True when target_url resolves to a loopback address."""
    if not target_url:
        return False
    try:
        from urllib.parse import urlparse

        host = (urlparse(target_url).hostname or "").lower()
    except Exception:
        return False
    return host in _LOOPBACK_HOSTS


def tls_verify_enabled() -> bool:
    """Whether internal TLS verification is on — the ``verify=`` bool for httpx.

    The same switch as step 3 of :func:`get_internal_tls_context`, in the shape
    httpx wants, so an httpx caller cannot end up reading the variable itself
    and inverting it. Verification is ON unless ``AUTOBOT_SKIP_TLS_VERIFY=true``
    is set explicitly; the polarity is the whole point. #14653 caught a node
    proxy one commit before merge whose own flag defaulted to *false* — TLS
    verification off unless an operator opted in, on the channel carrying the
    internal API key. A default that has to be opted into is not a default.

    Returns:
        True to verify (the default); False only on an explicit opt-out.
    """
    return os.environ.get("AUTOBOT_SKIP_TLS_VERIFY", "").lower() != "true"


def _project_ca_fallback() -> str:
    """``<project_root>/<AUTOBOT_TLS_CERT_DIR>/ca/ca-cert.pem``, with the one default (#19317)."""
    from autobot_shared.env_registry_tls import DEFAULT_TLS_CERT_DIR

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cert_dir = os.environ.get("AUTOBOT_TLS_CERT_DIR", DEFAULT_TLS_CERT_DIR)
    return os.path.join(project_root, cert_dir, "ca", "ca-cert.pem")


def get_internal_tls_context(
    target_url: Optional[str] = None,
    ca_path: Optional[str] = None,
    client_cert: Optional[str] = None,
    client_key: Optional[str] = None,
) -> ssl.SSLContext:
    """Create SSL context for internal service-to-service TLS (#6702).

    Trust hierarchy (first match wins):
    1. Explicit ``ca_path`` argument — mTLS callers that resolve the cert path
       themselves (e.g. celery_app with Redis mTLS).
    2. ``AUTOBOT_TLS_CA_PATH`` env var — production deployments with a shared CA.
    3. ``AUTOBOT_SKIP_TLS_VERIFY=true`` — development / CI only; never production.
    4. Project CA fallback at ``<project_root>/<AUTOBOT_TLS_CERT_DIR>/ca/ca-cert.pem``
       (single-host installs using the self-signed project CA).
    5. Loopback target with no CA configured — ``CERT_NONE`` (no MITM risk when
       the service is on the same host; logs a one-time warning; #6654).
    6. System trust store — default Python SSL strict behaviour.

    When ``client_cert`` and ``client_key`` are provided, mutual TLS (mTLS) is
    enabled: the client certificate is loaded for authentication in addition to
    the normal server verification.

    Set ``AUTOBOT_SKIP_TLS_VERIFY=true`` ONLY in dev/test environments.
    For non-loopback production deployments configure ``AUTOBOT_TLS_CA_PATH``.
    """
    ctx = ssl.create_default_context()
    # Reject the broken TLSv1/TLSv1_1 protocols on every path below (#12285).
    ctx.minimum_version = MIN_TLS_VERSION

    # 1. Explicit CA path (mTLS callers resolve the path before calling)
    if ca_path and os.path.isfile(ca_path):
        ctx.load_verify_locations(ca_path)
        if client_cert and client_key:
            ctx.load_cert_chain(client_cert, client_key)
        return ctx

    # 2. AUTOBOT_TLS_CA_PATH env var (production deployment)
    env_ca_path = os.environ.get("AUTOBOT_TLS_CA_PATH", "")
    if env_ca_path and os.path.isfile(env_ca_path):
        ctx.load_verify_locations(env_ca_path)
        if client_cert and client_key:
            ctx.load_cert_chain(client_cert, client_key)
        return ctx

    # 3. Dev/test override — skip verification entirely
    if not tls_verify_enabled():
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    # 4. AutoBot project CA fallback (single-host installs with self-signed certs)
    _fallback_ca = _project_ca_fallback()
    if os.path.isfile(_fallback_ca):
        ctx.load_verify_locations(_fallback_ca)
        if client_cert and client_key:
            ctx.load_cert_chain(client_cert, client_key)
        return ctx

    # 5. Loopback target — accept self-signed certs (no MITM possible, #6654)
    if _is_loopback_target(target_url):
        global _loopback_permissive_warned
        if not _loopback_permissive_warned:
            get_logger(__name__).warning(
                "TLS verification disabled for loopback target %s — no CA configured "
                "(set AUTOBOT_TLS_CA_PATH for strict verification, #6654)",
                target_url,
            )
            _loopback_permissive_warned = True
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    # 6. Strict by default (system trust store)
    if client_cert and client_key:
        ctx.load_cert_chain(client_cert, client_key)
    return ctx


def resolve_redis_mtls_paths() -> tuple[str, str, str]:
    """Return ``(ca, client_cert, client_key)`` for Redis mTLS (#6702, #18953).

    Explicit ``tls_ca_path`` / ``tls_cert_path`` / ``tls_key_path`` settings win;
    when any is missing, all three fall back to the legacy ``<cert_dir>`` layout
    under the project root. The one resolver for celery and the checkpointer.
    """
    from autobot_shared.ssot_config import config as ssot_config

    ca = ssot_config.misc.tls_ca_path
    cert = ssot_config.misc.tls_cert_path
    key = ssot_config.misc.tls_key_path
    if ca and cert and key:
        return ca, cert, key
    root = Path(__file__).resolve().parent.parent / ssot_config.tls.cert_dir
    return (
        str(root / "ca" / "ca-cert.pem"),
        str(root / "main-host" / "server-cert.pem"),
        str(root / "main-host" / "server-key.pem"),
    )


def redis_ssl_connection_kwargs() -> dict:
    """redis-py ``ssl_*`` kwargs whose verification policy equals the shared context's.

    Builds the context with :func:`get_internal_tls_context` and mirrors its
    ``verify_mode`` / ``check_hostname`` so redis-py (which defaults hostname
    checking off when only ``ssl_cert_reqs`` is passed) is never weaker than celery.
    """
    ca, cert, key = resolve_redis_mtls_paths()
    ctx = get_internal_tls_context(ca_path=ca, client_cert=cert, client_key=key)
    return {
        "ssl_ca_certs": ca,
        "ssl_certfile": cert,
        "ssl_keyfile": key,
        "ssl_cert_reqs": "required" if ctx.verify_mode == ssl.CERT_REQUIRED else "none",
        "ssl_check_hostname": ctx.check_hostname,
    }
