# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Send a test command for one commit to the remote test node (#20935; maintainer decision 2026-11-06).

The pushed SHA goes over SSH with ``git push`` into a mirror on the node, so only what the branch adds crosses
the link, the node holds no repository credential and every run starts from a clean checkout. The node's
address, user and key come from ``AUTOBOT_TEST_NODE_*`` settings and never from the repo.
Exit status: the command's own, 124 on timeout, 75 when the node is not
configured, not provisioned or not reachable (the caller falls back to local), 130/143 after SIGINT/SIGTERM.

    run.py --sha SHA [--timeout N] -- CMD...   run CMD on the node against SHA's tree
    run.py --provision                         install what a run needs on the node (idempotent)
"""

from __future__ import annotations

import argparse
import os
import shlex
import signal
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))  # run as a script: the repo root is not on the path

from autobot_shared.paths import scrubbed_git_env  # noqa: E402

UNAVAILABLE = 75
TIMEOUT_RC = 124
REQUIREMENTS = ("requirements-ci-test.txt", "tools/remote_test_node/requirements.txt")


@dataclass(frozen=True)
class NodeConfig:
    host: str
    user: str
    key: str
    port: str
    slots: int
    timeout: int
    connect_timeout: int
    base: str
    ssh_bin: str
    ttl_min: int


def load_config(env: "os._Environ[str] | dict[str, str]") -> "NodeConfig | str":
    """The settings, or the reason the node is not configured."""
    get = env.get
    if get("AUTOBOT_TEST_NODE_ENABLED", "1") == "0":
        return "AUTOBOT_TEST_NODE_ENABLED=0"
    host, user = get("AUTOBOT_TEST_NODE_HOST", ""), get("AUTOBOT_TEST_NODE_USER", "")
    if not host or not user:
        return "AUTOBOT_TEST_NODE_HOST / AUTOBOT_TEST_NODE_USER are not set"
    timeout = int(get("AUTOBOT_TEST_NODE_TIMEOUT", "600"))
    return NodeConfig(
        host=host,
        user=user,
        key=get("AUTOBOT_TEST_NODE_SSH_KEY", ""),
        port=get("AUTOBOT_TEST_NODE_PORT", "22"),
        slots=int(get("AUTOBOT_TEST_NODE_SLOTS", "3")),
        timeout=timeout,
        connect_timeout=int(get("AUTOBOT_TEST_NODE_CONNECT_TIMEOUT", "10")),
        base=get("AUTOBOT_TEST_NODE_BASE", ".autobot-test-node"),
        ssh_bin=get("AUTOBOT_TEST_NODE_SSH_BIN", "ssh"),
        ttl_min=timeout // 60 + 30,
    )


def ssh_options(cfg: NodeConfig) -> list[str]:
    """The ssh command line up to, not including, the destination (git reuses it as GIT_SSH_COMMAND)."""
    argv = [
        cfg.ssh_bin,
        "-p",
        cfg.port,
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={cfg.connect_timeout}",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]
    if cfg.key:
        argv += ["-i", os.path.expanduser(cfg.key), "-o", "IdentitiesOnly=yes"]
    return argv


def ssh_argv(cfg: NodeConfig) -> list[str]:
    return ssh_options(cfg) + [f"{cfg.user}@{cfg.host}"]


def _script_command(script: str, *args: str) -> str:
    """``bash -c <script> name args...`` as one remote command line: the node keeps no copy to go stale."""
    text = (HERE / script).read_text(encoding="utf-8")
    return " ".join(["bash", "-c", shlex.quote(text), script, *map(shlex.quote, args)])


def probe(cfg: NodeConfig) -> "str | None":
    """None when the node answers over SSH, else why not."""
    done = subprocess.run(
        ssh_argv(cfg) + ["true"], capture_output=True, text=True, check=False, timeout=cfg.connect_timeout + 10
    )
    return None if done.returncode == 0 else f"ssh to the test node failed (exit {done.returncode})"


def remote_cleanup(cfg: NodeConfig, job: str) -> None:
    """Belt and braces for the node's own trap: remove this job's dir whatever state the session is in."""
    mirror = shlex.quote(f"{cfg.base}/mirror.git")
    path = shlex.quote(f"{cfg.base}/runs/job.{job}")
    drop = f"rm -rf -- {path}; git --git-dir={mirror} update-ref -d refs/runs/{job}"
    subprocess.run(ssh_argv(cfg) + [drop], capture_output=True, check=False, timeout=60)


def ship_commit(cfg: NodeConfig, sha: str, job: str) -> "str | None":
    """Refresh the node's mirror of the base branch, then push only what ``sha`` adds. None, or why not."""
    mirror = shlex.quote(f"{cfg.base}/mirror.git")
    refresh = f"git --git-dir={mirror} fetch --quiet --no-tags origin +refs/heads/main:refs/heads/main"
    if subprocess.run(ssh_argv(cfg) + [refresh], capture_output=True, check=False, timeout=600).returncode != 0:
        return "the node's mirror could not be refreshed (run --provision?)"
    ssh_cmd = shlex.join(ssh_options(cfg))
    dest = f"{cfg.user}@{cfg.host}:{cfg.base}/mirror.git"
    done = subprocess.run(
        ["git", "push", "--quiet", dest, f"{sha}:refs/runs/{job}"],
        env=scrubbed_git_env({**os.environ, "GIT_SSH_COMMAND": ssh_cmd}),
        capture_output=True,
        check=False,
        timeout=1800,
    )
    return None if done.returncode == 0 else "the commit could not be pushed to the node"


def run_remote(cfg: NodeConfig, sha: str, cmd: list[str], timeout: int) -> int:
    job = uuid.uuid4().hex[:12]
    ssh = None
    old = {s: signal.signal(s, _raise_on_signal) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        why = ship_commit(cfg, sha, job)
        if why:
            return unavailable(why)
        remote = _script_command(
            "remote_job.sh", cfg.base, str(cfg.slots), str(timeout), str(cfg.ttl_min), job, "--", *cmd
        )
        ssh = subprocess.Popen(ssh_argv(cfg) + [remote], stdin=subprocess.DEVNULL, start_new_session=True)
        return ssh.wait(timeout=timeout + 120)
    except subprocess.TimeoutExpired:
        return TIMEOUT_RC
    except _Interrupted as exc:
        return 128 + exc.signum
    finally:
        _finish(cfg, job, ssh, old)


class _Interrupted(Exception):
    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum


def _raise_on_signal(signum: int, _frame: object) -> None:
    raise _Interrupted(signum)


def _finish(cfg: NodeConfig, job: str, ssh, old: dict) -> None:
    if ssh is not None and ssh.poll() is None:
        ssh.kill()
        ssh.wait()
    for sig, handler in old.items():
        signal.signal(sig, handler)
    remote_cleanup(cfg, job)


def python_floor(root: Path) -> str:
    """The repo's declared Python floor, read from .python-version (never written down here)."""
    text = (root / ".python-version").read_text(encoding="utf-8").strip()
    return ".".join(text.split(".")[:2])


def _origin_url() -> str:
    """The public URL the node's mirror follows; read here so no URL is written down in the tooling."""
    done = subprocess.run(
        ["git", "remote", "get-url", "origin"], capture_output=True, text=True, check=True, env=scrubbed_git_env()
    )
    return done.stdout.strip()


def provision(cfg: NodeConfig, root: Path) -> int:
    """Send provision.sh and the CI test requirements; safe to run again."""
    reqs = "\n".join((root / name).read_text(encoding="utf-8") for name in REQUIREMENTS if (root / name).is_file())
    done = subprocess.run(
        ssh_argv(cfg) + [_script_command("provision.sh", cfg.base, _origin_url(), python_floor(root))],
        input=reqs.encode("utf-8"),
        check=False,
        timeout=1800,
    )
    return done.returncode


def unavailable(reason: str) -> int:
    sys.stderr.write(f"[remote-test-node] UNAVAILABLE: {reason}\n")
    return UNAVAILABLE


def main(argv: "list[str] | None" = None, env: "dict[str, str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sha", help="commit whose tree the command runs against")
    parser.add_argument("--timeout", type=int, help="seconds the command may run on the node")
    parser.add_argument("--provision", action="store_true")
    parser.add_argument("cmd", nargs="*")
    args = parser.parse_args(argv)
    cfg = load_config(os.environ if env is None else env)
    if isinstance(cfg, str):
        return unavailable(f"not configured ({cfg})")
    if args.provision:
        return provision(cfg, Path.cwd())
    if not args.sha or not args.cmd:
        parser.error("--sha and a command are required")
    reason = probe(cfg)
    if reason:
        return unavailable(reason)
    rc = run_remote(cfg, args.sha, args.cmd, args.timeout or cfg.timeout)
    return unavailable("the SSH session failed mid-run") if rc == 255 else rc


if __name__ == "__main__":
    sys.exit(main())
