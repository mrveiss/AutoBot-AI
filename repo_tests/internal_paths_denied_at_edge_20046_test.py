# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20046: the service-to-service routes are denied at every public nginx edge.

``/api/internal/`` carries the SSH-password proposal and claim (backend) and deletion (SLM) routes. They are
authenticated by the shared internal key, and ``autobot-slm.conf.j2`` injects that key for admin sessions on
``/autobot-api/``; so unless the edge refuses these paths, an admin's browser session reaches them with the key
attached. Every file that proxies a public ``/api`` location must carry a ``location ^~`` deny for the internal
prefix under it.

The files are DISCOVERED, not listed (the first version hardcoded five and missed nine, among them the
vhosts that shell and Python installers generate). One rule finds them all because a generated vhost still
spells ``location /api/ ...`` at the start of a line: nginx configs, Jinja templates, shell heredocs,
Python f-strings (``{{``) and Ansible block scalars. Boundary: a tracked text file with that line. A
vhost assembled from fragments that never spell the line whole would be invisible, as would any file
outside the tracked tree; ``docker/nginx/nginx-common.conf`` and docs only MENTION the location in
comments and are not matched, because the match is line-anchored and a ``#`` line does not start with it.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.slm_credential_actions import PROPOSAL_PATH, claim_path, delete_path
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_TEXT_SUFFIXES = (".conf", ".j2", ".sh", ".py", ".yml", ".yaml", ".tmpl", ".template")
#: A real ``location`` line whose path starts with a public API prefix, and is not itself the deny.
_PROXIES = re.compile(
    r"^[ \t]*location[ \t]+(?:\^~[ \t]+|=[ \t]+|~\*?[ \t]+)?\^?(?P<path>/(?:slm/|autobot-)?api[^\s{]*|/slm/(?=[ \t]*\{))",
    re.MULTILINE,
)
_PREFIX_TO_DENY = {
    "/slm/api": "/slm/api/internal/",
    "/slm/": "/slm/api/internal/",  # a bare `location /slm/` proxies the SLM API too
    "/autobot-api": "/autobot-api/internal/",
    "/api": "/api/internal/",
}


def _is_candidate(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(_TEXT_SUFFIXES) and not (name.endswith("_test.py") or name.startswith("test_"))


_SERVER_START = re.compile(r"^[ \t]*server[ \t]*\{\{?", re.MULTILINE)
_COMMENT = re.compile(r"(?:^|[ \t])#[^\n]*")


def _uncommented(text: str) -> str:
    """*text* without ``#`` comments: a commented-out deny or location must neither satisfy nor trigger the guard."""
    return _COMMENT.sub("", text)


def _server_blocks(text: str) -> list[str]:
    """One chunk per ``server {`` (to the next one); a file with none is a single chunk, as a fragment is."""
    starts = [m.start() for m in _SERVER_START.finditer(text)]
    if not starts:
        return [text]
    bounds = [0 if starts[0] == 0 else starts[0], *starts[1:], len(text)]
    return [text[a:b] for a, b in zip(bounds, bounds[1:])]


def _chunk_prefixes(chunk: str) -> set[str]:
    found = set()
    for match in _PROXIES.finditer(chunk):
        path = match.group("path")
        if path.endswith("/internal/"):
            continue
        found.add(next(prefix for prefix in _PREFIX_TO_DENY if path.startswith(prefix)))
    return found


def _proxied_prefixes(text: str) -> set[str]:
    """The public prefixes (``/api``, ``/slm/api``, ``/autobot-api``) *text* proxies; a deny line does not count."""
    return {prefix for chunk in _server_blocks(_uncommented(text)) for prefix in _chunk_prefixes(chunk)}


def _denied(text: str, prefix: str) -> bool:
    """A ``location ^~ <prefix> { ... return 404; }`` block in *text* (plain config, f-string ``{{`` or script).

    Other directives may precede the ``return``; the block may not close first (no ``}`` before it).
    """
    pattern = rf"location[ \t]+\^~[ \t]+{re.escape(prefix)}[ \t]*\{{\{{?[^{{}}]*?\breturn[ \t]+404;"
    return re.search(pattern, text) is not None


def _violations(text: str) -> list[str]:
    """Per proxying server block: the internal prefixes it proxies without denying them in that same block."""
    missing: set[str] = set()
    for chunk in _server_blocks(_uncommented(text)):
        missing |= {_PREFIX_TO_DENY[p] for p in _chunk_prefixes(chunk) if not _denied(chunk, _PREFIX_TO_DENY[p])}
    return sorted(missing)


def _proxying_files(root: Path) -> list[str]:
    try:
        candidates = [rel for rel in tracked_paths(root) if _is_candidate(rel)]
    except EmptyEnumeration:
        return []
    return [rel for rel in candidates if _proxied_prefixes((root / rel).read_text(encoding="utf-8", errors="replace"))]


REACH = declare(
    "edge-configs-proxying-api-20046",
    discover=_proxying_files,
    what="tracked text files that proxy a public /api location, each checked for the internal-path deny",
    floor=13,  # mid-window; repinned by scripts/repin_reach_floors.py
    growth=4,
    roots=("autobot-infrastructure", "autobot-slm-backend", "docker"),
)

_KEY_INJECTING = "autobot-slm-backend/ansible/roles/slm_manager/templates/autobot-slm.conf.j2"


def test_every_file_that_proxies_api_denies_the_internal_prefix() -> None:
    root = repo_root()
    files = REACH.examined(root)
    bad = {
        rel: missing
        for rel in files
        if (missing := _violations((root / rel).read_text(encoding="utf-8", errors="replace")))
    }
    assert not bad, f"these files proxy a public /api location without denying the internal path (#20046): {bad}"


def test_the_discovery_finds_the_known_positives() -> None:
    """Instrument check: the generated vhosts and the key-injecting template must be among the files read."""
    files = set(REACH.examined(repo_root()))
    for known in (
        _KEY_INJECTING,
        "autobot-infrastructure/shared/scripts/install-slm.sh",
        "autobot-infrastructure/shared/scripts/install-bare-metal.sh",
        "autobot-infrastructure/shared/scripts/zero_downtime_deploy.py",
        "autobot-slm-backend/ansible/playbooks/deploy-native-services.yml",
        "autobot-slm-backend/ansible/roles/backend/templates/nginx-backend.conf.j2",
    ):
        assert known in files, f"{known} is not discovered, so this guard would not read it"


def test_the_key_injecting_prefix_is_denied() -> None:
    text = (repo_root() / _KEY_INJECTING).read_text(encoding="utf-8")
    assert "X-Internal-API-Key" in text and "/autobot-api" in _proxied_prefixes(text)
    assert _denied(text, "/autobot-api/internal/")


def test_the_routes_sit_under_the_denied_prefix() -> None:
    for path in (PROPOSAL_PATH, claim_path("x"), delete_path("n")):
        assert path.startswith("/api/internal/")


_PLAIN = "    location /api/ {\n        proxy_pass http://x;\n    }\n"
_DENY = "    location ^~ /api/internal/ {\n        return 404;\n    }\n"


def test_contrast_a_new_unprotected_file_fails_and_a_protected_one_passes() -> None:
    assert _violations(_PLAIN) == ["/api/internal/"]
    assert _violations(_DENY + _PLAIN) == []
    assert _violations("location /slm/api/ { proxy_pass http://x; }") == ["/slm/api/internal/"]
    assert _violations("location /autobot-api/ { proxy_pass http://x; }") == ["/autobot-api/internal/"]


def test_contrast_every_spelling_of_the_location_line_is_seen() -> None:
    assert _proxied_prefixes("server {{\n    location /api/ {{\n        proxy_pass x;\n    }}\n}}") == {
        "/api"
    }  # f-string
    assert _proxied_prefixes("              location /api/ {\n") == {"/api"}  # YAML block scalar
    assert _proxied_prefixes("location /api/ws {\n") == {"/api"}  # a websocket location still reaches /api/internal/
    assert _proxied_prefixes("location ~ ^/api/(a|b)/ {\n") == {"/api"}
    assert _violations("location ^~ /api/internal/ {{\n        return 404;\n    }}\nlocation /api/ {{\n") == []
    assert _proxied_prefixes("# location /api/ { is described here\n") == set()  # a comment is not a proxy
    assert _proxied_prefixes(_DENY) == set()  # the deny itself is not a proxy


def test_contrast_a_deny_in_another_server_block_does_not_protect_this_one() -> None:
    two = "server {\n" + _DENY + _PLAIN + "}\nserver {\n" + _PLAIN + "}\n"
    assert _violations(two) == ["/api/internal/"]
    assert _violations("server {\n" + _DENY + _PLAIN + "}\nserver {\n" + _DENY + _PLAIN + "}\n") == []


def test_contrast_a_commented_deny_does_not_count() -> None:
    assert _violations("# location ^~ /api/internal/ { return 404; }\n" + _PLAIN) == ["/api/internal/"]
    assert _violations("    # location ^~ /api/internal/ {\n    #   return 404;\n" + _PLAIN) == ["/api/internal/"]


def test_contrast_a_deny_with_another_directive_before_the_return_counts() -> None:
    logged = "    location ^~ /api/internal/ {\n        access_log off;\n        return 404;\n    }\n"
    assert _violations(logged + _PLAIN) == []
    closed_first = "    location ^~ /api/internal/ {\n    }\n    location /x { return 404; }\n"
    assert _violations(closed_first + _PLAIN) == ["/api/internal/"]


def test_contrast_a_bare_slm_location_needs_the_slm_internal_deny() -> None:
    bare = "server {\n    location /slm/ {\n        proxy_pass http://slm/;\n    }\n}\n"
    assert _violations(bare) == ["/slm/api/internal/"]
    assert (
        _violations("server {\n    location ^~ /slm/api/internal/ { return 404; }\n" + bare[len("server {\n") :]) == []
    )
