# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one home of the environment / deployment-mode / debug settings (#19315, #19316).

``AUTOBOT_ENVIRONMENT`` is the canonical name of the deployment environment. ``AUTOBOT_ENV`` is
the older short spelling of the SAME setting: it is read only when ``AUTOBOT_ENVIRONMENT`` is unset,
and no deployment file writes it. Every reader -- ``ssot_config.AutoBotConfig``, the env registry,
``network_constants``, ``tracing``, the log forwarder -- takes its value or its default from here.

:data:`PROFILES` is the one table of what each deployment profile sets. A file that writes one of
:data:`PROFILE_VARS` (compose, a Dockerfile, an ``.env`` template, an installer) carries exactly one
named profile, and ``repo_tests/deployment_profile_one_source_19315_test.py`` pins its values to
this table. A missing value resolves to :data:`DEFAULT_PROFILE`, which never enables development
behaviour or debug: an unconfigured host runs as production.

Dependency-free on purpose: standalone scripts and pre-init tracing import it without pydantic.
"""

from __future__ import annotations

import logging  # stdlib: this module stays dependency-free (imported by ssot_config itself)
import os
from typing import Any, Mapping, Optional

from autobot_shared.ssot_role_mirrors import FEATURE_ROUTERS_STRICT_DEFAULT, FEATURE_ROUTERS_STRICT_PRODUCTION

logger = logging.getLogger(__name__)

#: Canonical name of the deployment environment (production / development / test / ...).
ENVIRONMENT_VAR = "AUTOBOT_ENVIRONMENT"
#: Legacy short spelling of the same setting, consulted only when the canonical one is unset.
ENVIRONMENT_ALIAS_VAR = "AUTOBOT_ENV"
#: Topology selector (see ``service_registry_core.DeploymentMode``). Unset is ``""``: auto-detect,
#: decided by ``service_registry_core.resolve_deployment_mode`` (owner ruling on #19315, per #12771).
DEPLOYMENT_MODE_VAR = "AUTOBOT_DEPLOYMENT_MODE"
#: Debug switch; ``"true"``/``"false"`` as written in env files.
DEBUG_VAR = "AUTOBOT_DEBUG"

#: Every variable a profile may set; the guard pins every writer of these names.
PROFILE_VARS = (ENVIRONMENT_VAR, ENVIRONMENT_ALIAS_VAR, DEPLOYMENT_MODE_VAR, DEBUG_VAR)

#: The profile a missing value resolves to.
DEFAULT_PROFILE = "production"

#: profile -> the values it sets. A file carrying a profile may set a subset, never another value.
#: ``hybrid`` and ``native`` are not ``DeploymentMode`` members; their validity is #19187.
PROFILES: dict[str, dict[str, str]] = {
    # What an unset value resolves to. Mode "" = auto-detect (container -> docker_local, else local).
    "production": {ENVIRONMENT_VAR: "production", DEPLOYMENT_MODE_VAR: "", DEBUG_VAR: "false"},
    # The ansible fleet: backend.env.j2 writes the environment explicitly and leaves the mode to detection.
    "fleet": {ENVIRONMENT_VAR: "production"},
    # One host, production: docker-compose.yml and the Dockerfiles (environment only; the container
    # is detected as docker_local) and install-bare-metal.sh (environment and mode).
    "single-host": {ENVIRONMENT_VAR: "production", DEPLOYMENT_MODE_VAR: "local"},
    # Developer checkout: .env.example and docker-compose.override.example.yml.
    "development": {ENVIRONMENT_VAR: "development", DEPLOYMENT_MODE_VAR: "hybrid", DEBUG_VAR: "true"},
    # Development tooling overlays on .env.base (#18555).
    "dev-localhost": {ENVIRONMENT_VAR: "development", DEPLOYMENT_MODE_VAR: "local", DEBUG_VAR: "true"},
    "dev-native-vm": {ENVIRONMENT_VAR: "development", DEPLOYMENT_MODE_VAR: "distributed", DEBUG_VAR: "true"},
    # Topology-only selectors written by the deploy scripts and infrastructure overlays.
    "distributed": {DEPLOYMENT_MODE_VAR: "distributed"},
    "local": {DEPLOYMENT_MODE_VAR: "local"},
    "hybrid": {DEPLOYMENT_MODE_VAR: "hybrid"},
    "native": {DEPLOYMENT_MODE_VAR: "native"},
    "kubernetes": {DEPLOYMENT_MODE_VAR: "kubernetes"},
    "ansible-backend": {DEPLOYMENT_MODE_VAR: "production"},  # not a DeploymentMode member: #19187
}

#: The values a missing setting resolves to.
DEFAULTS: dict[str, str] = PROFILES[DEFAULT_PROFILE]
ENVIRONMENT_DEFAULT = DEFAULTS[ENVIRONMENT_VAR]
DEPLOYMENT_MODE_DEFAULT = DEFAULTS[DEPLOYMENT_MODE_VAR]
DEBUG_DEFAULT = DEFAULTS[DEBUG_VAR] == "true"
#: Names the environment is read from, canonical first (pydantic ``AliasChoices`` order).
ENV_NAMES = (ENVIRONMENT_VAR, ENVIRONMENT_ALIAS_VAR)

#: The ONLY environment names that relax a safety decision (e.g. the unapproved-sudo fallback).
#: An allow-list: every other value -- "prod", a typo, "staging" -- is treated as production.
NON_PRODUCTION_ENVIRONMENTS = frozenset({"development", "dev", "test", "ci"})
#: Every recognised name; anything else is warned about once (and is production for safety).
KNOWN_ENVIRONMENTS = NON_PRODUCTION_ENVIRONMENTS | {"production", "staging"}

_warned: set[str] = set()


def _warn_once(key: str, message: str, *args: object) -> None:
    if key not in _warned:
        _warned.add(key)
        logger.warning(message, *args)


def _env(environ: Optional[Mapping[str, str]]) -> Mapping[str, str]:
    return os.environ if environ is None else environ


def resolve_environment(canonical: Optional[str], alias: Optional[str]) -> str:
    """The one normalisation: strip + lower; canonical, else alias, else the default profile's.

    Warns once when both names are set and differ (the canonical one wins), and once per value
    outside :data:`KNOWN_ENVIRONMENTS`.
    """
    primary, legacy = (canonical or "").strip().lower(), (alias or "").strip().lower()
    if primary and legacy and primary != legacy:
        _warn_once(
            "conflict",
            "%s=%r and %s=%r differ; %s wins",
            ENVIRONMENT_VAR,
            primary,
            ENVIRONMENT_ALIAS_VAR,
            legacy,
            ENVIRONMENT_VAR,
        )
    name = primary or legacy or ENVIRONMENT_DEFAULT
    if name not in KNOWN_ENVIRONMENTS:
        _warn_once(
            f"unknown:{name}",
            "Unknown environment %r (known: %s); treated as production",
            name,
            ", ".join(sorted(KNOWN_ENVIRONMENTS)),
        )
    return name


def env_field(value: object) -> str:
    """pydantic before-validator for ``AutoBotConfig.environment``: the same normalisation."""
    return resolve_environment(value if isinstance(value, str) else None, os.environ.get(ENVIRONMENT_ALIAS_VAR))


def _ssot_environment() -> str:
    """The ssot-loaded value (it also reads ``.env``); the default where pydantic is absent."""
    try:
        from autobot_shared.ssot_config import get_config  # lazy: keeps this module dependency-free
    except ImportError:
        return ENVIRONMENT_DEFAULT
    return str(get_config().environment)


def environment_name(environ: Optional[Mapping[str, str]] = None) -> str:
    """The normalised environment: the process env, else (for ``os.environ``) the ssot/.env value."""
    env = _env(environ)
    canonical, alias = env.get(ENVIRONMENT_VAR), env.get(ENVIRONMENT_ALIAS_VAR)
    if environ is None and not (canonical or "").strip() and not (alias or "").strip():
        return _ssot_environment()
    return resolve_environment(canonical, alias)


def is_non_production(name: Optional[str]) -> bool:
    """True only for an allow-listed non-production name; every other value is production."""
    return resolve_environment(name, None) in NON_PRODUCTION_ENVIRONMENTS


def feature_routers_strict_default(environ: Optional[Mapping[str, str]] = None) -> str:
    """The boot mode an environment implies (#19395); an unnamed one stays strict.

    Only a NAMED environment counts: :data:`DEFAULT_PROFILE` is production, so resolving an unset
    name would quietly turn dev checkouts and CI lenient, and a broken router would stop failing them.
    """
    env = _env(environ)
    canonical, alias = env.get(ENVIRONMENT_VAR), env.get(ENVIRONMENT_ALIAS_VAR)
    if not (canonical or "").strip() and not (alias or "").strip():
        return FEATURE_ROUTERS_STRICT_DEFAULT
    if resolve_environment(canonical, alias) in NON_PRODUCTION_ENVIRONMENTS:
        return FEATURE_ROUTERS_STRICT_DEFAULT
    return FEATURE_ROUTERS_STRICT_PRODUCTION


def deployment_mode(environ: Optional[Mapping[str, str]] = None) -> str:
    """``AUTOBOT_DEPLOYMENT_MODE``, else the default profile's."""
    return _env(environ).get(DEPLOYMENT_MODE_VAR) or DEPLOYMENT_MODE_DEFAULT


# Which server answers on the frontend host decides its served URL (#19326). AUTOBOT_FRONTEND_PORT
# is the Vite dev server; the URL a user opens on a nginx host comes from tls.frontend_tls_port or
# port.frontend_http. Owner rulings 2026-10-24: unset is derived from the environment, because the
# updater never rewrites an existing .env (#19436); it is never guessed from ports.
FRONTEND_VITE = "vite"
FRONTEND_NGINX = "nginx"
FRONTEND_SERVED_BY_VALUES = (FRONTEND_VITE, FRONTEND_NGINX)
FRONTEND_SERVED_BY_VAR = "AUTOBOT_FRONTEND_SERVED_BY"


class FrontendServedByError(ValueError):
    """``AUTOBOT_FRONTEND_SERVED_BY`` is set to something other than ``vite`` / ``nginx``."""


def frontend_served_by(value: object, environment: Optional[str]) -> str:
    """*value* when valid, else by *environment*: development and test use Vite, anything else nginx."""
    text = "" if value is None else str(value).strip().lower()
    if text and text not in FRONTEND_SERVED_BY_VALUES:
        expected = ", ".join(FRONTEND_SERVED_BY_VALUES)
        raise FrontendServedByError(f"{FRONTEND_SERVED_BY_VAR}={value!r} -- expected one of {expected}")
    return text or (FRONTEND_VITE if is_non_production(environment) else FRONTEND_NGINX)


def frontend_url(config: Any, host: Optional[str] = None) -> str:
    """The URL *config* (an ``AutoBotConfig``) serves the frontend at; an unknown profile raises.

    *host* replaces the frontend's address for a caller on the frontend's own machine (#20058).
    """
    target = host or config.vm.frontend
    if frontend_served_by(config.frontend_served_by, config.environment) == FRONTEND_VITE:
        return f"http://{target}:{config.port.frontend}"
    if config.tls.frontend_tls_enabled:
        return f"https://{target}:{config.tls.frontend_tls_port}"
    return f"http://{target}:{config.port.frontend_http}"


def served_frontend_url(host: Optional[str] = None) -> str:
    """``frontend_url`` of the process's config, for ``ServiceURLs``; lazy because ssot_config imports this module."""
    from autobot_shared.ssot_config import config

    return frontend_url(config, host)


def try_frontend_url(config: Any) -> Optional[str]:
    """``config.frontend_url``, or ``None`` after a warning when the profile is unknown.

    For callers where the frontend is one optional target among several (health probes, the egress
    allowlist): the frontend is left out -- never defaulted to a port -- and the rest still work.
    """
    try:
        return config.frontend_url
    except FrontendServedByError as exc:
        logger.warning("frontend URL unavailable, the frontend is left out: %s", exc)
        return None
