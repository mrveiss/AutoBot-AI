# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
.env Drift Detector — Issue #2650
==================================

Compares the active .env file against the SSOT config field definitions
to surface stale, missing, or unrecognised environment variable entries
before they silently affect runtime behaviour.

Design goals:
- Non-breaking: detection and warnings only, never auto-mutates .env
- Non-blocking: all failures are caught and logged; never raises on import
- Zero new dependencies: uses stdlib + pydantic (already required)

Usage — programmatic:
    from autobot_shared.env_drift_detector import check_env_drift, DriftReport

    report = check_env_drift()          # uses PROJECT_ROOT/.env by default
    report = check_env_drift("/path/to/.env")  # explicit path

    if report.has_drift:
        for item in report.drifted:
            logger.warning("%s", item)

Usage — CLI:
    python -m autobot_shared.env_drift_detector
    python -m autobot_shared.env_drift_detector /opt/autobot/.env
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List

from autobot_shared.env_file import parse_env_file
from autobot_shared.env_unknown_keys import (
    POLICY_REFUSE,
    POLICY_WARN,
    UnknownEnvKeysRefused,
    declared_env_names,
    describe_unknown_key,
    is_agent_provider_override,
    resolve_policy,
    suggest_key,
)
from autobot_shared.paths import project_root

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class DriftItem:
    """A single env-var drift finding."""

    env_key: str
    severity: str  # "missing", "type_mismatch", "unknown"
    expected_default: str | None
    actual_value: str | None
    message: str


@dataclass
class DriftReport:
    """Aggregated result of a drift check run."""

    env_path: str
    ssot_keys: List[str] = field(default_factory=list)
    env_keys: List[str] = field(default_factory=list)
    drifted: List[DriftItem] = field(default_factory=list)
    unknown_keys: List[str] = field(default_factory=list)
    unknown_suggestions: Dict[str, str | None] = field(default_factory=dict)
    unknown_key_policy: str = POLICY_WARN
    error: str | None = None

    @property
    def has_drift(self) -> bool:
        """True when any drift or unknown entries are present."""
        return bool(self.drifted or self.unknown_keys)

    @property
    def refused(self) -> bool:
        """True when unknown keys are present and the policy is to refuse them (#17419)."""
        return bool(self.unknown_keys) and self.unknown_key_policy == POLICY_REFUSE

    @property
    def missing_keys(self) -> List[str]:
        """SSOT-defined keys absent from .env."""
        return [d.env_key for d in self.drifted if d.severity == "missing"]

    def summary(self) -> str:
        """Return a one-line summary suitable for log output."""
        if self.error:
            return f"env drift check failed: {self.error}"
        parts = [
            f"{len(self.drifted)} drifted",
            f"{len(self.unknown_keys)} unknown",
            f"({len(self.ssot_keys)} SSOT keys, {len(self.env_keys)} .env keys)",
        ]
        return "env drift: " + ", ".join(parts)


# ---------------------------------------------------------------------------
# Introspection helpers
# ---------------------------------------------------------------------------

# Pydantic BaseSettings subclasses defined in ssot_config that we inspect.
# Ordered from most to least specific — duplicates are fine, first alias wins.
_SETTINGS_CLASS_NAMES = [
    "VMConfig",
    "PortConfig",
    "LLMConfig",
    "TimeoutConfig",
    "RedisConfig",
    "CacheCoordinatorConfig",
    "CacheRedisConfig",
    "CacheL1Config",
    "CacheL2Config",
    "FeatureConfig",
    "PermissionConfig",
    "TLSConfig",
    "DatabasePoolConfig",
    "AutoBotConfig",
]


def _collect_ssot_field_defaults() -> Dict[str, str]:
    """Introspect SSOT config classes and return {env_var: str(default)} mapping.

    Returns an empty dict (with a logged warning) if ssot_config cannot be
    imported — this keeps the drift detector safe in restricted environments.
    """
    try:
        import autobot_shared.ssot_config as ssot_mod
    except Exception as exc:
        logger.warning("env_drift_detector: cannot import ssot_config: %s", exc)
        return {}

    result: Dict[str, str] = {}

    for cls_name in _SETTINGS_CLASS_NAMES:
        cls = getattr(ssot_mod, cls_name, None)
        if cls is None:
            continue
        try:
            fields = cls.model_fields  # pydantic v2
        except AttributeError:
            continue

        for field_name, field_info in fields.items():
            # Retrieve the env-var alias (the AUTOBOT_* key)
            alias = _get_env_alias(field_info)
            if alias is None:
                continue

            # Skip sub-config fields that themselves are BaseSettings instances
            if _is_settings_field(field_info):
                continue

            default = _default_as_str(field_info)

            # First definition wins — avoids AutoBotConfig sub-field duplication
            if alias not in result:
                result[alias] = default or ""

    return result


def _get_env_alias(field_info) -> str | None:
    """Extract the env-var alias from a pydantic FieldInfo."""
    # pydantic v2: alias is a string on FieldInfo
    alias = getattr(field_info, "alias", None)
    if isinstance(alias, str) and alias:
        return alias
    return None


def _is_settings_field(field_info) -> bool:
    """Return True when the field type is itself a BaseSettings subclass."""
    try:
        from pydantic_settings import BaseSettings as BS

        annotation = field_info.annotation
        if annotation is None:
            return False
        try:
            return issubclass(annotation, BS)
        except TypeError:
            return False
    except ImportError:
        return False


def _default_as_str(field_info) -> str | None:
    """Return the field default as a string, or None if no default."""
    from pydantic_core import PydanticUndefinedType

    default = field_info.default
    if isinstance(default, PydanticUndefinedType):
        return None
    if default is None:
        return None
    return str(default)


# ---------------------------------------------------------------------------
# .env file parser
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Core comparison logic (small, independently testable functions)
# ---------------------------------------------------------------------------


def _find_missing_keys(ssot_defaults: Dict[str, str], env_values: Dict[str, str]) -> List[DriftItem]:
    """Return DriftItems for SSOT-defined keys absent from .env."""
    items: List[DriftItem] = []
    for key, default in ssot_defaults.items():
        if key not in env_values:
            items.append(
                DriftItem(
                    env_key=key,
                    severity="missing",
                    expected_default=default,
                    actual_value=None,
                    message=(
                        f"Key '{key}' defined in SSOT config but absent from .env " f"(SSOT default: {default!r})"
                    ),
                )
            )
    return items


def _find_unknown_keys(declared: Iterable[str], env_values: Dict[str, str]) -> List[str]:
    """Return ``AUTOBOT_`` keys present in .env that no settings model or registry entry declares.

    *declared* is every name the models bind and the registry registers
    (:func:`declared_env_names`), not just the subset with an SSOT default, so a key a model
    reads through another class is not reported. Only the AUTOBOT_ prefix is flagged, to leave
    unrelated third-party variables (VITE_*, REDIS_*, TF_USE_LEGACY_KERAS, etc.) alone.
    """
    autobot_env = {k for k in env_values if k.startswith("AUTOBOT_")}
    return sorted(k for k in autobot_env - set(declared) if not is_agent_provider_override(k))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_env_drift(env_path: str | None = None) -> DriftReport:
    """Compare .env file against SSOT config field definitions.

    Args:
        env_path: Absolute path to the .env file to check.  When omitted the
            detector uses the same root-finding logic as ssot_config itself.

    Returns:
        DriftReport with findings.  Never raises — all errors are captured in
        ``DriftReport.error`` and logged as warnings.
    """
    # Resolve .env path
    resolved_path = _resolve_env_path(env_path)
    report = DriftReport(env_path=str(resolved_path))

    if not resolved_path.exists():
        report.error = f".env file not found at {resolved_path}"
        logger.warning("env_drift_detector: %s", report.error)
        return report

    # Collect expected keys from SSOT config introspection
    try:
        ssot_defaults = _collect_ssot_field_defaults()
    except Exception as exc:
        report.error = f"SSOT introspection failed: {exc}"
        logger.warning("env_drift_detector: %s", report.error)
        return report

    # Parse the .env file
    try:
        env_values = parse_env_file(resolved_path)
    except Exception as exc:
        report.error = f".env parse error: {exc}"
        logger.warning("env_drift_detector: %s", report.error)
        return report

    report.ssot_keys = sorted(ssot_defaults.keys())
    report.env_keys = sorted(env_values.keys())

    # Find missing keys (SSOT-defined but absent from .env)
    report.drifted = _find_missing_keys(ssot_defaults, env_values)

    # Find unknown AUTOBOT_ keys (in .env but not in SSOT config)
    try:
        declared = declared_env_names() | set(ssot_defaults)
    except Exception as exc:  # classifying against incomplete declarations would call valid names unknown
        report.error = f"declaration lookup failed: {exc}"
        logger.warning("env_drift_detector: %s", report.error)
        return report
    report.unknown_keys = _find_unknown_keys(declared, env_values)
    report.unknown_suggestions = {key: suggest_key(key, declared) for key in report.unknown_keys}
    report.unknown_key_policy = resolve_policy()

    _emit_drift_warnings(report)

    return report


def _resolve_env_path(env_path: str | None) -> Path:
    """Return a resolved Path for the .env file."""
    if env_path:
        return Path(env_path).resolve()

    # #13149: this was a hand-copied mirror of ssot_config's project-root walk,
    # and it drifted — it never gained the checkout step, so from a source tree
    # with no ``.env`` it reported drift against the deployed install's file.
    # ``project_root()`` is the one implementation both now share.
    #
    # ssot-config-exempt: bootstrap, before config is available.
    # #12782: the `/ ".env"` join used to sit inside a trailing comment, so the
    # fallback returned the DIRECTORY. parse_env_file then failed with
    # IsADirectoryError, swallowed it into an empty dict, and every SSOT key was
    # reported missing -- "194 drifted, (194 SSOT keys, 0 .env keys)" on a host
    # whose .env actually held 93 keys. Keep the join on the return itself.
    return project_root() / ".env"


def _emit_drift_warnings(report: DriftReport) -> None:
    """Emit structured log warnings for all findings."""
    if not report.has_drift:
        logger.info(
            "env drift check passed: all %d SSOT keys present in %s",
            len(report.ssot_keys),
            report.env_path,
        )
        return

    logger.warning(
        "env drift detected in %s — %s",
        report.env_path,
        report.summary(),
    )

    for item in report.drifted:
        logger.warning("env drift [%s] %s", item.severity.upper(), item.message)

    for key in report.unknown_keys:
        logger.warning(
            "env drift [UNKNOWN] %s",
            describe_unknown_key(key, report.unknown_suggestions.get(key), report.unknown_key_policy),
        )


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


#: Exit code for unknown ``AUTOBOT_`` keys once the policy has resolved to refuse (#17419).
EXIT_UNKNOWN_KEYS_REFUSED = 3


def raise_if_refused(report: DriftReport) -> None:
    """Log each unknown key, then abort startup when the policy is ``refuse`` (#17419); a no-op otherwise."""
    if not report.refused:
        return
    for key in report.unknown_keys:
        logger.error("%s", describe_unknown_key(key, report.unknown_suggestions.get(key), report.unknown_key_policy))
    raise UnknownEnvKeysRefused(f"{len(report.unknown_keys)} unknown AUTOBOT_* key(s) in .env; see the log above")


def _cli_main(args: List[str]) -> int:
    """CLI runner. Returns exit code: 0 = no drift, 1 = drift found, 2 = error, 3 = unknown keys refused."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    env_path = args[0] if args else None
    report = check_env_drift(env_path)

    if report.error:
        logger.error("env_drift_detector: %s", report.error)
        return 2

    logger.info(report.summary())

    if report.drifted:
        logger.warning("Missing SSOT keys (%d):", len(report.drifted))
        for item in report.drifted:
            logger.warning("  %s: %s", item.env_key, item.message)

    if report.unknown_keys:
        logger.warning("Unknown AUTOBOT_ keys in .env (%d):", len(report.unknown_keys))
        for key in report.unknown_keys:
            logger.warning(
                "  %s", describe_unknown_key(key, report.unknown_suggestions.get(key), report.unknown_key_policy)
            )

    if report.refused:
        return EXIT_UNKNOWN_KEYS_REFUSED
    return 1 if report.has_drift else 0


if __name__ == "__main__":
    sys.exit(_cli_main(sys.argv[1:]))
