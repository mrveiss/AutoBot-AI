# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Ansible Playbook Executor Service

Unified service for executing Ansible playbooks from API endpoints.
Used by Code Sync, Updates, and Infrastructure pages.
"""

import asyncio
import logging
import os
import re
import shlex
import shutil
import time
from pathlib import Path
from typing import Callable, Dict, List

from services.ansible_secrets import fetch_deploy_secrets
from services.ansible_utils import _find_ansible_playbook as _resolve_ansible_playbook
from services.inventory_builder import (
    build_registry_inventory,
    validate_inventory,
    write_temp_extra_vars,
    write_temp_inventory,
)
from services.provision_progress import TaskProgressTracker

logger = logging.getLogger(__name__)

# Per-user Ansible local tmp (#10006): a fixed shared path
# (/tmp/ansible_local_tmp) is created mode 0700 by whichever user runs
# ansible first, locking out every other user (operator debugging as
# themselves vs the SLM's autobot-user playbook executor). Under systemd
# PrivateTmp=true /tmp is namespaced anyway; the uid suffix protects runs
# outside systemd (dev mode, manual uvicorn).
ANSIBLE_LOCAL_TMP = f"/tmp/ansible_local_tmp_{os.getuid()}"  # nosec B108

# #11492: the self-update ansible-playbook run (update-all-nodes.yml against
# the SLM's own node) restarts autobot-slm-backend mid-run. The service is
# KillMode=control-group, so systemd SIGTERMs the whole cgroup on restart —
# including the ansible-playbook child — killing the run before Play 1's tail
# and all of Play 2/3 execute. Detaching that one run into its own transient
# systemd scope (a separate cgroup) lets it survive the restart.
SELF_UPDATE_DETACH_UNIT_PREFIX = os.getenv("SLM_SELF_UPDATE_UNIT_PREFIX", "autobot-selfupdate")

# Env vars forwarded to the detached scope via explicit --setenv=NAME=VALUE.
# `sudo` (env_reset, see setup-passwordless-sudo.yml) strips the environment
# before systemd-run ever sees it, and systemd-run does not forward the
# caller's process environment to the unit it starts — each var must be
# passed explicitly. Only a narrow allowlist (never secrets) is forwarded;
# ansible receives its stored secrets via `-e @file` (#11735 pattern), not env.
SYSTEMD_RUN_ENV_ALLOWLIST_EXACT = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "SSH_AUTH_SOCK")

# Invariant: no ANSIBLE_* var may carry a secret (e.g. ANSIBLE_VAULT_PASSWORD)
# through this allowlist — secrets ride via `-e @file` (#11735), never env.
# Enumerated exactly (not a prefix match) to the keys this module itself sets
# — _build_ansible_env's fixed set plus ANSIBLE_INVENTORY (execute_playbook)
# — so a caller-supplied or inherited ANSIBLE_VAULT_PASSWORD/-style var can
# never slip through just by starting with "ANSIBLE_".
ANSIBLE_ENV_ALLOWLIST_EXACT = (
    "ANSIBLE_FORCE_COLOR",
    "ANSIBLE_NOCOLOR",
    "ANSIBLE_HOST_KEY_CHECKING",
    "ANSIBLE_SSH_RETRIES",
    "ANSIBLE_LOCAL_TEMP",
    "ANSIBLE_INVENTORY",
)

# File-backed output for detached self-update runs (#11492). A pipe's read
# end is owned by this backend process, so once the Play 1 restart task kills
# it, the pipe read side closes — a subsequent write from the (now detached,
# still running) ansible-playbook process would raise BrokenPipeError,
# killing Play 2/3 exactly like the cgroup-kill this fix exists to prevent.
# The detached run's stdout/stderr are redirected to this file instead of the
# backend's pipe (see _wrap_with_systemd_scope), so a dead backend can never
# crash it; this backend tails the same file for live progress while it is
# still alive. Mirrors the existing /var/log/autobot/provision-wizard.log
# precedent (api/setup_wizard.py).
SELF_UPDATE_LOG_PATH = Path(os.getenv("SLM_SELF_UPDATE_LOG_PATH", "/var/log/autobot/self-update-ansible.log"))

# #12425: /var/log/autobot is a shared dir that any autobot-* service user
# may have created/re-created first (observed owned by the TTS worker,
# 0755) — the SLM's own `autobot` user then cannot create a new file there
# and _prepare_self_update_log_file() raises OSError. Silently dropping to
# an attached run in that case is the exact regression this constant exists
# to prevent: #11492's own Play-1 "restart autobot-slm-backend" SIGTERMs an
# attached run before Play 2/3 (the co-located backend/frontend deploy) ever
# execute. Before giving up and going attached, retry under this uid-scoped
# 0700 dir (same one execute_playbook already uses for temp inventories/
# extra-vars, so no additional permission is required beyond what a normal
# run already needs).
SELF_UPDATE_LOG_FALLBACK_PATH = Path(ANSIBLE_LOCAL_TMP) / "self-update-ansible.log"

# Poll interval while tailing the detached run's log file for live progress.
SELF_UPDATE_LOG_TAIL_POLL_SEC = float(os.getenv("SLM_SELF_UPDATE_LOG_TAIL_POLL_SEC", "1.0"))


class PlaybookExecutor:
    """Execute Ansible playbooks programmatically."""

    def __init__(self, ansible_dir: Path | None = None):
        """
        Initialize playbook executor.

        Args:
            ansible_dir: Path to Ansible directory (defaults to autobot-slm-backend/ansible)
        """
        if ansible_dir is None:
            # Use code_source for latest Ansible roles; fall back to deployed copy
            ansible_dir = Path(
                os.getenv(
                    "SLM_ANSIBLE_DIR",
                    "/opt/autobot/code_source/autobot-slm-backend/ansible",
                )
            )
            if not ansible_dir.exists():
                ansible_dir = Path("/opt/autobot/autobot-slm-backend/ansible")
        self.ansible_dir = ansible_dir
        self.inventory_path = ansible_dir / "inventory" / "slm-nodes.yml"

    def _find_ansible_playbook(self) -> str:
        """Find ansible-playbook executable.

        Shared search logic lives in services.ansible_utils (Issue #12693).
        """
        return _resolve_ansible_playbook()

    @staticmethod
    def _clean_task_name(task_name: str) -> str:
        """Strip Ansible role/display prefix and issue-number suffixes."""
        # "backend : Backend | Create venv" → "Create venv"
        if " | " in task_name:
            task_name = task_name.split(" | ", 1)[-1]
        # "[PRE-FLIGHT] Check SSH" → "Check SSH"
        if task_name.startswith("["):
            end = task_name.find("] ")
            if end != -1:
                task_name = task_name[end + 2 :]
        # Strip trailing "(#4679)" issue refs
        task_name = re.sub(r"\s*\(#\d+\)\s*$", "", task_name)
        return task_name.strip()

    def _parse_play1_task(self, task_name: str) -> Dict[str, str] | None:
        """
        Parse Play 1 (SLM) task name for progress.

        Helper for _parse_progress (Issue #880).
        """
        if "Starting SLM Server" in task_name:
            return {
                "stage": "slm_starting",
                "message": "Preparing SLM server update...",
            }
        elif "Sync autobot-slm-backend" in task_name:
            return {"stage": "slm_syncing", "message": "Syncing SLM backend code..."}
        elif "Restart autobot-slm-backend" in task_name:
            return {
                "stage": "slm_restarting",
                "message": "Restarting SLM backend (expect brief disconnect)...",
            }
        elif "Wait for SLM backend" in task_name:
            return {
                "stage": "slm_waiting",
                "message": "Waiting for SLM backend to stabilize...",
            }
        elif "SLM Server Update Complete" in task_name:
            return {"stage": "slm_complete", "message": "SLM server update complete ✓"}
        return None

    def _parse_play2_task(self, task_name: str) -> Dict[str, str] | None:
        """
        Parse Play 2 (Infrastructure) task name for progress.

        Helper for _parse_progress (Issue #880).
        """
        if "Starting Node Update" in task_name:
            return {
                "stage": "nodes_starting",
                "message": "Starting infrastructure node updates...",
            }
        elif "Backend | Sync" in task_name:
            return {"stage": "node_backend", "message": "Syncing backend node code..."}
        elif "Frontend | Sync" in task_name:
            return {
                "stage": "node_frontend",
                "message": "Syncing frontend node code...",
            }
        elif "NPU | Sync" in task_name:
            return {"stage": "node_npu", "message": "Syncing NPU worker code..."}
        elif "Browser | Sync" in task_name:
            return {
                "stage": "node_browser",
                "message": "Syncing browser automation code...",
            }
        elif "Node Update Complete" in task_name:
            return {"stage": "node_complete", "message": "Node update complete ✓"}
        return None

    def _parse_play_line(self, line: str) -> Dict[str, str] | None:
        """
        Parse PLAY line for overall progress.

        Helper for _parse_progress (Issue #880).
        """
        if "Play 1 - Update SLM Server First" in line:
            return {
                "stage": "play1_start",
                "message": "Play 1: Updating SLM server first...",
            }
        elif "Play 2 - Update Other Infrastructure" in line:
            return {
                "stage": "play2_start",
                "message": "Play 2: Updating infrastructure nodes...",
            }
        elif "Fleet Update Summary" in line:
            return {"stage": "complete", "message": "Fleet update complete ✓"}
        return None

    def _parse_progress(self, line: str) -> Dict[str, str] | None:
        """
        Parse Ansible output line for progress updates (Issue #880, #2829).

        Args:
            line: Single line of Ansible output

        Returns:
            Dict with 'stage' and 'message' keys if progress found, None otherwise
        """
        # Match TASK lines with [PLAY N] prefix (update-all-nodes.yml)
        if "TASK [" in line and "[PLAY " in line:
            try:
                task_start = line.index("TASK [")
                # rsplit (not split): the task's own display name embeds a
                # "[PLAY N]" prefix, i.e. its own "]" — splitting on the FIRST
                # "]" truncated at "[PLAY 1" and "[PLAY 1]" never matched
                # below (#11492 discovery while adding self-update log-tail
                # parsing tests). The trailing "] ***" padding never contains
                # "]" itself, so the LAST "]" is always the true delimiter.
                task_name = line[task_start + 6 :].rsplit("]", 1)[0]

                if "[PLAY 1]" in task_name:
                    return self._parse_play1_task(task_name)
                elif "[PLAY 2]" in task_name:
                    return self._parse_play2_task(task_name)
            except (ValueError, IndexError):
                pass

        # Match PLAY lines for overall progress
        if "PLAY [" in line:
            known = self._parse_play_line(line)
            if known:
                return known
            # Generic PLAY match — extract play name for any playbook
            try:
                play_name = line.split("PLAY [")[1].split("]")[0]
                return {"stage": "play", "message": play_name}
            except (IndexError, ValueError):
                pass

        # Generic TASK match — stream task names for any playbook (#2829)
        if "TASK [" in line:
            try:
                task_name = line.split("TASK [")[1].split("]")[0]
                # Detect provision phase markers: "Provision Phase 4a: Backend"
                if task_name.startswith("Provision Phase"):
                    return {"stage": "phase", "message": task_name}
                return {"stage": "task", "message": self._clean_task_name(task_name)}
            except (IndexError, ValueError):
                pass

        # Surface fatal/failed lines so the UI shows errors in real time
        stripped = line.strip()
        if stripped.startswith("fatal:") or stripped.startswith("FAILED!"):
            return {"stage": "error", "message": stripped[:200]}

        # PLAY RECAP line
        if "PLAY RECAP" in line:
            return {"stage": "recap", "message": "Play recap"}

        return None

    def _build_ansible_command(
        self,
        playbook_path: Path,
        limit: List[str] | None,
        tags: List[str] | None,
        extra_vars_file: Path | None,
        check_mode: bool,
        inventory_path: Path | None = None,
    ) -> List[str]:
        """
        Build Ansible command with parameters.

        Helper for execute_playbook (Issue #880).

        extra_vars are passed as ``-e @<file>`` (a 0600 temp JSON written by
        write_temp_extra_vars), never as ``-e key=value`` argv: extra_vars
        always include the stored SLM secrets (#3519), and argv is readable
        by every local user via /proc/<pid>/cmdline for the whole run
        (#11735).
        """
        ansible_cmd = self._find_ansible_playbook()
        effective_inventory = inventory_path or self.inventory_path
        cmd = [ansible_cmd, "-i", str(effective_inventory), str(playbook_path)]

        if limit:
            cmd.extend(["--limit", ",".join(limit)])
        if tags:
            cmd.extend(["--tags", ",".join(tags)])
        if extra_vars_file:
            cmd.extend(["-e", f"@{extra_vars_file}"])
        if check_mode:
            cmd.append("--check")

        return cmd

    async def _process_playbook_lines(
        self,
        line_iter,
        progress_callback: Callable | None,
    ) -> List[str]:
        """
        Shared line-processing loop for playbook output (Issue #880, #3033, #11492).

        Fires progress_callback for each recognized Ansible output line.
        Between recognized lines — when Ansible is silent during long-running
        tasks such as ``ollama pull`` or ``npm install`` — a TaskProgressTracker
        sends periodic heartbeat messages so the UI does not appear stuck.

        A new tracker is started each time a TASK line is detected and the
        previous one is cancelled, so heartbeats are scoped per task.

        ``line_iter`` is any async iterator of decoded, rstripped text lines —
        either live from the child's stdout pipe, or tailed from a log file
        for a detached self-update run (#11492) — so both sources share this
        one parsing/heartbeat implementation.
        """
        output_lines: List[str] = []
        current_tracker: TaskProgressTracker | None = None

        async def _stop_current_tracker() -> None:
            nonlocal current_tracker
            if current_tracker is not None:
                await current_tracker.__aexit__(None, None, None)
                current_tracker = None

        async def _start_tracker(task_name: str) -> None:
            nonlocal current_tracker
            await _stop_current_tracker()
            if progress_callback is not None:
                current_tracker = TaskProgressTracker(task_name, progress_callback)
                await current_tracker.__aenter__()

        try:
            async for line_str in line_iter:
                output_lines.append(line_str)

                if progress_callback:
                    progress = self._parse_progress(line_str)
                    if progress:
                        stage = progress.get("stage", "")
                        # Start a fresh tracker for every new task boundary
                        # so heartbeats reflect the task currently executing.
                        if stage in ("task", "heartbeat") or stage.endswith(
                            ("_starting", "_syncing", "_restarting", "_waiting")
                        ):
                            await _start_tracker(progress.get("message", stage))
                        try:
                            await progress_callback(progress)
                        except Exception as e:
                            logger.debug("Progress callback error: %s", e, exc_info=False)
        finally:
            await _stop_current_tracker()

        return output_lines

    @staticmethod
    async def _iter_pipe_lines(process: asyncio.subprocess.Process):
        """Yield decoded lines from a live child stdout pipe (Issue #880, #3033)."""
        if not process.stdout:
            return
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            yield line.decode("utf-8", errors="replace").rstrip()

    @staticmethod
    async def _iter_log_file_lines(log_path: Path, process: asyncio.subprocess.Process):
        """Tail a log file for a detached run's output (#11492).

        Polls for newly appended lines while ``process`` (the detaching
        wrapper) is still running; stops once it has exited and no further
        lines are pending. The detached ansible-playbook process itself keeps
        writing to this same file independently after this backend restarts —
        this generator simply stops watching, it never stops the write side.
        """
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            while True:
                line = await asyncio.to_thread(fh.readline)
                if not line:
                    if process.returncode is not None:
                        break
                    await asyncio.sleep(SELF_UPDATE_LOG_TAIL_POLL_SEC)
                    continue
                yield line.rstrip("\n")

    async def _stream_playbook_output(
        self,
        process: asyncio.subprocess.Process,
        progress_callback: Callable | None,
    ) -> List[str]:
        """Stream and parse live pipe output for progress. Helper for _run_subprocess."""
        return await self._process_playbook_lines(self._iter_pipe_lines(process), progress_callback)

    async def _tail_playbook_log(
        self,
        log_path: Path,
        process: asyncio.subprocess.Process,
        progress_callback: Callable | None,
    ) -> List[str]:
        """Tail a detached run's log file and parse it for progress (#11492)."""
        return await self._process_playbook_lines(self._iter_log_file_lines(log_path, process), progress_callback)

    @staticmethod
    def _ensure_ansible_temp_dirs() -> None:
        """Ensure Ansible temp directories exist with correct ownership (#2829).

        When another user (e.g. a developer running ansible manually) creates
        the local tmp or /tmp/ansible_fact_cache first, the autobot service
        user gets a permission denied error and Ansible exits with a
        misleading code 4.  Pre-creating the dirs avoids this; the local tmp
        path is additionally uid-scoped (#10006) so it can never collide
        across users.
        """
        for tmp_dir in (
            ANSIBLE_LOCAL_TMP,
            "/tmp/ansible_fact_cache",
        ):  # nosec B108
            Path(tmp_dir).mkdir(mode=0o700, exist_ok=True)

    async def _update_code_source(self) -> None:
        """
        Pull latest code into code_source before running a playbook (#2896).

        Derives code_source root from self.ansible_dir (two levels up).
        Skips silently when the path does not exist or has no .git dir — safe
        in local dev environments.  Never blocks provisioning: any failure is
        logged as a warning and the caller continues.
        """
        code_source_dir = self.ansible_dir.parent.parent
        git_dir = code_source_dir / ".git"
        if not git_dir.exists():
            logger.debug("_update_code_source: no .git at %s — skipping", code_source_dir)
            return

        branch = os.getenv("AUTOBOT_GIT_BRANCH", "Dev_new_gui")

        async def _run_git(*args: str) -> int:
            """Run a git command in code_source_dir with a 30-second timeout."""
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                str(code_source_dir),
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                await asyncio.wait_for(proc.communicate(), timeout=30)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return -1
            return proc.returncode

        try:
            if await _run_git("checkout", "--", ".") != 0:
                logger.warning("_update_code_source: git checkout -- . failed; continuing")

            if await _run_git("fetch", "origin") != 0:
                logger.warning("_update_code_source: git fetch origin failed; continuing")
                return

            if await _run_git("reset", "--hard", f"origin/{branch}") != 0:
                logger.warning(
                    "_update_code_source: git reset --hard origin/%s failed; continuing",
                    branch,
                )
                return

            # Log the resulting HEAD commit for traceability
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                str(code_source_dir),
                "rev-parse",
                "--short",
                "HEAD",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            commit_hash = stdout.decode("utf-8", errors="replace").strip()
            logger.info(
                "_update_code_source: code_source updated to %s on branch %s",
                commit_hash,
                branch,
            )
        except Exception as exc:
            logger.warning("_update_code_source: unexpected error — %s; continuing", exc)

    def _build_ansible_env(self) -> Dict[str, str]:
        """
        Build the environment dict for ansible-playbook subprocess. Ref: #1088.

        Helper for execute_playbook.
        """
        self._ensure_ansible_temp_dirs()
        return {
            **os.environ,
            "ANSIBLE_FORCE_COLOR": "0",
            "ANSIBLE_NOCOLOR": "1",
            "ANSIBLE_HOST_KEY_CHECKING": "False",
            "ANSIBLE_SSH_RETRIES": "3",
            "ANSIBLE_LOCAL_TEMP": ANSIBLE_LOCAL_TMP,
        }

    @staticmethod
    def _self_update_detach_available() -> bool:
        """Whether the self-update run can be detached into its own scope (#11492).

        Both must hold:
          - ``systemd-run`` is on PATH (creates the transient scope)
          - this process is itself managed by systemd — ``INVOCATION_ID`` is set
            only for units systemd starts, so it precisely answers "are we
            running as a systemd service" (as opposed to `sd_booted()`-style
            checks, which are true on any systemd host regardless of how this
            process was launched). Without it there is no same-cgroup restart
            to survive: dev ``uvicorn``, tests, containers without systemd as
            PID 1 all fall back to the direct exec unchanged.
        """
        return shutil.which("systemd-run") is not None and "INVOCATION_ID" in os.environ

    @staticmethod
    def _write_fresh_log_file(path: Path) -> Path | None:
        """Create/truncate a fresh 0600 log file at ``path`` (best-effort).

        Shared by the canonical (#11492) and fallback (#12425) self-update
        log paths. Truncated per run so log-tailing starts at byte 0 and a
        stale prior run's content is never replayed as this run's progress.
        Ansible output can contain sensitive paths/values — 0600, not the
        world-readable default umask.

        Returns None on any OSError; the caller decides whether to fall back
        to another path or give up.
        """
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
            os.chmod(path, 0o600)
            return path
        except OSError:
            return None

    @staticmethod
    def _prepare_self_update_log_file() -> Path | None:
        """Create/truncate a fresh log file for this detached run (#11492).

        The detached ansible-playbook process's stdout/stderr are redirected
        here (see _wrap_with_systemd_scope) instead of the backend's pipe, so
        a dead backend can never BrokenPipe-crash Play 2/3.

        Returns None on failure — the caller (#12425) falls back to a
        writable uid-scoped path before giving up; the caller must NOT detach
        without file-backed output in the meantime (a pipe-only detach would
        just move the same crash risk this fix exists to close from "cgroup
        kill" to "broken pipe"; direct-exec, though it dies with the backend,
        is at least a deterministic, well-understood failure mode).
        """
        result = PlaybookExecutor._write_fresh_log_file(SELF_UPDATE_LOG_PATH)
        if result is None:
            logger.error("Could not prepare canonical self-update log file %s", SELF_UPDATE_LOG_PATH)
        return result

    @staticmethod
    def _systemd_run_env_args(env: Dict[str, str]) -> List[str]:
        """Build explicit --setenv=NAME=VALUE args for the detached scope (#11492).

        Allowlist is a fixed enumeration (SYSTEMD_RUN_ENV_ALLOWLIST_EXACT +
        ANSIBLE_ENV_ALLOWLIST_EXACT), never a prefix match — a caller-supplied
        or inherited ANSIBLE_VAULT_PASSWORD/-style var must never forward just
        by starting with "ANSIBLE_".
        """
        allowed = SYSTEMD_RUN_ENV_ALLOWLIST_EXACT + ANSIBLE_ENV_ALLOWLIST_EXACT
        return [f"--setenv={key}={env[key]}" for key in allowed if key in env]

    def _wrap_with_systemd_scope(self, cmd: List[str], env: Dict[str, str], log_path: Path) -> List[str]:
        """Wrap an ansible-playbook cmd to run detached, file-backed (#11492).

        Two layers:
          - ``sudo -n systemd-run --scope --collect``: a separate transient
            scope = a separate cgroup, so ``systemctl restart
            autobot-slm-backend`` (KillMode=control-group) no longer SIGTERMs
            this run. ``sudo`` mirrors the existing privilege pattern already
            used for service restarts (_restart_slm_service) — the
            passwordless-sudo sudoers rule this service already relies on;
            ``-n`` (non-interactive) fast-fails instead of hanging on a
            password prompt if that sudoers rule is ever misconfigured.
            ``--uid``/``--gid`` drop back to the caller's own identity so
            ansible-playbook still runs as the SLM service user, not root;
            ``--working-directory`` replaces the ``cwd=`` kwarg systemd-run
            does not inherit.
          - ``sh -c 'exec "$0" "$@" >> <log> 2>&1'``: reopens the FINAL exec'd
            process's (ansible-playbook, not this shell) stdout/stderr onto
            the log file before replacing the shell image, so its output is
            never connected to the backend's pipe in the first place — a dead
            backend cannot BrokenPipe it. ``exec "$0" "$@"`` keeps every
            argument a literal positional parameter, so no argv needs shell
            escaping beyond the already-quoted log path.
        """
        unit_name = f"{SELF_UPDATE_DETACH_UNIT_PREFIX}-{os.getpid()}-{int(time.time())}"
        redirect_script = f'exec "$0" "$@" >> {shlex.quote(str(log_path))} 2>&1'
        file_backed_cmd = ["/bin/sh", "-c", redirect_script, *cmd]
        return [
            "sudo",
            "-n",
            "systemd-run",
            "--scope",
            "--collect",
            f"--unit={unit_name}",
            f"--uid={os.getuid()}",
            f"--gid={os.getgid()}",
            f"--working-directory={self.ansible_dir}",
            *self._systemd_run_env_args(env),
            "--",
            *file_backed_cmd,
        ]

    def _prepare_detached_run(self, cmd: List[str], env: Dict[str, str]) -> tuple[List[str], Path | None]:
        """Resolve the effective argv + log path for a requested detach (#11492).

        Helper for _run_subprocess. Returns (cmd, None) unchanged whenever
        detaching isn't possible (no systemd-run/service context, or neither
        the canonical nor fallback log file could be prepared) so the caller
        falls back to the exact pipe-attached behavior that existed before
        this fix.

        #12425: the canonical SELF_UPDATE_LOG_PATH (/var/log/autobot/...) can
        be unwritable by this service user (e.g. another autobot-* service
        owns the shared dir) without systemd-run itself being unavailable.
        Silently dropping to attached in that case is the regression this
        fallback closes — an attached run gets SIGTERM'd by Play 1's own
        "restart autobot-slm-backend" task before Play 2/3 (the co-located
        backend/frontend deploy) ever execute. Try a writable uid-scoped
        fallback path and still detach before giving up.
        """
        if not self._self_update_detach_available():
            logger.warning(
                "Self-update detach requested but systemd-run/service context "
                "unavailable — running attached (this run will die if the "
                "backend restarts mid-flight)"
            )
            return cmd, None

        log_path = self._prepare_self_update_log_file()
        if log_path is None:
            logger.warning(
                "Canonical self-update log path %s unwritable — retrying "
                "under fallback path %s before giving up on detach (#12425)",
                SELF_UPDATE_LOG_PATH,
                SELF_UPDATE_LOG_FALLBACK_PATH,
            )
            log_path = self._write_fresh_log_file(SELF_UPDATE_LOG_FALLBACK_PATH)

        if log_path is None:
            logger.critical(
                "UPDATE-ALL DEGRADED (#12425): neither the canonical (%s) nor "
                "the fallback (%s) self-update log path is writable — running "
                "ATTACHED as a last resort. The imminent Play-1 'restart "
                "autobot-slm-backend' WILL SIGTERM this run before Play 2/3 "
                "(backend/frontend deploy) execute, silently leaving the "
                "co-located app tier stale.",
                SELF_UPDATE_LOG_PATH,
                SELF_UPDATE_LOG_FALLBACK_PATH,
            )
            return cmd, None

        logger.info("Self-update run detached into transient systemd scope, output -> %s", log_path)
        return self._wrap_with_systemd_scope(cmd, env, log_path), log_path

    async def _run_subprocess(
        self,
        cmd: List[str],
        env: Dict[str, str],
        progress_callback: Callable | None,
        detach: bool = False,
    ) -> Dict[str, any]:
        """
        Launch ansible-playbook subprocess and collect output. Ref: #1088.

        Helper for execute_playbook.

        Args:
            detach: When True AND the runtime supports it (#11492), wrap the
                command in ``systemd-run --scope --collect`` with file-backed
                stdout/stderr so it survives a same-process ``systemctl
                restart autobot-slm-backend`` mid-run (the self-update path)
                without a dead backend's pipe crashing it. Falls back to the
                unchanged direct exec + pipe when systemd-run/systemd-service
                context or the log file is unavailable (dev mode, tests,
                containers).
        """
        effective_cmd = cmd
        log_path: Path | None = None
        stdout_target: int = asyncio.subprocess.PIPE
        stderr_target: int = asyncio.subprocess.STDOUT

        if detach:
            effective_cmd, log_path = self._prepare_detached_run(cmd, env)
            if log_path is not None:
                # Real output goes to the file (see _wrap_with_systemd_scope);
                # nothing meaningful is expected on this outer pipe, and
                # leaving it as PIPE-but-unread risks the wrapper deadlocking
                # once the OS pipe buffer fills.
                stdout_target = asyncio.subprocess.DEVNULL
                stderr_target = asyncio.subprocess.DEVNULL

        process = await asyncio.create_subprocess_exec(
            *effective_cmd,
            stdout=stdout_target,
            stderr=stderr_target,
            cwd=str(self.ansible_dir),
            env=env,
        )
        if log_path is not None:
            output_lines = await self._tail_playbook_log(log_path, process, progress_callback)
        else:
            output_lines = await self._stream_playbook_output(process, progress_callback)
        await process.wait()
        return {"output": "\n".join(output_lines), "returncode": process.returncode}

    async def _build_dynamic_inventory(self) -> Path:
        """Generate an Ansible inventory from the DB node registry (#10109, #10095).

        Queries all Node records, builds a YAML inventory where each host name
        equals node_id (so --limit <node_id> always resolves), and writes it to
        a uid-scoped temp file.  Nodes whose IP is local/loopback receive
        ``ansible_connection: local`` so the SLM never SSH-loops to itself.

        Returns:
            Path to the written temp inventory file.

        Raises:
            ValueError: when validate_inventory detects missing required groups.
        """
        from autobot_shared.network_utils import is_local_ip
        from models.database import Node
        from services.database import db_service

        async with db_service.session() as db:
            from sqlalchemy import select

            result = await db.execute(select(Node))
            nodes = list(result.scalars().all())

        inv = build_registry_inventory(nodes, is_local_ip)
        validate_inventory(inv)
        tmp_path = write_temp_inventory(inv, uid_tmp_dir=ANSIBLE_LOCAL_TMP)
        self._link_group_vars(tmp_path)
        logger.info(
            "_build_dynamic_inventory: wrote inventory for %d node(s) to %s",
            len(nodes),
            tmp_path,
        )
        return tmp_path

    def _link_group_vars(self, inventory_path: Path) -> None:
        """Expose the static group_vars beside the dynamic inventory (#11781).

        Ansible resolves ``group_vars/`` relative to the inventory SOURCE
        directory. The dynamic inventory is written to a uid-scoped /tmp dir,
        so none of ``inventory/group_vars/*.yml`` (24 vars in all.yml alone,
        e.g. ``slm_manager_node_id``) loaded — playbooks referencing them hit
        "undefined variable" (the self-update pre-flight "Notify SLM of new
        commit" task failed exactly this way). Symlink the real group_vars dir
        next to the temp inventory so dynamic runs get the same vars as static
        ones. Best-effort: a link failure must not block the deploy.
        """
        src = self.ansible_dir / "inventory" / "group_vars"
        if not src.is_dir():
            return
        link = inventory_path.parent / "group_vars"
        try:
            if link.is_symlink() or link.exists():
                if link.is_symlink() and link.resolve() == src.resolve():
                    return
                link.unlink()
            link.symlink_to(src, target_is_directory=True)
        except OSError as exc:
            logger.warning("Could not link group_vars for dynamic inventory: %s", exc)

    async def execute_playbook(
        self,
        playbook_name: str,
        limit: List[str] | None = None,
        tags: List[str] | None = None,
        extra_vars: Dict[str, str] | None = None,
        check_mode: bool = False,
        progress_callback: Callable | None = None,
        inventory_path: Path | None = None,
        detach: bool = False,
    ) -> Dict[str, any]:
        """
        Execute an Ansible playbook with optional progress updates (Issue #880).

        When ``inventory_path`` is None (the normal path for all non-wizard
        calls), a dynamic inventory is generated from the DB node registry
        (#10109, #10095).  When ``inventory_path`` is provided explicitly
        (wizard provisioning, Issue #1294), the caller's inventory is used
        unchanged.

        Args:
            playbook_name: Name of playbook file (e.g., "update-all-nodes.yml")
            limit: List of hosts to limit execution to
            tags: List of tags to run
            extra_vars: Extra variables to pass to playbook
            check_mode: Run in check mode (dry run)
            progress_callback: Async function to call with progress updates
            inventory_path: Override inventory file (Issue #1294, wizard provisioning)
            detach: Run detached in its own systemd scope (#11492). Only pass
                True for the SLM self-update path (the run that restarts
                autobot-slm-backend); ordinary per-role/per-node deploys leave
                this False, since they don't kill their own process.

        Returns:
            Dict with keys: success (bool), output (str), returncode (int)
        """
        await self._update_code_source()

        playbook_path = self.ansible_dir / playbook_name
        if not playbook_path.exists():
            raise FileNotFoundError(f"Playbook not found: {playbook_path}")

        # Determine which inventory to use.
        # Explicit caller-supplied path (wizard) → use as-is.
        # No path provided → generate from DB node registry (#10109, #10095).
        dynamic_inv_path: Path | None = None
        if inventory_path is not None:
            effective_inventory = inventory_path
            if not effective_inventory.exists():
                raise FileNotFoundError(f"Inventory not found: {effective_inventory}")
        else:
            try:
                dynamic_inv_path = await self._build_dynamic_inventory()
                effective_inventory = dynamic_inv_path
            except Exception as exc:
                logger.warning(
                    "execute_playbook: dynamic inventory failed (%s); " "falling back to static slm-nodes.yml",
                    exc,
                )
                effective_inventory = self.inventory_path
                if not effective_inventory.exists():
                    raise FileNotFoundError(f"Inventory not found: {effective_inventory}") from exc

        # Merge stored SLM secrets into extra_vars so standalone re-deploys
        # receive the same secrets as the full wizard provisioning flow (#3519).
        deploy_secrets = await fetch_deploy_secrets()
        merged_extra_vars: Dict[str, str] = {**deploy_secrets, **(extra_vars or {})}

        # Secrets ride along in extra_vars — hand them to ansible via a 0600
        # temp file (-e @file), never argv (#11735).
        extra_vars_file: Path | None = None
        if merged_extra_vars:
            extra_vars_file = write_temp_extra_vars(merged_extra_vars)

        cmd = self._build_ansible_command(
            playbook_path,
            limit,
            tags,
            extra_vars_file,
            check_mode,
            inventory_path=effective_inventory,
        )
        logger.info(f"Executing Ansible playbook: {' '.join(cmd[:5])}...")

        try:
            env = self._build_ansible_env()
            # Override ansible.cfg default inventory to prevent merging
            # with production.yml when wizard passes a temp inventory (#2836)
            env["ANSIBLE_INVENTORY"] = str(effective_inventory)
            proc_result = await self._run_subprocess(cmd, env, progress_callback, detach=detach)
            success = proc_result["returncode"] == 0
            if success:
                logger.info(f"Playbook {playbook_name} completed successfully")
            else:
                logger.error(f"Playbook {playbook_name} failed with code {proc_result['returncode']}")
            return {
                "success": success,
                "output": proc_result["output"],
                "returncode": proc_result["returncode"],
            }

        except Exception as e:
            logger.exception(f"Failed to execute playbook {playbook_name}: {e}")
            return {
                "success": False,
                "output": f"Error: {str(e)}",
                "returncode": -1,
            }
        finally:
            # Clean up the per-run temp inventory and extra-vars files
            if dynamic_inv_path is not None:
                try:
                    dynamic_inv_path.unlink(missing_ok=True)
                except OSError as exc:
                    logger.debug("Could not remove temp inventory %s: %s", dynamic_inv_path, exc)
            if extra_vars_file is not None:
                try:
                    extra_vars_file.unlink(missing_ok=True)
                except OSError as exc:
                    logger.debug("Could not remove temp extra-vars file %s: %s", extra_vars_file, exc)


# Singleton instance
_playbook_executor: PlaybookExecutor | None = None


def get_playbook_executor() -> PlaybookExecutor:
    """Get singleton playbook executor instance."""
    global _playbook_executor
    if _playbook_executor is None:
        _playbook_executor = PlaybookExecutor()
    return _playbook_executor
