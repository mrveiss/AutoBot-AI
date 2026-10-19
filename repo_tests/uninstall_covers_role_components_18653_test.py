# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The uninstaller covers what AutoBot deploys and removes no account it did not create (#18653).

`install.sh --uninstall` used to stop halfway (it deleted its own log directory and died on
the next write), knew about only part of what the playbooks install, and ran
`userdel -r autobot` unconditionally -- on a reused machine that account was the owner's own
uid-1000 login. It is now scripts/uninstall.sh. These pin:

- coverage: every systemd unit, sudoers file and apt source the Ansible roles deploy under a
  literal name is matched by the uninstaller's lists (a new role component cannot be missed);
- the install record: every key install.sh records is one the uninstaller reads;
- accounts: the real plan_users() selects an account only from the record or AutoBot's own
  admin marker, never by name;
- the log sits outside every path it removes.

**What these do not cover.** Names templated from facts or computed expressions resolve only
when a literal prefix is already covered; nothing here runs an uninstall on a real host -- a run on a host with a prior install is the end-to-end proof.
"""

from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml
from repo_tests._paths import repo_root

from tools.lint._comment_syntax import code_text
from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()
_UNINSTALL = _ROOT / "scripts" / "uninstall.sh"
_INSTALL = _ROOT / "install.sh"


def _array(name: str) -> list[str]:
    match = re.search(rf"^readonly {name}=\((.*?)\)", _UNINSTALL.read_text(encoding="utf-8"), re.S | re.M)
    assert match, f"readonly {name}=(...) not found in scripts/uninstall.sh"
    body = code_text(match.group(1), name="uninstall.sh", strip_trailing=True)
    return [tok.strip("\"'") for tok in body.split()]


def _role_files() -> list[Path]:
    files = [_ROOT / p for p in tracked_paths(_ROOT, "autobot-slm-backend/ansible/*.yml")]
    assert len(files) > 100, f"read {len(files)} ansible files -- the scan is broken"
    return files


def _docs() -> list[tuple[Path, object]]:
    out = []
    for path in _role_files():
        try:
            out.append((path, yaml.safe_load(path.read_text(encoding="utf-8"))))
        except yaml.YAMLError:
            continue
    assert len(out) > 0.9 * len(_role_files()), "too many ansible files failed to parse -- the scan would miss them"
    return out


def _variables(docs) -> dict[str, str]:
    """Plain-string values from role defaults, group_vars and play-level vars."""
    values: dict[str, str] = {}

    def take(mapping) -> None:
        for key, value in (mapping or {}).items():
            if isinstance(value, str) and "{{" not in value:
                values.setdefault(key, value)

    for path, doc in docs:
        if path.match("*/defaults/main.yml") or "group_vars" in path.parts:
            take(doc if isinstance(doc, dict) else {})
        elif isinstance(doc, list):
            for play in doc:
                if isinstance(play, dict) and isinstance(play.get("vars"), dict):
                    take(play["vars"])
    return values


def _walk(node):
    """(dest, loop items) for every module call with a `dest:`."""
    if isinstance(node, dict):
        loop = node.get("loop") or node.get("with_items")
        for value in node.values():
            if isinstance(value, dict) and isinstance(value.get("dest"), str):
                yield value["dest"], loop if isinstance(loop, list) else None
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _resolve(dest: str, variables: dict[str, str]) -> str:
    dest = re.sub(
        r"\{\{\s*(\w+)\s*\|\s*default\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}", lambda m: variables.get(m[1], m[2]), dest
    )
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: variables.get(m[1], m[0]), dest)


def _deployed(prefixes: tuple[str, ...]) -> tuple[set[str], set[str]]:
    """Destinations under `prefixes` the roles write: (resolved, still templated)."""
    docs = _docs()
    variables = _variables(docs)
    resolved, open_ = set(), set()
    for _, doc in docs:
        for dest, loop in _walk(doc):
            dest = dest.strip()
            if not dest.startswith(prefixes):
                continue
            for item in loop if (loop and "{{ item }}" in dest) else [None]:
                name = _resolve(dest.replace("{{ item }}", str(item)) if item is not None else dest, variables)
                (open_ if "{{" in name else resolved).add(name)
    return resolved, open_


def _covered(path: str, exact: set[str], globs: list[str]) -> bool:
    if path in exact or any(fnmatch.fnmatch(path, g) for g in globs):
        return True
    head = path.split("{{", 1)[0]  # a templated tail after a literal prefix a glob already covers
    return "{{" in path and any(g.endswith("*") and head.startswith(g[:-1]) and len(head) >= len(g) - 1 for g in globs)


def test_every_deployed_systemd_unit_is_removed_or_kept() -> None:
    resolved, open_ = _deployed(("/etc/systemd/system/",))
    assert len(resolved) >= 25, f"read {len(resolved)} deployed units -- the scan is broken"
    unit_dir = "/etc/systemd/system/"
    exact = {unit_dir + u for u in _array("UNITS") + _array("KEPT_UNITS")} | set(_array("UNIT_DROPINS"))
    globs = [unit_dir + g for g in _array("UNIT_GLOBS")]
    missed = sorted(d for d in resolved | open_ if not _covered(d, exact, globs))
    assert not missed, f"roles deploy units scripts/uninstall.sh neither removes nor keeps: {missed}"


def test_every_deployed_sudoers_file_is_removed() -> None:
    resolved, open_ = _deployed(("/etc/sudoers.d/",))
    assert resolved, "no sudoers destinations read -- the scan is broken"
    exact = {"/etc/sudoers.d/" + s for s in _array("SUDOERS")} | {
        "/etc/sudoers.d/autobot"
    }  # install.sh's own, via the record
    missed = sorted(d for d in resolved | open_ if not _covered(d, exact, []))
    assert not missed, f"roles deploy sudoers files scripts/uninstall.sh never removes: {missed}"


def test_every_deployed_config_file_is_removed() -> None:
    prefixes = (
        "/etc/logrotate.d/",
        "/etc/rsyslog.d/",
        "/etc/dnsmasq.d/",
        "/etc/nginx/sites-available/",
        "/etc/nginx/sites-enabled/",
    )
    resolved, open_ = _deployed(prefixes)
    assert len(resolved) >= 8, f"read {len(resolved)} config destinations -- the scan is broken"
    exact = (
        set(_array("PATHS")) | set(_array("DATA_PATHS")) | set(_array("SHARED_PATHS")) | set(_array("POSTGRES_PATHS"))
    )
    missed = sorted(d for d in resolved | open_ if not _covered(d, exact, _array("PATH_GLOBS")))
    assert not missed, f"roles deploy config files scripts/uninstall.sh never removes: {missed}"


def test_every_apt_source_a_role_adds_is_removed_or_kept() -> None:
    sources = _array("APT_SOURCES") + _array("KEPT_APT_SOURCES") + _array("POSTGRES_APT_SOURCES")
    added = set()
    for path in _role_files():
        added |= set(re.findall(r"""apt_repo_filename:\s*["']([a-z0-9-]+)["']""", path.read_text(encoding="utf-8")))
    assert added, "no apt_repo_filename read -- the scan is broken"
    missed = sorted(a for a in added if not any(a.startswith(s) for s in sources))
    assert not missed, f"roles add apt sources scripts/uninstall.sh neither removes nor keeps: {missed}"


def test_every_recorded_key_is_read_by_the_uninstaller() -> None:
    keys = set(re.findall(r"record_install (\w+) ", _INSTALL.read_text(encoding="utf-8")))
    assert {"created_user", "package", "apt_source"} <= keys, f"install.sh records only {sorted(keys)}"
    text = _UNINSTALL.read_text(encoding="utf-8")
    unread = sorted(k for k in keys if f"record_values {k}" not in text)
    assert not unread, f"install.sh records keys the uninstaller never reads: {unread}"


def test_the_log_lives_outside_everything_it_removes() -> None:
    log = re.search(r'^readonly LOG_FILE="([^"$]+)', _UNINSTALL.read_text(encoding="utf-8"), re.M).group(1)
    removed = [p for p in _array("PATHS") + _array("DATA_PATHS") + _array("SHARED_PATHS") if not p.startswith("${")] + [
        "/opt/autobot"
    ]
    assert not any(log.startswith(p.rstrip("/") + "/") for p in removed), f"{log} is inside a removed path"


def _plan_users(record: str | None, admin_gecos: str) -> list[str]:
    text = _UNINSTALL.read_text(encoding="utf-8")
    funcs = "\n".join(
        re.search(rf"^{n}\(\) \{{.*?^\}}", text, re.S | re.M).group(0) for n in ("record_values", "plan_users")
    )
    markers = re.search(r"^readonly ADMIN_MARKERS=.*$", text, re.M).group(0)
    with tempfile.TemporaryDirectory() as tmp:
        rec = Path(tmp) / "install-record"
        if record is not None:
            rec.write_text(record, encoding="utf-8")
        script = f"""set -euo pipefail
INSTALL_RECORD={rec}
ADMIN_ACCOUNT=autobot_admin
{markers}
id() {{ case "$1" in autobot|autobot_admin) return 0 ;; *) return 1 ;; esac; }}
getent() {{ echo "autobot_admin:x:1001:1001:{admin_gecos}:/home/autobot_admin:/bin/bash"; }}
{funcs}
plan_users
"""
        out = subprocess.run([shutil.which("bash") or "bash", "-c", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return out.stdout.split()


def test_no_account_is_removed_without_a_record_or_the_marker() -> None:
    """The defect: `autobot` existed (the owner's uid-1000 login) and would have been userdel'd."""
    assert _plan_users(None, "Martins") == []
    assert _plan_users("package=nodejs\n", "Someone Else") == []


def test_an_account_the_installer_created_is_removed() -> None:
    assert _plan_users("created_user=autobot\n", "Someone Else") == ["autobot"]


def test_autobots_admin_account_is_removed_by_its_marker() -> None:
    assert _plan_users(None, "Emergency Admin User (fallback access)") == ["autobot_admin"]
    assert _plan_users(None, "AutoBot Backup Admin (Emergency Access)") == ["autobot_admin"]


def test_no_system_wide_autoremove() -> None:
    code = code_text(_UNINSTALL)
    assert "autoremove" not in code, "a system-wide apt autoremove removes packages that are not AutoBot's"


def test_the_exit_trap_deletes_only_a_temp_copy() -> None:
    text = _UNINSTALL.read_text(encoding="utf-8")
    assert re.search(r"^trap '\[\[ \"\$\{BASH_SOURCE\[0\]\}\" == \$\{COPY_PATTERN\} \]\] && rm", text, re.M)
    assert 'readonly COPY_PATTERN="/var/tmp/autobot-uninstall.*.sh"' in text


def _postgres(stubs: str) -> int:
    text = _UNINSTALL.read_text(encoding="utf-8")
    funcs = "\n".join(
        re.search(rf"^{n}\(\) \{{.*?^\}}", text, re.S | re.M).group(0)
        for n in ("psql_on", "cluster_is_autobots", "postgres_holds_only_autobot")
    )
    script = f"""set -euo pipefail
DATABASES=(slm slm_users autobot_users)
DB_ROLES=(slm_app)
{stubs}
{funcs}
postgres_holds_only_autobot && echo REMOVE || echo KEEP
"""
    with tempfile.TemporaryDirectory() as tmp:
        out = subprocess.run(
            [shutil.which("bash") or "bash", "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
            env={"PATH": tmp},  # only the empty temp dir: a host's real pg_lsclusters/psql must never answer
        )
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


_ONLY_AUTOBOT = r"""
pg_lsclusters() { echo "16 main 5432 online postgres /var/lib/postgresql/16/main x"; }
psql() { :; }
sudo() { shift 2; case "$*" in *pg_database*) printf 'postgres\ntemplate0\ntemplate1\nslm\nslm_users\n' ;; *count*) echo 0 ;; *pg_roles*) printf 'postgres\nslm_app\n' ;; esac; }
"""


def test_postgres_holding_only_autobot_is_removed() -> None:
    assert _postgres(_ONLY_AUTOBOT) == "REMOVE"


def test_postgres_is_kept_whenever_it_cannot_be_fully_inspected() -> None:
    """01's HIGH: an uninspected PostgreSQL read as "only AutoBot's" and was rm -rf'd."""
    no_lsclusters = "psql() { :; }"
    failing = _ONLY_AUTOBOT.replace("pg_lsclusters() { echo", "pg_lsclusters() { return 3; echo")
    no_cluster = _ONLY_AUTOBOT.replace(
        'pg_lsclusters() { echo "16 main 5432 online postgres /var/lib/postgresql/16/main x"; }',
        "pg_lsclusters() { :; }",
    )
    offline = _ONLY_AUTOBOT.replace("5432 online", "5432 down")
    silent = _ONLY_AUTOBOT.replace("sudo() { shift 2;", "sudo() { return 2; shift 2;")
    for stubs in (no_lsclusters, failing, no_cluster, offline, silent):
        assert stubs != _ONLY_AUTOBOT, "the replacement matched nothing -- this case would test nothing"
        assert _postgres(stubs) == "KEEP", stubs


def test_postgres_with_anything_else_in_it_is_kept() -> None:
    other_db = _ONLY_AUTOBOT.replace(r"slm\nslm_users", r"slm\nshop")
    tables_in_postgres = _ONLY_AUTOBOT.replace("*count*) echo 0", "*count*) echo 4")
    other_role = _ONLY_AUTOBOT.replace(r"postgres\nslm_app", r"postgres\nslm_app\nanalyst")
    for stubs in (other_db, tables_in_postgres, other_role):
        assert stubs != _ONLY_AUTOBOT, "the replacement matched nothing -- this case would test nothing"
        assert _postgres(stubs) == "KEEP", stubs


def test_every_opt_autobot_child_the_roles_write_is_classified() -> None:
    """01's HIGH: a default uninstall rm -rf'd all of /opt/autobot, and the roles keep data there."""
    data, code_dirs = set(_array("OPT_DATA")), set(_array("OPT_CODE"))
    assert not data & code_dirs, f"classified as both data and code: {sorted(data & code_dirs)}"
    children = set()
    pattern = re.compile(r"/opt/autobot/([A-Za-z0-9_][A-Za-z0-9_.-]*[A-Za-z0-9_]|\.env)")
    # The roles AND the code that writes under /opt/autobot at runtime (snapshots, db-backups).
    code = [
        _ROOT / p
        for p in tracked_paths(_ROOT, "autobot-backend/*.py", "autobot_shared/*.py", "autobot-slm-backend/*.py")
        if not p.endswith("_test.py") and "/tests/" not in p
    ]
    for path in _role_files() + code:
        children |= set(pattern.findall(path.read_text(encoding="utf-8")))
    assert len(children) >= 25, f"read {len(children)} /opt/autobot children -- the scan is broken"
    unclassified = sorted(children - data - code_dirs)
    assert not unclassified, f"/opt/autobot children neither OPT_DATA nor OPT_CODE: {unclassified}"
    assert {"backups", "data", "models", ".env"} <= data


def _plan_opt_code(purge_data: bool) -> set[str]:
    text = _UNINSTALL.read_text(encoding="utf-8")
    func = "\n".join(
        re.search(rf"^{name}\(\) \{{.*?^\}}", text, re.S | re.M).group(0)
        for name in ("existing", "opt_children", "nested_data_in", "plan_opt_code")
    )
    func += "\n" + re.search(r"^is_code_child\(\) \{.*\}$", text, re.M).group(0)
    opt_data = re.search(r"^readonly OPT_DATA=.*$", text, re.M).group(0)
    opt_data += "\n" + re.search(r"^readonly OPT_CODE=\(.*?\)$", text, re.S | re.M).group(0)
    opt_data += "\n" + re.search(r"^readonly OPT_NESTED_DATA=\(.*?\)$", text, re.S | re.M).group(0)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "autobot"
        for child in (
            "backups",
            "data",
            "models",
            ".env",
            "venv",
            "autobot-backend",
            "code_source",
            "db-backups",
            "snapshots",
            "owners-own-folder",
            ".ansible",
        ):
            (base / child).mkdir(parents=True) if child != ".env" else None
        (base / ".env").write_text("X=1", encoding="utf-8")
        script = f"""set -euo pipefail
AUTOBOT_BASE={base}
PURGE_DATA={'true' if purge_data else 'false'}
{opt_data}
{func}
plan_opt_code
"""
        out = subprocess.run([shutil.which("bash") or "bash", "-c", script], capture_output=True, text=True, timeout=30)
        assert out.returncode == 0, out.stderr
        return {Path(line).name for line in out.stdout.split()}


def test_a_default_uninstall_removes_only_code_under_opt_autobot() -> None:
    """An ALLOW-list (01, round 3): only OPT_CODE goes -- snapshots, db-backups and a folder
    of the owner's are kept even though nothing lists them."""
    assert _plan_opt_code(purge_data=False) == {"venv", "autobot-backend", "code_source"}


def test_purge_data_takes_the_whole_tree_through_data_paths_instead() -> None:
    assert _plan_opt_code(purge_data=True) == set()
    assert _array("DATA_PATHS")[0] == "${AUTOBOT_BASE}"


_DATA_LIKE = re.compile(r"/(data|chromadb|db|\.env|[^/]*\.sqlite[0-9]*|[^/]*\.db)(/|$)")


def _is_secret(sub: str) -> bool:
    name = sub.rsplit("/", 1)[-1]
    return name == ".env" or name.startswith(".env.") or name.endswith(".env")


def _nested_covered(sub: str, nested: list[str]) -> bool:
    """A secret is kept by rule (nested_data_in finds every .env); other data must be listed."""
    if _is_secret(sub):
        return True
    return any(sub == n or sub.startswith(n + "/") or n.startswith(sub + "/") for n in nested)


def _templated_data_paths(code_dirs: set[str]) -> set[str]:
    """01's round 5: roles name code dirs through {{ *_install_dir }} -- resolve them."""
    variables = _variables(_docs())
    templated = re.compile(r"\{\{\s*(\w+_(?:install_dir|dir|home|path))\s*\}\}/([A-Za-z0-9_./-]+)")
    found = set()
    for path in _role_files():
        for var, rest in templated.findall(path.read_text(encoding="utf-8")):
            base = variables.get(var, "")
            if not base.startswith("/opt/autobot/"):
                continue
            sub = f"{base.removeprefix('/opt/autobot/')}/{rest.rstrip('.,;:)')}"
            if sub.split("/", 1)[0] in code_dirs and (_DATA_LIKE.search("/" + sub) or _is_secret(sub)):
                found.add(sub)
    return found


def test_install_dir_variables_resolve_to_code_dirs() -> None:
    """The resolution is live: ai/tts/npu .env files (01's round 5) are seen through their vars."""
    found = _templated_data_paths(set(_array("OPT_CODE")))
    assert {"autobot-ai-stack/.env", "autobot-tts-worker/.env"} <= found, sorted(found)


def test_every_data_path_inside_a_code_dir_is_preserved() -> None:
    """01's round 4: ChromaDB lived at /opt/autobot/autobot-db-stack/chromadb/data, a code dir."""
    code_dirs, nested = set(_array("OPT_CODE")), _array("OPT_NESTED_DATA")
    alternation = "|".join(re.escape(c) for c in sorted(code_dirs))
    pattern = re.compile(rf"/opt/autobot/((?:{alternation})/[A-Za-z0-9_./-]+)")
    code = [
        _ROOT / p
        for p in tracked_paths(_ROOT, "autobot-backend/*.py", "autobot_shared/*.py", "autobot-slm-backend/*.py")
        if not p.endswith("_test.py") and "/tests/" not in p
    ]
    found = set()
    for path in _role_files() + code:
        for sub in pattern.findall(path.read_text(encoding="utf-8")):
            sub = sub.rstrip(".,;:)")
            if _DATA_LIKE.search("/" + sub):
                found.add(sub)
    found |= _templated_data_paths(code_dirs)
    assert found, "no data-like path under a code dir read -- the scan is broken"
    uncovered = sorted(s for s in found if not _nested_covered(s, nested))
    assert not uncovered, f"data inside OPT_CODE dirs that a default uninstall would delete: {uncovered}"


def test_a_code_dir_loses_its_code_and_keeps_the_data_inside() -> None:
    text = _UNINSTALL.read_text(encoding="utf-8")
    funcs = "\n".join(
        re.search(rf"^{n}\(\) \{{.*?^\}}", text, re.S | re.M).group(0)
        for n in ("existing", "nested_data_in", "remove_code_keeping_data")
    )
    nested = re.search(r"^readonly OPT_NESTED_DATA=\(.*?\)$", text, re.S | re.M).group(0)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "autobot"
        for rel in (
            "autobot-db-stack/chromadb/data/chroma.sqlite3",
            "autobot-db-stack/bin/run.sh",
            "autobot-db-stack/.env",
            "autobot-backend/data/kb.json",
            "autobot-backend/app/main.py",
            "autobot-ai-stack/.env",
            "autobot-ai-stack/conf/extra.env",
            "autobot-ai-stack/src/app.py",
        ):
            (base / rel).parent.mkdir(parents=True, exist_ok=True)
            (base / rel).write_text("x", encoding="utf-8")
        script = f"""set -euo pipefail
AUTOBOT_BASE={base}
log() {{ echo "$*"; }}
{nested}
{funcs}
remove_code_keeping_data {base}/autobot-db-stack
remove_code_keeping_data {base}/autobot-backend
remove_code_keeping_data {base}/autobot-ai-stack
"""
        out = subprocess.run([shutil.which("bash") or "bash", "-c", script], capture_output=True, text=True, timeout=30)
        assert out.returncode == 0, out.stderr
        assert (base / "autobot-db-stack/chromadb/data/chroma.sqlite3").exists(), "the ChromaDB store was deleted"
        assert (base / "autobot-db-stack/.env").exists() and (base / "autobot-backend/data/kb.json").exists()
        assert (
            not (base / "autobot-db-stack/bin").exists() and not (base / "autobot-backend/app").exists()
        ), "code stayed"
        # 01, round 5: an UNLISTED .env is a secret, never code -- kept by rule
        assert (base / "autobot-ai-stack/.env").exists() and (base / "autobot-ai-stack/conf/extra.env").exists()
        assert not (base / "autobot-ai-stack/src").exists()
        assert "KEPT" in out.stdout
