# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Derive DEFAULT_ROLES' manifest-owned shape from autobot-infrastructure/*/manifest.yml (#16025).

``role_registry.DEFAULT_ROLES`` and the manifests independently declared the
same role's identifier, systemd units, health check and ports -- two sources
of truth that could (and did) drift apart. The manifests are canonical for
those four fields (``services/manifest_loader.py``'s own docstring already
claimed this); this module reads the loaded manifests and augments
``role_registry``'s static catalog with the manifest's values, so a future
edit to one ``manifest.yml`` is the only place those facts have to change.

Phase 1 (#16025) derived the identifier, units, health and ports. Phase 2 derives ``source_paths`` and
``target_path`` from ``deploy.source`` / ``deploy.sync`` / ``deploy.sync_target`` (and a service's own
``sync_target``), for every role a manifest resolves to. ``sync_target`` is what the code-sync rsyncs INTO, which
is not the manifest's ``destination`` (the install directory); the two disagree for several roles, and that
discrepancy is tracked separately rather than settled here -- the fields hold exactly what the registry did.
NOT derived, and still declared only in ``role_registry.py``: ``display_name``, ``sync_type``, ``auto_restart``,
``post_sync_cmd``, ``required``, ``degraded_without``, ``ansible_playbook``.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Tuple
from urllib.parse import urlparse

from models.manifest import RoleManifest, ServiceType

_DEFAULT_HTTPS_PORT = 443
_DEFAULT_HTTP_PORT = 80

# #16025: fields apply_manifest_shape never sets -- role_registry.py's static
# dicts remain their sole declaration until each gets a manifest field.
# Pinned so this set can only shrink as fields migrate out of it, never grow.
REGISTRY_ONLY_FIELDS: frozenset = frozenset(
    {
        "display_name",
        "sync_type",
        "auto_restart",
        "post_sync_cmd",
        "required",
        "degraded_without",
        "ansible_playbook",
    }
)

# #16025: derived health would regress this one role. slm-backend sits behind
# nginx on the SLM manager, so its manifest health.endpoint (no explicit port
# in the URL -- an implicit 443) describes the EXTERNAL, proxied check. The
# registry's health_check_port (8000) is the backend process's OWN bind port,
# used to verify the process directly during a deploy -- a different check,
# not a stale duplicate of the same one (verified: autobot-slm-backend's own
# manifest declares its systemd unit with no `system_service`, i.e. the unit
# IS the process on 8000; slm-frontend has no such distinct internal port --
# nginx IS its primary service -- so it is not excluded).
HEALTH_DERIVATION_EXCLUDED = frozenset({"slm-backend"})


def canonical_manifest_role(role_name: str) -> str:
    """The manifest ``role:`` spelling role_name would own, if any manifest declares it.

    ``role_must_have_prefix`` (``models/manifest.py``) makes ``autobot-<name>``
    the only valid spelling. ``autobot_shared`` is the one registry name
    already carrying an (underscore) prefix of its own -- the same file's
    ``role_must_have_prefix`` docstring settles that split: path keeps the
    underscore, role is hyphenated -- so it translates rather than doubling
    the prefix.
    """
    if role_name.startswith("autobot-"):
        return role_name
    if role_name.startswith("autobot_"):
        return "autobot-" + role_name[len("autobot_") :].replace("_", "-")
    return f"autobot-{role_name}"


def find_role_manifest(role_name: str, manifests: Dict[str, RoleManifest]) -> Tuple[RoleManifest | None, bool]:
    """The manifest role_name resolves to, and whether it owns the WHOLE manifest.

    Direct ownership (role_name, canonicalized, equals a manifest's own
    ``role``) wins every service the manifest declares -- e.g. "backend" owns
    autobot-backend's autobot-backend AND autobot-celery units alike. Failing
    that, a service tagging role_name in its own ``slm_roles`` narrows the
    match to just that service -- the shared-manifest case
    (autobot-database's redis/postgres/chromadb) and the fan-out case
    (autobot-ollama's one unit backing both autobot-llm-cpu and
    autobot-llm-gpu).
    """
    canonical = canonical_manifest_role(role_name)
    for manifest in manifests.values():
        if manifest.role == canonical:
            return manifest, True
    for manifest in manifests.values():
        if any(role_name in svc.slm_roles for svc in manifest.services):
            return manifest, False
    return None, False


def systemd_units(role_name: str, manifest: RoleManifest, owns_whole_manifest: bool) -> List[str]:
    """The systemd units role_name runs, per the resolved manifest.

    Only ``type: systemd`` services count -- a ``oneshot`` build step (the
    frontend roles' ``npm run build``) is not a unit to detect or restart.
    """
    services = manifest.services
    if not owns_whole_manifest:
        services = [svc for svc in services if role_name in svc.slm_roles]
    return [svc.system_service or svc.name for svc in services if svc.type == ServiceType.SYSTEMD]


def sync_from_manifest(
    role_name: str, manifest: RoleManifest, owns_whole_manifest: bool, placeholders: Mapping[str, str]
) -> Tuple[List[str], str]:
    """(source_paths, target_path) the code-sync uses for role_name, per the resolved manifest.

    A manifest with ``deploy.sync: false`` ships nothing. The target is the deploy-level ``sync_target`` unless a
    service tagging role_name carries its own; ``{base_dir}`` / ``{agent_dir}`` come from ``placeholders`` so the
    registry's AUTOBOT_BASE_DIR / SLM_AGENT_DIR override still decides them.
    """
    deploy = manifest.deploy
    target = deploy.sync_target
    if not owns_whole_manifest:
        own = [
            svc.sync_target for svc in manifest.services if role_name in svc.slm_roles and svc.sync_target is not None
        ]
        if own:
            target = own[0]
    return ([deploy.source] if deploy.sync else []), target.format_map(placeholders)


def health_from_manifest(manifest: RoleManifest) -> Tuple[int | None, str | None]:
    """(port, path) implied by the manifest's ``health.endpoint``, or (None, None)."""
    if manifest.health is None:
        return None, None
    parsed = urlparse(manifest.health.endpoint)
    if parsed.port is not None:
        port = parsed.port
    elif parsed.scheme == "https":
        port = _DEFAULT_HTTPS_PORT
    elif parsed.scheme == "http":
        port = _DEFAULT_HTTP_PORT
    else:
        return None, None
    return port, (parsed.path or None)


def manifest_ports(manifest: RoleManifest) -> List[Dict]:
    """The manifest's declared ports, as plain dicts (role_registry has no schema for these yet)."""
    return [
        {
            "port": p.port,
            "protocol": p.protocol.value,
            "public": p.public,
            "loopback_only": p.loopback_only,
        }
        for p in manifest.ports
    ]


def _as_unit_list(value) -> List[str] | None:
    """Wrap an existing bare systemd_service string into a single-element list."""
    if not value or isinstance(value, list):
        return None
    return [value]


_default_roles_cache: List[Dict] | None = None


def default_roles_for(static_roles: List[Dict], placeholders: Mapping[str, str] | None = None) -> List[Dict]:
    """Memoized ``role_registry.DEFAULT_ROLES``: static_roles, each manifest-augmented.

    A shallow ``dict(role)`` copy per entry -- ``apply_manifest_shape`` mutates
    what it is given, and the caller's static list must stay untouched.
    Cached process-wide: manifest loading is file I/O, and there is one
    static role list in practice, built once at ``role_registry`` import time.
    """
    global _default_roles_cache
    if _default_roles_cache is None:
        from services.manifest_loader import get_manifest_loader

        manifests = get_manifest_loader().load_all()
        _default_roles_cache = [apply_manifest_shape(dict(role), manifests, placeholders) for role in static_roles]
    return _default_roles_cache


def apply_manifest_shape(
    role_data: Dict, manifests: Dict[str, RoleManifest], placeholders: Mapping[str, str] | None = None
) -> Dict:
    """Return role_data augmented with its manifest-derived identifier/units/health/ports.

    Mutates and returns the same (already-copied) dict the caller passes in;
    every registry-only field (post_sync_cmd, ansible_playbook, ...) is left
    untouched. A role no manifest resolves to keeps its own static
    ``source_paths`` / ``target_path``.
    """
    name = role_data["name"]
    manifest, owns_whole = find_role_manifest(name, manifests)
    if manifest is None:
        wrapped = _as_unit_list(role_data.get("systemd_service"))
        if wrapped is not None:
            role_data["systemd_service"] = wrapped
        return role_data

    role_data["canonical_name"] = manifest.role
    role_data["ports"] = manifest_ports(manifest)
    role_data["source_paths"], role_data["target_path"] = sync_from_manifest(
        name, manifest, owns_whole, placeholders or {}
    )

    units = systemd_units(name, manifest, owns_whole)
    if units:
        role_data["systemd_service"] = units
    else:
        wrapped = _as_unit_list(role_data.get("systemd_service"))
        if wrapped is not None:
            role_data["systemd_service"] = wrapped

    if role_data.get("health_check_port") is not None and name not in HEALTH_DERIVATION_EXCLUDED:
        port, path = health_from_manifest(manifest)
        if port is not None:
            role_data["health_check_port"] = port
            role_data["health_check_path"] = path

    return role_data
