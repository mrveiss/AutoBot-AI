# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Canonical SSL/TLS context factory for internal service-to-service connections.

Issue #6702: consolidates 4+ duplicate ssl.create_default_context() call sites
(slm_client.py, dag_executor.py, celery_app.py, notification_service.py) into
one function with a documented trust hierarchy.
"""

import os
import ssl
from typing import Optional

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

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
    if os.environ.get("AUTOBOT_SKIP_TLS_VERIFY", "").lower() == "true":
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    # 4. AutoBot project CA fallback (single-host installs with self-signed certs)
    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _cert_dir = os.environ.get("AUTOBOT_TLS_CERT_DIR", "certs")
    _fallback_ca = os.path.join(_project_root, _cert_dir, "ca", "ca-cert.pem")
    if os.path.isfile(_fallback_ca):
        ctx.load_verify_locations(_fallback_ca)
        if client_cert and client_key:
            ctx.load_cert_chain(client_cert, client_key)
        return ctx

    # 5. Loopback target — accept self-signed certs (no MITM possible, #6654)
    if _is_loopback_target(target_url):
        global _loopback_permissive_warned
        if not _loopback_permissive_warned:
            logger.warning(
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
