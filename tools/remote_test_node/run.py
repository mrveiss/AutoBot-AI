# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Send a test command for one commit to the remote test node (#20935; maintainer decision 2026-11-06).

The pushed SHA goes over SSH with ``git send-pack`` into a mirror on the node, so only what the branch adds crosses
the link, the node holds no repository credential and every run starts from a clean checkout. The node's
address, user and key come from ``AUTOBOT_TEST_NODE_*`` settings and never from the repo.
Exit status: the command's own, 124 when the command started and hit its limit on the node, 75 when the node is not
configured, not provisioned, not reachable or gave no result within the limit (the caller falls back to local),
130/143 after SIGINT/SIGTERM.

    run.py --sha SHA [--timeout N] -- CMD...   run CMD on the node against SHA's tree
    run.py --provision                         install what a run needs on the node (idempotent)
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import signal
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent  # provisioning reads files by repo path, never from the caller's working directory
sys.path.insert(0, str(REPO_ROOT))  # run as a script: the repo root is not on the path

from autobot_shared.env_registry import REGISTRY  # noqa: E402
from autobot_shared.env_utils import within_range  # noqa: E402
from autobot_shared.paths import scrubbed_git_env  # noqa: E402

UNAVAILABLE = 75
REQUIREMENTS = ("requirements-ci-test.txt", "requirements-remote-test-node.txt")
CONSTRAINTS = "constraints/shared.txt"
CONSTRAINTS_MARKER = "#--constraints--"  # provision.sh splits its stdin here
_CONSTRAINT_LINE = re.compile(r"^\s*(?:-c\s*=?\s*|--constraint(?:\s+|=))\S+\s*(?:#.*)?$")
_INCLUDE_LINE = re.compile(r"^\s*(?:-r|--requirement)(?:\s|=|$)|^\s*-r\S")
_VERSION = re.compile(r"^\d+(?:\.\d+)*$")


@dataclass(frozen=True)
class RemoteNodeSettings:
    host: str
    user: str
    key: str
    port: str
    slots: int
    timeout: int
    connect_timeout: int
    base: str
    ssh_bin: str
    known_hosts: str


def _int_setting(env: "os._Environ[str] | dict[str, str]", name: str) -> int:
    """An integer setting checked against the registry's spec.

    A malformed or out-of-range value reads as the default.
    """
    spec = REGISTRY[name]
    raw = env.get(name)
    if raw is None or raw == "":
        return spec.default
    try:
        value = int(raw)
    except ValueError:
        sys.stderr.write(f"[remote-test-node] {name} is not an integer; using the default {spec.default}\n")
        return spec.default
    return value if within_range(name, value, spec.range) else spec.default


def load_config(env: "os._Environ[str] | dict[str, str]") -> "RemoteNodeSettings | str":
    """The settings, or the reason the node is not configured."""
    get = env.get
    if get("AUTOBOT_TEST_NODE_ENABLED", "1") == "0":
        return "AUTOBOT_TEST_NODE_ENABLED=0"
    host, user = get("AUTOBOT_TEST_NODE_HOST", ""), get("AUTOBOT_TEST_NODE_USER", "")
    if not host or not user:
        return "AUTOBOT_TEST_NODE_HOST / AUTOBOT_TEST_NODE_USER are not set"
    return RemoteNodeSettings(
        host=host,
        user=user,
        key=get("AUTOBOT_TEST_NODE_SSH_KEY", ""),
        port=get("AUTOBOT_TEST_NODE_PORT", "22"),
        slots=_int_setting(env, "AUTOBOT_TEST_NODE_SLOTS"),
        timeout=_int_setting(env, "AUTOBOT_TEST_NODE_TIMEOUT"),
        connect_timeout=_int_setting(env, "AUTOBOT_TEST_NODE_CONNECT_TIMEOUT"),
        base=get("AUTOBOT_TEST_NODE_BASE", ".autobot-test-node"),
        ssh_bin=get("AUTOBOT_TEST_NODE_SSH_BIN", "ssh"),
        known_hosts=get("AUTOBOT_TEST_NODE_KNOWN_HOSTS", ""),
    )


def node_ssh_options(cfg: RemoteNodeSettings) -> list[str]:
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
    ]
    if cfg.known_hosts:  # pinned: only the keys in this file are trusted
        argv += ["-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={os.path.expanduser(cfg.known_hosts)}"]
    else:  # trust on first use: a later change of the node's key is refused
        argv += ["-o", "StrictHostKeyChecking=accept-new"]
    if cfg.key:
        argv += ["-i", os.path.expanduser(cfg.key), "-o", "IdentitiesOnly=yes"]
    return argv


def ssh_argv(cfg: RemoteNodeSettings) -> list[str]:
    return node_ssh_options(cfg) + [f"{cfg.user}@{cfg.host}"]


def _script_command(script: str, *args: str) -> str:
    """``bash -c <script> name args...`` as one remote command line: the node keeps no copy to go stale."""
    text = (HERE / script).read_text(encoding="utf-8")
    return " ".join(["bash", "-c", shlex.quote(text), script, *map(shlex.quote, args)])


def probe(cfg: RemoteNodeSettings) -> "str | None":
    """None when the node answers over SSH, else why not."""
    try:
        done = subprocess.run(
            ssh_argv(cfg) + ["true"], capture_output=True, text=True, check=False, timeout=cfg.connect_timeout + 10
        )
    except subprocess.TimeoutExpired:
        return "ssh to the test node timed out"
    except OSError as exc:  # the ssh executable is missing or not runnable
        return f"ssh to the test node could not start ({exc.__class__.__name__})"
    return None if done.returncode == 0 else f"ssh to the test node failed (exit {done.returncode})"


def remote_cleanup(cfg: RemoteNodeSettings, job: str) -> None:
    """Belt and braces for the node's own trap: remove this job's dir whatever state the session is in."""
    mirror = shlex.quote(f"{cfg.base}/mirror.git")
    path = shlex.quote(f"{cfg.base}/runs/job.{job}")
    drop = f"rm -rf -- {path}; git --git-dir={mirror} update-ref -d refs/runs/{job}"
    try:
        subprocess.run(ssh_argv(cfg) + [drop], capture_output=True, check=False, timeout=60)
    except (subprocess.TimeoutExpired, OSError) as exc:  # never mask the run's own result; the node's sweep covers it
        sys.stderr.write(f"[remote-test-node] cleanup of job {job} did not finish ({exc.__class__.__name__})\n")


def ship_commit(cfg: RemoteNodeSettings, sha: str, job: str) -> "str | None":
    """Refresh the node's mirror of the base branch, then send only what ``sha`` adds; None, or why not.

    ``send-pack``, not ``push``: a push would run this repo's pre-push hook, which calls this tool.
    """
    try:
        return _refresh_and_send(cfg, sha, job)
    except subprocess.TimeoutExpired:
        return "shipping the commit to the node timed out"
    except OSError as exc:
        return f"shipping the commit to the node could not start ({exc.__class__.__name__})"


def _refresh_and_send(cfg: RemoteNodeSettings, sha: str, job: str) -> "str | None":
    mirror = shlex.quote(f"{cfg.base}/mirror.git")
    refresh = f"git --git-dir={mirror} fetch --quiet --no-tags origin +refs/heads/main:refs/heads/main"
    if subprocess.run(ssh_argv(cfg) + [refresh], capture_output=True, check=False, timeout=600).returncode != 0:
        return "the node's mirror could not be refreshed (run --provision?)"
    ssh_cmd = shlex.join(node_ssh_options(cfg))
    dest = f"{cfg.user}@{cfg.host}:{cfg.base}/mirror.git"
    done = subprocess.run(
        ["git", "send-pack", "--quiet", dest, f"{sha}:refs/runs/{job}"],
        env=scrubbed_git_env({**os.environ, "GIT_SSH_COMMAND": ssh_cmd}),
        capture_output=True,
        check=False,
        timeout=1800,
    )
    return None if done.returncode == 0 else "the commit could not be pushed to the node"


def run_remote(cfg: RemoteNodeSettings, sha: str, cmd: list[str], timeout: int) -> int:
    job = uuid.uuid4().hex[:12]
    ssh = None
    old = {s: signal.signal(s, _raise_on_signal) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        why = ship_commit(cfg, sha, job)
        if why:
            return report_unavailable(why)
        remote = _script_command(
            "remote_job.sh", cfg.base, str(cfg.slots), str(timeout), str(timeout // 60 + 30), job, "--", *cmd
        )
        ssh = subprocess.Popen(ssh_argv(cfg) + [remote], stdin=subprocess.DEVNULL, start_new_session=True)
        return ssh.wait(timeout=timeout + 120)
    except subprocess.TimeoutExpired:
        # The command runs under the node's own `timeout`, which reports 124 through the session. No answer at all
        # within the limit means the session hung or the run never started (e.g. waiting for a slot): not a verdict.
        return report_unavailable("the remote session gave no result within the time limit")
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


def _finish(cfg: RemoteNodeSettings, job: str, ssh, old: dict) -> None:
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
    return _without_credentials(done.stdout.strip())


def _without_credentials(url: str) -> str:
    """The URL the node's mirror follows: no userinfo, no query, no fragment, so it holds and shows no secret.

    Userinfo is removed (not masked) so the URL still fetches, in every form: with a scheme, and schemeless
    (a colon in the text before the last ``@``, ahead of any ``/``, marks ``name:secret`` userinfo). That includes
    ``ssh://user@host/x``, which loses its username because the node holds no key, so it could not use it anyway.
    Query and fragment are dropped because a git remote needs neither and ``?token=`` would otherwise travel.
    The scp form ``git@host:path`` has no secret and passes through unchanged. A URL that cannot be read safely
    raises ``ValueError`` without the URL in the message.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        raise ValueError("the origin URL cannot be parsed") from None
    if "://" in url:
        host = parts.netloc.rsplit("@", 1)[-1]
        return urlunsplit((parts.scheme, host, parts.path, "", ""))
    head, at, tail = url.rpartition("@")
    if not at:
        return url
    colon, slash = head.find(":"), head.find("/")
    if colon != -1 and (slash == -1 or colon < slash):
        if not tail:
            raise ValueError("the origin URL cannot be read safely")
        return tail
    return url


def _pins() -> list[str]:
    """The uv and pip versions the node installs, from the registry (the node's own environment is not read)."""
    pins = [
        os.environ.get(n) or REGISTRY[n].default
        for n in ("AUTOBOT_TEST_NODE_UV_VERSION", "AUTOBOT_TEST_NODE_PIP_VERSION")
    ]
    for pin in pins:
        if not _VERSION.match(pin):
            raise ValueError(f"not a version number: {pin!r}")
    return pins


def _requirements_payload(root: Path) -> str:
    """The requirement files with their relative constraint lines dropped, then the shared constraints after a marker.

    Every form pip accepts (``-c X``, ``-cX``, ``-c=X``, ``--constraint X``, ``--constraint=X``) is dropped, because
    the constraints travel after the marker. A ``-r`` line would pull in a file the node does not have: reject it.
    """
    kept: list[str] = []
    for name in REQUIREMENTS:
        if not (root / name).is_file():
            continue
        for line in (root / name).read_text(encoding="utf-8").splitlines():
            if _INCLUDE_LINE.match(line):
                raise ValueError(f"{name}: a -r/--requirement line cannot be sent to the node: {line.strip()!r}")
            if not _CONSTRAINT_LINE.match(line):
                kept.append(line)
    constraints = (root / CONSTRAINTS).read_text(encoding="utf-8").splitlines()
    return "\n".join([*kept, CONSTRAINTS_MARKER, *constraints]) + "\n"


def provision(cfg: RemoteNodeSettings, root: Path) -> int:
    """Send provision.sh and the CI test requirements; safe to run again."""
    try:
        reqs = _requirements_payload(root)
        pins = _pins()
        script = _script_command("provision.sh", cfg.base, _origin_url(), python_floor(root), *pins)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"[remote-test-node] provision refused: {exc}", file=sys.stderr)
        return 1
    done = subprocess.run(
        ssh_argv(cfg) + [script],
        input=reqs.encode("utf-8"),
        check=False,
        timeout=1800,
    )
    return done.returncode


def report_unavailable(reason: str) -> int:
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
        return report_unavailable(f"not configured ({cfg})")
    if not args.provision and (not args.sha or not args.cmd):
        parser.error("--sha and a command are required")
    try:
        return _dispatch(cfg, args)
    except subprocess.TimeoutExpired:
        return report_unavailable("a step of the remote run timed out before the command started")
    except OSError as exc:  # ssh / git missing or not runnable
        return report_unavailable(f"the remote run could not start ({exc.__class__.__name__})")


def _dispatch(cfg: RemoteNodeSettings, args: argparse.Namespace) -> int:
    if args.provision:
        return provision(cfg, REPO_ROOT)
    reason = probe(cfg)
    if reason:
        return report_unavailable(reason)
    rc = run_remote(cfg, args.sha, args.cmd, args.timeout or cfg.timeout)
    return report_unavailable("the SSH session failed mid-run") if rc == 255 else rc


if __name__ == "__main__":
    sys.exit(main())
