# Plugin SDK — `required_env` Field on PluginManifest

**Date:** 2026-05-05
**Author:** mrveiss
**Status:** Draft (pending review)
**Issue:** #6971
**Discovered during:** ARC Prize plugin design ([`docs/superpowers/specs/2026-05-05-arc-prize-plugin-design.md`](2026-05-05-arc-prize-plugin-design.md))

---

## Problem Statement

`PluginManifest` ([`autobot_shared/plugin_sdk/base.py`](../../autobot_shared/plugin_sdk/base.py)) has no way for a plugin to declare the environment-variable-backed secrets it needs. Plugins requiring API keys (e.g., the upcoming ARC Prize plugin needs `ARC_PRIZE_API_KEY`) currently must:

1. Read env vars in `initialize()` themselves
2. Document the var name in their README and hope operators read it
3. Implement their own settings-status UI reflecting whether the var is set

Each plugin re-invents the same pattern. The result is inconsistent install UX and no central place for the host UI to surface "plugin X needs key Y, get it at Z."

## Goals

- Let plugins declare required env vars in `plugin.json` with metadata (description, docs URL, how to obtain)
- Have the loader fail loudly when a `required=true` var is missing, succeed quietly when an `optional` var is missing (with an info log)
- Expose per-plugin env-status via the existing plugins API for UI consumption
- Never echo secret values back through the API

## Non-Goals

- Marketplace UI surfacing of `obtain_steps` / `docs_url` (separate frontend issue, filed at PR time)
- Bulk endpoint listing all plugins' env status (per-plugin covers the immediate consumer; bulk added if needed)
- Migration of existing core plugins to use `required_env` (none of them need it; migrated only when they do)
- Encrypting / vaulting env values (env-var-only is the established AutoBot secrets pattern)

---

## Design

### 1. New schema: `RequiredEnvVar`

Added to `autobot_shared/plugin_sdk/base.py`:

```python
class RequiredEnvVar(BaseModel):
    """Declares an environment variable a plugin needs at runtime."""

    name: str = Field(..., description="Env var name, e.g. 'MY_PLUGIN_API_KEY'")
    secret: bool = Field(False, description="If true, host UI hides the value")
    required: bool = Field(False, description="If true, plugin refuses to load without it")
    description: str = Field(..., description="One-line purpose of the variable")
    docs_url: Optional[str] = Field(None, description="URL where the credential is obtained")
    obtain_steps: List[str] = Field(
        default_factory=list,
        description="Bullet list shown by the host settings UI",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Env-var names: uppercase letters, digits, underscores; must start with letter."""
        if not v:
            raise ValueError("Env var name cannot be empty")
        if not v[0].isalpha() or not v[0].isupper():
            raise ValueError("Env var name must start with an uppercase letter")
        if not all(c.isupper() or c.isdigit() or c == "_" for c in v):
            raise ValueError("Env var name must be UPPER_SNAKE_CASE")
        return v
```

### 2. PluginManifest extension

```python
class PluginManifest(BaseModel):
    # ... existing fields ...
    required_env: List[RequiredEnvVar] = Field(
        default_factory=list,
        description="Environment variables this plugin needs at runtime",
    )
```

Default empty list — opt-in for existing plugins; nothing breaks for any current plugin.

### 3. Loader behavior — `autobot_shared/plugin_sdk/loader.py`

Add a method:

```python
def _check_required_env(
    self, manifest: PluginManifest
) -> tuple[list[str], list[str]]:
    """Return (missing_required, missing_optional) env var names."""
    missing_required: list[str] = []
    missing_optional: list[str] = []
    for env in manifest.required_env:
        if not os.environ.get(env.name):
            (missing_required if env.required else missing_optional).append(env.name)
    return missing_required, missing_optional
```

Call from `load_plugin` before instantiation:

```python
missing_required, missing_optional = self._check_required_env(manifest)
if missing_required:
    logger.error(
        "Cannot load plugin %s: required env vars not set: %s",
        manifest.name, missing_required,
    )
    return None
if missing_optional:
    logger.info(
        "Plugin %s loaded with optional env vars unset: %s",
        manifest.name, missing_optional,
    )
```

Add accessor:

```python
def get_env_status(self, plugin_name: str) -> Optional[Dict[str, Dict[str, Any]]]:
    """Return per-env-var configuration status for a loaded plugin.

    Never returns the env var *values* — only whether they are configured
    and the manifest metadata. Designed to be safe to expose via API.
    """
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
            "obtain_steps": env.obtain_steps,
        }
        for env in plugin.manifest.required_env
    }
```

### 4. API endpoint — `autobot-backend/plugin_manager.py`

Match the conventions of existing endpoints in the file (auth via `check_admin_permission`, error wrapping via `@with_error_handling`, decorator order per memory #6352 — `@with_error_handling` must be BELOW `@router.get`):

```python
class PluginEnvStatusEntry(BaseModel):
    configured: bool
    secret: bool
    required: bool
    description: str
    docs_url: Optional[str]
    obtain_steps: List[str]

class PluginEnvStatusResponse(BaseModel):
    plugin_name: str
    env_vars: Dict[str, PluginEnvStatusEntry]


@router.get("/plugins/{plugin_name}/env-status")
@with_error_handling(error_code_prefix="PLUGIN_ENV_STATUS")
async def get_plugin_env_status(
    plugin_name: str,
    admin_check: bool = Depends(check_admin_permission),
) -> PluginEnvStatusResponse:
    """Return per-env-var configuration status for a loaded plugin.

    The response never contains env-var values, only configuration state.
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
        env_vars={k: PluginEnvStatusEntry(**v) for k, v in status_data.items()},
    )
```

Auth: `Depends(check_admin_permission)` matches `GET /plugins`, `POST /plugins/{plugin_name}/load`, and the rest of the file.

Response shape:

```json
{
  "plugin_name": "arc-prize",
  "env_vars": {
    "ARC_PRIZE_API_KEY": {
      "configured": false,
      "secret": true,
      "required": false,
      "description": "ARC Prize API key.",
      "docs_url": "https://docs.arcprize.org/api-keys",
      "obtain_steps": ["Sign in at arcprize.org", "Visit Settings → API Keys", "Generate a 'data-access' scope key"]
    }
  }
}
```

### 5. Tests — `autobot_shared/plugin_sdk/plugin_sdk_test.py`

Add the following test cases (TDD: written before implementation):

- `test_required_env_var_validates_uppercase_name` — rejects lowercase, leading digit, mixed-case
- `test_required_env_var_accepts_valid_name` — `MY_PLUGIN_API_KEY` accepted
- `test_manifest_default_required_env_empty` — backward compat: existing plugin.json without the field still parses
- `test_manifest_with_required_env_parses` — JSON with `required_env` array deserializes to typed list
- `test_load_plugin_fails_when_required_env_missing` — using monkeypatch to clear env, plugin load returns None, error log emitted
- `test_load_plugin_succeeds_when_required_env_set` — monkeypatch sets env, plugin loads
- `test_load_plugin_succeeds_with_optional_env_missing` — plugin loads, info log emitted with the missing var name
- `test_load_plugin_fails_with_mix_of_required_and_optional` — only the required-missing one blocks load
- `test_get_env_status_returns_correct_shape` — keys: configured, secret, required, description, docs_url, obtain_steps
- `test_get_env_status_returns_none_for_unknown_plugin` — None returned for non-existent plugin
- `test_get_env_status_never_returns_value` — even if configured, response shape has only `configured: bool`, never the actual env value

Plus one API-level test in `autobot-backend/tests/test_plugin_manager_api.py` (or wherever existing plugin API tests live):

- `test_env_status_endpoint_returns_status_for_loaded_plugin`
- `test_env_status_endpoint_404_for_unknown_plugin`

---

## Migration / Compatibility

- **Backward compatible.** `required_env` defaults to empty list. Every existing `plugin.json` (4 in-tree plugins) continues to load identically.
- No database changes.
- No frontend changes in this PR.

---

## Risks

| Risk | Mitigation |
| --- | --- |
| Operator sets `required_env.name = "PATH"` (or any system-critical var) accidentally creating a "required" gate that's always satisfied | Acceptable — env vars are the existing secrets contract; a misuse is the operator's problem, not the SDK's |
| Endpoint accidentally exposes secret values | Loader's `get_env_status` returns `configured: bool` only; never reads `os.environ.get(name)` *value* outside the boolean cast |
| `required=true` in a `plugin.json` written by a third-party makes the plugin un-installable in environments without the var | Working as intended — that's the contract. Operator must set the var or the plugin doesn't load. |

---

## Out of Scope (filed at PR-merge time)

- `feat(frontend/marketplace): surface plugin required_env in install UI` — display `obtain_steps` and `docs_url` in the marketplace plugin-detail view
- `feat(plugin-sdk): bulk env-status endpoint GET /plugins/env-status` — if/when a UI consumer needs all-plugins-in-one-call

---

## Acceptance Criteria

- [ ] `RequiredEnvVar` schema added to `autobot_shared/plugin_sdk/base.py` with name validator
- [ ] `PluginManifest.required_env: List[RequiredEnvVar] = []` field added
- [ ] `PluginLoader._check_required_env` returns `(missing_required, missing_optional)`
- [ ] `PluginLoader.load_plugin` fails loud (returns None + error log) on missing required env
- [ ] `PluginLoader.load_plugin` logs info on missing optional env
- [ ] `PluginLoader.get_env_status` returns per-var status dict; never returns env var values
- [ ] `GET /api/plugins/{plugin_name}/env-status` endpoint implemented in `autobot-backend/plugin_manager.py`
- [ ] All 11 SDK tests pass
- [ ] Both API tests pass
- [ ] All existing 4 in-tree plugins still load identically (regression check)
- [ ] No new mypy / pyright errors
- [ ] No new pre-commit hook failures
