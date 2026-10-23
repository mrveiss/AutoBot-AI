# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Env vars that are read under their live, un-prefixed names (#18094).

NPU worker, SLM and image-generation provider variables predate the
``AUTOBOT_`` prefix and are consumed by deployables that cannot import the
backend (the NPU worker container, the SLM agent). They are registered under
their live names, with no renames, so the registry describes what the code
actually reads. Split out of ``env_registry.py`` for the size-ceiling reason
``env_registry_slm.py`` records.

Registration contract (import side effect, ordering): see ``env_registry``.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var
from autobot_shared.network_constants import NetworkConstants


def _register(name: str, type_: type, default, description: str, component: str) -> None:
    register_env_var(EnvVarSpec(name=name, type=type_, default=default, description=description, component=component))


# --- NPU worker --------------------------------------------------------------

_register(
    "NPU_WORKER_PORT",
    int,
    8081,
    "Port the NPU worker listens on (worker) and that `autobot doctor` probes. "
    "AUTOBOT_NPU_WORKER_PORT is the ssot alias and wins in doctor; this bare name "
    "is still honoured so existing deployments keep working.",
    "npu",
)
_register(
    "NPU_WORKER_BIND_HOST",
    str,
    NetworkConstants.BIND_ALL_INTERFACES,
    "Address the NPU worker binds its listener to. Read first by the worker; "
    "falls back to the legacy NPU_WORKER_HOST. Never used to CONNECT to a worker.",
    "npu",
)
_register(
    "NPU_WORKER_HOST",
    str,
    NetworkConstants.BIND_ALL_INTERFACES,
    "Legacy, ambiguous name. In the worker it is the BIND address, used only when "
    "NPU_WORKER_BIND_HOST is unset. Connect-side readers use AUTOBOT_NPU_WORKER_HOST "
    "(ssot); `autobot doctor` still honours this name as a connect host when that is "
    "unset, mapping a 0.0.0.0 bind value to loopback.",
    "npu",
)

# --- SLM ---------------------------------------------------------------------

_register(
    "SLM_NODE_ID",
    str,
    "00-SLM-Manager",
    "Node id. The SLM backend uses it as the manager's own registry id (default shown). "
    "slm/agent/agent.py accepts --node-id. "
    "The agent refuses to start without one.",
    "slm",
)
_register(
    "SLM_SECRET_KEY",
    str,
    "",
    "SLM JWT signing secret. Empty and unset are equivalent (both mean not configured).",
    "slm",
)
_register(
    "SLM_ENCRYPTION_KEY",
    str,
    "",
    "Key for SLM data-at-rest encryption. Empty and unset are equivalent (not configured).",
    "slm",
)
_register(
    "SLM_ADMIN_PASSWORD",
    str,
    "",
    "SLM admin password, the one name for it (#19318). Its home is SLM_ADMIN_PASSWORD in "
    "slm-secrets.env (install.sh or the slm_manager role generates it). Empty means the SLM "
    "creates the admin with a random password and never resets an existing one. No default "
    "password. AUTOBOT_SLM_ADMIN_PASSWORD is a deprecated alias that only install.sh and "
    "the shared ansible reader honour.",
    "slm",
)
_register(
    "SLM_ADMIN_PASSWORD_FILE",
    str,
    "",
    "Path to a file holding the SLM admin password (the hardened compose overlay's mounted "
    "secret). Seeds a fresh install only; an existing admin keeps its stored password (#19368). "
    "Set but unreadable or empty stops the first start with an error.",
    "slm",
)
_register(
    "SLM_USERS_DATABASE_URL",
    str,
    None,
    "SQLAlchemy DSN of the SLM admin-users database. Unset falls back to the "
    "slm_users database on the colocated PostgreSQL.",
    "slm",
)

# --- image-generation providers (credentials; prefer the secrets service) -----

for _name, _provider in (
    ("OPENAI_API_KEY", "OpenAI image"),
    ("FLUX_API_KEY", "Flux"),
    ("STABILITY_API_KEY", "Stability AI"),
):
    _register(
        _name,
        str,
        None,
        f"{_provider} API key for the image-generation plugin. Environment fallback only: "
        "credentials belong in the secrets service.",
        "image_generation",
    )
