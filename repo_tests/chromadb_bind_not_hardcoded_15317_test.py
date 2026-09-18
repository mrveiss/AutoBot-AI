# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No ChromaDB launch site binds a wildcard interface (#15317).

Two of the three files originally reviewed here had `--host 0.0.0.0` -- every
interface, in front of four unpatchable advisories, one a pre-auth RCE. The
host firewall was the only remaining control. A first version of this guard
regex-scanned a hand-kept tuple of three files for that literal, which left
two real gaps (PR #16882 review, round 1):

* it never resolved `chromadb_bind_host` itself -- the two live templates
  read `{{ chromadb_bind_host }}` (unrendered Jinja), so a future edit to its
  real default in `group_vars/all.yml` could widen the bind and every check
  here would keep passing;
* `install-bare-metal.sh`'s own launch site was outside the hand-kept tuple,
  so the docstring's "every file" claim was false as written.

Round 2 of the same review found the fix for round 1 itself had three gaps:

* the ansible sweep had no equivalent for Docker Compose -- `docker-compose.yml`
  publishes ChromaDB via `ports:`, which binds every interface exactly like a
  systemd `--host` flag does, and nothing here looked at it;
* `--host\\s+0\\.0\\.0\\.0` missed the `--host=0.0.0.0` equals-form;
* `chromadb_bind_host`'s value was read with a regex, which a YAML anchor/alias
  or a block scalar evades -- the literal text on the assignment line is not
  necessarily the resolved value.

This version resolves the variable's actual value via `yaml.safe_load` (not a
regex), discovers ansible launch sites by sweeping tracked
`.service`/`.service.j2`/`.sh` files, and discovers Docker Compose ChromaDB
`ports:` sites by sweeping `docker-compose*.yml` and any compose file under
`docker/` -- so all of the above are structural fixes, not a longer list.

No named cluster-mode allowlist: `docs/architecture/NETWORK_TOPOLOGY.md`'s
only documented multi-node path is setting `chromadb_bind_host` to a specific
fleet IP, which is never a wildcard, and #15317's own AC is explicit --
"never an 'allow from anywhere' rule". So the checks below only special-case
the wildcard *shape* (`0.0.0.0` / `::` / empty / a host-segment-free port
mapping), not "anything other than 127.0.0.1"; a specific address passes with
no allowlist entry needed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from repo_tests._paths import repo_root
from repo_tests._reach import declare
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_REPO_ROOT = repo_root()

# The canonical bind-address default. Checked directly, separately from the
# override sweep below, so its own absence (a rename, a moved file) is a
# distinct, clearly-named failure rather than one more zero-length list.
_GROUP_VARS_ALL = "autobot-slm-backend/ansible/inventory/group_vars/all.yml"

# The two live templates that must read the SAME variable -- named directly
# (not sweep-discovered) because this test asserts a relationship between
# exactly these two files, not "some files somewhere".
_LIVE_TEMPLATES = (
    "autobot-slm-backend/ansible/roles/ai-stack/templates/autobot-chromadb.service.j2",
    "autobot-slm-backend/ansible/roles/redis/templates/autobot-chromadb.service.j2",
)

# Extensions a ChromaDB `chroma run` ExecStart has ever appeared in: two
# ansible .j2 templates, one decorative reference .service, and the
# bare-metal installer's inline heredoc .sh unit.
_LAUNCH_SITE_PATTERNS = ("*.service", "*.service.j2", "*.sh")

# A `chroma run` invocation followed by `--host <value>` (space OR `=`, #15317
# review round 2) within a bounded window, tolerating the `chroma run \` +
# newline-indented `--host ...` continuation style install-bare-metal.sh and
# the redis template use, as well as the single-line form the ai-stack
# template uses. 120 chars covers both comfortably while staying far short of
# an unrelated "chroma run" or "--host" mention elsewhere in a file (measured:
# the guard's own module docstring above and every prose "chroma runs
# on/from/unauthenticated" hit in the tree sit hundreds of characters from the
# nearest "--host").
_CHROMA_LAUNCH_SITE_WINDOW = re.compile(r"chroma\s+run\b[\s\S]{0,120}?--host[\s=]+\S+")

# A bind literal typed directly into a rendered/heredoc ExecStart, space or
# `=` form. 127.0.0.1 is the chosen safe default and is not itself a
# violation; a real regression looks like 0.0.0.0 or the IPv6 wildcard.
_HARDCODED_WIDE_BIND = re.compile(r"--host[\s=]+(?:0\.0\.0\.0|::)")

_WILDCARD_BIND_VALUES = {"0.0.0.0", "::", ""}

# Every file a `chromadb_bind_host` override could legitimately live in:
# other group_vars files, host_vars (none exist today -- the pattern still
# sweeps for one), and every role's own defaults.
_OVERRIDE_SEARCH_PATTERNS = (
    "autobot-slm-backend/ansible/inventory/group_vars/*.yml",
    "autobot-slm-backend/ansible/inventory/host_vars/*.yml",
    "autobot-slm-backend/ansible/roles/*/defaults/main.yml",
)

# docker-compose*.yml at the repo root, and any compose file anywhere under
# docker/ (e.g. the MCP-bridges overlay, which does not have "compose" in its
# own filename -- #15317 review round 2 asked for "any compose file", not one
# matching a naming convention).
_COMPOSE_FILE_PATTERNS = ("docker-compose*.yml", "docker/*.yml")


def _load_yaml_mapping(path: Path) -> dict:
    """Parse *path* as YAML, tolerating an empty or non-mapping document."""
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def _bind_host_value_in_file(path: Path) -> str | None:
    """The value assigned to `chromadb_bind_host` in *path*, or None if the
    key is absent. A real YAML parse, not a regex, so a YAML anchor/alias or
    a block scalar resolves to its actual value instead of evading the check
    (#15317 review round 2)."""
    data = _load_yaml_mapping(path)
    if "chromadb_bind_host" not in data:
        return None
    value = data["chromadb_bind_host"]
    return "" if value is None else str(value).strip()


def _is_wildcard_bind(value: str) -> bool:
    """True for 0.0.0.0 / :: / empty -- never for a specific address.

    A specific fleet IP (loopback or otherwise) is the documented multi-node
    override and must pass; only the wildcard shape is special-cased.
    """
    return value.strip().strip("'\"") in _WILDCARD_BIND_VALUES


def _discover_chroma_launch_sites(root: Path) -> list[str]:
    """Every tracked launch-site-shaped file that actually invokes
    `chroma run ... --host` -- sweep, not a hand-kept list (#15317 review)."""
    try:
        candidates = tracked_paths(root, *_LAUNCH_SITE_PATTERNS)
    except EmptyEnumeration:
        return []
    return [
        rel
        for rel in candidates
        if _CHROMA_LAUNCH_SITE_WINDOW.search((root / rel).read_text(encoding="utf-8", errors="ignore"))
    ]


def _discover_override_candidate_files(root: Path) -> list[str]:
    """Every group_vars/host_vars/role-defaults file that could carry a
    `chromadb_bind_host` override, whether or not it actually does."""
    found: list[str] = []
    for pattern in _OVERRIDE_SEARCH_PATTERNS:
        try:
            found.extend(tracked_paths(root, pattern))
        except EmptyEnumeration:
            continue
    return found


def _bind_host_overrides(root: Path, candidates: list[str]) -> list[tuple[str, str]]:
    """(path, value) for each candidate that assigns chromadb_bind_host,
    excluding the canonical default (group_vars/all.yml, checked on its own by
    test_chromadb_bind_host_default_resolves_to_a_non_wildcard)."""
    overrides = []
    for rel in candidates:
        if rel == _GROUP_VARS_ALL:
            continue
        value = _bind_host_value_in_file(root / rel)
        if value is not None:
            overrides.append((rel, value))
    return overrides


def _looks_like_chromadb_service(name: str, service: dict) -> bool:
    """A compose service is ChromaDB if its name says so or it runs the image."""
    image = str(service.get("image") or "")
    return "chromadb" in name.lower() or "chromadb/chroma" in image


def _compose_port_offender(entry: object) -> str | None:
    """None for a safe port mapping (host segment present, not a wildcard);
    otherwise a short description of what is wrong. Handles both compose
    syntaxes: the short string form (`"127.0.0.1:8100:8000"`, bracketed IPv6
    `"[::1]:8100:8000"`, or a bare `"8100:8000"`/`"8100"` -- no host segment,
    binds every interface) and the long dict form (`host_ip:`/`target:`/
    `published:`)."""
    if isinstance(entry, dict):
        host = str(entry.get("host_ip") or "").strip()
        if not host:
            return "missing host_ip"
        return host if host in _WILDCARD_BIND_VALUES else None
    text = str(entry)
    if text.startswith("["):
        end = text.find("]")
        host = text[: end + 1] if end != -1 else text
        return host if host in ("[::]", "[0.0.0.0]") else None
    parts = text.split(":")
    if len(parts) < 3:
        return "missing host segment"
    return parts[0] if parts[0] in _WILDCARD_BIND_VALUES else None


def _discover_compose_files(root: Path) -> list[str]:
    """Every tracked compose-shaped YAML file: docker-compose*.yml at the repo
    root, and any compose file under docker/ -- filtered to files that
    actually declare `services:`, so a stray non-compose .yml cannot inflate
    the count."""
    found: list[str] = []
    for pattern in _COMPOSE_FILE_PATTERNS:
        try:
            found.extend(tracked_paths(root, pattern))
        except EmptyEnumeration:
            continue
    return [rel for rel in found if "services" in _load_yaml_mapping(root / rel)]


def _discover_compose_chromadb_port_sites(root: Path) -> list[tuple[str, str, object]]:
    """(file, service_name, port_entry) for every `ports:` entry on a service
    that looks like ChromaDB, across every file COMPOSE_FILES reaches."""
    sites: list[tuple[str, str, object]] = []
    for rel in COMPOSE_FILES.examined(root):
        services = _load_yaml_mapping(root / rel).get("services") or {}
        for name, service in services.items():
            service = service or {}
            if not _looks_like_chromadb_service(name, service):
                continue
            for entry in service.get("ports") or []:
                sites.append((rel, name, entry))
    return sites


#: 4 known launch sites today: the two live ansible templates, the infra
#: decorative reference copy, and install-bare-metal.sh's heredoc unit.
CHROMA_LAUNCH_SITES = declare(
    "chromadb-bind-launch-sites",
    discover=_discover_chroma_launch_sites,
    floor=4,
    growth=2,
    what="files invoking `chroma run ... --host` -- ChromaDB bind launch sites (#15317)",
)

#: 37 candidates as of #15317's guard rewrite: 8 group_vars files + 29
#: role defaults/main.yml files + 0 host_vars (the directory does not exist
#: yet). Re-measure with `git ls-files` before lowering.
BIND_HOST_OVERRIDE_CANDIDATES = declare(
    "chromadb-bind-host-override-candidates",
    discover=_discover_override_candidate_files,
    floor=30,
    growth=15,
    what="group_vars/host_vars/role-defaults files scanned for a chromadb_bind_host override (#15317)",
)

#: 4 compose-shaped files today: docker-compose.yml, docker-compose.hardened.yml,
#: docker-compose.override.example.yml, docker/mcp-bridges.yml.
COMPOSE_FILES = declare(
    "chromadb-compose-files",
    discover=_discover_compose_files,
    floor=3,
    growth=3,
    what="docker-compose-shaped YAML files scanned for a ChromaDB service (#15317 review round 2)",
)

#: 1 real site today: docker-compose.yml's autobot-chromadb `ports:` entry.
#: docker-compose.hardened.yml's chromadb service is a read_only/tmpfs
#: overlay with no `ports:` key of its own (it inherits the base file's).
COMPOSE_CHROMADB_PORT_SITES = declare(
    "chromadb-compose-port-sites",
    discover=_discover_compose_chromadb_port_sites,
    floor=1,
    growth=2,
    what="ChromaDB service `ports:` entries across compose files (#15317 review round 2)",
)


def test_the_sweep_reaches_the_known_chroma_launch_sites() -> None:
    """Vacuity floor: a sweep that quietly narrows -- wrong root, wrong
    extensions, a pattern typo -- must not pass as a clean tree."""
    CHROMA_LAUNCH_SITES.examined(_REPO_ROOT)


def test_no_chroma_launch_site_hardcodes_a_wide_bind() -> None:
    offenders = [
        rel
        for rel in CHROMA_LAUNCH_SITES.examined(_REPO_ROOT)
        if _HARDCODED_WIDE_BIND.search((_REPO_ROOT / rel).read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        f"{offenders} bind ChromaDB to a wildcard literally -- in front of four unpatchable "
        "advisories (one pre-auth RCE), the host firewall becomes the only remaining "
        "control. Bind through chromadb_bind_host (group_vars/all.yml), not a literal (#15317)."
    )


def test_the_ai_stack_and_redis_templates_share_one_bind_variable() -> None:
    """The two live templates must read the SAME variable, or a value set in one
    place silently fails to narrow the unit the other role renders."""
    for rel_path in _LIVE_TEMPLATES:
        text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
        assert "{{ chromadb_bind_host }}" in text, f"{rel_path} does not read chromadb_bind_host"


def test_chromadb_bind_host_default_resolves_to_a_non_wildcard() -> None:
    """The gap the PR #16882 review named: the old guard never looked at what
    chromadb_bind_host actually resolves to, only at whether the templates
    named it. A future edit widening group_vars/all.yml:426 must fail here."""
    value = _bind_host_value_in_file(_REPO_ROOT / _GROUP_VARS_ALL)
    assert value is not None, f"chromadb_bind_host not found in {_GROUP_VARS_ALL} -- this guard would be vacuous"
    assert not _is_wildcard_bind(value), (
        f"chromadb_bind_host resolves to {value!r} in {_GROUP_VARS_ALL} -- a wildcard bind reopens "
        "the every-interface exposure #15317 closed, in front of four unpatchable ChromaDB "
        "advisories, one a pre-auth RCE."
    )


def test_the_override_scan_reaches_a_real_population() -> None:
    """Vacuity floor for the override sweep, distinct from the launch-site
    floor above -- a broken glob here would make the next test check zero
    files and still read as a clean pass."""
    BIND_HOST_OVERRIDE_CANDIDATES.examined(_REPO_ROOT)


def test_no_chromadb_bind_host_override_widens_to_a_wildcard() -> None:
    """Any group_vars/host_vars/role-default that overrides chromadb_bind_host
    must still resolve to a real address. #15317's own AC is explicit that a
    multi-node install needs a scoped firewall rule, "never an allow from
    anywhere rule" -- so a specific fleet IP passes (the documented multi-node
    override) and 0.0.0.0/::/empty do not, wherever they are set."""
    candidates = BIND_HOST_OVERRIDE_CANDIDATES.examined(_REPO_ROOT)
    offenders = [
        (rel, value) for rel, value in _bind_host_overrides(_REPO_ROOT, list(candidates)) if _is_wildcard_bind(value)
    ]
    assert not offenders, f"{offenders} override chromadb_bind_host to a wildcard bind (#15317)"


def test_is_wildcard_bind_matches_only_the_documented_wildcard_forms() -> None:
    """0.0.0.0 / :: / empty fail; a specific address -- loopback or a fleet
    IP, the documented multi-node override -- passes. No named cluster-mode
    allowlist: only the wildcard shape is special-cased (#15317 review)."""
    for wildcard in ("0.0.0.0", "::", "", '""', "''"):
        assert _is_wildcard_bind(wildcard), f"{wildcard!r} should be treated as a wildcard bind"
    for real in ("127.0.0.1", "10.0.4.23", "192.168.1.50"):
        assert not _is_wildcard_bind(real), f"{real!r} must not be flagged as a wildcard"


def test_the_compose_sweep_reaches_real_compose_files() -> None:
    """Vacuity floor for the compose sweep (#15317 review round 2)."""
    COMPOSE_FILES.examined(_REPO_ROOT)


def test_the_compose_sweep_reaches_a_chromadb_port_site() -> None:
    """Vacuity floor distinct from the file-count floor above -- a broken
    service-name/image match here would check zero port entries and still
    read as a clean pass."""
    COMPOSE_CHROMADB_PORT_SITES.examined(_REPO_ROOT)


def test_no_compose_chromadb_port_binds_a_wildcard_or_bare_port() -> None:
    """docker-compose.yml:132 publishes ChromaDB at "127.0.0.1:8100:8000" --
    safe today, but a bare "8100:8000" (host segment omitted -> every
    interface) or an explicit "0.0.0.0:8100:8000" edit must fail here
    (#15317 review round 2)."""
    offenders = []
    for rel, svc, entry in COMPOSE_CHROMADB_PORT_SITES.examined(_REPO_ROOT):
        reason = _compose_port_offender(entry)
        if reason is not None:
            offenders.append((rel, svc, entry, reason))
    assert not offenders, f"{offenders} publish ChromaDB without a safe, host-scoped port mapping (#15317)"


def test_the_wide_bind_sweep_catches_a_synthetic_wildcard_launch_site(tmp_path: Path) -> None:
    """Negative control: a fabricated wide-bind unit must be caught by the same
    discovery-marker + literal-scan pair the real guard runs above, proving
    neither step is silently vacuous just because today's tree is clean."""
    fake_unit = tmp_path / "fake-chromadb.service"
    fake_unit.write_text(
        "ExecStart=/venv/bin/chroma run \\\n    --host 0.0.0.0 \\\n    --port 8100\n",
        encoding="utf-8",
    )
    text = fake_unit.read_text(encoding="utf-8")
    assert _CHROMA_LAUNCH_SITE_WINDOW.search(text), "sweep marker failed to recognize a synthetic chroma launch site"
    assert _HARDCODED_WIDE_BIND.search(text), "literal-bind detector failed to catch a synthetic 0.0.0.0"


@pytest.mark.parametrize("host_flag", ["--host 0.0.0.0", "--host=0.0.0.0", "--host   0.0.0.0"])
def test_the_wide_bind_regex_catches_space_and_equals_forms(host_flag: str) -> None:
    """Negative control for review round 2's nit: --host=0.0.0.0 (no space)
    must be caught exactly like the space-separated form."""
    text = f"ExecStart=/venv/bin/chroma run \\\n    {host_flag} \\\n    --port 8100\n"
    assert _CHROMA_LAUNCH_SITE_WINDOW.search(text), f"sweep marker missed {host_flag!r}"
    assert _HARDCODED_WIDE_BIND.search(text), f"literal-bind detector missed {host_flag!r}"


def test_the_variable_check_catches_a_synthetic_wildcard_override(tmp_path: Path) -> None:
    """Negative control for the resolved-value path: a fabricated override
    file must be caught by the same extract + wildcard-check pair the real
    guard runs above."""
    fake_vars = tmp_path / "fake_group_vars.yml"
    fake_vars.write_text('chromadb_bind_host: "0.0.0.0"\n', encoding="utf-8")
    value = _bind_host_value_in_file(fake_vars)
    assert value == "0.0.0.0"
    assert _is_wildcard_bind(value), "wildcard check failed to catch a synthetic 0.0.0.0 override"


@pytest.mark.parametrize(
    ("yaml_body", "case"),
    [
        ("other_var: &host_anchor 0.0.0.0\nchromadb_bind_host: *host_anchor\n", "anchor/alias"),
        ("chromadb_bind_host: |\n  0.0.0.0\n", "block scalar"),
    ],
)
def test_the_variable_check_resolves_yaml_forms_a_regex_would_miss(tmp_path: Path, yaml_body: str, case: str) -> None:
    """Negative control for review round 2's nit: a YAML anchor/alias or a
    block scalar must resolve to the real value via yaml.safe_load, not
    evade a line-level regex the way the old extractor would have."""
    fake_vars = tmp_path / "fake_group_vars_yaml_form.yml"
    fake_vars.write_text(yaml_body, encoding="utf-8")
    value = _bind_host_value_in_file(fake_vars)
    assert value is not None, f"{case}: value not resolved"
    assert _is_wildcard_bind(value), f"{case}: {value!r} should be treated as a wildcard bind"


def test_the_compose_port_check_catches_a_synthetic_wildcard(tmp_path: Path) -> None:
    """Negative control for the compose gap (#15317 review round 2): a bare
    port:port mapping and an explicit 0.0.0.0 host must both be caught by the
    same classifier the real guard runs above; a real loopback mapping must not."""
    fake_compose = tmp_path / "docker-compose.fake.yml"
    fake_compose.write_text(
        'services:\n  autobot-chromadb:\n    image: chromadb/chroma:1.5.9\n    ports:\n      - "8100:8000"\n',
        encoding="utf-8",
    )
    services = _load_yaml_mapping(fake_compose)["services"]
    assert _looks_like_chromadb_service("autobot-chromadb", services["autobot-chromadb"])
    bare_entry = services["autobot-chromadb"]["ports"][0]
    assert _compose_port_offender(bare_entry) is not None, "bare port:port mapping should be flagged"
    assert _compose_port_offender("0.0.0.0:8100:8000") is not None, "explicit 0.0.0.0 host should be flagged"
    assert _compose_port_offender("127.0.0.1:8100:8000") is None, "a real loopback mapping must not be flagged"
