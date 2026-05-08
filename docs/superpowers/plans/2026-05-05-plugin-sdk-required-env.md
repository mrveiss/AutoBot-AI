# Plugin SDK `required_env` Field — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `required_env: List[RequiredEnvVar]` field to `PluginManifest` so plugins declare needed environment variables, with loader-level enforcement and a `GET /plugins/{name}/env-status` endpoint that exposes per-var configuration state without ever leaking values.

**Architecture:** Four files modified in lock-step. Pydantic schema (`RequiredEnvVar`) added next to `PluginManifest`. `PluginLoader` gets two methods: `_check_required_env` (used during load to fail-loud on missing required vars) and `get_env_status` (used by API to return safe state dict). New FastAPI endpoint reads `get_env_status` and returns a typed response with no env-var values. Backward compatible: default empty list means all 4 in-tree plugins continue to load identically. TDD throughout, one commit per task.

**Tech Stack:** Python 3.11+, pydantic v2, FastAPI, pytest, pytest-asyncio.

**Spec:** [`docs/superpowers/specs/2026-05-05-plugin-sdk-required-env-design.md`](../specs/2026-05-05-plugin-sdk-required-env-design.md)
**Issue:** #6971

---

## File Structure

| File | Change | Responsibility |
| --- | --- | --- |
| `autobot_shared/plugin_sdk/base.py` | Modify | `RequiredEnvVar` model + field on `PluginManifest` |
| `autobot_shared/plugin_sdk/loader.py` | Modify | `_check_required_env` + `get_env_status` + integration with `load_plugin` |
| `autobot-backend/plugin_manager.py` | Modify | `PluginEnvStatusEntry`/`PluginEnvStatusResponse` models + `GET /plugins/{name}/env-status` endpoint |
| `autobot_shared/plugin_sdk/plugin_sdk_test.py` | Modify | All SDK-level unit tests (8 test functions added) |
| `autobot-backend/tests/api/test_plugin_manager.py` | Create | API endpoint tests (2 test functions) |

---

## Task 0: Worktree Setup

**Files:** none (creates `.worktrees/issue-6971/`)

- [ ] **Step 1: Verify main session is on Dev_new_gui and clean**

```bash
git -C /home/martins/AutoBot-Ai/AutoBot-AI branch --show-current
git -C /home/martins/AutoBot-Ai/AutoBot-AI status --porcelain
```

Expected: branch is `Dev_new_gui`, status is empty (clean tree).

- [ ] **Step 2: Create worktree**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI
git worktree add .worktrees/issue-6971 -b issue-6971 origin/Dev_new_gui
git -C .worktrees/issue-6971 branch --unset-upstream
```

Expected: `.worktrees/issue-6971/` exists, on branch `issue-6971` with no upstream.

- [ ] **Step 3: Confirm worktree readiness**

```bash
git -C /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971 status
git -C /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971 log --oneline -3
```

Expected: clean, recent commits visible from Dev_new_gui base.

**All subsequent commands run inside `.worktrees/issue-6971/` via `git -C` or by entering the directory. Never `cd` back to the main checkout — that breaks parallel worktrees per CLAUDE.md.**

---

## Task 1: `RequiredEnvVar` schema (TDD)

**Files:**

- Modify: `autobot_shared/plugin_sdk/base.py`
- Test: `autobot_shared/plugin_sdk/plugin_sdk_test.py`

- [ ] **Step 1: Write the failing tests**

Append to `plugin_sdk_test.py` after the existing `PluginManifest validation` section:

```python
# ---------------------------------------------------------------------------
# RequiredEnvVar validation
# ---------------------------------------------------------------------------


def test_required_env_var_accepts_valid_name():
    from plugin_sdk.base import RequiredEnvVar

    var = RequiredEnvVar(
        name="MY_PLUGIN_API_KEY",
        description="The API key.",
    )
    assert var.name == "MY_PLUGIN_API_KEY"
    assert var.secret is False
    assert var.required is False
    assert var.docs_url is None
    assert var.obtain_steps == []


def test_required_env_var_rejects_lowercase_name():
    from plugin_sdk.base import RequiredEnvVar

    with pytest.raises(Exception):
        RequiredEnvVar(name="my_plugin_api_key", description="x")


def test_required_env_var_rejects_leading_digit():
    from plugin_sdk.base import RequiredEnvVar

    with pytest.raises(Exception):
        RequiredEnvVar(name="1MY_KEY", description="x")


def test_required_env_var_rejects_special_chars():
    from plugin_sdk.base import RequiredEnvVar

    with pytest.raises(Exception):
        RequiredEnvVar(name="MY-KEY", description="x")


def test_required_env_var_rejects_empty_name():
    from plugin_sdk.base import RequiredEnvVar

    with pytest.raises(Exception):
        RequiredEnvVar(name="", description="x")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
pytest autobot_shared/plugin_sdk/plugin_sdk_test.py -v -k required_env_var 2>&1 | tail -20
```

Expected: 5 tests fail with `ImportError` or `AttributeError` because `RequiredEnvVar` is not defined yet.

- [ ] **Step 3: Implement `RequiredEnvVar`**

In `autobot_shared/plugin_sdk/base.py`, after the imports section and before `class PluginStatus`, add:

```python
class RequiredEnvVar(BaseModel):
    """
    Declares an environment variable a plugin needs at runtime.

    Used in PluginManifest.required_env to surface configuration requirements
    to operators and host UIs. Values are NEVER returned through the API —
    only the configured/missing state is reported.
    """

    name: str = Field(
        ...,
        description="Env var name, e.g. 'MY_PLUGIN_API_KEY'",
    )
    secret: bool = Field(
        False,
        description="If true, host UI hides the value from any preview surface",
    )
    required: bool = Field(
        False,
        description="If true, the plugin refuses to load when the var is missing",
    )
    description: str = Field(
        ...,
        description="One-line purpose of the variable",
    )
    docs_url: Optional[str] = Field(
        None,
        description="URL where the credential is obtained",
    )
    obtain_steps: List[str] = Field(
        default_factory=list,
        description="Bullet list shown by the host settings UI",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Env-var names must be UPPER_SNAKE_CASE starting with a letter."""
        if not v:
            raise ValueError("Env var name cannot be empty")
        if not v[0].isalpha() or not v[0].isupper():
            raise ValueError("Env var name must start with an uppercase letter")
        if not all(c.isupper() or c.isdigit() or c == "_" for c in v):
            raise ValueError("Env var name must be UPPER_SNAKE_CASE")
        return v
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
pytest autobot_shared/plugin_sdk/plugin_sdk_test.py -v -k required_env_var 2>&1 | tail -10
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
git add autobot_shared/plugin_sdk/base.py autobot_shared/plugin_sdk/plugin_sdk_test.py
git commit -m "feat(plugin-sdk): add RequiredEnvVar schema with name validator (#6971)"
```

---

## Task 2: `PluginManifest.required_env` field (TDD)

**Files:**

- Modify: `autobot_shared/plugin_sdk/base.py`
- Test: `autobot_shared/plugin_sdk/plugin_sdk_test.py`

- [ ] **Step 1: Write the failing tests**

Append to `plugin_sdk_test.py` after the `RequiredEnvVar validation` section:

```python
# ---------------------------------------------------------------------------
# PluginManifest.required_env field
# ---------------------------------------------------------------------------


def test_manifest_default_required_env_is_empty_list():
    """Backward compat: existing plugin.json without the field still parses."""
    m = _make_manifest()
    assert m.required_env == []


def test_manifest_with_required_env_parses():
    from plugin_sdk.base import RequiredEnvVar

    m = _make_manifest(
        required_env=[
            {
                "name": "MY_API_KEY",
                "description": "API key for service.",
                "secret": True,
                "required": False,
                "docs_url": "https://example.com/keys",
                "obtain_steps": ["Sign in", "Generate key"],
            }
        ]
    )
    assert len(m.required_env) == 1
    var = m.required_env[0]
    assert isinstance(var, RequiredEnvVar)
    assert var.name == "MY_API_KEY"
    assert var.secret is True
    assert var.docs_url == "https://example.com/keys"
    assert var.obtain_steps == ["Sign in", "Generate key"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
pytest autobot_shared/plugin_sdk/plugin_sdk_test.py -v -k manifest_default_required_env or manifest_with_required_env 2>&1 | tail -10
```

Expected: 2 tests fail because `required_env` is not on `PluginManifest`.

- [ ] **Step 3: Add field to `PluginManifest`**

In `autobot_shared/plugin_sdk/base.py`, inside the `PluginManifest` class, after the `hooks: List[str] = Field(...)` line (line 54), add:

```python
    required_env: List[RequiredEnvVar] = Field(
        default_factory=list,
        description="Environment variables this plugin needs at runtime",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
pytest autobot_shared/plugin_sdk/plugin_sdk_test.py -v -k "manifest_default_required_env or manifest_with_required_env" 2>&1 | tail -10
```

Expected: 2 passed.

- [ ] **Step 5: Run full SDK test suite to confirm no regressions**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
pytest autobot_shared/plugin_sdk/plugin_sdk_test.py -v 2>&1 | tail -15
```

Expected: all existing tests still pass + 7 new ones pass.

- [ ] **Step 6: Commit**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
git add autobot_shared/plugin_sdk/base.py autobot_shared/plugin_sdk/plugin_sdk_test.py
git commit -m "feat(plugin-sdk): add required_env field to PluginManifest (#6971)"
```

---

## Task 3: Loader `_check_required_env` (TDD)

**Files:**

- Modify: `autobot_shared/plugin_sdk/loader.py`
- Test: `autobot_shared/plugin_sdk/plugin_sdk_test.py`

- [ ] **Step 1: Write the failing tests**

Append to `plugin_sdk_test.py`. Note: import `PluginLoader` if not already imported (check the existing imports at top of file).

```python
# ---------------------------------------------------------------------------
# PluginLoader._check_required_env
# ---------------------------------------------------------------------------


def test_check_required_env_returns_empty_when_no_required_env(monkeypatch):
    from plugin_sdk.loader import PluginLoader

    loader = PluginLoader([])
    manifest = _make_manifest()
    missing_required, missing_optional = loader._check_required_env(manifest)
    assert missing_required == []
    assert missing_optional == []


def test_check_required_env_finds_missing_required(monkeypatch):
    from plugin_sdk.loader import PluginLoader

    monkeypatch.delenv("TEST_REQUIRED_VAR", raising=False)
    loader = PluginLoader([])
    manifest = _make_manifest(
        required_env=[
            {
                "name": "TEST_REQUIRED_VAR",
                "description": "Required.",
                "required": True,
            }
        ]
    )
    missing_required, missing_optional = loader._check_required_env(manifest)
    assert missing_required == ["TEST_REQUIRED_VAR"]
    assert missing_optional == []


def test_check_required_env_finds_missing_optional(monkeypatch):
    from plugin_sdk.loader import PluginLoader

    monkeypatch.delenv("TEST_OPTIONAL_VAR", raising=False)
    loader = PluginLoader([])
    manifest = _make_manifest(
        required_env=[
            {
                "name": "TEST_OPTIONAL_VAR",
                "description": "Optional.",
                "required": False,
            }
        ]
    )
    missing_required, missing_optional = loader._check_required_env(manifest)
    assert missing_required == []
    assert missing_optional == ["TEST_OPTIONAL_VAR"]


def test_check_required_env_separates_required_and_optional(monkeypatch):
    from plugin_sdk.loader import PluginLoader

    monkeypatch.delenv("TEST_REQ_A", raising=False)
    monkeypatch.delenv("TEST_OPT_B", raising=False)
    monkeypatch.setenv("TEST_REQ_C", "value")
    loader = PluginLoader([])
    manifest = _make_manifest(
        required_env=[
            {"name": "TEST_REQ_A", "description": "x", "required": True},
            {"name": "TEST_OPT_B", "description": "x", "required": False},
            {"name": "TEST_REQ_C", "description": "x", "required": True},
        ]
    )
    missing_required, missing_optional = loader._check_required_env(manifest)
    assert missing_required == ["TEST_REQ_A"]
    assert missing_optional == ["TEST_OPT_B"]


def test_check_required_env_treats_empty_string_as_missing(monkeypatch):
    """An env var set to empty string is treated as not configured."""
    from plugin_sdk.loader import PluginLoader

    monkeypatch.setenv("TEST_EMPTY_VAR", "")
    loader = PluginLoader([])
    manifest = _make_manifest(
        required_env=[
            {"name": "TEST_EMPTY_VAR", "description": "x", "required": True}
        ]
    )
    missing_required, _ = loader._check_required_env(manifest)
    assert missing_required == ["TEST_EMPTY_VAR"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
pytest autobot_shared/plugin_sdk/plugin_sdk_test.py -v -k check_required_env 2>&1 | tail -20
```

Expected: 5 tests fail with `AttributeError: 'PluginLoader' object has no attribute '_check_required_env'`.

- [ ] **Step 3: Implement `_check_required_env`**

In `autobot_shared/plugin_sdk/loader.py`, after `_check_dependencies` (around line 195), add:

```python
    def _check_required_env(
        self, manifest: PluginManifest
    ) -> tuple[List[str], List[str]]:
        """
        Check which env vars declared by the manifest are unset.

        Returns:
            Tuple of (missing_required, missing_optional) env var names.
            An env var set to an empty string is treated as missing.
        """
        import os

        missing_required: List[str] = []
        missing_optional: List[str] = []
        for env in manifest.required_env:
            if not os.environ.get(env.name):
                if env.required:
                    missing_required.append(env.name)
                else:
                    missing_optional.append(env.name)
        return missing_required, missing_optional
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
pytest autobot_shared/plugin_sdk/plugin_sdk_test.py -v -k check_required_env 2>&1 | tail -10
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
git add autobot_shared/plugin_sdk/loader.py autobot_shared/plugin_sdk/plugin_sdk_test.py
git commit -m "feat(plugin-sdk): _check_required_env returns (missing_required, missing_optional) (#6971)"
```

---

## Task 4: Loader `load_plugin` integration (TDD)

**Files:**

- Modify: `autobot_shared/plugin_sdk/loader.py`
- Test: `autobot_shared/plugin_sdk/plugin_sdk_test.py`

- [ ] **Step 1: Write the failing tests**

Append to `plugin_sdk_test.py`. These tests use the existing `_ConcretePlugin` and need a way to register that class as a discoverable entry point. Follow the pattern from any existing `load_plugin` tests if present (otherwise mock `_import_plugin_class`).

```python
# ---------------------------------------------------------------------------
# PluginLoader.load_plugin integration with required_env
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_plugin_returns_none_when_required_env_missing(monkeypatch, caplog):
    """Plugin with a missing required env var fails to load with an error log."""
    from plugin_sdk.loader import PluginLoader

    monkeypatch.delenv("TEST_REQ_LOAD_FAIL", raising=False)

    loader = PluginLoader([])
    manifest = _make_manifest(
        required_env=[
            {
                "name": "TEST_REQ_LOAD_FAIL",
                "description": "x",
                "required": True,
            }
        ]
    )

    monkeypatch.setattr(
        loader, "_import_plugin_class", lambda ep: _ConcretePlugin
    )

    with caplog.at_level("ERROR"):
        result = await loader.load_plugin(manifest)

    assert result is None
    assert any(
        "TEST_REQ_LOAD_FAIL" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_load_plugin_succeeds_with_optional_env_missing(monkeypatch, caplog):
    """Plugin with missing optional env var loads, with info log."""
    from plugin_sdk.base import PluginRegistry
    from plugin_sdk.loader import PluginLoader

    PluginRegistry().clear()
    monkeypatch.delenv("TEST_OPT_LOAD_OK", raising=False)

    loader = PluginLoader([])
    manifest = _make_manifest(
        name="opt-test-plugin",
        required_env=[
            {
                "name": "TEST_OPT_LOAD_OK",
                "description": "x",
                "required": False,
            }
        ],
    )

    monkeypatch.setattr(
        loader, "_import_plugin_class", lambda ep: _ConcretePlugin
    )

    with caplog.at_level("INFO"):
        plugin = await loader.load_plugin(manifest)

    assert plugin is not None
    assert any(
        "TEST_OPT_LOAD_OK" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_load_plugin_succeeds_when_all_required_env_set(monkeypatch):
    """Plugin loads normally when all required env vars are configured."""
    from plugin_sdk.base import PluginRegistry
    from plugin_sdk.loader import PluginLoader

    PluginRegistry().clear()
    monkeypatch.setenv("TEST_REQ_LOAD_PRESENT", "value")

    loader = PluginLoader([])
    manifest = _make_manifest(
        name="all-set-plugin",
        required_env=[
            {
                "name": "TEST_REQ_LOAD_PRESENT",
                "description": "x",
                "required": True,
            }
        ],
    )

    monkeypatch.setattr(
        loader, "_import_plugin_class", lambda ep: _ConcretePlugin
    )

    plugin = await loader.load_plugin(manifest)
    assert plugin is not None
    assert plugin.manifest.name == "all-set-plugin"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
pytest autobot_shared/plugin_sdk/plugin_sdk_test.py -v -k "load_plugin_returns_none_when_required_env_missing or load_plugin_succeeds_with_optional_env_missing or load_plugin_succeeds_when_all_required_env_set" 2>&1 | tail -15
```

Expected: 1 fails (loads anyway because the check isn't wired), 2 may pass coincidentally — what matters is the first one fails and the missing-required-env error log isn't emitted.

- [ ] **Step 3: Wire `_check_required_env` into `load_plugin`**

In `autobot_shared/plugin_sdk/loader.py`, inside `load_plugin`, immediately after the dependency check block (around line 99), add:

```python
            # Check required environment variables
            missing_required, missing_optional = self._check_required_env(manifest)
            if missing_required:
                logger.error(
                    "Cannot load plugin %s: required env vars not set: %s",
                    manifest.name,
                    missing_required,
                )
                return None
            if missing_optional:
                logger.info(
                    "Plugin %s loaded with optional env vars unset: %s",
                    manifest.name,
                    missing_optional,
                )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
pytest autobot_shared/plugin_sdk/plugin_sdk_test.py -v -k "load_plugin_returns_none_when_required_env_missing or load_plugin_succeeds_with_optional_env_missing or load_plugin_succeeds_when_all_required_env_set" 2>&1 | tail -10
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
git add autobot_shared/plugin_sdk/loader.py autobot_shared/plugin_sdk/plugin_sdk_test.py
git commit -m "feat(plugin-sdk): load_plugin enforces required_env at load time (#6971)"
```

---

## Task 5: Loader `get_env_status` accessor (TDD)

**Files:**

- Modify: `autobot_shared/plugin_sdk/loader.py`
- Test: `autobot_shared/plugin_sdk/plugin_sdk_test.py`

- [ ] **Step 1: Write the failing tests**

Append to `plugin_sdk_test.py`:

```python
# ---------------------------------------------------------------------------
# PluginLoader.get_env_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_env_status_returns_correct_shape(monkeypatch):
    from plugin_sdk.base import PluginRegistry
    from plugin_sdk.loader import PluginLoader

    PluginRegistry().clear()
    monkeypatch.setenv("TEST_STATUS_PRESENT", "actual_secret_value")
    monkeypatch.delenv("TEST_STATUS_MISSING", raising=False)

    loader = PluginLoader([])
    manifest = _make_manifest(
        name="status-shape-plugin",
        required_env=[
            {
                "name": "TEST_STATUS_PRESENT",
                "description": "Set var.",
                "secret": True,
                "required": False,
                "docs_url": "https://example.com",
                "obtain_steps": ["one", "two"],
            },
            {
                "name": "TEST_STATUS_MISSING",
                "description": "Unset var.",
                "secret": False,
                "required": False,
            },
        ],
    )
    monkeypatch.setattr(
        loader, "_import_plugin_class", lambda ep: _ConcretePlugin
    )
    await loader.load_plugin(manifest)

    status = loader.get_env_status("status-shape-plugin")
    assert status is not None
    assert set(status.keys()) == {"TEST_STATUS_PRESENT", "TEST_STATUS_MISSING"}

    present = status["TEST_STATUS_PRESENT"]
    assert present == {
        "configured": True,
        "secret": True,
        "required": False,
        "description": "Set var.",
        "docs_url": "https://example.com",
        "obtain_steps": ["one", "two"],
    }

    missing = status["TEST_STATUS_MISSING"]
    assert missing["configured"] is False
    assert missing["secret"] is False
    assert missing["docs_url"] is None
    assert missing["obtain_steps"] == []


def test_get_env_status_returns_none_for_unknown_plugin():
    from plugin_sdk.loader import PluginLoader

    loader = PluginLoader([])
    assert loader.get_env_status("does-not-exist") is None


@pytest.mark.asyncio
async def test_get_env_status_never_returns_value(monkeypatch):
    """Critical privacy test: env-var values must NEVER be in the response."""
    from plugin_sdk.base import PluginRegistry
    from plugin_sdk.loader import PluginLoader

    PluginRegistry().clear()
    secret_value = "sk-supersecret-do-not-leak-1234"
    monkeypatch.setenv("TEST_SECRET_LEAK_CHECK", secret_value)

    loader = PluginLoader([])
    manifest = _make_manifest(
        name="leak-check-plugin",
        required_env=[
            {
                "name": "TEST_SECRET_LEAK_CHECK",
                "description": "Sensitive.",
                "secret": True,
                "required": True,
            }
        ],
    )
    monkeypatch.setattr(
        loader, "_import_plugin_class", lambda ep: _ConcretePlugin
    )
    await loader.load_plugin(manifest)

    status = loader.get_env_status("leak-check-plugin")
    serialized = repr(status)
    assert secret_value not in serialized
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
pytest autobot_shared/plugin_sdk/plugin_sdk_test.py -v -k get_env_status 2>&1 | tail -15
```

Expected: 3 fail with `AttributeError: 'PluginLoader' object has no attribute 'get_env_status'`.

- [ ] **Step 3: Implement `get_env_status`**

In `autobot_shared/plugin_sdk/loader.py`, after `_check_required_env`, add:

```python
    def get_env_status(
        self, plugin_name: str
    ) -> Optional[Dict[str, Dict[str, object]]]:
        """
        Return per-env-var configuration status for a loaded plugin.

        SECURITY: response NEVER contains env var values, only the
        configured/missing boolean and the manifest metadata.

        Args:
            plugin_name: Name of a loaded plugin

        Returns:
            Dict mapping env-var name to status dict, or None if the
            plugin is not loaded.
        """
        import os

        plugin = self.registry.get_plugin(plugin_name)
        if plugin is None:
            return None
        return {
            env.name: {
                "configured": bool(os.environ.get(env.name)),
                "secret": env.secret,
                "required": env.required,
                "description": env.description,
                "docs_url": env.docs_url,
                "obtain_steps": list(env.obtain_steps),
            }
            for env in plugin.manifest.required_env
        }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
pytest autobot_shared/plugin_sdk/plugin_sdk_test.py -v -k get_env_status 2>&1 | tail -10
```

Expected: 3 passed.

- [ ] **Step 5: Run full SDK test suite for regression**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
pytest autobot_shared/plugin_sdk/plugin_sdk_test.py -v 2>&1 | tail -20
```

Expected: all SDK tests pass (existing + 18 new from Tasks 1-5).

- [ ] **Step 6: Commit**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
git add autobot_shared/plugin_sdk/loader.py autobot_shared/plugin_sdk/plugin_sdk_test.py
git commit -m "feat(plugin-sdk): get_env_status returns per-var state without values (#6971)"
```

---

## Task 6: API endpoint `GET /plugins/{name}/env-status` (TDD)

**Files:**

- Modify: `autobot-backend/plugin_manager.py`
- Create: `autobot-backend/tests/api/test_plugin_manager.py`

- [ ] **Step 1: Write the failing API tests**

Create `autobot-backend/tests/api/test_plugin_manager.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Unit tests for the plugin manager FastAPI endpoints (Issue #6971).

Covers GET /plugins/{plugin_name}/env-status — env-var configuration
status without leaking values.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_env_status_endpoint_returns_status_for_loaded_plugin(monkeypatch):
    from plugin_manager import get_plugin_env_status

    fake_loader = MagicMock()
    fake_loader.get_env_status.return_value = {
        "MY_API_KEY": {
            "configured": True,
            "secret": True,
            "required": False,
            "description": "API key",
            "docs_url": "https://example.com/keys",
            "obtain_steps": ["Sign in", "Generate"],
        }
    }

    with patch("plugin_manager.get_plugin_loader", return_value=fake_loader):
        result = await get_plugin_env_status(
            plugin_name="my-plugin",
            admin_check=True,
        )

    assert result.plugin_name == "my-plugin"
    assert "MY_API_KEY" in result.env_vars
    entry = result.env_vars["MY_API_KEY"]
    assert entry.configured is True
    assert entry.secret is True
    assert entry.docs_url == "https://example.com/keys"
    assert entry.obtain_steps == ["Sign in", "Generate"]


@pytest.mark.asyncio
async def test_env_status_endpoint_404_for_unknown_plugin(monkeypatch):
    from plugin_manager import get_plugin_env_status

    fake_loader = MagicMock()
    fake_loader.get_env_status.return_value = None

    with patch("plugin_manager.get_plugin_loader", return_value=fake_loader):
        with pytest.raises(HTTPException) as exc_info:
            await get_plugin_env_status(
                plugin_name="does-not-exist",
                admin_check=True,
            )

    assert exc_info.value.status_code == 404
    assert "does-not-exist" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_env_status_endpoint_returns_empty_for_plugin_without_required_env(monkeypatch):
    from plugin_manager import get_plugin_env_status

    fake_loader = MagicMock()
    fake_loader.get_env_status.return_value = {}

    with patch("plugin_manager.get_plugin_loader", return_value=fake_loader):
        result = await get_plugin_env_status(
            plugin_name="simple-plugin",
            admin_check=True,
        )

    assert result.plugin_name == "simple-plugin"
    assert result.env_vars == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
pytest autobot-backend/tests/api/test_plugin_manager.py -v 2>&1 | tail -10
```

Expected: 3 fail with `ImportError: cannot import name 'get_plugin_env_status'`.

- [ ] **Step 3: Add response models and endpoint**

In `autobot-backend/plugin_manager.py`, near the top after the existing imports/Pydantic models, add:

```python
class PluginEnvStatusEntry(BaseModel):
    """Per-env-var status (never contains the actual value)."""

    configured: bool
    secret: bool
    required: bool
    description: str
    docs_url: Optional[str]
    obtain_steps: List[str]


class PluginEnvStatusResponse(BaseModel):
    """Response for GET /plugins/{plugin_name}/env-status."""

    plugin_name: str
    env_vars: Dict[str, PluginEnvStatusEntry]
```

Then add the endpoint at the end of the file (after the last existing endpoint):

```python
@router.get("/plugins/{plugin_name}/env-status")
@with_error_handling(error_code_prefix="PLUGIN_ENV_STATUS")
async def get_plugin_env_status(
    plugin_name: str,
    admin_check: bool = Depends(check_admin_permission),
) -> PluginEnvStatusResponse:
    """
    Return per-env-var configuration status for a loaded plugin.

    The response never contains env-var values, only the configured/missing
    state and manifest metadata. Designed for host UIs to surface install
    requirements without leaking secrets.

    Issue #6971.
    """
    loader = get_plugin_loader()
    status_data = loader.get_env_status(plugin_name)
    if status_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not found: {plugin_name}",
        )
    return PluginEnvStatusResponse(
        plugin_name=plugin_name,
        env_vars={
            k: PluginEnvStatusEntry(**v) for k, v in status_data.items()
        },
    )
```

Verify imports at top of file include `Dict, List, Optional` from `typing` and `BaseModel` from `pydantic`. Add any missing.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
pytest autobot-backend/tests/api/test_plugin_manager.py -v 2>&1 | tail -10
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
git add autobot-backend/plugin_manager.py autobot-backend/tests/api/test_plugin_manager.py
git commit -m "feat(plugin-manager): GET /plugins/{name}/env-status endpoint (#6971)"
```

---

## Task 7: Backward-compatibility regression check

**Files:** none modified

- [ ] **Step 1: Verify all 4 in-tree plugin manifests still parse**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
PYTHONPATH=autobot_shared python3 -c "
import json
from pathlib import Path
from plugin_sdk.base import PluginManifest

for f in Path('plugins').rglob('plugin.json'):
    with open(f) as fp:
        data = json.load(fp)
    m = PluginManifest(**data)
    print(f'  OK: {m.name} v{m.version} (required_env={len(m.required_env)})')
"
```

Expected: 4 lines printed (`hello-plugin`, `logger-plugin`, `mcp-wrapper-plugin`, `kb-event-plugin`), each with `required_env=0`. No exceptions.

- [ ] **Step 2: Run full SDK test suite**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
pytest autobot_shared/plugin_sdk/plugin_sdk_test.py -v 2>&1 | tail -20
```

Expected: all SDK tests pass (existing + ~18 new).

- [ ] **Step 3: Run new API tests**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
pytest autobot-backend/tests/api/test_plugin_manager.py -v 2>&1 | tail -10
```

Expected: 3 passed.

- [ ] **Step 4: Run pre-commit hooks**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
pre-commit run --files \
    autobot_shared/plugin_sdk/base.py \
    autobot_shared/plugin_sdk/loader.py \
    autobot_shared/plugin_sdk/plugin_sdk_test.py \
    autobot-backend/plugin_manager.py \
    autobot-backend/tests/api/test_plugin_manager.py 2>&1 | tail -30
```

Expected: all hooks pass. If any auto-format hook modifies files, re-stage and amend the most recent commit:

```bash
git add -u
git commit --amend --no-edit
```

- [ ] **Step 5: Final commit if any lint fixes were needed**

If pre-commit modified files but the amend already happened above, this step is a no-op. If lint fixes touched multiple commits, *do not* rebase; create one final cleanup commit:

```bash
git status
# If clean, skip. Otherwise:
git add -u
git commit -m "style: auto-format from pre-commit (#6971)"
```

---

## Task 8: Push and open PR

**Files:** none modified

- [ ] **Step 1: Push branch**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
git push -u origin issue-6971
```

Expected: branch pushed; URL printed.

- [ ] **Step 2: Open PR targeting Dev_new_gui**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-6971
gh pr create \
    --base Dev_new_gui \
    --title "feat(plugin-sdk): declarative required_env field on PluginManifest (#6971)" \
    --body "$(cat <<'EOF'
## Summary

Adds `required_env: List[RequiredEnvVar]` to `PluginManifest` so plugins declare environment-variable-backed secrets they need, with loader-level enforcement and a host endpoint that surfaces configuration state without leaking values.

Closes #6971.

## What changes

- New `RequiredEnvVar` Pydantic model (UPPER_SNAKE_CASE name validator, opt-in `secret`/`required` flags, `docs_url`/`obtain_steps` for UX surfacing)
- `PluginManifest.required_env` field with `default_factory=list` — backward compatible
- `PluginLoader._check_required_env` → returns (missing_required, missing_optional)
- `PluginLoader.load_plugin` fails loud on missing required env (returns None + error log); logs info on missing optional env
- `PluginLoader.get_env_status` → returns per-var state dict; **never contains env values**
- New endpoint `GET /api/plugins/{plugin_name}/env-status` (admin-gated, matches existing patterns)

## Test plan

- [x] 18 new SDK unit tests (`autobot_shared/plugin_sdk/plugin_sdk_test.py`)
- [x] 3 new API tests (`autobot-backend/tests/api/test_plugin_manager.py`)
- [x] Privacy test: `test_get_env_status_never_returns_value` asserts secret values cannot appear in serialized response
- [x] Backward-compat regression: all 4 in-tree plugin manifests parse with `required_env=[]`
- [x] Pre-commit hooks pass
- [ ] Reviewer to verify response model serialization through OpenAPI schema generation

## Spec / Plan

- Spec: `docs/superpowers/specs/2026-05-05-plugin-sdk-required-env-design.md`
- Plan: `docs/superpowers/plans/2026-05-05-plugin-sdk-required-env.md`

## Out of scope (filed separately at PR-merge time)

- Marketplace UI surfacing of `obtain_steps` and `docs_url`
- Bulk endpoint `GET /plugins/env-status` returning all plugins

## Related

- Discovered while designing the ARC Prize Phase 1 plugin
- Sibling blocker: #6970 (extension-point hook dispatch sites)
EOF
)"
```

Expected: PR URL printed; PR open against `Dev_new_gui`.

- [ ] **Step 3: Verify PR**

```bash
gh pr view --json number,title,baseRefName,state -q '.'
```

Expected: PR shows base=`Dev_new_gui`, state=`OPEN`.

---

## Task 9: Post-merge cleanup (after PR is merged)

**Files:** none modified

- [ ] **Step 1: After merge — file follow-up issues mentioned in spec**

```bash
gh issue create --repo mrveiss/AutoBot-AI \
    --title "feat(frontend/marketplace): surface plugin required_env in install UI" \
    --label "tech-debt,frontend" \
    --body "..."
```

(Body will reference the merged PR + spec.)

- [ ] **Step 2: Remove worktree**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI
git worktree remove .worktrees/issue-6971
git branch -D issue-6971
```

- [ ] **Step 3: Confirm closure with proof comment on #6971**

Per CLAUDE.md "Issue Closure Verification Gate":

```bash
gh api repos/mrveiss/AutoBot-AI/issues/6971/comments -f body="✅ Closed with proof of implementation

**Commit(s):** <merged-PR-merge-commit-hash>

**Acceptance Criteria Met:**
- ✅ RequiredEnvVar schema added with UPPER_SNAKE_CASE validator
- ✅ PluginManifest.required_env field with backward-compatible default
- ✅ Loader fails loud on missing required env (test: test_load_plugin_returns_none_when_required_env_missing)
- ✅ Loader logs info on missing optional env (test: test_load_plugin_succeeds_with_optional_env_missing)
- ✅ get_env_status returns shape with no values (test: test_get_env_status_never_returns_value)
- ✅ GET /plugins/{name}/env-status endpoint (3 API tests pass)
- ✅ All 4 in-tree plugins still load (regression check passed)
- ✅ Pre-commit hooks pass
- ✅ Follow-up issue filed: <issue-number-from-Step-1>"
```

---

## Self-Review Findings

**Spec coverage check:**

| Spec section | Implementation task |
| --- | --- |
| `RequiredEnvVar` model + name validator | Task 1 |
| `PluginManifest.required_env` field with default empty | Task 2 |
| `PluginLoader._check_required_env` returning `(missing_required, missing_optional)` | Task 3 |
| `load_plugin` fails loud on required, logs on optional | Task 4 |
| `PluginLoader.get_env_status` never returns values | Task 5 |
| `GET /api/plugins/{name}/env-status` endpoint with auth + decorators | Task 6 |
| 11 SDK tests + 2 API tests | Tasks 1-6 (18 SDK tests, 3 API tests — exceeds spec) |
| Existing 4 in-tree plugins still load | Task 7 |
| No new mypy/pyright errors | Pre-commit hooks (Task 7 Step 4) |
| No new pre-commit failures | Task 7 Step 4 |

**Placeholder scan:** every step has actual code/commands; no TBD/TODO/"add error handling" patterns. Verified.

**Type consistency:** `RequiredEnvVar` field names (`name`, `secret`, `required`, `description`, `docs_url`, `obtain_steps`) match across schema (Task 1), get_env_status return shape (Task 5), and `PluginEnvStatusEntry` API model (Task 6). Verified.

**One gap caught during review:** the spec said "11 SDK tests"; this plan ships 18. The extras come from splitting some compound tests (e.g., separating "rejects lowercase" / "rejects leading digit" / "rejects special chars" / "rejects empty" into 4 tests instead of 1) and adding a privacy-leak test that wasn't enumerated in the spec. More tests is better, no spec violation.
