# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for HealthCollector state-change pub/sub logic (#3404)."""

import importlib.util
import json
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from slm.agent.health_collector import _STATE_CHANGE_CHANNEL_TEMPLATE, HealthCollector

# stdlib logging, not autobot_shared.logging_manager: the root conftest stubs
# "config" as a MagicMock for the whole session, and LoggingManager reads
# numeric handler settings from it — get_logger() would blow up at collection
# time here (see autobot_shared/user_management/password_epoch.py for the
# same, already-documented exception).
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_collector() -> HealthCollector:
    """Return a HealthCollector with service discovery disabled."""
    return HealthCollector(discover_services=False)


def _svc(name: str, status: str, error_message: str = "") -> dict:
    base = {"name": name, "status": status}
    if error_message:
        base["error_message"] = error_message
    return base


# ---------------------------------------------------------------------------
# _detect_and_publish_state_changes
# ---------------------------------------------------------------------------


class TestDetectAndPublishStateChanges:
    def test_first_observation_does_not_publish(self):
        collector = _make_collector()
        with patch.object(collector, "_publish_state_change") as mock_pub:
            collector._detect_and_publish_state_changes([_svc("nginx", "running")])
        mock_pub.assert_not_called()

    def test_first_observation_stores_state(self):
        collector = _make_collector()
        collector._detect_and_publish_state_changes([_svc("nginx", "running")])
        assert collector._last_known_status["nginx"] == "running"

    def test_same_state_does_not_publish(self):
        collector = _make_collector()
        collector._last_known_status["nginx"] = "running"
        with patch.object(collector, "_publish_state_change") as mock_pub:
            collector._detect_and_publish_state_changes([_svc("nginx", "running")])
        mock_pub.assert_not_called()

    def test_state_change_publishes_event(self):
        collector = _make_collector()
        collector._last_known_status["nginx"] = "running"
        with patch.object(collector, "_publish_state_change") as mock_pub:
            collector._detect_and_publish_state_changes([_svc("nginx", "failed")])
        mock_pub.assert_called_once_with(
            service_name="nginx",
            prev_state="running",
            new_state="failed",
            error_context="",
        )

    def test_error_context_forwarded_on_failure(self):
        collector = _make_collector()
        collector._last_known_status["redis"] = "running"
        with patch.object(collector, "_publish_state_change") as mock_pub:
            collector._detect_and_publish_state_changes([_svc("redis", "failed", error_message="OOM killed")])
        _, kwargs = mock_pub.call_args
        assert kwargs["error_context"] == "OOM killed"

    def test_updates_last_known_status_on_change(self):
        collector = _make_collector()
        collector._last_known_status["nginx"] = "running"
        collector._detect_and_publish_state_changes([_svc("nginx", "failed")])
        assert collector._last_known_status["nginx"] == "failed"

    def test_service_without_name_is_skipped(self):
        collector = _make_collector()
        with patch.object(collector, "_publish_state_change") as mock_pub:
            collector._detect_and_publish_state_changes([{"status": "failed"}])
        mock_pub.assert_not_called()

    def test_multiple_services_each_evaluated_independently(self):
        collector = _make_collector()
        collector._last_known_status["nginx"] = "running"
        collector._last_known_status["sshd"] = "running"
        with patch.object(collector, "_publish_state_change") as mock_pub:
            collector._detect_and_publish_state_changes([_svc("nginx", "failed"), _svc("sshd", "running")])
        assert mock_pub.call_count == 1
        args = mock_pub.call_args
        assert args.kwargs["service_name"] == "nginx"


# ---------------------------------------------------------------------------
# _publish_state_change
# ---------------------------------------------------------------------------


class TestPublishStateChange:
    def _mock_redis(self):
        mock = MagicMock()
        mock.publish = MagicMock(return_value=1)
        return mock

    def test_publishes_to_correct_channel(self):
        collector = _make_collector()
        mock_redis = self._mock_redis()
        with patch("slm.agent.health_collector.get_redis_client", return_value=mock_redis):
            collector._publish_state_change("nginx", "running", "failed", "")
        expected_channel = _STATE_CHANGE_CHANNEL_TEMPLATE.format(service="nginx")
        call_args = mock_redis.publish.call_args[0]
        assert call_args[0] == expected_channel

    def test_payload_contains_required_fields(self):
        collector = _make_collector()
        collector.hostname = "test-host"
        mock_redis = self._mock_redis()
        captured = {}

        def _capture_publish(channel, payload):
            captured["payload"] = json.loads(payload)

        mock_redis.publish.side_effect = _capture_publish
        with patch("slm.agent.health_collector.get_redis_client", return_value=mock_redis):
            collector._publish_state_change("nginx", "running", "failed", "segfault")

        p = captured["payload"]
        assert p["service"] == "nginx"
        assert p["hostname"] == "test-host"
        assert p["prev_state"] == "running"
        assert p["new_state"] == "failed"
        assert p["error_context"] == "segfault"

    def test_redis_unavailable_does_not_raise(self):
        collector = _make_collector()
        with patch("slm.agent.health_collector.get_redis_client", return_value=None):
            # Must not propagate any exception.
            collector._publish_state_change("nginx", "running", "failed", "")

    def test_redis_exception_does_not_raise(self):
        collector = _make_collector()
        mock_redis = self._mock_redis()
        mock_redis.publish.side_effect = ConnectionError("redis gone")
        with patch("slm.agent.health_collector.get_redis_client", return_value=mock_redis):
            collector._publish_state_change("nginx", "running", "failed", "")


# ---------------------------------------------------------------------------
# NotificationEvent.SERVICE_FAILED round-trip (import smoke test)
# ---------------------------------------------------------------------------

# The consumer of the published event is autobot-backend's NotificationService
# (the OTHER backend) — "services.notification_service" does not exist in the
# slm-backend tree, so the bare import could never resolve here (#11798).
# Spec-load the real module from the repo checkout under a private name.  Skip
# when the sibling checkout is not present (deployment layouts).  Resolved by
# upward search so the slm/agent and ansible copies (drift-checked identical)
# both find the repo root from their different depths.


def _find_backend_notif_path():
    for _parent in Path(__file__).resolve().parents:
        _cand = _parent / "autobot-backend" / "services" / "notification_service.py"
        if _cand.exists():
            return _cand
    return None


_BACKEND_NOTIF_PATH = _find_backend_notif_path()

# #14538: "services" and "constants" are the only two first-party roots that
# collide across the two backends — each tree has its own, different package
# by that name.  The root conftest also replaces "services" with a
# session-wide MagicMock for every OTHER test file's sake, so a plain
# sys.meta_path fallback finder never even gets consulted here: Python's own
# import machinery rejects a MagicMock parent as "not a package" before any
# finder runs.  Discover exactly what is missing from the real
# ModuleNotFoundError instead — one level at a time, exactly the way the
# hand-maintained stub dict this replaces did implicitly (pre-populating
# sys.modules bypasses the parent-package check entirely) — rather than from
# a list that has to be kept in sync by hand.
_AUTO_STUB_ROOTS = ("services", "constants")


# Sentinel: the key was absent from sys.modules before we touched it — the
# other value a real key could legitimately hold, ``None``, blocks an import
# on purpose and must not be confused with "nothing was here" (#14538).
_ABSENT = object()


def _stub_module(name: str):
    stub = MagicMock(name=f"autostub:{name}", unsafe=True)
    stub.__name__ = name
    stub.__path__ = []
    return stub


def _install(name: str, module, previous: dict) -> None:
    """Install *module* at ``sys.modules[name]``, remembering the FIRST prior
    value so ``_restore_all`` can put it back exactly.  A bare
    ``sys.modules.pop()`` on cleanup would evict a REAL, already-imported
    module the rest of the process still holds — itself the class of
    ``sys.modules`` leak this repo's shard guard exists to catch."""
    if name not in previous:
        previous[name] = sys.modules.get(name, _ABSENT)
    sys.modules[name] = module


def _stub_or_reraise(exc: ModuleNotFoundError, forbidden: tuple[str, ...], previous: dict) -> None:
    """Narrow-and-loud (#14538): stub *only* a genuinely-missing name rooted
    at ``_AUTO_STUB_ROOTS`` and not under *forbidden* (the subject under
    test) — anything else (a real bug, a third-party dep, a typo) is
    re-raised untouched rather than silently papered over."""
    missing = exc.name or ""
    in_scope = missing.split(".", 1)[0] in _AUTO_STUB_ROOTS
    is_forbidden = any(missing == name or missing.startswith(f"{name}.") for name in forbidden)
    if not in_scope or is_forbidden:
        raise exc
    _install(missing, _stub_module(missing), previous)
    logger.warning("cross-tree loader auto-stubbed missing module %r (#14538)", missing)


def _pop_stub_attr(parent, child: str, stubbed_names: list[str]) -> None:
    """Undo a parent-package attribute Python's import system may have bound
    for one of our stubs — never touches an attribute we did not create."""
    existing = getattr(parent, child, None)
    if existing is not None and getattr(existing, "__name__", None) in stubbed_names:
        delattr(parent, child)


def _restore_all(previous: dict) -> None:
    """Put every touched ``sys.modules`` key back exactly as found: deleted
    if it was genuinely absent, restored if it held something real — so
    nothing survives past one load (the leak this repo's shard-level import
    guard exists to catch).  A *real* prior value is put back untouched and
    its parent is never poked, since we never bound a parent attribute for
    an already-existing key in the first place."""
    for name, was in previous.items():
        if was is not _ABSENT:
            sys.modules[name] = was
            continue
        sys.modules.pop(name, None)
        parent_name, _, child = name.rpartition(".")
        if parent_name and parent_name not in previous:
            parent = sys.modules.get(parent_name)
            if parent is not None:
                _pop_stub_attr(parent, child, list(previous))


def _exec_retrying(source_path, private_name: str, forbidden: tuple[str, ...], previous: dict, max_attempts: int):
    for _ in range(max_attempts):
        spec = importlib.util.spec_from_file_location(private_name, source_path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except ModuleNotFoundError as exc:
            _stub_or_reraise(exc, forbidden, previous)
            continue
        return module
    raise RuntimeError(f"exceeded {max_attempts} auto-stub retries loading {source_path}")


def _exec_with_auto_stub(
    source_path,
    private_name: str,
    forbidden: tuple[str, ...] = (),
    preseed: dict | None = None,
    max_attempts: int = 25,
):
    """Exec *source_path* under *private_name*, auto-stubbing any
    services.*/constants.* import genuinely absent from this rootdir
    (#14538) — a new top-level import added over there does not require
    editing this test.  *preseed* installs fixed stubs unconditionally
    before the first attempt, for the rare case that is not a missing
    module at all (see ``_load_backend_notification_service``).  Returns
    ``(module, stubbed_names)``; every touched key — preseeded or
    discovered — is restored to its exact prior state before returning."""
    previous: dict = {}
    for name, stub in (preseed or {}).items():
        _install(name, stub, previous)
    try:
        module = _exec_retrying(source_path, private_name, forbidden, previous, max_attempts)
    finally:
        stubbed = list(previous)
        _restore_all(previous)
    return module, stubbed


def _load_backend_notification_service():
    # autobot_shared.logging_manager resolves for real here, but this
    # session's root conftest globally replaces "config" with a MagicMock
    # for every OTHER test file's sake (conftest.py's own documented
    # reason) — get_logger() reads numeric log-rotation settings through
    # that same "config" and blows up constructing a real
    # RotatingFileHandler.  Not a #14538 module-absence case — a
    # config-mocking test harness conflict, the same class already
    # documented in autobot_shared/user_management/password_epoch.py — so
    # it is preseeded rather than left to the missing-module discovery.
    preseed = {"autobot_shared.logging_manager": MagicMock(get_logger=MagicMock(return_value=MagicMock()))}
    module, _stubbed = _exec_with_auto_stub(
        _BACKEND_NOTIF_PATH,
        "_backend_notification_service",
        forbidden=("services.notification_service",),
        preseed=preseed,
    )
    return module


class TestServiceFailedEvent:
    @pytest.mark.skipif(_BACKEND_NOTIF_PATH is None, reason="autobot-backend checkout not present (env-bound)")
    def test_service_failed_enum_value(self):
        mod = _load_backend_notification_service()

        assert mod.NotificationEvent.SERVICE_FAILED.value == "service_failed"

    @pytest.mark.skipif(_BACKEND_NOTIF_PATH is None, reason="autobot-backend checkout not present (env-bound)")
    def test_service_failed_template_renders(self):
        mod = _load_backend_notification_service()

        svc = mod.NotificationService()
        result = svc.render_template(
            mod.NotificationEvent.SERVICE_FAILED.value,
            {
                "service": "nginx",
                "hostname": "node-01",
                "prev_state": "running",
                "new_state": "failed",
                "error_context": "OOM killed",
            },
        )
        assert "nginx" in result
        assert "node-01" in result
        assert "running" in result
        assert "failed" in result


# ---------------------------------------------------------------------------
# Cross-tree loader regression (#14538): a new backend import must not force
# an edit here, the loader must never touch the subject under test, and it
# must never leak a synthetic stub past its own scope.
# ---------------------------------------------------------------------------


class TestCrossTreeAutoStub:
    def test_new_services_import_is_auto_stubbed_not_fatal(self, tmp_path):
        """The acceptance criterion itself: add a throwaway import to a
        module loaded this way, confirm the load still succeeds."""
        throwaway = tmp_path / "throwaway_new_import.py"
        throwaway.write_text(
            "from services.totally_new_unstubbed_module import whatever\nVALUE = 42\n",
            encoding="utf-8",
        )

        mod, stubbed = _exec_with_auto_stub(throwaway, "_throwaway_new_import")

        assert mod.VALUE == 42
        assert "services.totally_new_unstubbed_module" in stubbed

    def test_stub_does_not_leak_into_sys_modules_or_parent_package(self, tmp_path):
        """Whether "constants" itself needs stubbing depends on whether a
        real one is on sys.path in this environment (autobot-backend's is,
        in this repo's pytest.ini) — assert only on the submodule this test
        owns, never on that environment detail."""
        throwaway = tmp_path / "throwaway_constants_import.py"
        throwaway.write_text("import constants.made_up_ttl_14538\n", encoding="utf-8")

        mod, stubbed = _exec_with_auto_stub(throwaway, "_throwaway_constants_import")

        assert "constants.made_up_ttl_14538" in stubbed
        assert "constants.made_up_ttl_14538" not in sys.modules
        assert not hasattr(mod.constants, "made_up_ttl_14538")

    def test_forbidden_subject_under_test_is_never_stubbed(self, tmp_path):
        """Narrow-and-loud: a forbidden prefix must fail with the real
        ModuleNotFoundError rather than silently stub the module under
        test."""
        throwaway = tmp_path / "throwaway_forbidden_import.py"
        throwaway.write_text("from services.gateway.egress_governor import egress_governor\n", encoding="utf-8")

        with pytest.raises(ModuleNotFoundError):
            _exec_with_auto_stub(throwaway, "_throwaway_forbidden_import", forbidden=("services.gateway",))

    def test_third_party_or_stdlib_failures_are_never_auto_stubbed(self, tmp_path):
        """Scope check: only services.*/constants.* are in-scope, so an
        absent name outside that (stdlib/third-party) still raises for
        real — the loader must not become a blanket import-error muter."""
        throwaway = tmp_path / "throwaway_out_of_scope_import.py"
        throwaway.write_text("import definitely_not_a_real_package_14538\n", encoding="utf-8")

        with pytest.raises(ModuleNotFoundError):
            _exec_with_auto_stub(throwaway, "_throwaway_out_of_scope_import")
