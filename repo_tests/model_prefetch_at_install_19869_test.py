# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19869, #19738: install fetches the pinned speech-to-text and code-embedding models, and checks they are there."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

from autobot_shared import model_prefetch
from autobot_shared.env_registry import REGISTRY
from autobot_shared.pinned_model_registry import ModelIntegrityError, get_pinned_revision, pinned_weight_files
from autobot_shared.ssot_hf_models import CODE_EMBEDDING_MODEL, PREFETCHED_HF_MODELS, SPEECH_TO_TEXT_MODEL

_ROOT = repo_root()
_ROLE = _ROOT / "autobot-slm-backend" / "ansible" / "roles" / "backend"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tasks(path: Path) -> list[dict]:
    return yaml.safe_load(_text(path))


def _assigned_name(path: Path, target: str) -> str:
    """The Name a module-level ``target = <Name>`` assigns (not a literal)."""
    for node in ast.parse(_text(path)).body:
        if isinstance(node, ast.Assign) and [t.id for t in node.targets if isinstance(t, ast.Name)] == [target]:
            assert isinstance(node.value, ast.Name), f"{target} in {path.name} is a literal, not the SSOT constant"
            return node.value.id
    raise AssertionError(f"{target} not found in {path}")


# --- the ids are written once, pinned, and read by what loads them ---------------------------------


def test_every_prefetched_model_is_pinned_with_weights() -> None:
    assert PREFETCHED_HF_MODELS == (SPEECH_TO_TEXT_MODEL, CODE_EMBEDDING_MODEL)
    for repo_id in PREFETCHED_HF_MODELS:
        assert len(get_pinned_revision(repo_id)) == 40 and pinned_weight_files(repo_id)


def test_the_loaders_read_the_ssot_ids() -> None:
    gen = _ROOT / "autobot-backend" / "code_embedding_generator.py"
    pipe = _ROOT / "autobot-backend" / "media" / "audio" / "pipeline.py"
    assert _assigned_name(gen, "CODEBERT_MODEL_NAME") == "CODE_EMBEDDING_MODEL"
    assert _assigned_name(pipe, "WHISPER_MODEL") == "SPEECH_TO_TEXT_MODEL"
    for path in (gen, pipe):  # neither id is a string literal in code (a comment may still name it)
        literals = {n.value for n in ast.walk(ast.parse(_text(path))) if isinstance(n, ast.Constant)}
        assert not literals & set(PREFETCHED_HF_MODELS)


def test_contrast_an_unregistered_id_has_no_weight_files() -> None:
    with pytest.raises(KeyError):
        pinned_weight_files("someone/unpinned-model")


# --- behaviour of the fetch ---------------------------------------------------------------------


class _Hub:
    """Stands in for the hub: records calls, fails the first ``fail_first`` downloads of each model."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, fail_first: int = 0, always_fail: tuple[str, ...] = ()) -> None:
        self.calls: list[tuple[str, str, bool]] = []
        self.verified: list[str] = []
        self._fail_first, self._always_fail, self._seen = fail_first, always_fail, {}
        monkeypatch.setattr(model_prefetch, "_snapshot", self._snapshot)
        monkeypatch.setattr(model_prefetch, "verify_cached_model", self.verified.append)
        monkeypatch.setattr(model_prefetch, "_cache_dir", lambda: Path("/nonexistent/hf/hub"))
        monkeypatch.setattr(model_prefetch, "free_space", lambda path: f"7.0 GiB free in {path}")

    def _snapshot(self, repo_id: str, revision: str, *, local_only: bool) -> None:
        self.calls.append((repo_id, revision, local_only))
        self._seen[repo_id] = self._seen.get(repo_id, 0) + 1
        if repo_id in self._always_fail or (not local_only and self._seen[repo_id] <= self._fail_first):
            raise OSError("no route to host")


def _run(**kw: object) -> list[str]:
    return model_prefetch.run(PREFETCHED_HF_MODELS, check_only=False, retries=2, delay=0, sleep=lambda _s: None, **kw)


def test_each_model_is_fetched_at_its_pinned_revision_then_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = _Hub(monkeypatch)
    lines = _run()
    assert [line.split()[:2] for line in lines] == [["OK", m] for m in PREFETCHED_HF_MODELS]
    assert hub.calls == [(m, get_pinned_revision(m), False) for m in PREFETCHED_HF_MODELS]
    assert hub.verified == list(PREFETCHED_HF_MODELS)


def test_a_dropped_download_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = _Hub(monkeypatch, fail_first=2)
    assert all(line.startswith("OK") for line in _run())
    assert len(hub.calls) == 2 * 3  # two failures and the success, per model


def test_a_failure_after_the_retries_names_the_model_revision_and_room_and_the_rest_still_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _Hub(monkeypatch, always_fail=(SPEECH_TO_TEXT_MODEL,))
    lines = _run()
    failed = next(line for line in lines if line.startswith("FAILED"))
    assert SPEECH_TO_TEXT_MODEL in failed and get_pinned_revision(SPEECH_TO_TEXT_MODEL) in failed
    assert "after 3 attempts" in failed and "no route to host" in failed and "7.0 GiB free" in failed
    assert lines[1].startswith("OK") and CODE_EMBEDDING_MODEL in lines[1]  # the other model was still fetched


def test_contrast_a_digest_mismatch_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = _Hub(monkeypatch)

    def tampered(repo_id: str) -> None:
        raise ModelIntegrityError("sha256 mismatch")

    monkeypatch.setattr(model_prefetch, "verify_cached_model", tampered)
    lines = _run()
    assert all(line.startswith("FAILED") and "sha256 mismatch" in line for line in lines)
    assert len(hub.calls) == len(PREFETCHED_HF_MODELS)  # one try each


def test_check_mode_downloads_nothing_and_reports_what_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = _Hub(monkeypatch, always_fail=(CODE_EMBEDDING_MODEL,))
    lines = model_prefetch.run(PREFETCHED_HF_MODELS, check_only=True, retries=2, delay=0)
    assert all(local_only for _m, _r, local_only in hub.calls)
    assert lines[0].startswith("OK") and lines[1].startswith("FAILED") and "is not in the cache" in lines[1]


def test_exit_status_is_one_when_any_model_failed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _Hub(monkeypatch, always_fail=(CODE_EMBEDDING_MODEL,))
    assert model_prefetch.main(["--retries", "0", "--delay", "0"]) == 1
    assert "FAILED" in capsys.readouterr().out
    _Hub(monkeypatch)
    assert model_prefetch.main(["--retries", "0", "--delay", "0"]) == 0


# --- the native install runs it, as the service user, and fails the host that lacks a model --------


def test_the_role_fetches_after_the_venv_and_autobot_shared_are_in_place() -> None:
    names = [str(t.get("name", "")) for t in _walk(_tasks(_ROLE / "tasks" / "main.yml"))]
    reinstall = names.index("Reinstall autobot_shared to pick up ssot_config fixes")
    assert names.index("Backend | Pre-fetch the pinned HuggingFace models (#19869, #19738)") > reinstall


def _walk(tasks: list) -> list:
    flat = []
    for task in tasks:
        flat.append(task)
        for key in ("block", "rescue", "always"):
            flat.extend(_walk(task.get(key) or []))
    return flat


def test_the_fetch_and_the_check_run_as_the_service_user_with_the_role_s_retries() -> None:
    tasks = _tasks(_ROLE / "tasks" / "prefetch_models.yml")
    fetch, check = tasks[0], tasks[1]
    for task in (fetch, check):
        assert task["become_user"] == "{{ backend_user }}"
        assert "autobot_shared.model_prefetch" in task["ansible.builtin.command"]["cmd"]
    assert (
        "--check" in check["ansible.builtin.command"]["cmd"]
        and "--check" not in fetch["ansible.builtin.command"]["cmd"]
    )
    defaults = yaml.safe_load(_text(_ROLE / "defaults" / "main.yml"))
    for var in (
        "backend_model_prefetch_retries",
        "backend_model_prefetch_retry_delay",
    ):
        assert defaults[var] > 0 and var in str(fetch)
    assert fetch["timeout"] > 0  # the whole fetch is bounded
    assert not any(model in _text(_ROLE / "tasks" / "prefetch_models.yml") for model in PREFETCHED_HF_MODELS)


def test_a_missing_model_warns_and_only_stops_a_host_that_asked_for_it() -> None:
    warn, stop = _tasks(_ROLE / "tasks" / "prefetch_models.yml")[-2:]
    assert "ansible.builtin.debug" in warn and "select('match', '^FAILED')" in warn["ansible.builtin.debug"]["msg"]
    assert "ansible.builtin.fail" in stop and "backend_model_prefetch_required | bool" in stop["when"]
    defaults = yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    assert defaults["backend_model_prefetch_required"] is False and defaults["backend_prefetch_models"] is True


def test_an_air_gapped_native_install_can_skip_the_fetch() -> None:
    main = (_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")
    include = main[main.index("include_tasks: prefetch_models.yml") :]
    assert include.splitlines()[1].strip() == "when: backend_prefetch_models | bool"


# --- Docker keeps the cache on a volume and fetches into it -----------------------------------------


def test_compose_mounts_the_cache_volume_where_the_image_points_hf_home() -> None:
    dockerfile = _text(_ROOT / "docker" / "backend" / "Dockerfile")
    hf_home = next(line.split("=", 1)[1].strip() for line in dockerfile.splitlines() if line.startswith("ENV HF_HOME="))
    assert (
        f"mkdir -p /app/data /app/logs {hf_home} " in dockerfile
    )  # exists and is owned before the volume is first mounted
    compose = yaml.safe_load(_text(_ROOT / "docker-compose.yml"))
    assert "huggingface_cache" in compose["volumes"]
    for service in ("autobot-backend", "autobot-worker"):
        assert f"huggingface_cache:{hf_home}" in str(compose["services"][service]["volumes"])
    assert "huggingface_cache" not in str(compose["services"]["autobot-redis"])  # contrast: not everywhere


def test_the_entrypoint_fetches_in_the_background_and_never_stops_the_container() -> None:
    script = _text(_ROOT / "docker" / "backend" / "entrypoint.sh")
    block = script[script.index("autobot_shared.model_prefetch") - 40 : script.index('exec "$@"')]
    assert script.index("run_migrations ||") < script.index("autobot_shared.model_prefetch") < script.index('exec "$@"')
    assert "exit 1" not in block and ") &" in block and "WARNING" in block
    assert "AUTOBOT_PREFETCH_MODELS" in script and REGISTRY["AUTOBOT_PREFETCH_MODELS"].default is True


def test_a_failed_fetch_in_the_real_shell_does_not_stop_what_follows(tmp_path: Path) -> None:
    """The entrypoint's own block, run in sh, with a python3 that fails."""
    script = _text(_ROOT / "docker" / "backend" / "entrypoint.sh")
    block = script[script.index('case "${AUTOBOT_PREFETCH_MODELS') : script.index('exec "$@"')]
    fake = tmp_path / "python3"
    fake.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake.chmod(0o755)
    env = {"PATH": f"{tmp_path}:/usr/bin:/bin"}
    done = subprocess.run(
        ["sh", "-c", f"{block}\nwait\necho STARTED\n"], capture_output=True, text=True, env=env, check=False
    )
    assert done.returncode == 0 and "STARTED" in done.stdout and "WARNING" in done.stdout
