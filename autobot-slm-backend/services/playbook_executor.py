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
import shutil
from pathlib import Path
from typing import Callable, Dict, List

from services.ansible_secrets import fetch_deploy_secrets
from services.provision_progress import TaskProgressTracker

logger = logging.getLogger(__name__)

# Per-user Ansible local tmp (#10006): a fixed shared path
# (/tmp/ansible_local_tmp) is created mode 0700 by whichever user runs
# ansible first, locking out every other user (operator debugging as
# themselves vs the SLM's autobot-user playbook executor). Under systemd
# PrivateTmp=true /tmp is namespaced anyway; the uid suffix protects runs
# outside systemd (dev mode, manual uvicorn).
ANSIBLE_LOCAL_TMP = f"/tmp/ansible_local_tmp_{os.getuid()}"  # nosec B108


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
        """Find ansible-playbook executable."""
        ansible_path = shutil.which("ansible-playbook")
        if ansible_path:
            return ansible_path

        # Try common paths
        common_paths = [
            "/usr/bin/ansible-playbook",
            "/usr/local/bin/ansible-playbook",
        ]
        for path in common_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path

        raise FileNotFoundError("ansible-playbook not found. Install: apt install ansible")

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
                task_name = line[task_start + 6 :].split("]")[0]

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
        extra_vars: Dict[str, str] | None,
        check_mode: bool,
        inventory_path: Path | None = None,
    ) -> List[str]:
        """
        Build Ansible command with parameters.

        Helper for execute_playbook (Issue #880).
        """
        ansible_cmd = self._find_ansible_playbook()
        effective_inventory = inventory_path or self.inventory_path
        cmd = [ansible_cmd, "-i", str(effective_inventory), str(playbook_path)]

        if limit:
            cmd.extend(["--limit", ",".join(limit)])
        if tags:
            cmd.extend(["--tags", ",".join(tags)])
        if extra_vars:
            for key, value in extra_vars.items():
                cmd.extend(["-e", f"{key}={value}"])
        if check_mode:
            cmd.append("--check")

        return cmd

    async def _stream_playbook_output(
        self,
        process: asyncio.subprocess.Process,
        progress_callback: Callable | None,
    ) -> List[str]:
        """
        Stream and parse playbook output for progress (Issue #880, #3033).

        Fires progress_callback for each recognized Ansible output line.
        Between recognized lines — when Ansible is silent during long-running
        tasks such as ``ollama pull`` or ``npm install`` — a TaskProgressTracker
        sends periodic heartbeat messages so the UI does not appear stuck.

        A new tracker is started each time a TASK line is detected and the
        previous one is cancelled, so heartbeats are scoped per task.
        """
        output_lines = []
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

        if process.stdout:
            try:
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break

                    line_str = line.decode("utf-8", errors="replace").rstrip()
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

    async def _run_subprocess(
        self,
        cmd: List[str],
        env: Dict[str, str],
        progress_callback: Callable | None,
    ) -> Dict[str, any]:
        """
        Launch ansible-playbook subprocess and collect output. Ref: #1088.

        Helper for execute_playbook.
        """
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(self.ansible_dir),
            env=env,
        )
        output_lines = await self._stream_playbook_output(process, progress_callback)
        await process.wait()
        return {"output": "\n".join(output_lines), "returncode": process.returncode}

    async def execute_playbook(
        self,
        playbook_name: str,
        limit: List[str] | None = None,
        tags: List[str] | None = None,
        extra_vars: Dict[str, str] | None = None,
        check_mode: bool = False,
        progress_callback: Callable | None = None,
        inventory_path: Path | None = None,
    ) -> Dict[str, any]:
        """
        Execute an Ansible playbook with optional progress updates (Issue #880).

        Args:
            playbook_name: Name of playbook file (e.g., "update-all-nodes.yml")
            limit: List of hosts to limit execution to
            tags: List of tags to run
            extra_vars: Extra variables to pass to playbook
            check_mode: Run in check mode (dry run)
            progress_callback: Async function to call with progress updates
            inventory_path: Override inventory file (Issue #1294, wizard provisioning)

        Returns:
            Dict with keys: success (bool), output (str), returncode (int)
        """
        await self._update_code_source()

        playbook_path = self.ansible_dir / playbook_name
        effective_inventory = inventory_path or self.inventory_path

        if not playbook_path.exists():
            raise FileNotFoundError(f"Playbook not found: {playbook_path}")
        if not effective_inventory.exists():
            raise FileNotFoundError(f"Inventory not found: {effective_inventory}")

        # Merge stored SLM secrets into extra_vars so standalone re-deploys
        # receive the same secrets as the full wizard provisioning flow (#3519).
        deploy_secrets = await fetch_deploy_secrets()
        merged_extra_vars: Dict[str, str] = {**deploy_secrets, **(extra_vars or {})}

        cmd = self._build_ansible_command(
            playbook_path,
            limit,
            tags,
            merged_extra_vars or None,
            check_mode,
            inventory_path=effective_inventory,
        )
        logger.info(f"Executing Ansible playbook: {' '.join(cmd[:5])}...")

        try:
            env = self._build_ansible_env()
            # Override ansible.cfg default inventory to prevent merging
            # with production.yml when wizard passes a temp inventory (#2836)
            env["ANSIBLE_INVENTORY"] = str(effective_inventory)
            proc_result = await self._run_subprocess(cmd, env, progress_callback)
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


# Singleton instance
_playbook_executor: PlaybookExecutor | None = None


def get_playbook_executor() -> PlaybookExecutor:
    """Get singleton playbook executor instance."""
    global _playbook_executor
    if _playbook_executor is None:
        _playbook_executor = PlaybookExecutor()
    return _playbook_executor
