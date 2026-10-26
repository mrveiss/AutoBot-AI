# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM admin password has one name, one reader per layer, and no default (#19318).

Three ansible roles fell back to a guessable literal when the variable was unset, while the
backend treated unset as "do not seed", and the installer exported a second name the backend
never read. Now:

- ``SLM_ADMIN_PASSWORD`` is the one name (registered in ``autobot_shared/env_registry_npu.py``).
  ``AUTOBOT_SLM_ADMIN_PASSWORD`` survives only as a deprecated alias where it was a documented
  operator interface.
- Ansible resolves it in ONE place, ``_shared/tasks/read_slm_admin_password.yml``; every
  playbook or role that logs in with it includes that reader.
- Nothing supplies a literal fallback for it, in Jinja, shell, or Python.

The sweep reads the file types that can hold the password: ``.py``, ``.sh``, ``.j2``,
``.yml``/``.yaml`` (Ansible, compose, workflows), env files and Dockerfiles. ``.cfg``,
``.ini`` and ``.toml`` are left out on purpose: on 2026-10-23 none of the 12 tracked ones
named SLM_ADMIN_PASSWORD, its alias, AUTOBOT_ADMIN_PASSWORD or admin_password, and the python
path filter does not cover those trees (#15900). If one ever needs to hold it, widen the
filter to cover it and add the suffix here; do not add a record entry.

Test files are out of the sweep: they plant the old shapes on purpose (see
``compose_exposure_and_credentials_17500_test.py``). The detectors are proven on planted
copies below instead.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_CANONICAL = "SLM_ADMIN_PASSWORD"  # pragma: allowlist secret
_ALIAS = "AUTOBOT_" + _CANONICAL
_READER = "autobot-slm-backend/ansible/_shared/tasks/read_slm_admin_password.yml"
_SEED_READER = "autobot-slm-backend/ansible/_shared/tasks/read_admin_seed_password.yml"
_PY_READER = "autobot-slm-backend/services/admin_seed_password.py"
_SELF = "repo_tests/slm_admin_password_one_home_19318_test.py"

#: Where the deprecated alias may still appear, and why.
_ALIAS_HOMES = {
    "install.sh": "the documented installer override (#7057); maps onto the canonical name with a warning",
    _READER: "setup-internal-ca.yml documented reading it from the environment; warns",
    "autobot_shared/env_registry_npu.py": "the registry entry names it as the deprecated alias",
}
#: Upper-case names containing SLM_ADMIN_PASS that are not a second name for the variable.
_NOT_A_SECOND_NAME = {
    _CANONICAL + "_FILE": "a PATH to the value (hardened compose secret); seeds a fresh install only (#19368)",
}
#: Files that read the password from the environment or from slm-secrets.env, and why.
_READERS = {
    _READER: "the one ansible reader",
    _PY_READER: "the SLM's one reader of SLM_ADMIN_PASSWORD and its _FILE (#19368)",
    "autobot-slm-backend/ansible/roles/slm_manager/tasks/main.yml": "the store's owner reads back what it wrote",
    "autobot-slm-backend/scripts/autobot-admin.py": "reset-password rewrites the store's line",
    "install.sh": "the installer writes the store and preserves it on reinstall",
    "docker-compose.yml": "compose passes it to the container, required with :? (#17793)",
    _SEED_READER: "the one read of the main-app admin seed, which falls back to this password (#19370)",
}

_NAMES = re.compile(r"\b[A-Z0-9_]*SLM_ADMIN_PASS[A-Z0-9_]*\b")
_JINJA = re.compile(r"\{\{.*?\}\}", re.S)
_JINJA_LITERAL_DEFAULT = re.compile(r"default\(\s*(['\"])[^'\"]+\1")
_SHELL_DEFAULT = re.compile(r"\$\{(?:AUTOBOT_)?SLM_ADMIN_PASSWORD:?[-=][^}$]+\}")
_PY_DEFAULT = re.compile(
    r"(?:getenv|environ\.get|\benv)\(\s*['\"](?:AUTOBOT_)?SLM_ADMIN_PASSWORD['\"]\s*,\s*['\"][^'\"]+['\"]"
)
_LITERAL_ASSIGNMENT = re.compile(r"(?<![\w$])(?:AUTOBOT_)?SLM_ADMIN_PASSWORD=['\"]?[A-Za-z0-9]")
_READ = re.compile(
    r"lookup\(\s*['\"]env['\"]\s*,\s*['\"](?:AUTOBOT_)?SLM_ADMIN_PASSWORD"
    r"|\^SLM_ADMIN_PASSWORD="
    r"|\$\{(?:AUTOBOT_)?SLM_ADMIN_PASSWORD\b"
    r"|(?:getenv|environ\.get|environ\[|\benv)\(?\s*['\"](?:AUTOBOT_)?SLM_ADMIN_PASSWORD['\"]"
)
_LOGIN = re.compile(r"password:\s*['\"]\{\{\s*slm_admin_password\b")
_SUFFIXES = ("*.py", "*.sh", "*.yml", "*.yaml", "*.j2", "*.env*", "Dockerfile*")


def _code_files(root: Path) -> list[str]:
    """Tracked code and config files, test files excluded (they plant the old shapes)."""
    try:
        return sorted(tracked_paths(root, *_SUFFIXES, exclude=("*_test.py", "test_*.py", "**/test_*.py")))
    except EmptyEnumeration:
        return []  # an empty tree: the reach's min_fraction raises the typed refusal instead


def _suffix_matched_count(root: Path) -> int:
    """The sweep's own population, counted INDEPENDENTLY: every tracked file, filtered in Python.

    ``_code_files`` enumerates with ``tracked_paths``'s glob patterns; matching names here with
    ``fnmatch`` instead keeps this denominator from failing in lockstep with the glob it checks
    (the shape of ``hooks_path_override_15961_test._suffix_matched_count``).
    """
    try:
        listed = tracked_paths(root)
    except EmptyEnumeration:
        return 0
    tests = ("*_test.py", "test_*.py")
    return sum(
        1
        for rel in listed
        if any(fnmatch.fnmatch(rel.rsplit("/", 1)[-1], p) for p in _SUFFIXES)
        and not any(fnmatch.fnmatch(rel.rsplit("/", 1)[-1], t) for t in tests)
    )


#: Relative reach against its own population: the glob sweep must reach nearly all of what the
#: independent count finds; 0.95 fires once it loses a twentieth of it.
REACH = declare(
    "slm-admin-password-one-home-sweep",
    discover=_code_files,
    min_fraction=0.95,
    reference=_suffix_matched_count,
    what="tracked code/config files searched for the SLM admin password",
)


def literal_defaults(text: str) -> list[str]:
    """Every literal fallback given to the SLM admin password in ``text``."""
    hits = [
        m.group(0)
        for block in _JINJA.findall(text)
        if re.search(r"(?i)slm_admin_password", block)
        for m in _JINJA_LITERAL_DEFAULT.finditer(block)
    ]
    hits += _SHELL_DEFAULT.findall(text) + _PY_DEFAULT.findall(text)
    return hits + [m.group(0) for m in _LITERAL_ASSIGNMENT.finditer(text)]


def second_names(text: str, rel: str) -> set[str]:
    """Upper-case names for the variable other than the canonical one, outside their allowed homes."""
    found = set(_NAMES.findall(text)) - {_CANONICAL} - set(_NOT_A_SECOND_NAME)
    return found - {_ALIAS} if rel in _ALIAS_HOMES else found


def reads(text: str) -> bool:
    """Whether ``text`` reads the password from the environment or from slm-secrets.env."""
    return bool(_READ.search(text))


def logs_in_without_reader(text: str) -> bool:
    """A playbook/role that sends slm_admin_password without including the one reader."""
    return bool(_LOGIN.search(text)) and "read_slm_admin_password.yml" not in text


def _sweep(check) -> list[str]:
    """Apply ``check(text, rel)`` to every swept file; returns ``rel: finding`` lines."""
    root = repo_root()
    out = []
    for rel in REACH.examined(root):
        if rel == _SELF:
            continue
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        out += [f"{rel}: {f}" for f in check(text, rel)]
    return out


def test_no_literal_default_for_the_admin_password() -> None:
    hits = _sweep(lambda text, _rel: literal_defaults(text))
    assert not hits, "the SLM admin password has no default -- empty means generate or require (#19318):\n" + "\n".join(
        hits
    )


def test_one_name_for_the_admin_password() -> None:
    hits = _sweep(lambda text, rel: sorted(second_names(text, rel)))
    assert not hits, f"a second name for {_CANONICAL} (#19318); use the canonical one:\n" + "\n".join(hits)


def test_only_the_known_readers_read_it() -> None:
    hits = _sweep(lambda text, rel: ["reads the password"] if reads(text) and rel not in _READERS else [])
    assert not hits, f"a new reader of {_CANONICAL}; go through {_READER} or {_PY_READER} (#19318):\n" + "\n".join(hits)


def test_every_login_goes_through_the_one_reader() -> None:
    hits = _sweep(lambda text, rel: ["logs in"] if rel != _READER and logs_in_without_reader(text) else [])
    assert not hits, f"logs in with slm_admin_password without including {_READER} (#19318):\n" + "\n".join(hits)


def test_the_canonical_name_is_registered_with_no_default() -> None:
    from autobot_shared.env_registry import REGISTRY

    spec = REGISTRY[_CANONICAL]
    assert spec.default == "" and _ALIAS in spec.description


def test_the_allowlists_name_real_files() -> None:
    root = repo_root()
    missing = [rel for rel in (*_ALIAS_HOMES, *_READERS) if not (root / rel).is_file()]
    assert not missing, f"allowlisted files that no longer exist: {missing}"


_GUESS = "ad" + "min"  # built here: no credential-shaped literal in this file


def test_contrast_the_detectors_fire_on_the_old_shapes() -> None:
    role_default = "slm_admin_password: \"{{ lookup('env', '%s') | default('%s', true) }}\"" % (_CANONICAL, _GUESS)
    folded = "p: >-\n  {{ hostvars[h]['slm_admin_password']\n     | default('%s') }}" % _GUESS
    assert literal_defaults(role_default) == [f"default('{_GUESS}'"]
    assert literal_defaults(folded) == [f"default('{_GUESS}'"]
    assert literal_defaults("{{ slm_admin_password | default('') }}") == []
    assert literal_defaults("X=${%s:-%s}" % (_CANONICAL, _GUESS)) == ["${%s:-%s}" % (_CANONICAL, _GUESS)]
    assert literal_defaults("X=${%s:-${%s:-${P}}}" % (_CANONICAL, _ALIAS)) == []
    assert literal_defaults('os.getenv("%s", "%s")' % (_CANONICAL, _GUESS))
    assert literal_defaults('os.getenv("%s", "")' % _CANONICAL) == []
    assert literal_defaults("%s=%s" % (_CANONICAL, _GUESS)) and not literal_defaults(_CANONICAL + "=${P}")


def test_contrast_a_second_name_and_a_stray_reader_are_caught() -> None:
    assert second_names(f"lookup('env', '{_ALIAS}')", "roles/x.yml") == {_ALIAS}
    assert second_names(f"lookup('env', '{_ALIAS}')", "install.sh") == set()
    assert second_names("SLM_ADMIN_PASS=x SLM_ADMIN_PASSWD=y", "a.sh") == {"SLM_ADMIN_PASS", "SLM_ADMIN_PASSWD"}
    assert reads("{{ lookup('env', '%s') }}" % _CANONICAL) and reads("grep -oP '^%s=\\K.*' f" % _CANONICAL)
    assert not reads("ensure_secret %s password" % _CANONICAL)
    login = 'password: "{{ slm_admin_password }}"'
    assert logs_in_without_reader(login)
    assert not logs_in_without_reader("include_tasks: _shared/tasks/read_slm_admin_password.yml\n" + login)


_SEED_READ = re.compile(r"\^AUTOBOT_ADMIN_PASSWORD=")


def test_the_main_app_admin_seed_is_read_once_in_ansible() -> None:
    """#19370: the deploy path and the update path each had their own copy of this read."""
    hits = _sweep(
        lambda text, rel: (
            ["reads the admin seed"]
            if rel.startswith("autobot-slm-backend/ansible/") and rel != _SEED_READER and _SEED_READ.search(text)
            else []
        )
    )
    assert not hits, f"a second read of AUTOBOT_ADMIN_PASSWORD; include {_SEED_READER} (#19370):\n" + "\n".join(hits)
