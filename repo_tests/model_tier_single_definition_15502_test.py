# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The model tier map has one definition, and its mirrors still equal it (#15502).

`autobot_shared/ssot_config.py` defines the tier models once, as module constants. Several files
hand-copy them because they cannot import Python: the Ansible role defaults and two defaults
in `env_registry.py`. The frontend holds no model literal at all: it fetches the one name it
needs from the backend (owner decision 2026-10-10). This guard parses (never imports) the
canonical file and asserts that

* each of the nine names is assigned exactly once at module level;
* every recorded mirror equals the tier it mirrors;
* no TypeScript or Vue source under `autobot-frontend/src` holds a local-model string literal;
* `complete.yaml` names no model at all (owner decision 2026-10-10: its model sections were dead
  and are deleted), with a contrast fixture proving the scan sees a model key when one exists;
* no backend module grows a hand-written tier map: a dict literal with two or more values that
  are canonical local model names. Readers use the constants, so none exists today.

Nothing here changes a model value; it only makes a drift fail instead of rotting.
"""

from __future__ import annotations

import ast
import functools
import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_SSOT = "autobot_shared/ssot_config.py"
_TIERS = (
    "DEFAULT_LLM_MODEL",
    "DEFAULT_EMBEDDING_MODEL",
    "TRIVIAL_MODEL",
    "ROUTING_MODEL",
    "CLASSIFICATION_MODEL",
    "LIGHT_PROCESSING_MODEL",
    "INSTRUCTION_MODEL",
    "SYSTEM_MODEL",
    "QUALITY_MODEL",
)
_AI_STACK = "autobot-slm-backend/ansible/roles/ai-stack/defaults/main.yml"
_AGENT_CONFIG_ROLE = "autobot-slm-backend/ansible/roles/agent_config/defaults/main.yml"
_ENV_REGISTRY = "autobot_shared/env_registry.py"
_AGENTS_YAML = "autobot-infrastructure/shared/config/agents.yaml"
_COMPLETE_YAML = "autobot-infrastructure/shared/config/complete.yaml"
_LLM_ROLE = "autobot-slm-backend/ansible/roles/llm/defaults/main.yml"
_PULL_PLAYBOOKS = (
    "autobot-slm-backend/ansible/playbooks/deploy-native-services.yml",
    "autobot-slm-backend/ansible/playbooks/deploy-hybrid-docker.yml",
)
_SETTINGS_JSON = "autobot-infrastructure/shared/config/settings.json"
#: The `# <Tier> tier (<model>)` comment ai-stack puts above each group of vars -> the constant it names.
_COMMENT_TIER = {
    "Quality": "QUALITY_MODEL",
    "Instruction": "INSTRUCTION_MODEL",
    "Classification": "CLASSIFICATION_MODEL",
    "Light": "LIGHT_PROCESSING_MODEL",
    "System": "SYSTEM_MODEL",
}
#: env_registry's two hand-copied defaults (they cannot import ssot_config) -> the constant they copy.
_ENV_MIRRORS = {"AUTOBOT_CLASSIFICATION_MODEL": "CLASSIFICATION_MODEL", "AUTOBOT_ORCHESTRATOR_MODEL": "ROUTING_MODEL"}


def _read(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


def _load_yaml(rel: str) -> Any:
    return yaml.safe_load(_read(rel))


def _module_assignments(source: str) -> dict[str, list[ast.expr]]:
    """Every module-level assignment value per name, descending into if/try/with but not def/class."""
    found: dict[str, list[ast.expr]] = {}

    def visit(stmts: list[ast.stmt]) -> None:
        for node in stmts:
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and node.value is not None:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for tgt in targets:
                    if isinstance(tgt, ast.Name):
                        found.setdefault(tgt.id, []).append(node.value)
            elif isinstance(node, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
                for body in ("body", "orelse", "finalbody"):
                    visit(getattr(node, body, []))
                for handler in getattr(node, "handlers", []):
                    visit(handler.body)

    visit(ast.parse(source).body)
    return found


def _resolve(assigned: dict[str, list[ast.expr]], name: str) -> str:
    """The string a tier constant holds, following a `NAME = OTHER_NAME` alias."""
    value = assigned[name][-1]
    if isinstance(value, ast.Name):
        return _resolve(assigned, value.id)
    assert isinstance(value, ast.Constant) and isinstance(value.value, str), f"{name} is not a string literal"
    return value.value


@functools.lru_cache(maxsize=1)
def _canonical() -> dict[str, str]:
    assigned = _module_assignments(_read(_SSOT))
    return {name: _resolve(assigned, name) for name in _TIERS}


def _local_models() -> frozenset[str]:
    return frozenset(_canonical().values())


# --- (a) one definition ----------------------------------------------------


def test_each_tier_name_is_assigned_exactly_once() -> None:
    assigned = _module_assignments(_read(_SSOT))
    counts = {name: len(assigned.get(name, [])) for name in _TIERS}
    assert counts == dict.fromkeys(_TIERS, 1), f"#15502: tier names must be assigned once in {_SSOT}: {counts}"


def test_the_assignment_counter_sees_a_second_definition() -> None:
    twice = 'TRIVIAL_MODEL = "a"\nif True:\n    TRIVIAL_MODEL = "b"\n'
    assert len(_module_assignments(twice)["TRIVIAL_MODEL"]) == 2
    assert len(_module_assignments('def f():\n    TRIVIAL_MODEL = "b"\n').get("TRIVIAL_MODEL", [])) == 0


# --- (b) mirrors -----------------------------------------------------------


def _ai_stack_vars() -> list[tuple[str, str, str]]:
    """`(var, value, tier constant)` for every `ai_*_model`, tier read from the file's own comment."""
    out: list[tuple[str, str, str]] = []
    tier = ""
    for line in _read(_AI_STACK).splitlines():
        comment = re.match(r"# (\w+) tier \(([^)]+)\)", line)
        if comment:
            assert _canonical()[_COMMENT_TIER[comment.group(1)]] == comment.group(2), f"stale comment: {line}"
            tier = _COMMENT_TIER[comment.group(1)]
        var = re.match(r'(ai_\w+_model):\s*"([^"]+)"', line)
        if var:
            out.append((var.group(1), var.group(2), tier))
    return out


def test_ai_stack_model_vars_equal_their_tier() -> None:
    """Mirror: Ansible defaults cannot import ssot_config; the file's own tier comments map var -> tier."""
    rows = _ai_stack_vars()
    assert len(rows) == 15, f"expected 15 ai_*_model vars, parsed {len(rows)}"
    bad = {v: (val, _canonical()[t]) for v, val, t in rows if val != _canonical()[t]}
    assert not bad, f"#15502: ai-stack vars differ from their tier (var: (value, canonical)): {bad}"


def test_agent_config_ollama_models_are_the_canonical_local_models() -> None:
    """Mirror: the provisioning list must pull exactly the models the tiers can select."""
    assert set(_load_yaml(_AGENT_CONFIG_ROLE)["ollama_models"]) == _local_models()


def _env_registry_defaults() -> dict[str, str]:
    out: dict[str, str] = {}
    for call in ast.walk(ast.parse(_read(_ENV_REGISTRY))):
        if isinstance(call, ast.Call) and getattr(call.func, "id", "") == "EnvVarSpec":
            kw = {k.arg: k.value for k in call.keywords}
            name, default = kw.get("name"), kw.get("default")
            if isinstance(name, ast.Constant) and isinstance(default, ast.Constant):
                out[name.value] = default.value
    return out


def test_env_registry_hand_copied_defaults_equal_the_ssot() -> None:
    """Mirror: env_registry cannot import ssot_config at registration time (#14856)."""
    defaults = _env_registry_defaults()
    got = {name: defaults.get(name) for name in _ENV_MIRRORS}
    assert got == {name: _canonical()[const] for name, const in _ENV_MIRRORS.items()}


# --- (c) complete.yaml names no model --------------------------------------

_MODEL_KEYS = frozenset(
    {"model", "models", "default_model", "fallback_models", "emergency_fallback_model", "simple", "complex"}
)


def _model_key_paths(doc: Any, prefix: str = "") -> list[str]:
    """Dotted paths of every model-bearing key (a string, or a non-empty list / mapping of them)."""
    found: list[str] = []
    if isinstance(doc, dict):
        for key, val in doc.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if key in _MODEL_KEYS and val:
                found.append(path)
            else:
                found.extend(_model_key_paths(val, path))
    elif isinstance(doc, list):
        for idx, val in enumerate(doc):
            found.extend(_model_key_paths(val, f"{prefix}[{idx}]"))
    return found


def _ai_stack_value(role: str) -> str:
    return {v: val for v, val, _ in _ai_stack_vars()}[f"ai_{role}_model"]


def test_complete_yaml_names_no_model() -> None:
    """The tier map is the only model authority; complete.yaml carries no model selection (#15502)."""
    # The whole document (#19430): the old exemption for knowledge_base.semantic_chunking.model
    # rested on it being a chunker model, but it named the embedding tier and nothing read it. The
    # chunker's sentence model is code-pinned in utils/semantic_chunker_base.py.
    assert _model_key_paths(_load_yaml(_COMPLETE_YAML)) == []


def test_the_model_key_scan_sees_a_model_when_one_exists() -> None:
    """Contrast fixture: a complete.yaml-shaped doc that still names models is reported."""
    doc = {
        "llm": {"models": {"rag": "x"}, "tiered_routing": {"models": {"simple": "y"}}, "fallback_models": ["z"]},
        "agents": {"chat": {"enabled": True, "model": "w"}},
        "agent_global": {"default_model": "v"},
    }
    assert sorted(_model_key_paths(doc)) == [
        "agent_global.default_model",
        "agents.chat.model",
        "llm.fallback_models",
        "llm.models",
        "llm.tiered_routing.models",
    ]
    assert _model_key_paths({"llm": {"embedding": {"dimensions": 768}}}) == []


_KB_ROLES = ("kb_librarian", "knowledge_extraction", "knowledge_retrieval")


@pytest.mark.parametrize("role", _KB_ROLES)
def test_agents_yaml_kb_roles_are_on_the_instruction_tier(role: str) -> None:
    """Owner decision 2026-10-10: agents.yaml agrees with the deployed ai-stack role -> tier assignment."""
    assert _load_yaml(_AGENTS_YAML)["llm"]["models"][role] == _ai_stack_value(role)
    assert _ai_stack_value(role) == _canonical()["INSTRUCTION_MODEL"]


# --- (d) no new hand-written tier map --------------------------------------


def _tier_maps(source: str, models: frozenset[str]) -> list[int]:
    """Line numbers of dict literals (or `dict(k=v)` calls) with >= 2 values naming a canonical model."""
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            values = node.values
        elif isinstance(node, ast.Call) and getattr(node.func, "id", "") == "dict":
            values = [kw.value for kw in node.keywords]
        else:
            continue
        named = [v for v in values if isinstance(v, ast.Constant) and v.value in models]
        if len(named) >= 2:
            hits.append(node.lineno)
    return hits


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _source_population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, "autobot-backend", "autobot-slm-backend", "autobot_shared")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "model-tier-map-scan",
    discover=_source_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=3100,  # re-pinned mid-window (train 73): population 3250, window [2950, 3250] (#17844)
    what="non-test python source",
    roots=("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    growth=300,
)


def test_a_tier_map_is_flagged_and_a_reference_is_not() -> None:
    models = _local_models()
    assert _tier_maps('M = {"simple": "gemma2:2b", "complex": "qwen3.5:9b"}\n', models) == [1]
    assert _tier_maps('M = dict(simple="gemma2:2b", complex="qwen3.5:9b")\n', models) == [1]
    assert _tier_maps('M = {"x": TRIVIAL_MODEL, "y": QUALITY_MODEL}\n', models) == []
    assert _tier_maps('M = {"x": "qwen3.5:9b", "y": "not-a-model"}\n', models) == []


def test_the_map_scan_is_not_vacuous() -> None:
    """The scan reads the files that hold the literals, and finds the literals it hunts for."""
    population = REACH.examined(repo_root())
    assert _SSOT in population and _ENV_REGISTRY in population
    literal_holders = [r for r in population if any(m in _read(r) for m in _local_models())]
    assert _SSOT in literal_holders, "the canonical file's own literals were not seen"


def test_no_module_hand_writes_a_tier_map() -> None:
    models = _local_models()
    found = {r: lines for r in REACH.examined(repo_root()) if (lines := _tier_maps(_read(r), models))}
    assert not found, f"#15502: hand-written tier map(s) {found}; import the tier constants from {_SSOT}"


# --- (e) the frontend holds no model literal --------------------------------

_FRONTEND_SRC = "autobot-frontend/src"
_CONTEXT_WINDOW = "autobot-frontend/src/composables/chat/useContextWindow.ts"
_FAMILIES = "qwen|llama|gemma|phi|mistral|dolphin|nomic"
#: A local model name: a family followed by `:tag` anywhere in a literal, or a whole literal that is a
#: tagless name (`nomic-embed-text`). Hosted catalogue ids (`gpt-...`) are out of scope, and no
#: underscore is allowed in the tagless shape so `llama_index` is not a model.
_MODEL_TAG = re.compile(rf"\b(?:{_FAMILIES})[\w.\-]*:|^(?:{_FAMILIES})[A-Za-z0-9.\-]*$")
#: `(file, literal)` -> why it is not a model *choice*. Every entry needs a reason; a stale one fails.
FRONTEND_LITERAL_ALLOWLIST: dict[tuple[str, str], str] = {
    **{
        (
            _CONTEXT_WINDOW,
            family,
        ): "family prefix keying the fallback context-window size table; matching only, never a model choice or default"
        for family in ("llama3", "llama3.1", "llama3.2", "mistral", "gemma", "gemma2", "qwen", "phi3")
    },
    (
        "autobot-frontend/src/components/admin/NpuWorkerPairConfirmDialog.stories.ts",
        "gemma-3-4b",
    ): "Storybook fixture data, not shipped",
    ("autobot-frontend/src/components/chat/MessageItem.stories.ts", "llama3"): "Storybook fixture data, not shipped",
}
_TS_TOKEN = re.compile(r"""//[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|`(?:\\.|[^`\\])*`""", re.S)
_VUE_TOKEN = re.compile(r"""/\*.*?\*/|'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|`(?:\\.|[^`\\])*`""", re.S)


def _model_literals(source: str, models: frozenset[str], *, vue: bool = False) -> list[str]:
    """String literals naming a local model: a canonical tier model, or a `family...:tag` shape.

    Comments are skipped, and so is anything that is not a quoted string, so an identifier such as
    `llama_index_configured: boolean` is not mistaken for a model tag.
    """
    found = []
    for token in (_VUE_TOKEN if vue else _TS_TOKEN).finditer(source):
        text = token.group(0)
        if text[0] in "/":
            continue
        body = text[1:-1]
        if body in models or _MODEL_TAG.search(body):
            found.append(body)
    return found


def _frontend_population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, _FRONTEND_SRC, exclude=(f"{_FRONTEND_SRC}/types/generated",))
    except EmptyEnumeration:
        return []
    return [
        rel
        for rel in tracked
        if rel.endswith((".ts", ".vue")) and not rel.endswith(".spec.ts") and "/__tests__/" not in rel
    ]


REACH_FRONTEND = declare(
    "frontend-model-literal-scan",
    discover=_frontend_population,
    # Mid-window, from REACH_FRONTEND.window(); the arithmetic is on the PR, not here.
    # #18242: population 1171 -> window [1071, 1171]; 1080 sat in the bottom band, re-pinned mid-window.
    floor=1121,
    what="frontend ts and vue source",
    roots=(_FRONTEND_SRC,),
    growth=100,
)


def test_a_frontend_model_literal_is_flagged_and_a_lookalike_is_not() -> None:
    models = _local_models()
    canonical = next(iter(sorted(models)))
    assert _model_literals(f"const m = '{canonical}'", models) == [canonical]
    assert _model_literals('const m = "llama3.2:1b-instruct-q4_K_M"', models) == ["llama3.2:1b-instruct-q4_K_M"]
    assert _model_literals("const m = `mistral:7b`", models) == ["mistral:7b"]
    assert _model_literals('<p title="qwen3:8b">', models, vue=True) == ["qwen3:8b"]
    assert _model_literals("// qwen3.5:9b is the default\nconst x = 1", models) == []
    assert _model_literals("llama_index_configured: boolean\nconst a = 'llama_index'", models) == []
    assert _model_literals("const hosted = 'gpt-3.5-turbo'", models) == []


def test_a_tagless_model_name_is_flagged_and_prose_is_not() -> None:
    models = _local_models()
    assert _model_literals("const m = 'nomic-embed-text'", models) == ["nomic-embed-text"]
    assert _model_literals('const m = "llama3.2"', models) == ["llama3.2"]
    assert _model_literals("const t = 'llama_index'", models) == []
    assert _model_literals("const t = 'Phi is a letter'", models) == []


def test_every_frontend_allowlist_entry_is_still_needed_and_has_a_reason() -> None:
    models = _local_models()
    for (rel, literal), reason in FRONTEND_LITERAL_ALLOWLIST.items():
        assert reason.strip(), (rel, literal)
        assert literal in _model_literals(
            _read(rel), models, vue=rel.endswith(".vue")
        ), f"stale allowlist entry {rel}: {literal}"


def test_the_frontend_scan_is_not_vacuous() -> None:
    population = REACH_FRONTEND.examined(repo_root())
    assert "autobot-frontend/src/config/ssot-config.ts" in population
    assert not [r for r in population if "/__tests__/" in r or r.endswith(".spec.ts") or "types/generated" in r]
    assert any(r.endswith(".vue") for r in population), "no .vue file was scanned"


def test_frontend_holds_no_model_literal() -> None:
    """Owner decision 2026-10-10: the frontend fetches model names from the backend at runtime."""
    models = _local_models()
    found = {}
    for rel in REACH_FRONTEND.examined(repo_root()):
        hits = [
            h
            for h in _model_literals(_read(rel), models, vue=rel.endswith(".vue"))
            if (rel, h) not in FRONTEND_LITERAL_ALLOWLIST
        ]
        if hits:
            found[rel] = hits
    assert not found, f"#15502: the frontend hardcodes model name(s) {found}; fetch them from the backend"


_READERS = (
    "autobot-backend/config/registry_defaults.py",
    "autobot-backend/llm_shared/tiered_routing/tier_config.py",
    "autobot-backend/api/agent_config.py",
    "autobot-slm-backend/agent_seed_roster.py",
    "autobot-slm-backend/services/capability_tiers.py",
    "autobot-backend/orchestration/orchestrator_config.py",
)


@pytest.mark.parametrize("rel", _READERS)
def test_a_canonical_reader_imports_the_ssot_and_holds_no_model_literal(rel: str) -> None:
    source = _read(rel)
    assert "autobot_shared.ssot_config" in source, f"{rel} no longer reads the SSOT"
    literals = [
        n.value for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Constant) and n.value in _local_models()
    ]
    assert not literals, f"#15502: {rel} holds model literal(s) {sorted(set(literals))}; use the constants"


# --- (f) the settings.json template holds no model -----------------------------


def _json_strings(node: Any) -> list[str]:
    """Every key and every string value of a JSON document, at any depth."""
    if isinstance(node, dict):
        return [str(k) for k in node] + [s for v in node.values() for s in _json_strings(v)]
    if isinstance(node, list):
        return [s for v in node for s in _json_strings(v)]
    return [node] if isinstance(node, str) else []


def _model_strings(doc: Any, models: frozenset[str]) -> list[str]:
    return [s for s in _json_strings(doc) if s in models or _MODEL_TAG.search(s)]


def test_a_json_model_name_is_flagged_as_key_or_value_and_a_url_is_not() -> None:
    models = _local_models()
    doc = {"a": {"qwen3.5:9b": 1}, "b": ["gemma2:2b"], "c": {"d": "mistral:7b"}}
    assert _model_strings(doc, models) == ["qwen3.5:9b", "gemma2:2b", "mistral:7b"]
    assert _model_strings({"endpoint": "http://localhost:11434", "provider": "ollama"}, models) == []


def test_settings_json_template_holds_no_model_name() -> None:
    """Owner decision 2026-10-10: the tier map is the only model authority; the template names none."""
    found = _model_strings(json.loads(_read(_SETTINGS_JSON)), _local_models())
    assert not found, f"#15502: {_SETTINGS_JSON} names model(s) {found}; the tier map owns them"


def test_settings_json_template_has_no_stale_hosted_defaults_or_nested_copy() -> None:
    text = _read(_SETTINGS_JSON).lower()
    assert "gpt-3.5-turbo" not in text and "dialogpt" not in text
    assert "settings" not in json.loads(text), "the nested top-level `settings` duplicate is gone"


# --- (g) provisioning: which tier models each node class pulls ------------------

#: The skip is declared, not accidental: a CPU-only node pulls the CPU class (models of at most
#: ~4B parameters) and the llm role warns which GPU-class tiers it left out (roles/llm/tasks).
_CPU_CLASS = frozenset({"nomic-embed-text:latest", "llama3.2:1b", "gemma2:2b", "phi3:mini"})
_GPU_CLASS = frozenset({"qwen3.5:9b", "mistral:7b-instruct", "dolphin-llama3:8b"})


def test_the_llm_role_node_classes_are_the_pinned_per_class_tier_sets() -> None:
    defaults = _load_yaml(_LLM_ROLE)
    assert set(defaults["llm_cpu_models"]) == _CPU_CLASS
    assert set(defaults["llm_gpu_models"]) == _GPU_CLASS
    assert len(defaults["llm_cpu_models"]) == len(_CPU_CLASS) and len(defaults["llm_gpu_models"]) == len(_GPU_CLASS)


def test_the_node_classes_together_cover_every_canonical_local_tier_model() -> None:
    defaults = _load_yaml(_LLM_ROLE)
    union = set(defaults["llm_cpu_models"]) | set(defaults["llm_gpu_models"])
    assert union == _local_models(), f"tier models no node class pulls: {sorted(_local_models() - union)}"
    assert not set(defaults["llm_cpu_models"]) & set(defaults["llm_gpu_models"]), "a model sits in both classes"


def _pull_loops(node: Any) -> list[list[str]]:
    """The `loop:` of every task named `Pull required Ollama models...`, at any depth of a play."""
    found: list[list[str]] = []
    if isinstance(node, dict):
        if str(node.get("name", "")).startswith("Pull required Ollama models") and isinstance(node.get("loop"), list):
            found.append(node["loop"])
        for value in node.values():
            found += _pull_loops(value)
    elif isinstance(node, list):
        for item in node:
            found += _pull_loops(item)
    return found


@pytest.mark.parametrize("rel", _PULL_PLAYBOOKS)
def test_a_deploy_playbook_inline_pull_list_is_the_canonical_local_models(rel: str) -> None:
    loops = [loop for doc in yaml.safe_load_all(_read(rel)) for loop in _pull_loops(doc)]
    assert len(loops) == 1, f"{rel}: expected one inline Ollama pull list, found {len(loops)}"
    assert sorted(loops[0]) == sorted(_local_models()), f"#15502: {rel} pulls {sorted(loops[0])}"


def test_the_pull_list_finder_sees_a_nested_loop_and_ignores_other_tasks() -> None:
    play = [
        {
            "tasks": [
                {"block": [{"name": "Pull required Ollama models (x)", "loop": ["a", "b"]}]},
                {"name": "Other", "loop": ["c"]},
            ]
        }
    ]
    assert _pull_loops(play) == [["a", "b"]]


# --- (f) the backend env template and its vars file are pinned mirrors ------

_BACKEND_ENV_TEMPLATE = "autobot-slm-backend/ansible/roles/backend/templates/backend.env.j2"
_BACKEND_ENV_VARS = "autobot-slm-backend/ansible/playbooks/vars/backend-env.yml"
_BACKEND_ROLE_DEFAULTS = "autobot-slm-backend/ansible/roles/backend/defaults/main.yml"
#: Ansible var -> the tier constant its inline default must equal.
_BACKEND_VAR_TIER = {
    "backend_llm_model": "DEFAULT_LLM_MODEL",
    "backend_routing_model": "ROUTING_MODEL",
    "backend_classification_model": "CLASSIFICATION_MODEL",
    "backend_light_model": "LIGHT_PROCESSING_MODEL",
    "backend_instruction_model": "INSTRUCTION_MODEL",
    "backend_system_model": "SYSTEM_MODEL",
    "backend_embedding_model": "DEFAULT_EMBEDDING_MODEL",
}
_TEMPLATE_DEFAULT = re.compile(r"^AUTOBOT_\w+_MODEL=\{\{ (\w+) \| default\('([^']+)'\) \}\}$", re.M)
_VARS_DEFAULT = re.compile(r"^(\w+): \"\{\{ lookup\('env', '\w+'\) \| default\('([^']+)', true\) \}\}\"$", re.M)


def _template_defaults(text: str) -> list[tuple[str, str]]:
    return _TEMPLATE_DEFAULT.findall(text)


def test_backend_env_template_inline_defaults_equal_their_tier() -> None:
    pairs = _template_defaults(_read(_BACKEND_ENV_TEMPLATE))
    assert len(pairs) >= 12, "the scan found almost nothing: the template line shape changed"
    bad = [(v, d) for v, d in pairs if d != _canonical()[_BACKEND_VAR_TIER[v]]]
    assert bad == [], f"#15502: {_BACKEND_ENV_TEMPLATE} defaults diverge from the tier map: {bad}"


def test_backend_env_template_kb_roles_and_embedding_use_their_own_tier() -> None:
    """The KB roles are INSTRUCTION-tier (not LIGHT) and the embedding alias is not a chat model."""
    got = {
        m.group(1): m.group(2)
        for m in re.finditer(r"^AUTOBOT_(\w+)_MODEL=\{\{ (\w+) \|", _read(_BACKEND_ENV_TEMPLATE), re.M)
    }
    for role in ("KB_LIBRARIAN", "KNOWLEDGE_EXTRACTION", "KNOWLEDGE_RETRIEVAL"):
        assert got[role] == "backend_instruction_model", role
    assert got["EMBEDDING"] == "backend_embedding_model"


def test_backend_env_vars_file_and_role_default_equal_their_tier() -> None:
    found = dict(_VARS_DEFAULT.findall(_read(_BACKEND_ENV_VARS)))
    assert set(found) == set(_BACKEND_VAR_TIER), f"unexpected model vars: {sorted(found)}"
    assert {v: found[v] for v in found} == {v: _canonical()[t] for v, t in _BACKEND_VAR_TIER.items()}
    role = _load_yaml(_BACKEND_ROLE_DEFAULTS)
    assert role["backend_llm_model"] == _canonical()["DEFAULT_LLM_MODEL"]


def test_the_template_scan_flags_a_diverging_default_and_ignores_a_plain_var() -> None:
    drift = "AUTOBOT_RAG_MODEL={{ backend_instruction_model | default('phi3:mini') }}\nAUTOBOT_X_MODEL={{ v }}\n"
    assert _template_defaults(drift) == [("backend_instruction_model", "phi3:mini")]
