# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""scripts/ci/build_wiki.py renders the wiki from docs/ (#19278)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location("build_wiki_19278", Path(__file__).with_name("build_wiki.py"))
bw = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bw)

URL = "https://forge.example/org/repo"
SHA = "a" * 40  # a commit-shaped id; a real-looking hex literal trips detect-secrets


def test_relative_links_point_at_the_repository_at_the_commit():
    md = "[a](../user-guide/x.md) [b](./y.md#part) [c](https://example.com) [d](#local) [e](/abs)"
    out = bw.rewrite_links(md, "docs/user/getting-started.md", SHA, URL)
    assert f"[a]({URL}/blob/{SHA}/docs/user-guide/x.md)" in out
    assert f"[b]({URL}/blob/{SHA}/docs/user/y.md#part)" in out
    assert "[c](https://example.com)" in out and "[d](#local)" in out and "[e](/abs)" in out


def test_api_paths_are_read_from_the_generated_types():
    types = 'export interface paths {\n    "/api/health": {\n    "/api/knowledge/search": {\n        "/api/nested": {\n'
    assert bw.api_paths(types) == ["/api/health", "/api/knowledge/search"]


def test_reference_links_are_rewritten_and_fenced_code_is_left_alone():
    md = "See [x][1].\n\n[1]: ../a.md#top\n[2]: https://example.com\n\n```\n[k](./code.md)\n```\n"
    out = bw.rewrite_links(md, "docs/user/g.md", SHA, URL)
    assert f"[1]: {URL}/blob/{SHA}/docs/a.md#top" in out
    assert "[2]: https://example.com" in out
    assert "[k](./code.md)" in out


def test_private_addresses_and_home_paths_are_redacted_and_scanned():
    private = ".".join(["192", "168", "1", "20"])  # built at runtime: no address literal in source
    public = ".".join(["8", "8", "8", "8"])
    home = "/".join(["", "home", "someone"])  # built at runtime: no developer path literal in source
    text = f"host {private} and {public}; see {home}/x and /opt/autobot/y"
    out = bw.redact(text)
    assert private not in out and "<private-ip>" in out and public in out
    assert home not in out and "/opt/autobot/y" in out
    assert bw.scan_output("P", out) == []
    assert bw.scan_output("P", text) == [f"P: {private}", f"P: {home}"]


def test_the_api_page_check_is_self_consistent_with_its_path_list():
    paths = ["/api/health", "/api/knowledge/search"]
    page = bw.render_api(paths, SHA, URL)
    assert bw.check_api_page(page, paths) == []
    assert bw.check_api_page(page + "\n- `/api/v1/made-up`\n", paths) == ["/api/v1/made-up"]
    assert "## /api/knowledge" in page and "Generated" in page


def test_every_page_is_built_with_its_source_header(tmp_path):
    written = bw.build(tmp_path, SHA, URL)
    assert {"Home", "API", "Configuration", "Deployment"} <= set(written)
    for name in written:
        text = (tmp_path / f"{name}.md").read_text(encoding="utf-8")
        assert text.startswith("> **Generated** from") and SHA[:12] in text, name


def test_every_manifest_source_exists():
    import yaml

    pages = yaml.safe_load(bw.MANIFEST.read_text(encoding="utf-8"))["pages"]
    missing = [s for s in pages.values() if s != "api" and not (bw.ROOT / s).is_file()]
    assert not missing, f"manifest names missing sources: {missing}"


def test_the_repo_url_comes_from_actions_env_or_the_origin_remote(monkeypatch):
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://forge.example")
    monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
    assert bw.repo_url() == "https://forge.example/org/repo"
    monkeypatch.delenv("GITHUB_SERVER_URL")
    assert bw.repo_url().startswith("https://") and not bw.repo_url().endswith(".git")


def test_an_address_glued_to_a_word_is_still_redacted():
    private = ".".join(["10", "0", "0", "7"])  # built at runtime: no address literal in source
    assert bw.redact(f"host{private}:8443") == "host<private-ip>:8443"
    assert bw.redact("v1.10.0.0.1") == "v1.10.0.0.1"  # a longer dotted run is not an address


def test_the_config_page_check_reports_only_unregistered_variables():
    page = "| Variable | ... |\n|---|---|\n| `AUTOBOT_KNOWN` | x |\n| `AUTOBOT_GHOST` | y |\nprose `AUTOBOT_PROSE`\n"
    assert bw.check_config_page(page, {"AUTOBOT_KNOWN"}) == ["AUTOBOT_GHOST"]
    assert bw.check_config_page(page, {"AUTOBOT_KNOWN", "AUTOBOT_GHOST"}) == []


def test_the_published_config_page_documents_only_registered_variables():
    """#19278 AC3: the configuration page names no variable the code does not register."""
    page = (bw.ROOT / bw.CONFIG_SOURCE).read_text(encoding="utf-8")
    registered = bw._registered()
    assert len(bw.check_config_page(page, set())) > 100, "the row parser no longer matches ENV_VARS.md"
    assert bw.check_config_page(page, registered) == []


def test_the_config_page_is_the_manifest_configuration_source():
    import yaml

    pages = yaml.safe_load(bw.MANIFEST.read_text(encoding="utf-8"))["pages"]
    assert pages["Configuration"] == bw.CONFIG_SOURCE
