# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The deployment scripts run without the backend, and keep their host/port env contract (#18132, #12771).

* ``monitor_services.py`` must import in a clean interpreter (no backend on PYTHONPATH).
  The old ``from utils.service_registry import ...`` line is the contrast case: it fails there.
* The scripts' registry resolves each service URL from the SSOT env names. Every old
  ``AUTOBOT_<NAME>_HOST`` is an SSOT alias except ``AUTOBOT_PLAYWRIGHT_VNC_HOST``, which is
  now ``AUTOBOT_BROWSER_SERVICE_HOST`` (migration note in ``deployment_registry.py``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

from repo_tests._paths import repo_root

from autobot_shared.service_registry_core import SERVICE_DEFINITIONS

_ROOT = repo_root()
_SCRIPTS = _ROOT / "autobot-infrastructure/shared/scripts"
_OLD_IMPORT = textwrap.dedent(f"""
    import sys
    sys.path.insert(0, {str(_SCRIPTS.parent)!r})
    from utils.service_registry import RegistryServiceStatus, get_service_registry
    """)
_IMPORT_MONITOR = textwrap.dedent(f"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("monitor_services", {str(_SCRIPTS / "monitor_services.py")!r})
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    print("IMPORTED", module.HealthStatus.__name__)
    """)
_RESOLVE = textwrap.dedent(f"""
    import json, sys
    sys.path.insert(0, {str(_SCRIPTS)!r})
    from deployment_registry import ServiceRegistry
    print(json.dumps(ServiceRegistry().services))
    """)
# Hosts by their SSOT env alias, ports by theirs: distinct per service so a mix-up shows.
_ENV = {
    "AUTOBOT_BACKEND_HOST": "10.0.0.1", "AUTOBOT_BACKEND_PORT": "18001",
    "AUTOBOT_FRONTEND_HOST": "10.0.0.2", "AUTOBOT_FRONTEND_PORT": "15173",
    "AUTOBOT_REDIS_HOST": "10.0.0.3", "AUTOBOT_REDIS_PORT": "16379",
    "AUTOBOT_OLLAMA_HOST": "10.0.0.4", "AUTOBOT_OLLAMA_PORT": "21434",
    "AUTOBOT_AI_STACK_HOST": "10.0.0.5", "AUTOBOT_AI_STACK_PORT": "18080",
    "AUTOBOT_NPU_WORKER_HOST": "10.0.0.6", "AUTOBOT_NPU_WORKER_PORT": "18081",
    "AUTOBOT_BROWSER_SERVICE_HOST": "10.0.0.7", "AUTOBOT_BROWSER_SERVICE_PORT": "19001",
}  # fmt: skip
_EXPECTED = {
    "backend": "http://10.0.0.1:18001",
    "frontend": "http://10.0.0.2:15173",
    "redis": "redis://10.0.0.3:16379",
    "ollama": "http://10.0.0.4:21434",
    "ai-stack": "http://10.0.0.5:18080",
    "npu-worker": "http://10.0.0.6:18081",
    "playwright-vnc": "http://10.0.0.7:19001",
}


def _run(code: str, tmp_path, extra_env: dict[str, str]) -> subprocess.CompletedProcess:
    """Run `code` in an isolated interpreter: no PYTHONPATH, cwd outside the repo, env as given."""
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path), **extra_env}
    return subprocess.run(  # noqa: S603 - fixed argv, our own interpreter
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
        timeout=120,
        check=False,
    )


def test_monitor_services_imports_with_a_clean_pythonpath(tmp_path) -> None:
    done = _run(_IMPORT_MONITOR, tmp_path, {})
    assert done.returncode == 0 and "IMPORTED HealthStatus" in done.stdout, done.stderr[-800:]


def test_contrast_old_backend_import_fails_without_the_backend_on_the_path(tmp_path) -> None:
    done = _run(_OLD_IMPORT, tmp_path, {})
    assert done.returncode != 0 and "ModuleNotFoundError" in done.stderr, done.stderr[-400:]


def test_script_does_not_import_the_backend_service_registry() -> None:
    assert "utils.service_registry" not in (_SCRIPTS / "monitor_services.py").read_text(encoding="utf-8")


def test_resolved_url_per_service_follows_the_ssot_env_names(tmp_path) -> None:
    assert set(_EXPECTED) == set(SERVICE_DEFINITIONS)
    done = _run(_RESOLVE, tmp_path, _ENV)
    assert done.returncode == 0, done.stderr[-800:]
    assert json.loads(done.stdout.splitlines()[-1]) == _EXPECTED


def test_retired_vnc_host_name_is_not_honoured_the_browser_name_is(tmp_path) -> None:
    """Contrast: the pre-#12771 name does nothing; its replacement moves only the VNC service."""
    old = {**{k: v for k, v in _ENV.items() if "BROWSER" not in k}, "AUTOBOT_PLAYWRIGHT_VNC_HOST": "10.9.9.9"}
    done = _run(_RESOLVE, tmp_path, old)
    assert done.returncode == 0, done.stderr[-800:]
    assert json.loads(done.stdout.splitlines()[-1])["playwright-vnc"].startswith("http://127.0.0.1:")
