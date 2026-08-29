# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15269 -- nothing stops a new consumer reading a credential straight from config.

``services/provider_key_vault.py``'s vault seam (``resolve_provider_key``) is opt-in.
Before this guard, a module that read a credential-shaped ``ssot_config`` field and
used it directly was indistinguishable, to CI, from one that resolved through the
vault -- which is how #15267 (web-search credentials) and #15268 (two HuggingFace
token fallbacks) both arose *after* the seam already existed. Neither
``scan_secrets_hook_test.py`` nor ``secrets_root_key_provisioned_test.py`` asks where
a consumer's credential comes from; this one does.

Mechanism
---------
1. :func:`credential_shaped_fields` derives the field universe from
   ``autobot_shared/ssot_config.py`` itself -- any field whose declared env-var alias
   ends in one of :data:`_CREDENTIAL_ALIAS_SUFFIXES` (the naming convention #15269's
   evidence names, plus ``_PASS`` so ``SEARXNG_BASIC_AUTH_PASS`` -- #15267's own
   evidence -- is not excluded by the shorter ``_PASSWORD`` alone).
2. :func:`_ssot_config_bindings` finds every identifier in a file bound to the
   ssot_config singleton: the flat proxy, plain or aliased (``from ... import config``
   / ``... import config as X``), the whole module aliased (``import ... as X``), and
   a local variable assigned from the factory, however that was imported/aliased
   (``cfg = get_config()`` / ``ssot = get_ssot_config()``) -- plus the factory names
   themselves, for the un-assigned chained-call shape (``get_config().field``, seen in
   ``initialization/lifespan.py``). An empty result means the file never touches
   ssot_config at all.
3. :func:`find_direct_reads` greps every git-tracked, non-test production ``.py`` file
   for a *direct* read of one of those fields through any binding
   :func:`_ssot_config_bindings` found -- ``config.<field>``, ``cfg.llm.<field>``
   (nested submodel access, real inside ``ssot_config.py``'s own
   ``AutoBotConfig.__getattr__`` delegation), ``get_config().auth.<field>`` (chained,
   unassigned), or ``getattr(config, "<field>", ...)`` -- that is **not** spanned by a
   ``resolve_provider_key(...)`` call, including a 120-column-wrapped one -- the shape
   every vault-routed call site in the repo already uses
   (``services/provider_key_vault.py``, ``llm_shared/provider_registry.py``,
   ``agent_loop/search/registry.py``).
4. Every match must be on :data:`ALLOWLIST`, keyed by ``(file, field)`` (not line
   number, which drifts on any unrelated edit) with a written reason -- either
   ``AUTH_BOOTSTRAP`` (the credential gates the vault/DB itself or is the platform's
   own internal-auth token, so vaulting it would be a confused-deputy cycle -- the
   same classification ``autobot-slm-backend/services/system_secrets_vault.py``
   documents for ``autobot_internal_api_key``), ``NOT_A_READ`` (the regex's only match
   is prose, e.g. a docstring cross-reference), or ``TRACKED_GAP #NNNN`` (a real gap,
   same defect class, not yet migrated -- named so the allowlist shrinks as the
   tracking issue closes rather than growing without bound).

An unlisted match fails the test with the offending ``file:line`` -- never the
credential value, which this module never reads (only field *names* and source
*lines*, neither of which is a secret).

The mutation this guard exists to catch
----------------------------------------
``test_a_new_bare_credential_read_is_rejected`` proves the detector on synthetic
source text reproducing the exact pre-fix shape of #15267 (an unwrapped
``getattr(config, "brave_search_api_key", "")``) and of #15268 (an unwrapped
``config.hf_token or config.huggingface_api_token``) -- both flagged -- and on a
wholly novel field name standing in for a consumer that does not exist yet, proving
the check is general rather than a fixed list of two prior mistakes.
``test_nested_submodel_access_is_rejected`` and
``test_get_config_import_and_chained_call_are_rejected`` do the same for the two
binding shapes a security review found this detector originally missed --
``cfg.llm.<field>`` (nested submodel access, real via ``AutoBotConfig.__getattr__``)
and a file that only imports ``get_config`` -- both reproducing the real
pre-fix line of ``voice_processing/realtime/openai_provider.py`` (fixed in this
same PR) and ``initialization/lifespan.py`` (an existing, allowlisted gap).
"""

from __future__ import annotations

import re
import subprocess  # nosec B404 - fixed argv (git ls-files), no shell, no caller input
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SSOT_CONFIG = REPO_ROOT / "autobot_shared" / "ssot_config.py"

#: Alias suffixes that mark a ssot_config field as credential-shaped. ``_PASS`` is
#: added to the issue's stated ``_PASSWORD`` so ``SEARXNG_BASIC_AUTH_PASS`` -- named
#: in #15267's own evidence -- is not silently excluded by the shorter suffix alone.
_CREDENTIAL_ALIAS_SUFFIXES = ("_API_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_PASS")

_FIELD_ALIAS_RE = re.compile(r'^\s*([a-z_0-9]+):\s*[^=]+=\s*Field\([^)]*alias="([A-Z0-9_]+)"', re.MULTILINE)

_SKIP_PATH_SUBSTRINGS = ("/tests/", "repo_tests/", "/ssot_config.py")

#: ``from autobot_shared.ssot_config import <names>`` -- captures the whole imported
#: name list so aliases (``config as X``, ``get_config as Y``) can be pulled out of it.
_FROM_IMPORT_RE = re.compile(r"from\s+autobot_shared\.ssot_config\s+import\s+([^\n]+)")
#: ``import autobot_shared.ssot_config as X`` -- the whole-module-alias form.
_IMPORT_AS_RE = re.compile(r"import\s+autobot_shared\.ssot_config\s+as\s+(\w+)")
#: The two factory functions, however aliased on import (``get_config as ssot``).
_FACTORY_FUNCTION_NAMES = ("get_config", "get_ssot_config")


def credential_shaped_fields(ssot_text: str) -> dict[str, str]:
    """Map field-name -> alias for every ssot_config field shaped like a credential."""
    fields: dict[str, str] = {}
    for match in _FIELD_ALIAS_RE.finditer(ssot_text):
        field, alias = match.group(1), match.group(2)
        if alias.endswith(_CREDENTIAL_ALIAS_SUFFIXES):
            fields[field] = alias
    return fields


def _ssot_config_bindings(text: str) -> tuple[set[str], set[str]]:
    """``(roots, factories)`` -- every identifier in *text* bound to the ssot_config
    singleton, and every name the ``get_config``/``get_ssot_config`` factory itself can
    be called under.

    Three binding shapes seen in production: the flat proxy, plain or aliased
    (``from ... import config`` / ``... import config as X``); the whole module
    aliased (``import ... as X``); and a local variable assigned from the factory,
    however that factory was imported/aliased (``cfg = get_config()`` --
    ``voice_processing/realtime/openai_provider.py``, ``initialization/lifespan.py``).
    An empty ``roots`` (with an empty ``factories``) means the file never touches
    ssot_config at all.
    """
    roots: set[str] = set()
    factories: set[str] = set()
    for match in _FROM_IMPORT_RE.finditer(text):
        imported = match.group(1)
        alias = re.search(r"\bconfig\s+as\s+(\w+)", imported)
        if alias:
            roots.add(alias.group(1))
        elif re.search(r"(?<![\w.])config\b", imported):
            roots.add("config")
        for factory in _FACTORY_FUNCTION_NAMES:
            factory_alias = re.search(rf"\b{factory}\s+as\s+(\w+)", imported)
            if factory_alias:
                factories.add(factory_alias.group(1))
            elif re.search(rf"(?<![\w.]){factory}\b", imported):
                factories.add(factory)
    for match in _IMPORT_AS_RE.finditer(text):
        roots.add(match.group(1))
    for factory in factories:
        roots.update(m.group(1) for m in re.finditer(rf"\b(\w+)\s*=\s*{re.escape(factory)}\(\)", text))
    return roots, factories


def _read_pattern(field: str, roots: set[str], factories: set[str]) -> re.Pattern[str]:
    """A direct read of *field* through any binding in *roots*/*factories*.

    Matches an arbitrary chain of ``.submodel`` segments before the field (nested
    submodel access, e.g. ``cfg.llm.openai_api_key`` -- real, via
    ``AutoBotConfig.__getattr__`` delegation for the flat form and directly for the
    nested one) and the unassigned chained-call shape (``get_config().field``).
    Never matches ``self.config.<field>`` (a different, per-instance object almost
    everywhere it appears) or the field name buried inside a longer identifier or
    string literal (``(?<![\\w.])`` rejects both).
    """
    parts: list[str] = []
    if roots:
        root_alt = "|".join(re.escape(r) for r in sorted(roots))
        chain = rf"(?:{root_alt})(?:\.\w+)*"
        parts.append(rf"(?<![\w.]){chain}\.{field}\b")
        parts.append(rf'getattr\(\s*{chain}\s*,\s*["\']{field}["\']')
    if factories:
        factory_alt = "|".join(re.escape(f) for f in sorted(factories))
        parts.append(rf"(?<![\w.])(?:{factory_alt})\(\)(?:\.\w+)*\.{field}\b")
    if not parts:
        return re.compile(r"(?!)")  # a pattern that can never match anything
    return re.compile("|".join(parts))


def _vault_routed_line_numbers(lines: list[str]) -> set[int]:
    """1-indexed line numbers spanned by a ``resolve_provider_key(...)`` call.

    Tracks paren depth from the call's opening ``(`` so a 120-column-wrapped call's
    continuation line -- which does not itself contain the text
    ``resolve_provider_key(`` -- is still recognised as vault-routed rather than as
    an unwrapped read of its argument.
    """
    routed: set[int] = set()
    lineno = 0
    while lineno < len(lines):
        start = lines[lineno].find("resolve_provider_key(")
        if start == -1:
            lineno += 1
            continue
        depth = 0
        cursor = lineno
        offset = start + len("resolve_provider_key")
        while cursor < len(lines):
            segment = lines[cursor][offset:]
            depth += segment.count("(") - segment.count(")")
            routed.add(cursor + 1)
            offset = 0
            if depth <= 0:
                break
            cursor += 1
        lineno = cursor + 1
    return routed


def find_direct_reads(text: str, fields: dict[str, str]) -> list[tuple[str, int, str]]:
    """Every ``(field, line_no, line)`` in *text* reading *fields* directly.

    Discovers *text*'s own ssot_config bindings (see :func:`_ssot_config_bindings`)
    rather than assuming a fixed set of names, so a file is skipped entirely --
    rather than false-positiving on an unrelated same-named local -- when it never
    touches ssot_config at all. A line spanned by a ``resolve_provider_key(...)``
    call (see :func:`_vault_routed_line_numbers`) is vault-routed and excluded -- the
    call-site shape every seam consumer in the repo already uses.
    """
    roots, factories = _ssot_config_bindings(text)
    if not roots and not factories:
        return []
    hits: list[tuple[str, int, str]] = []
    lines = text.splitlines()
    routed_lines = _vault_routed_line_numbers(lines)
    for field in fields:
        pattern = _read_pattern(field, roots, factories)
        for lineno, line in enumerate(lines, start=1):
            if lineno in routed_lines:
                continue
            if pattern.search(line):
                hits.append((field, lineno, line.strip()))
    return hits


def _tracked_python_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "*.py"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def _is_production_file(rel_path: str) -> bool:
    if rel_path.endswith("_test.py") or Path(rel_path).name.startswith("test_"):
        return False
    return not any(needle in rel_path for needle in _SKIP_PATH_SUBSTRINGS)


def production_credential_reads() -> dict[tuple[str, str], list[tuple[int, str]]]:
    """Every ``(repo-relative file, field) -> [(line_no, line), ...]`` direct read."""
    fields = credential_shaped_fields(SSOT_CONFIG.read_text(encoding="utf-8"))
    found: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for rel in _tracked_python_files():
        if not _is_production_file(rel):
            continue
        path = REPO_ROOT / rel
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for field, lineno, line in find_direct_reads(text, fields):
            found.setdefault((rel, field), []).append((lineno, line))
    return found


# ---------------------------------------------------------------------------
# The allowlist. Every entry is a written classification, not a bare pass.
# ---------------------------------------------------------------------------

_AUTH_BOOTSTRAP = "AUTH_BOOTSTRAP"  # gates the vault/DB itself; vaulting it is circular
_NOT_A_READ = "NOT_A_READ"  # the regex's only match here is prose, not code
_TRACKED = "TRACKED_GAP"  # a real gap, same defect class, named issue tracks its fix

#: ``(repo-relative file, ssot_config field name) -> reason``. No credential values
#: appear anywhere in this table -- only field names and source-code file paths.
ALLOWLIST: dict[tuple[str, str], str] = {
    # --- auth-bootstrap: internal/platform authentication, not a third-party
    # --- provider credential. Same classification IRREDUCIBLE_KEYS documents for
    # --- autobot_internal_api_key in autobot-slm-backend/services/system_secrets_vault.py.
    ("autobot-backend/agents/base_agent.py", "mcp_token"): f"{_AUTH_BOOTSTRAP}: internal MCP server shared secret",
    ("autobot-backend/mcp/autobot_server.py", "mcp_token"): f"{_AUTH_BOOTSTRAP}: internal MCP server shared secret",
    ("autobot-backend/services/execution/claude_code_backend.py", "mcp_token"): (
        f"{_AUTH_BOOTSTRAP}: internal MCP server shared secret"
    ),
    ("autobot-backend/auth_middleware.py", "jwt_secret"): (
        f"{_AUTH_BOOTSTRAP}: platform user-session signing key"
    ),
    ("autobot-backend/services/slm_client.py", "jwt_secret"): (
        f"{_AUTH_BOOTSTRAP}: platform user-session signing key, reused to mint SLM service JWTs "
        "(two of the three matches in this file are a docstring cross-reference, not a second read)"
    ),
    ("autobot-backend/services/run_jwt.py", "run_jwt_secret"): f"{_AUTH_BOOTSTRAP}: run-worker JWT signing key",
    ("autobot-backend/services/mcp_isolated_runtime.py", "run_jwt_secret"): (
        f"{_AUTH_BOOTSTRAP}: run-worker JWT signing key"
    ),
    ("autobot-backend/middleware/service_auth_enforcement.py", "service_auth_override_token"): (
        f"{_AUTH_BOOTSTRAP}: internal service-to-service auth override"
    ),
    ("autobot-backend/orchestration/dag_executor.py", "slm_auth_token"): (
        f"{_AUTH_BOOTSTRAP}: internal backend-to-SLM service auth token"
    ),
    ("autobot-backend/services/command_extraction_service.py", "slm_auth_token"): (
        f"{_AUTH_BOOTSTRAP}: internal backend-to-SLM service auth token"
    ),
    ("autobot-backend/user_management/config.py", "postgres_password"): (
        f"{_AUTH_BOOTSTRAP}: the vault's own Postgres backing store cannot gate itself"
    ),
    ("autobot-backend/auth_middleware.py", "internal_api_key"): (
        f"{_AUTH_BOOTSTRAP}: the exact confused-deputy example "
        "autobot-slm-backend/services/system_secrets_vault.py documents for this same credential"
    ),
    ("autobot-backend/initialization/lifespan.py", "slm_auth_token"): (
        f"{_AUTH_BOOTSTRAP}: internal backend-to-SLM service auth token, same as the two siblings above"
    ),
    ("autobot-backend/user_management/services/seed.py", "admin_password"): (
        f"{_AUTH_BOOTSTRAP}: bootstrap admin-account creation, read before any auth subsystem exists"
    ),
    ("autobot_shared/security/password_weakness.py", "admin_password"): (
        f"{_AUTH_BOOTSTRAP}: same bootstrap admin password as seed.py, checked for weakness"
    ),
    # --- auth-bootstrap: internal data-layer service credentials (Redis/ChromaDB),
    # --- same class as the Postgres password above -- the app's own storage
    # --- layer must be reachable before anything, including the vault, can start.
    ("autobot-backend/api/npu_workers.py", "password"): f"{_AUTH_BOOTSTRAP}: Redis connection password",
    ("autobot-backend/celery_app.py", "password"): f"{_AUTH_BOOTSTRAP}: Redis connection password",
    ("autobot-backend/config/__init__.py", "password"): f"{_AUTH_BOOTSTRAP}: Redis connection password",
    ("autobot-backend/config/defaults.py", "password"): f"{_AUTH_BOOTSTRAP}: Redis connection password",
    ("autobot-backend/config/service_config.py", "password"): f"{_AUTH_BOOTSTRAP}: Redis connection password",
    ("autobot-backend/knowledge/base.py", "password"): f"{_AUTH_BOOTSTRAP}: Redis connection password",
    ("autobot-backend/utils/async_chromadb_client.py", "chromadb_auth_token"): (
        f"{_AUTH_BOOTSTRAP}: internal ChromaDB data-layer service credential"
    ),
    ("autobot-backend/utils/chromadb_auth.py", "chromadb_auth_token"): (
        f"{_AUTH_BOOTSTRAP}: internal ChromaDB data-layer service credential"
    ),
    ("autobot-backend/utils/chromadb_client.py", "chromadb_auth_token"): (
        f"{_AUTH_BOOTSTRAP}: internal ChromaDB data-layer service credential"
    ),
    # --- prose the regex matches textually but which reads nothing.
    ("autobot-backend/services/mcp_isolated_runtime.py", "jwt_secret"): (
        f"{_NOT_A_READ}: docstring prose contrasting run_jwt_secret with the platform session key"
    ),
    ("autobot-backend/services/run_jwt.py", "jwt_secret"): (
        f"{_NOT_A_READ}: docstring prose contrasting run_jwt_secret with the platform session key"
    ),
    # --- tracked gap: third-party/service credentials, same defect class as
    # --- #15267/#15268, not yet migrated. See #15276.
    ("autobot-backend/llm_shared/adapters/anthropic_adapter.py", "anthropic_api_key"): (
        f"{_TRACKED} #15276: AdapterRegistry connectivity-test path"
    ),
    ("autobot-backend/llm_shared/adapters/groq_adapter.py", "groq_api_key"): (
        f"{_TRACKED} #15276: AdapterRegistry connectivity-test path"
    ),
    ("autobot-backend/llm_shared/adapters/openai_adapter.py", "openai_api_key"): (
        f"{_TRACKED} #15276: AdapterRegistry connectivity-test path"
    ),
    ("autobot-backend/llm_shared/providers/anthropic.py", "anthropic_api_key"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/groq.py", "groq_api_key"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/openai.py", "openai_api_key"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/mistral.py", "mistral_api_key"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/custom_openai.py", "custom_openai_api_key"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/openrouter.py", "openrouter_api_key"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/huggingface.py", "hf_token"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/huggingface.py", "huggingface_api_token"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/nous_portal.py", "hf_token"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/nous_portal.py", "huggingface_api_token"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/llm_shared/providers/nous_portal.py", "nous_api_key"): (
        f"{_TRACKED} #15276: Provider class's fallback for construction outside the registry"
    ),
    ("autobot-backend/services/execution/claude_code_backend.py", "anthropic_api_key"): (
        f"{_TRACKED} #15276: execution backend reads the key directly rather than via the registry"
    ),
    ("autobot-backend/services/provider_health/providers.py", "anthropic_api_key"): (
        f"{_TRACKED} #15276: health-check probe reads config directly rather than via the registry"
    ),
    ("autobot-backend/services/provider_health/providers.py", "openai_api_key"): (
        f"{_TRACKED} #15276: health-check probe reads config directly rather than via the registry"
    ),
    ("autobot-backend/services/provider_health/providers.py", "google_api_key"): (
        f"{_TRACKED} #15276: health-check probe reads config directly rather than via the registry"
    ),
    ("autobot-backend/agent_loop/slack_hook.py", "slack_bot_token"): f"{_TRACKED} #15276: Slack bot token",
    ("autobot-backend/security/threat_intelligence.py", "virustotal_api_key"): (
        f"{_TRACKED} #15276: threat-intel API key"
    ),
    ("autobot-backend/security/threat_intelligence.py", "urlvoid_api_key"): (
        f"{_TRACKED} #15276: threat-intel API key"
    ),
    ("autobot-backend/services/notification_service.py", "smtp_password"): f"{_TRACKED} #15276: SMTP credential",
    ("autobot-backend/initialization/lifespan.py", "anthropic_api_key"): (
        f"{_TRACKED} #15276: AdapterRegistry gating check (adapter-listing only, not the LLM-call routing path)"
    ),
    ("autobot-backend/initialization/lifespan.py", "groq_api_key"): (
        f"{_TRACKED} #15276: AdapterRegistry gating check (adapter-listing only, not the LLM-call routing path)"
    ),
    ("autobot-backend/initialization/lifespan.py", "openai_api_key"): (
        f"{_TRACKED} #15276: AdapterRegistry gating check (adapter-listing only, not the LLM-call routing path)"
    ),
    ("autobot-backend/integrations/capability_registry.py", "slack_bot_token"): (
        f"{_TRACKED} #15276: the third CredentialGatedRegistry sibling (see "
        "autobot_shared/credential_gated_registry.py's own docstring) never migrated"
    ),
    ("autobot-backend/integrations/capability_registry.py", "discord_bot_token"): (
        f"{_TRACKED} #15276: the third CredentialGatedRegistry sibling (see "
        "autobot_shared/credential_gated_registry.py's own docstring) never migrated"
    ),
    ("autobot-backend/knowledge/base.py", "anthropic_api_key"): (
        f"{_TRACKED} #15276: LlamaIndex LLM configuration reads the key directly"
    ),
    ("autobot-backend/knowledge/base.py", "openai_api_key"): (
        f"{_TRACKED} #15276: LlamaIndex LLM/embedding configuration reads the key directly"
    ),
}


def test_the_ssot_config_field_scan_finds_known_credential_fields() -> None:
    """Guard the guard: an empty field set would make every other assertion vacuous."""
    fields = credential_shaped_fields(SSOT_CONFIG.read_text(encoding="utf-8"))
    assert "openai_api_key" in fields
    assert "searxng_basic_auth_pass" in fields
    assert len(fields) >= 20, f"only {len(fields)} credential-shaped fields found -- the alias regex likely broke"


def test_every_direct_production_read_is_vault_routed_or_allowlisted() -> None:
    """The regression guard: a new bare credential read must be on ALLOWLIST or fail.

    This is the check that would have caught #15267 (five web-search credentials read
    via bare ``getattr(config, ...)``) and #15268 (two HuggingFace token fallbacks read
    via bare ``config.hf_token or config.huggingface_api_token``) before either
    shipped -- both were direct reads of credential-shaped fields with no
    ``resolve_provider_key(`` on the line, in production files, and neither was on any
    allowlist because no allowlist existed.
    """
    found = production_credential_reads()
    unlisted = {key: lines for key, lines in found.items() if key not in ALLOWLIST}
    assert not unlisted, "direct (non-vault) credential reads with no allowlist entry:\n" + "\n".join(
        f"  {file}:{lineno} (field={field}): {line}"
        for (file, field), lines in sorted(unlisted.items())
        for lineno, line in lines
    )


def test_allowlist_entries_still_correspond_to_a_real_match() -> None:
    """A stale entry (the read it excused was already fixed) should shrink, not linger.

    Keeps the allowlist an accurate map of today's gaps rather than a write-only log:
    a fixed site should be deleted from ALLOWLIST in the same PR that fixes it.
    """
    found = production_credential_reads()
    stale = sorted(key for key in ALLOWLIST if key not in found)
    assert not stale, f"allowlist entries with no matching read left -- delete them: {stale}"


def test_a_new_bare_credential_read_is_rejected() -> None:
    """Prove the detector on synthetic source, reproducing #15267 and #15268 verbatim.

    None of the three snippets below is a real credential -- ``brave_search_api_key``
    and ``hf_token``/``huggingface_api_token`` are ssot_config *field names*, and
    ``new_service_api_key`` is a field that does not exist, standing in for a consumer
    that does not exist yet either.
    """
    fields = {
        "brave_search_api_key": "BRAVE_SEARCH_API_KEY",
        "hf_token": "HF_TOKEN",
        "huggingface_api_token": "HUGGINGFACE_API_TOKEN",
        "new_service_api_key": "NEW_SERVICE_API_KEY",
    }

    pre_fix_15267 = (
        "from autobot_shared.ssot_config import config\n"
        'brave_key = getattr(config, "brave_search_api_key", "")\n'
    )
    pre_fix_15268 = (
        "from autobot_shared.ssot_config import config\n"
        "hf_token = config.hf_token or config.huggingface_api_token\n"
    )
    novel_consumer = "from autobot_shared.ssot_config import config\n" "key = config.new_service_api_key\n"

    for label, snippet, expected_field in (
        ("#15267 shape", pre_fix_15267, "brave_search_api_key"),
        ("#15268 shape", pre_fix_15268, "hf_token"),
        ("a wholly novel consumer", novel_consumer, "new_service_api_key"),
    ):
        hits = find_direct_reads(snippet, fields)
        hit_fields = {field for field, _lineno, _line in hits}
        assert expected_field in hit_fields, f"{label} was not flagged by find_direct_reads: {snippet!r}"


def test_the_seam_call_site_shape_is_not_flagged() -> None:
    """The positive control: today's real vault-routed call sites must NOT trip this.

    Without this, the guard could be trivially "satisfied" by a detector that flags
    everything, allowlist notwithstanding.
    """
    fields = {"anthropic_api_key": "ANTHROPIC_API_KEY"}
    routed = (
        "from autobot_shared.ssot_config import config\n"
        "from services.provider_key_vault import resolve_provider_key\n"
        "anthropic_key = resolve_provider_key(\"ANTHROPIC_API_KEY\", config.anthropic_api_key)\n"
    )
    assert find_direct_reads(routed, fields) == []


def test_nested_submodel_access_is_rejected() -> None:
    """A file bound via ``get_config()`` reading a nested submodel field directly.

    Reproduces the exact pre-fix shape of
    ``voice_processing/realtime/openai_provider.py`` (found by this widened
    detector, then fixed in this same PR): ``cfg = get_config()`` followed by
    ``cfg.llm.openai_api_key``, never spelled ``config.openai_api_key``, so the
    original single-segment-only pattern missed it entirely.
    """
    fields = {"openai_api_key": "OPENAI_API_KEY", "admin_password": "AUTOBOT_ADMIN_PASSWORD"}
    nested_via_local_var = (
        "from autobot_shared.ssot_config import get_config\ncfg = get_config()\nx = cfg.llm.openai_api_key\n"
    )
    nested_via_flat_singleton = (
        "from autobot_shared.ssot_config import config\ny = config.auth.admin_password\n"
    )
    hits = find_direct_reads(nested_via_local_var, fields)
    assert {"openai_api_key"} == {field for field, _lineno, _line in hits}
    hits = find_direct_reads(nested_via_flat_singleton, fields)
    assert {"admin_password"} == {field for field, _lineno, _line in hits}


def test_get_config_import_and_chained_call_are_rejected() -> None:
    """A file that only imports ``get_config`` (never ``config``) is not skipped.

    Reproduces ``initialization/lifespan.py:1353``'s unassigned chained-call shape
    (``get_config().field``, no local variable at all) -- the other blind spot the
    original single-import-form gate missed.
    """
    fields = {"slm_auth_token": "SLM_AUTH_TOKEN"}
    chained_call = "from autobot_shared.ssot_config import get_config\nx = get_config().slm_auth_token\n"
    hits = find_direct_reads(chained_call, fields)
    assert {"slm_auth_token"} == {field for field, _lineno, _line in hits}


def test_a_file_with_no_ssot_config_binding_is_never_scanned() -> None:
    """The other half of the same guard: no false positive on an unrelated local.

    A bare ``cfg`` that was never bound to ``get_config()``/``config`` must not be
    mistaken for the singleton merely because some *other* file in the sweep uses
    that name -- root discovery is per-file, not a fixed global name list.
    """
    fields = {"openai_api_key": "OPENAI_API_KEY"}
    unrelated = "cfg = SomeUnrelatedObject()\nx = cfg.llm.openai_api_key\n"
    assert find_direct_reads(unrelated, fields) == []
