# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Render-and-execute harness for the nightly Redis backup template (#17932).

Split out of ``redis_backup_template_renders_runnable_17932_test.py`` when that file
reached the 600-line ceiling (#5060). The seam is HARNESS from ASSERTIONS: this module
renders the two templates and executes the result against a staged fake host, and holds
no assertion about what the script should do. Two guards import it --
``redis_backup_template_renders_runnable_17932_test`` (rendering and file handling) and
``redis_backup_sends_its_credential_17932_test`` (the client credential) -- and sharing
the harness rather than duplicating it is what keeps them testing one script instead of
two renders that have quietly diverged.

Everything here is executable rather than textual, deliberately. The defect this file
exists under was CREATED by rendering -- the template source was correct -- so an
assertion over the ``.j2`` text would have passed throughout the 125 days the live
fleet produced no archive.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import jinja2
import pytest
from repo_tests._paths import repo_root

TEMPLATE = repo_root() / "autobot-slm-backend" / "ansible" / "roles" / "redis" / "templates" / "redis-backup.sh.j2"

#: The role variables this template substitutes. Kept explicit rather than loaded from
#: `vars/main.yml` so that a variable renamed in one place and not the other raises an
#: undefined-name error here instead of silently rendering an empty string.
RENDER_VARS = {
    "redis_port": 6379,
    "redis_backup_retention_days": 30,
    # #17932 review: the PATH of the credential file, never the credential. See
    # `test_no_credential_is_substituted_into_the_backup_script`.
    "redis_backup_env_file": "/etc/autobot/redis-backup.env",
}

#: The credential template deployed beside the script, on the provisioning path only.
ENV_TEMPLATE = TEMPLATE.with_name("redis-backup.env.j2")

#: A fixture credential written into a tmp_path env file by the tests. Not a secret, and
#: deliberately distinctive so an assertion that it is ABSENT from the rendered script
#: cannot pass by matching nothing -- which is also why it reads as one to detect-secrets.
FIXTURE_PASSWORD = "fixture-redis-password-7a1f"  # pragma: allowlist secret
FIXTURE_USERNAME = "default"

#: Reach floor. A render that yields a stub is not evidence about a backup script.
#: Deliberately well below both the pre-fix script (51 lines) and the current one,
#: so a defective-but-whole script still reaches the assertions and FAILS on them
#: rather than erroring in the fixture -- a fixture error is a worse signal.
MIN_RENDERED_LINES = 30

_BASH = shutil.which("bash")
_TAR = shutil.which("tar")


def render(*, persistence: bool = True, trim_blocks: bool = True) -> str:
    """Render the template the way ``ansible.builtin.template`` would.

    ``trim_blocks`` is a parameter rather than a constant because the differential
    check below needs both settings; everything else matches the module's defaults.
    """
    env = jinja2.Environment(  # noqa: S701 - shell output, not markup; repo-owned source
        autoescape=False,
        trim_blocks=trim_blocks,
        lstrip_blocks=False,
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )
    source = TEMPLATE.read_text(encoding="utf-8")
    assert source.strip(), f"{TEMPLATE} is empty -- nothing was measured"
    return env.from_string(source).render(redis_persistence=persistence, **RENDER_VARS)


def _command_lines(rendered: str) -> list[str]:
    """Non-blank, non-comment lines, stripped -- what the shell will actually execute."""
    out = []
    for raw in rendered.splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


# End-to-end: the rendered script is executed against a fake Redis host.
#
# This is what a text assertion cannot do -- it answers "was an archive produced", which
# is the question the live fleet answered `no` to for 125 days while its log said `yes`.
# --------------------------------------------------------------------------------------

_RUNNABLE = pytest.mark.skipif(
    _BASH is None or _TAR is None,
    reason="bash and tar are required to execute the rendered script; neither was assumed",
)

#: stdout and stderr are merged because the cron entry merges them
#: (`redis-backup.sh >> ...log 2>&1`), so the assertions below are about the file an
#: operator actually opens, not about two streams nobody sees separately.
_MERGED = subprocess.STDOUT

_OLD_ARCHIVE_AGE_SECONDS = 40 * 24 * 3600

#: The BGSAVE wait budget the harness gives the script, well under the 120s subprocess
#: timeout. The default is 300s, which a stuck run would spend before anything is learnt.
_HARNESS_BGSAVE_TIMEOUT_SECONDS = 6


def _retarget(script: str, backup_dir: Path, data_dir: Path, env_file: Path | None = None) -> str:
    """Point the script's two hardcoded directories at tmpdirs.

    Each substitution must match exactly once: if either variable is renamed, this
    raises instead of running a script that still writes to /var.
    """
    script, backups = re.subn(r"^BACKUP_DIR=.*$", f'BACKUP_DIR="{backup_dir}"', script, count=1, flags=re.M)
    script, data = re.subn(r"^REDIS_DATA_DIR=.*$", f'REDIS_DATA_DIR="{data_dir}"', script, count=1, flags=re.M)
    assert backups == 1, "BACKUP_DIR assignment not found -- the harness would test nothing"
    assert data == 1, "REDIS_DATA_DIR assignment not found -- the harness would test nothing"
    if env_file is not None:
        script, creds = re.subn(
            r"^REDIS_BACKUP_ENV_FILE=.*$", f'REDIS_BACKUP_ENV_FILE="{env_file}"', script, count=1, flags=re.M
        )
        assert creds == 1, "REDIS_BACKUP_ENV_FILE assignment not found -- the auth path would be untested"
    return script


def _fake_redis_cli(bin_dir: Path, *, lastsave: str = "advancing") -> None:
    """A redis-cli stub. `lastsave="advancing"` advances once so the wait loop ends.

    `lastsave="noauth"` returns the server's error TEXT on stdout and exits 0, which is
    the behaviour this script has to survive: without `-e` redis-cli reports a server
    error reply that way, so the string would otherwise be compared against itself in
    the wait loop forever (#17932 review).

    Every invocation appends its argv and the REDISCLI_AUTH it was given to two logs, so
    a test can assert what the script actually sent rather than what its source says.
    """
    state = bin_dir / "lastsave.seen"
    reply = (
        f'if [ -e "{state}" ]; then echo 2000; else : > "{state}"; echo 1000; fi'
        if lastsave == "advancing"
        else 'echo "NOAUTH Authentication required."'
    )
    (bin_dir / "redis-cli").write_text(
        "#!/bin/bash\n"
        f'printf \'%s\\n\' "$*" >> "{bin_dir / "argv.log"}"\n'
        f'printf \'%s\\n\' "${{REDISCLI_AUTH-<unset>}}" >> "{bin_dir / "auth.log"}"\n'
        'for arg in "$@"; do\n'
        '  if [ "$arg" = "LASTSAVE" ]; then\n'
        f"    {reply}\n"
        "    exit 0\n"
        "  fi\n"
        "done\n"
        'echo "Background saving started"\n',
        encoding="utf-8",
    )
    (bin_dir / "redis-cli").chmod(0o755)


def _stage(tmp_path: Path, *, aof: str, lastsave: str = "advancing") -> tuple[Path, Path, Path]:
    """A data dir in the requested AOF layout, an empty backup dir, and a fake bin dir."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "dump.rdb").write_text("REDIS-fake-rdb", encoding="utf-8")
    if aof == "appendonlydir":
        aof_dir = data_dir / "appendonlydir"
        aof_dir.mkdir()
        (aof_dir / "appendonly.aof.manifest").write_text("file appendonly.aof.1.base.rdb seq 1 type b\n", "utf-8")
        (aof_dir / "appendonly.aof.1.incr.aof").write_text("*1\r\n$4\r\nPING\r\n", encoding="utf-8")
    elif aof == "appendonly.aof":
        (data_dir / "appendonly.aof").write_text("*1\r\n$4\r\nPING\r\n", encoding="utf-8")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_redis_cli(bin_dir, lastsave=lastsave)
    return data_dir, backup_dir, bin_dir


def _run(
    tmp_path: Path,
    *,
    aof: str,
    break_tar: bool = False,
    env_file: Path | None = None,
    lastsave: str = "advancing",
) -> tuple[int, str, Path]:
    """Execute the rendered script against the staged fake host; return rc, log, backups."""
    data_dir, backup_dir, bin_dir = _stage(tmp_path, aof=aof, lastsave=lastsave)
    if break_tar:
        (bin_dir / "tar").write_text('#!/bin/bash\necho "tar: fake failure" >&2\nexit 2\n', encoding="utf-8")
        (bin_dir / "tar").chmod(0o755)
    path = tmp_path / "redis-backup.sh"
    path.write_text(_retarget(render(persistence=aof != "none"), backup_dir, data_dir, env_file), encoding="utf-8")
    done = subprocess.run(  # noqa: S603 - fixed argv, tmpdir-scoped script, redis-cli shadowed
        [str(_BASH), str(path)],
        stdout=subprocess.PIPE,
        stderr=_MERGED,
        text=True,
        timeout=120,
        env={
            "PATH": f"{bin_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(tmp_path),
            # The script's own override point, held short so a run that WAITS instead of
            # failing is observable inside the subprocess timeout rather than killing it.
            # A killed subprocess reports nothing, which is the one outcome a guard about
            # silent failure must not produce.
            "REDIS_BACKUP_BGSAVE_TIMEOUT_SECONDS": str(_HARNESS_BGSAVE_TIMEOUT_SECONDS),
        },
    )
    return done.returncode, done.stdout, backup_dir


def _archives(backup_dir: Path) -> list[Path]:
    return sorted(backup_dir.glob("redis-backup-*.tar.gz"))


def render_env(*, password: str = "", username: str = "") -> str:
    """Render the credential file the way `ansible.builtin.template` would."""
    env = jinja2.Environment(  # noqa: S701 - env-file output, not markup; repo-owned source
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=False,
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )
    source = ENV_TEMPLATE.read_text(encoding="utf-8")
    assert source.strip(), f"{ENV_TEMPLATE} is empty -- nothing was measured"
    return env.from_string(source).render(redis_client_password=password, redis_username=username)


def _env_file(tmp_path: Path, *, password: str, username: str) -> Path:
    path = tmp_path / "redis-backup.env"
    path.write_text(render_env(password=password, username=username), encoding="utf-8")
    return path
