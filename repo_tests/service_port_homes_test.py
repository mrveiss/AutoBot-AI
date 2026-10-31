# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A service port found with two numbers has ONE home per concept; a re-added copy fails.

Homes are ``PortConfig`` fields in ``autobot_shared/ssot_config.py``; Python readers import them.
A file that cannot import them (the Windows NPU worker bundle, shell, YAML, PowerShell, the MCP
tracker's TypeScript) states the number at each site, and ``PINNED`` holds every site equal to its
home -- a non-Python copy pinned by a failing guard counts as derived (owner ruling, #19343).

Two checks, each with a contrast test proving it fires:

1. ``PINNED``: every listed copy states its concept's SSOT value at every site its pattern finds,
   and finds at least ``floor`` sites, so a reworded file cannot pass by matching nothing.
2. ``FORBIDDEN``: a number that, outside its home and its pinned SITES, can only be a second
   definition. A pin admits the sites its pattern captures, not its whole file: those are masked
   and the rest of the file is swept like any other. Production Python is read through the AST
   (docstrings are prose and are skipped); other sources are read as text with ``#``/``//``
   comments stripped. A discovered file that cannot be read fails the sweep, never counts as clean.

Concepts: the Windows NPU worker, 8082, separate from the Linux worker's ``npu`` (#19325); the
noVNC web port, ``vnc``, which the browser host serves on the same 6080 as the backend desktop --
the frontend's Playwright default of 6081 was a port no host listens on, now retired (#19327).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import NamedTuple, Sequence

import pytest
from repo_tests._paths import repo_root
from repo_tests._pinned_sweep import masked
from repo_tests._reach import declare

from autobot_shared.ssot_config import PortConfig
from tools.lint import check_getenv_ssot_drift  # noqa: F401 -- puts tools/lint on sys.path for the sibling import

from tools.lint import _env_fork_scan as scan_mod  # isort: skip
from tools.lint._scan_helpers import EmptyEnumeration  # isort: skip

_ROOT = repo_root()
_SSOT_HOME = "autobot_shared/ssot_config.py"
#: Literal tables of every SSOT port by design: the hardcoded-value detector's rules (#14316).
_DETECTOR_TABLES = frozenset({"scripts/lib/hardcoded-value-rules.sh"})
_WIN = "autobot-npu-worker/resources/windows-npu-worker"
_ANSIBLE = "autobot-slm-backend/ansible"


class Pin(NamedTuple):
    """One non-importing copy: the concept it restates, where, how to find each site, and how many."""

    field: str
    rel: str
    pattern: str
    floor: int


#: Every copy that cannot import its home. Each pattern has ONE capture group: the port number.
PINNED: tuple[Pin, ...] = (
    Pin("npu_windows", f"{_WIN}/app/utils/config_bootstrap.py", r"^DEFAULT_WORKER_PORT = (\d+)$", 1),
    Pin("npu_windows", f"{_WIN}/gui/utils/app_config.py", r"^DEFAULT_WORKER_PORT = (\d+)$", 1),
    Pin("npu_windows", f"{_WIN}/config/npu_worker.yaml", r"^service:\n(?:  .*\n)*?  port: (\d+)", 1),
    Pin("npu_windows", f"{_WIN}/installer/installer.iss", r"(?:-LocalPort |localhost:)(\d+)", 2),
    Pin("npu_windows", f"{_WIN}/scripts/install.ps1", r"(?:-LocalPort |localhost:|allow port |port: )(\d+)", 6),
    Pin("npu_windows", f"{_WIN}/scripts/check-health.ps1", r"\[int\]\$Port = (\d+)", 1),
    Pin("npu_windows", f"{_WIN}/scripts/update.ps1", r"localhost:(\d+)", 1),
    Pin("npu_windows", f"{_WIN}/scripts/start-service.ps1", r"localhost:(\d+)", 1),
    Pin("npu_windows", f"{_WIN}/scripts/restart-service.ps1", r"localhost:(\d+)", 1),
    Pin("npu_windows", f"{_WIN}/scripts/uninstall.ps1", r"rules for port (\d+)", 1),
    Pin("npu_windows", f"{_WIN}/installer/build.ps1", r"localhost:(\d+)", 1),
    Pin(
        "npu_windows",
        f"{_WIN}/PACKAGE_INFO.txt",
        r"(?:localhost:|<windows-ip>:|findstr :|\"port\": |service\.port:\s+|(?<![.-])[Pp]ort[:(]?\s+\(?)(\d{4})\b",
        19,
    ),
    Pin("npu_windows", "autobot-infrastructure/shared/config/npu_workers.yaml", r"AUTOBOT_BACKEND_HOST\}:(\d+)", 1),
    Pin(
        "npu_windows",
        "autobot-infrastructure/shared/config/npu_workers.example.yaml",
        r'id: "windows-npu-1"\n(?:.*\n)*?\s+port: (\d+)',
        1,
    ),
    Pin(
        "npu_windows",
        "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/src/constants/network.ts",
        r"'NPU_WORKER_WINDOWS_PORT', '(\d+)'",
        1,
    ),
    Pin(
        "npu_windows",
        "autobot-infrastructure/shared/scripts/lib/ssot-config.sh",
        r"AUTOBOT_NPU_WORKER_WINDOWS_PORT:=(\d+)",
        1,
    ),
    Pin("vnc", ".env.example", r"^AUTOBOT_VNC_PORT=(\d+)$", 1),
    Pin("vnc", ".env.example", r"^VITE_(?:DESKTOP|TERMINAL|PLAYWRIGHT)_VNC_PORT=(\d+)$", 3),
    Pin("vnc", "autobot-infrastructure/shared/scripts/lib/ssot-config.sh", r"AUTOBOT_VNC_PORT:=(\d+)", 1),
    Pin(
        "vnc",
        "autobot-infrastructure/shared/scripts/infrastructure/browser-vnc-websockify.service",
        r"0\.0\.0\.0:(\d+)",
        1,
    ),
    Pin(
        "vnc",
        "autobot-infrastructure/shared/docker/compose/docker-compose.playwright-vnc.yml",
        r':(\d+):\d+"\s+# noVNC',
        1,
    ),
    Pin("vnc", f"{_ANSIBLE}/roles/vnc/defaults/main.yml", r"WEBSOCKIFY_PORT'\) \| default\('(\d+)'", 1),
    Pin("vnc", f"{_ANSIBLE}/roles/common/defaults/main.yml", r"^\s+novnc: (\d+)", 1),
    Pin("vnc", f"{_ANSIBLE}/roles/slm_manager/defaults/main.yml", r"^novnc_port: (\d+)", 1),
    Pin("vnc", f"{_ANSIBLE}/roles/distributed_setup/defaults/main.yml", r"^vnc_port: (\d+)", 1),
    Pin("vnc", f"{_ANSIBLE}/inventory/production.yml", r"novnc_port: (\d+)", 1),
    Pin("vnc", f"{_ANSIBLE}/roles/frontend/templates/nginx-frontend.conf.j2", r"\(ansible_host\) \}\}:(\d+)/", 1),
)

#: number -> the PortConfig field a reader should use instead. A number equal to its field's value
#: is forbidden outside that field's homes and pins; a RETIRED number (no host serves it) everywhere.
FORBIDDEN: dict[int, str] = {
    8082: "npu_windows",  # #19325
    6081: "vnc",  # #19327: retired -- the browser host's noVNC is port.vnc; nothing listens on 6081
}

#: number -> {file: (how many sites, reason)} for a forbidden number that legitimately stays.
#: Shrink-only and per occurrence: a new site in a listed file fails, and so does a stale count.
KNOWN: dict[int, dict[str, tuple[int, str]]] = {
    8082: {
        "autobot-slm-backend/ansible/fix-slm-env-ports.yml": (
            4,
            "a one-off fixer that rewrites a Linux worker env still set to the old wrong 8082 -- "
            "it names the bad value it removes, it does not define the Windows port",
        ),
    },
}

_TEXT_SUFFIXES = (".ts", ".js", ".vue", ".sh", ".yml", ".yaml", ".j2", ".ps1", ".iss")
#: Root-level files swept as well: ``.env.example`` carries port keys beyond its pins, and a retired
#: port is forbidden everywhere, so it is read in full (#19429 review).
_ROOT_FILES = (".env.example",)
_SCAN_ROOTS = (*scan_mod.SCAN_ROOTS, "autobot-frontend", *_ROOT_FILES)
_NOT_PRODUCTION = re.compile(r"(_test\.py$|(^|/)test_[^/]*\.py$|/tests?/|/__tests__/|\.spec\.|\.test\.|/generated/)")
#: Stories are sample data, so a live number may stand in one -- but a RETIRED number may not (#19429).
_STORY = re.compile(r"\.stories\.")
_COMMENT = re.compile(r"(^|[ \t])(#|//).*$|^[ \t]*(/\*|\*).*$", re.MULTILINE)
#: A port as a whole number: not part of a longer one, a version (1.6081) or an issue ref (#6081).
_WORD = r"(?<![\d.#]){}(?!\d)"


def ssot_port(field: str) -> int:
    """The declared default of ``PortConfig.<field>`` -- the home every copy is held to."""
    return int(PortConfig.model_fields[field].default)


def _production(rel: str) -> bool:
    return rel.split("/")[0] in _SCAN_ROOTS and not _NOT_PRODUCTION.search(rel)


def _scanned_files(root: Path) -> list[str]:
    """Tracked production Python and text sources under the sweep roots; ``[]`` on an empty tree."""
    try:
        paths = scan_mod.tracked_paths(root, "*.py", *(f"*{s}" for s in _TEXT_SUFFIXES), *_ROOT_FILES)
    except EmptyEnumeration:
        return []
    return sorted(rel for rel in paths if _production(rel))


FILES = declare(
    "service-port-homes-scan",
    discover=_scanned_files,
    floor=5505,  # mid-window: population 5580, window (5430, 5580)
    growth=150,
    what="production python and text sources swept for a second definition of a service port",
    roots=_SCAN_ROOTS,
)


def pin_violations(pin: Pin, text: str, value: int) -> list[str]:
    """Each site in *text* that states a number other than *value*, or a shortfall below the floor."""
    found = [m for m in re.finditer(pin.pattern, text, re.MULTILINE)]
    out = [
        f"{pin.rel}:{text.count(chr(10), 0, m.start(1)) + 1}: states {m.group(1)}, home says {value} "
        f"(PortConfig.{pin.field})"
        for m in found
        if int(m.group(1)) != value
    ]
    if len(found) < pin.floor:
        out.append(f"{pin.rel}: pattern found {len(found)} site(s), floor {pin.floor} -- reworded or moved?")
    return out


def _docstrings(tree: ast.Module) -> set[int]:
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    return {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, holders) and node.body and isinstance(node.body[0], ast.Expr)
    }


def _python_sites(source: str, value: int, rel: str = "<source>") -> list[int]:
    """Lines of each non-docstring int or string constant stating *value*."""
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError as exc:  # name the file: a bare SyntaxError would hide which one broke the sweep
        raise AssertionError(f"{rel}: swept but does not parse ({exc.msg}, line {exc.lineno})") from exc
    word = re.compile(_WORD.format(value))
    prose = _docstrings(tree)
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or id(node) in prose or isinstance(node.value, bool):
            continue
        if node.value == value or (isinstance(node.value, str) and word.search(node.value)):
            lines.append(node.lineno)
    return lines


def _text_sites(text: str, value: int) -> list[int]:
    """Lines stating *value* in a non-Python source, comments stripped."""
    code = _COMMENT.sub("", text)
    word = re.compile(_WORD.format(value))
    return [code.count("\n", 0, m.start()) + 1 for m in word.finditer(code)]


def sites(rel: str, text: str, value: int) -> list[int]:
    """Where *rel* states *value* as code, whatever its language."""
    return _python_sites(text, value, rel) if rel.endswith(".py") else _text_sites(text, value)


def _homes(number: int) -> set[str]:
    """Where *number* may stand: its field's home and pins -- none at all for a retired number."""
    field = FORBIDDEN[number]
    if ssot_port(field) != number:
        return set()
    return {_SSOT_HOME} | {pin.rel for pin in PINNED if pin.field == field}


def _unpinned(rel: str, text: str, number: int) -> str:
    """*text* with the sites *rel*'s pins hold at *number* masked; any other statement remains."""
    for pin in PINNED:
        if pin.rel == rel and ssot_port(pin.field) == number:
            text = masked(text, pin.pattern)
    return text


def forbidden_sites(number: int, sources: dict[str, str], known_table: dict | None = None) -> list[str]:
    """Every statement of a FORBIDDEN number outside its home and pinned sites, beyond its KNOWN count.

    Only the SSOT home (for a live number) and the detector tables are exempt as whole files.
    """
    retired, known, out = not _homes(number), (KNOWN if known_table is None else known_table).get(number, {}), []
    exempt = _DETECTOR_TABLES | (set() if retired else {_SSOT_HOME})
    for rel, text in sorted(sources.items()):
        if rel in exempt or (bool(_STORY.search(rel)) and not retired):
            continue
        lines = sites(rel, _unpinned(rel, text, number), number)
        if len(lines) > known.get(rel, (0, ""))[0]:
            out += [f"{rel}:{line}: {number} -- read PortConfig.{FORBIDDEN[number]}" for line in lines]
    return out


def _read(rel: str) -> str:
    """Lenient, for the pin check only: a missing pin file reads empty and fails its floor there."""
    try:
        return (_ROOT / rel).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def read_sources(root: Path, paths: Sequence[str]) -> dict[str, str]:
    """The text of every discovered path; one that cannot be read fails the sweep, never reads as clean."""
    out = {}
    for rel in paths:
        try:
            out[rel] = (root / rel).read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:  # its repr carries the whole byte string; name the spot instead
            raise AssertionError(
                f"{rel}: discovered but unreadable (not UTF-8 at byte {exc.start}: {exc.reason})"
            ) from exc
        except OSError as exc:
            raise AssertionError(f"{rel}: discovered but unreadable ({type(exc).__name__}: {exc.strerror})") from exc
    return out


def _sources() -> dict[str, str]:
    return read_sources(_ROOT, FILES.examined(_ROOT))


def test_every_pinned_copy_states_its_home() -> None:
    bad = [v for pin in PINNED for v in pin_violations(pin, _read(pin.rel), ssot_port(pin.field))]
    assert bad == [], "\n".join(bad)


def test_no_forbidden_number_outside_its_homes() -> None:
    sources = _sources()
    assert len(sources) >= 1000, f"the sweep read {len(sources)} files -- a clean result would be blind"
    missing = [pin.rel for pin in PINNED if pin.rel.endswith(".py") and pin.rel not in sources]
    assert missing == [], f"the sweep never reached the in-bundle homes {missing}"
    found = [f for number in FORBIDDEN for f in forbidden_sites(number, sources)]
    assert found == [], f"checked {len(sources)} files:\n" + "\n".join(found)


def stale_known(sources: dict[str, str], known_table: dict = KNOWN) -> list[str]:
    """Each KNOWN entry whose file now states its number fewer times than recorded."""
    return [
        f"{rel}: known {count}, states {len(sites(rel, sources.get(rel, ''), number))}"
        for number, entries in known_table.items()
        for rel, (count, _) in entries.items()
        if len(sites(rel, sources.get(rel, ""), number)) < count
    ]


def test_the_known_counts_only_shrink() -> None:
    stale = stale_known(_sources())
    assert stale == [], f"{stale} -- lower the KNOWN count, or delete the entry at zero"


def test_the_known_allowance_holds_at_its_count_and_fails_one_above() -> None:
    known = {8082: {"x/fix.sh": (2, "names the bad value it removes")}}
    at_count = {"x/fix.sh": "A=8082\nB=8082\n"}
    assert forbidden_sites(8082, at_count, known) == []
    assert len(forbidden_sites(8082, {"x/fix.sh": "A=8082\nB=8082\nC=8082\n"}, known)) == 3


def test_a_known_count_above_the_real_sites_is_stale() -> None:
    known = {8082: {"x/fix.sh": (3, "names the bad value it removes")}}
    assert stale_known({"x/fix.sh": "A=8082\n"}, known) == ["x/fix.sh: known 3, states 1"]


def test_an_unpinned_retired_port_in_env_example_is_reported() -> None:
    assert _production(".env.example")
    text = "AUTOBOT_VNC_PORT=6080\nSOME_OTHER_VNC=6081\n"
    assert [f.split(":")[1] for f in forbidden_sites(6081, {".env.example": text})] == ["2"]


def test_a_python_file_that_does_not_parse_is_named() -> None:
    with pytest.raises(AssertionError, match=r"x/broken\.py: swept but does not parse"):
        sites("x/broken.py", "def f(:\n", 8082)


def test_a_pinned_copy_that_drifts_is_caught() -> None:
    pin = Pin("npu_windows", "x/check-health.ps1", r"\[int\]\$Port = (\d+)", 1)
    assert pin_violations(pin, "    [int]$Port = 8082\n", 8082) == []
    assert pin_violations(pin, "    [int]$Port = 8081\n", 8082) == [
        "x/check-health.ps1:1: states 8081, home says 8082 (PortConfig.npu_windows)"
    ]
    assert pin_violations(pin, "    $Port = 8082\n", 8082), "a reworded site must fail the floor, not pass"


def test_a_re_added_copy_is_caught_in_each_language() -> None:
    assert sites("a.py", 'DEFAULT = 8082\nURL = f"http://localhost:8082"\n', 8082) == [1, 2]
    assert sites("a.py", '"""Listens on 8082."""\n# 8082 in a comment\n', 8082) == []
    assert sites("a.ps1", "$p = 8082 # the worker\n# port 8082\n", 8082) == [1]
    assert sites("a.ts", "const P = '18082' // 8082\n", 8082) == []
    found = forbidden_sites(8082, {"autobot-backend/x.py": "PORT = 8082\n"})
    assert found == ["autobot-backend/x.py:1: 8082 -- read PortConfig.npu_windows"]
    assert sites("a.ts", " * Extracted (issue #6081).\n/* 6081 */\n", 6081) == []
    assert sites("a.ts", "\n  /** doc */\nport: 8082\n", 8082) == [3], "stripping a comment must not shift lines"


def test_a_second_site_in_a_pinned_file_is_caught() -> None:
    # A pin admits its own site, not its file: the pinned copy alone passes, one extra fails.
    rel = f"{_WIN}/app/utils/config_bootstrap.py"
    pinned = "DEFAULT_WORKER_PORT = 8082\n"
    assert forbidden_sites(8082, {rel: pinned}) == []
    assert forbidden_sites(8082, {rel: pinned + "X = 8082\n"}) == [f"{rel}:2: 8082 -- read PortConfig.npu_windows"]
    assert forbidden_sites(8082, {_SSOT_HOME: pinned + "X = 8082\n"}) == [], "the SSOT home is exempt whole"


def test_masking_blanks_only_the_pinned_capture() -> None:
    text = "DEFAULT_WORKER_PORT = 8082\nOTHER = 8082\n"
    assert masked(text, r"^DEFAULT_WORKER_PORT = (\d+)$") == "DEFAULT_WORKER_PORT = ____\nOTHER = 8082\n"


def test_an_unreadable_discovered_file_fails_the_sweep(tmp_path: Path) -> None:
    (tmp_path / "ok.sh").write_text("P=1\n", encoding="utf-8")
    (tmp_path / "bad.sh").write_bytes(b"P=\xff\xfe\n")
    assert read_sources(tmp_path, ["ok.sh"]) == {"ok.sh": "P=1\n"}
    with pytest.raises(AssertionError, match=r"bad.sh: discovered but unreadable \(not UTF-8 at byte 2") as caught:
        read_sources(tmp_path, ["ok.sh", "bad.sh"])
    assert "\\xff" not in str(caught.value), "the message names the spot, never dumps the bytes"


def test_a_retired_number_has_no_home() -> None:
    assert _homes(6081) == set(), "6081 is served by no host; nothing may state it"
    found = forbidden_sites(6081, {"autobot-frontend/src/config/x.ts": "port: getEnvNumber('P', 6081),\n"})
    assert found == ["autobot-frontend/src/config/x.ts:1: 6081 -- read PortConfig.vnc"]


def test_a_retired_number_is_caught_in_a_story_but_a_live_one_is_not() -> None:
    story = "autobot-frontend/src/components/x.stories.ts"
    assert forbidden_sites(6081, {story: "vnc_port: 6081,\n"}) == [f"{story}:1: 6081 -- read PortConfig.vnc"]
    assert forbidden_sites(8082, {story: "port: 8082,\n"}) == []
