# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
A role's health check is an explicit per-role field of its manifest (#22032, parent #16025).

Before this, ``role_manifest_shape`` derived health from the manifest's one ``health.endpoint`` for an opt-in list
of roles (``HEALTH_DERIVED_ROLES``) plus one own-bind exception (``HEALTH_OWN_BIND``). Both are gone: the
manifest's ``role_health`` entry for the role is the only declaration, validated by ``RoleHealthCheck``.
"""

import ast

import pytest
from pydantic import ValidationError

from models.manifest import ManifestService, RoleHealthCheck, RoleManifest
from services import role_manifest_shape as rms
from services.manifest_loader import ManifestLoader

#: Each manifest-backed role's resolved (health port, health path) BEFORE #22032, derived from the opt-in list, the
#: own-bind table and the manifests' ``health.endpoint`` of that commit; None is "no health check". The change is
#: behaviour-neutral exactly when every role still resolves to its value here. tts-worker, vnc and docker resolve to no
#: manifest, so the registry (not a manifest) owns theirs.
_BEFORE = {
    "slm-backend": (8000, "/api/health"),
    "slm-frontend": (443, "/"),
    "slm-database": None,
    "slm-monitoring": (9090, "/-/healthy"),
    "backend": (8443, "/api/health"),
    "celery": None,
    "scheduler": None,
    "frontend": (443, "/api/health"),
    "redis": None,
    "postgres": None,
    "chromadb": (8100, "/api/v2/heartbeat"),
    "ai-stack": (8080, "/health"),
    "npu-worker": (8081, "/health"),
    "browser-service": (9001, "/health"),
    "autobot-llm-cpu": (11434, "/api/tags"),
    "autobot-llm-gpu": (11434, "/api/tags"),
    "autobot_shared": None,
    "slm-agent": None,
}
_NO_MANIFEST_ROLES = frozenset({"tts-worker", "vnc", "docker"})


def _manifests():
    from repo_tests._paths import repo_root

    return ManifestLoader(infra_base=repo_root() / "autobot-infrastructure").load_all()


def _resolved(name: str, manifests) -> tuple[int, str] | None:
    shaped = rms.apply_manifest_shape({"name": name, "source_paths": [], "target_path": "/x"}, manifests, {})
    port, path = shaped.get("health_check_port"), shaped.get("health_check_path")
    return None if port is None and path is None else (port, path)


def test_every_role_resolves_to_the_health_it_had_before_the_field_existed():
    manifests = _manifests()
    assert {name: _resolved(name, manifests) for name in _BEFORE} == _BEFORE


def _registry_role_names() -> set[str]:
    from repo_tests._paths import repo_root

    from tools.lint import _parse_cache

    source = (repo_root() / "autobot-slm-backend" / "services" / "role_registry.py").read_text(encoding="utf-8")
    names = set()
    for node in ast.walk(_parse_cache.parse(source)):
        if isinstance(node, ast.Dict):
            fields = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
            name = fields.get("name")
            if isinstance(name, ast.Constant) and "display_name" in fields:
                names.add(name.value)
    return names


def test_the_pin_names_every_registry_role_a_manifest_resolves_to():
    manifests = _manifests()
    resolving = {n for n in _registry_role_names() if rms.find_role_manifest(n, manifests)[0] is not None}
    assert resolving == set(_BEFORE), f"pin out of step with the registry: {resolving ^ set(_BEFORE)}"
    assert not _NO_MANIFEST_ROLES & resolving


def test_every_manifest_declares_role_health_and_the_static_reader_agrees_with_the_runtime():
    from repo_tests._paths import repo_root
    from repo_tests._registry_role_units import manifest_role_health

    manifests = _manifests()
    assert all(m.role_health for m in manifests.values()), [r for r, m in manifests.items() if not m.role_health]
    static = manifest_role_health(repo_root())
    assert static == _BEFORE
    assert {r for m in manifests.values() for r in m.role_health} == set(static)


def test_the_ssot_ports_still_match_the_declared_health_ports():
    """The #19321 / #19324 one-home rule: the declared port is the SSOT port, now that no registry literal says so."""
    from autobot_shared.ssot_config import config

    assert _BEFORE["chromadb"][0] == config.port.chromadb
    assert _BEFORE["npu-worker"][0] == config.port.npu
    assert _BEFORE["browser-service"][0] == config.port.browser


def test_the_opt_in_lists_are_gone_from_the_shape_module():
    assert not hasattr(rms, "HEALTH_DERIVED_ROLES")
    assert not hasattr(rms, "HEALTH_OWN_BIND")
    assert not hasattr(rms, "HEALTH_DERIVATION_EXCLUDED")


# ---------------------------------------------------------------------------
# RoleHealthCheck validator -- contrast pairs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_a_port_outside_the_tcp_range_is_rejected(port):
    with pytest.raises(ValidationError):
        RoleHealthCheck(checked=True, port=port, path="/h")


@pytest.mark.parametrize("port", [1, 8443, 65535])
def test_a_port_inside_the_tcp_range_is_accepted(port):
    assert RoleHealthCheck(checked=True, port=port, path="/h").port == port


@pytest.mark.parametrize("path", ["health", "", None])
def test_a_checked_role_needs_a_path_starting_with_a_slash(path):
    with pytest.raises(ValidationError):
        RoleHealthCheck(checked=True, port=80, path=path)


def test_a_slash_path_is_accepted_for_a_checked_role():
    assert RoleHealthCheck(checked=True, port=80, path="/").path == "/"


def test_a_checked_role_needs_a_port():
    with pytest.raises(ValidationError):
        RoleHealthCheck(checked=True, path="/h")


def test_an_explicit_none_is_accepted_and_carries_no_port_or_path():
    none = RoleHealthCheck(checked=False)
    assert (none.port, none.path) == (None, None)
    with pytest.raises(ValidationError):
        RoleHealthCheck(checked=False, port=80)
    with pytest.raises(ValidationError):
        RoleHealthCheck(checked=False, path="/h")


def test_checked_must_be_stated_not_defaulted():
    with pytest.raises(ValidationError):
        RoleHealthCheck(port=80, path="/h")


def _manifest_tagging(roles: list[str], role_health: dict) -> RoleManifest:
    return RoleManifest(
        role="autobot-x",
        description="fixture",
        deploy={"source": "x/", "destination": "/opt/x/", "sync": False},
        services=[ManifestService(name="x", slm_roles=roles)],
        role_health=role_health,
    )


def test_a_tagged_role_without_a_health_entry_is_rejected():
    with pytest.raises(ValidationError, match="role_health declares nothing for the slm_roles"):
        _manifest_tagging(["a", "b"], {"a": RoleHealthCheck(checked=False)})


def test_every_tagged_role_with_an_entry_is_accepted():
    declared = {"a": RoleHealthCheck(checked=False), "b": RoleHealthCheck(checked=True, port=9, path="/h")}
    assert set(_manifest_tagging(["a", "b"], declared).role_health) == {"a", "b"}


def _undeclared(manifests: dict, role_names: set[str]) -> list[str]:
    """Registry roles that resolve to a manifest which declares no ``role_health`` entry for them."""
    found = []
    for name in sorted(role_names):
        manifest, _owns = rms.find_role_manifest(name, manifests)
        if manifest is not None and name not in (manifest.role_health or {}):
            found.append(name)
    return found


def test_every_real_manifest_declares_health_for_every_role_it_serves():
    assert _undeclared(_manifests(), _registry_role_names()) == []


def test_a_synthetic_manifest_missing_an_entry_is_flagged_and_a_complete_one_passes():
    def build(role_health):
        svc = ManifestService(name="x", slm_roles=["a"])
        return RoleManifest(
            role="autobot-x",
            description="fixture",
            deploy={"source": "x/", "destination": "/opt/x/", "sync": False},
            services=[svc],
            role_health=role_health,
        )

    assert _undeclared({"autobot-x": build({})}, {"a"}) == ["a"]
    assert _undeclared({"autobot-x": build(None)}, {"a"}) == ["a"]
    assert _undeclared({"autobot-x": build({"a": RoleHealthCheck(checked=False)})}, {"a"}) == []


def test_a_stale_manifest_without_role_health_parses_and_its_roles_keep_units_and_sync():
    stale = RoleManifest(
        role="autobot-backend",
        description="stale",
        deploy={"source": "autobot-backend/", "destination": "/opt/b/", "sync_target": "{base_dir}"},
        services=[
            ManifestService(name="autobot-backend"),
            ManifestService(name="autobot-celery", slm_roles=["celery"]),
        ],
    )
    assert stale.role_health is None
    shaped = rms.apply_manifest_shape({"name": "celery"}, {"autobot-backend": stale}, {"base_dir": "/b"})
    assert shaped["systemd_service"] == ["autobot-celery"] and shaped["target_path"] == "/b"
    assert "health_check_port" not in shaped
