# tools/schema-split

Scripts for splitting `autobot-backend/api/schemas_common.py` into per-domain schema files.

Used in issue #5799 to decompose the 3,748-line monolith into 7 domain modules.

## Files

| File | Purpose |
|------|---------|
| `split_schemas.py` | Parses schemas_common.py, classifies 375+ classes by domain, writes domain files |
| `update_imports.py` | Rewrites all `api/*.py` imports to use domain-specific modules |
| `README.md` | This file |

## Domain files managed

| Domain file | Class prefix patterns |
|-------------|----------------------|
| `schemas_terminal.py` | Terminal*, AgentTerminal*, SSH*, CommandAssess*, AdminExecute*, PackageManagers* |
| `schemas_analytics.py` | Analytics*, Cost*, Budget*, UsageSummary*, Metrics*, ModelPricing*, AllAgent* |
| `schemas_knowledge.py` | Knowledge* |
| `schemas_agent.py` | AgentMessage*, AgentCommand*, AgentHealth*, AgentConfig*, LLM*, Memory* |
| `schemas_system.py` | System*, NPU*, WakeWord*, FeatureFlag*, AdminFile* |
| `schemas_workflows.py` | Workflow*, Registry*, RUM*, Elevation*, AdvancedControl*, StateTracking*, Validation*, StructuredThinking* |
| `schemas_code.py` | CodeReview*, Git*, Skills*, Database*, Template*, Log*, Voice*, AccessControl*, FileSandbox*, MCP*, HTTP* |
| `schemas_common.py` | Success*, Data*, UsageRecord* (truly cross-domain only) |

## When to run

Run these scripts only when doing a **full domain re-split** — e.g., adding a new domain file or reclassifying a large batch of classes.

For **adding a single new schema class**, just add it directly to the correct domain file and import it from there. Do not run these scripts for one-class additions.

## Usage

```bash
# From repo root
cd /path/to/AutoBot-AI

# 1. Preview the classification without writing files
python3 tools/schema-split/split_schemas.py --dry-run

# 2. Write domain files (modifies schemas_common.py and creates schemas_*.py)
python3 tools/schema-split/split_schemas.py

# 3. Preview import rewrites
python3 tools/schema-split/update_imports.py --dry-run

# 4. Apply import rewrites to all api/*.py endpoint files
python3 tools/schema-split/update_imports.py

# 5. Verify all schema files are importable (not just syntax-valid)
cd autobot-backend
for mod in schemas_terminal schemas_analytics schemas_knowledge schemas_agent schemas_system schemas_workflows schemas_code schemas_common; do
  python3 -c "import sys; sys.path.insert(0, '.'); from api import $mod; print('OK:', '$mod')" 2>&1
done
cd ..

# 6. Compile-check all modified files
python3 -m py_compile autobot-backend/api/schemas_*.py
```

## Adding a new domain

If a new domain grows large enough to warrant its own file (e.g., `schemas_integrations.py`):

1. Add entry to `DOMAIN_FILE` and `DOMAIN_HEADERS` in `split_schemas.py`
2. Add entry to `DOMAIN_MODULE` in `update_imports.py`
3. Add classification rule to `DOMAIN_RULES` in both scripts (longer prefixes first)
4. Run the scripts as above

## Known limitations

- **Base-class imports**: The script detects base classes used in domain files (e.g., `SuccessMessageResponse`) and adds import lines automatically. However, it only covers base classes defined in `schemas_common.py`. If domain files inherit from classes defined elsewhere, those imports must be added manually.
- **Non-api imports**: The scripts only update `api/*.py`. If any other directory imports from `schemas_common`, update those manually.
- **Regex-based extraction**: Class detection uses `^class (\w+)\(` regex, not AST. Multi-line class definitions with decorators may need manual review.
