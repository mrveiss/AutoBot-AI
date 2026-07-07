---
name: dead-code-audit
description: Systematic codebase audit for unwired code — identify unregistered routers, uninvoked hooks, orphaned components, and file discovery issues. All findings become "wire it in" issues — never deletion issues.
---

# /dead-code-audit — Codebase Unwired Code Audit

**POLICY: Code is never deleted. It was created for a reason. Every finding becomes a "wire it in" issue.**

Performs a comprehensive scan of the AutoBot codebase to find:
- **Not wired** — complete, implemented code that exists but isn't connected to the app
- **Intentionally isolated** — test fixtures, examples, stubs (marked SKIP)

There is no "DEAD" classification. Code with zero references is still NOT_WIRED — find the right place to connect it.

Findings are classified, deduplicated against existing issues, and batch-filed as GitHub issues for human review. No automatic deletion or wiring.

## Usage

```bash
/dead-code-audit
```

Scans the entire codebase (no arguments). Runs 3 audit agents in parallel, classifies findings, and files issues.

---

# Workflow

## Phase 0: Tracker Cross-Reference Pre-flight (REQUIRED)

Before launching agents, run the automated tracker-cross-reference audit. This catches a class of findings the structural agents miss: **production modules whose docstring cites a CLOSED tracker issue but have zero production callers**. This is the systemic premature-closure pattern surfaced by #6836.

```bash
python3 pipeline-scripts/audit-unwired-trackers.py --json > /tmp/tracker-findings.json
jq 'length' /tmp/tracker-findings.json
```

Each entry in the output represents a feature whose tracker was closed before the integration step. Treat each as a `NOT_WIRED` finding for Phase 2 below.

The same script runs weekly via `.github/workflows/unwired-tracker-audit.yml` and files capped batches automatically — but running it interactively at audit time gives full visibility.

---

## Phase 1: Parallel Audit Agents

Three agents run simultaneously, each scanning a different domain:

### Agent A: Backend — Unregistered API Routers

**Task:** Find all Python files in `autobot-backend/api/` that define an APIRouter but are not registered in any router registry.

**Scan steps:**

1. Find all files defining routers:
   ```bash
   grep -rl "router = APIRouter" autobot-backend/api/ --include="*.py"
   ```

2. Find all router files actually imported in registries:
   ```bash
   grep -rh "from api\." autobot-backend/initialization/router_registry/ --include="*.py" | sort -u
   grep -rh "import.*api\." autobot-backend/initialization/router_registry/ --include="*.py" | sort -u
   ```

3. Compare: files in step 1 but not referenced in step 2 = unregistered

4. For each unregistered router:
   - Read the file and extract endpoint definitions
   - Check if it's imported anywhere else (tests, docstrings)
   - Check if there's already a GitHub issue for it (`gh issue list --search "<filename>"`)
   - Classify:
     - Has complete endpoints + never imported anywhere → `NOT_WIRED`
     - Has only placeholder/empty endpoints → `DEAD`
     - Imported only in tests → `SKIP` (test fixtures are intentional)

5. For NOT_WIRED findings, extract:
   - Endpoints defined (path + method)
   - Module name and prefix
   - Any git blame to understand why it wasn't wired

**Report back with:**
```
ROUTERS_FOUND: <count>
NOT_WIRED_ROUTERS: <list of filenames>
DEAD_ROUTERS: <list of filenames>
SKIPPED_ROUTERS: <list of filenames>

Per router:
<filename>: <count> endpoints, <endpoint_list>, classified as <NOT_WIRED|DEAD|SKIP>
```

### Agent B: Backend — Uninvoked HookPoints + Unregistered Extensions

**Task:** Find HookPoint enum values that are defined but never emitted, and extensions that are defined but never registered.

**HookPoint scan:**

1. Get all defined HookPoints:
   ```bash
   grep "    [A-Z_]*" autobot-backend/extensions/hooks.py | sed 's/[[:space:]]*\([A-Z_]*\).*/\1/'
   ```

2. Find actual invocation sites (where hooks are emitted):
   ```bash
   grep -rn "invoke_hook\|\.invoke(" autobot-backend/ \
     --include="*.py" \
     --exclude="hooks.py" \
     --exclude="manager.py" \
     --exclude="*_test.py"
   ```

3. Extract which HookPoints are actually invoked from step 2

4. Compare: HookPoints in step 1 but not in step 2 = uninvoked

5. Classify all uninvoked HookPoints as `NOT_WIRED` (they were defined with intent, never used)

**Extension registration scan:**

1. List all extensions in builtin:
   ```bash
   ls -1 autobot-backend/extensions/builtin/ | grep -E "\.py$" | sed 's/\.py$//'
   ```

2. Find which extensions are registered at startup:
   ```bash
   grep -rn "register_extension\|add_extension\|ExtensionManager" autobot-backend/initialization/ \
     --include="*.py"
   ```

3. Compare: extensions in builtin/ but not registered = `NOT_WIRED`

4. For each NOT_WIRED extension:
   - Read class definition
   - Check if it's referenced anywhere (tests, docs, plugins)
   - Classify as `NOT_WIRED` or `SKIP` if only in tests

**Report back with:**
```
HOOKPOINTS_TOTAL: <count>
HOOKPOINTS_INVOKED: <count> (e.g., 3 of 24)
HOOKPOINTS_NOT_WIRED: <list of names>

EXTENSIONS_IN_BUILTIN: <list>
EXTENSIONS_REGISTERED: <list>
EXTENSIONS_NOT_WIRED: <list>

Per hookpoint:
<NAME>: defined in hooks.py, 0 invocation sites, classified as NOT_WIRED

Per extension:
<ClassName>: defined in <file>, not registered at startup, classified as NOT_WIRED
```

### Agent C: Frontend — Orphaned Views + Components + Shadow Files

**Task:** Find Vue views not in the router, orphaned components, and duplicate/shadow router files.

**Orphaned views scan:**

1. List all Vue files in views directory:
   ```bash
   find autobot-frontend/src/views -name "*.vue" | sed 's|.*/||;s|\.vue||'
   ```

2. Find all component registrations in routers:
   ```bash
   cat autobot-frontend/src/router/index.ts | grep -oE "[A-Z][a-zA-Z]*View"
   cat autobot-frontend/src/App.vue | grep -oE "[A-Z][a-zA-Z]*View"
   ```

3. Compare: views in step 1 but not in step 2 = orphaned

4. For each orphaned view:
   - Read file to check if it has real content or is a scaffold/placeholder
   - Check if it's imported anywhere else (other files, tests)
   - Classify as `DEAD` (empty/placeholder) or `NOT_WIRED` (has real content but not in router)

**Orphaned components scan:**

1. List all components:
   ```bash
   find autobot-frontend/src/components -name "*.vue"
   ```

2. For each component, check if it's imported anywhere:
   ```bash
   grep -r "import.*ComponentName\|ComponentName" autobot-frontend/src \
     --include="*.vue" --include="*.ts" --include="*.tsx" | grep -v "<filename>" | wc -l
   ```

3. If import count = 0: component is orphaned

4. Classify as `DEAD` (empty) or `NOT_WIRED` (has content)

**Shadow router files:**

1. List all router files:
   ```bash
   ls -1 autobot-frontend/src/router*
   ```

2. Check which one is actually imported by main.ts:
   ```bash
   grep -n "import.*router" autobot-frontend/src/main.ts
   ```

3. Any router file NOT imported = shadow → classify as `DEAD`

**Report back with:**
```
VIEWS_TOTAL: <count>
VIEWS_IN_ROUTER: <count>
VIEWS_ORPHANED: <list of names>

COMPONENTS_TOTAL: <count>
COMPONENTS_ORPHANED: <list of filenames>

ROUTER_FILES: <list>
ROUTER_ACTIVE: <filename used by main.ts>
ROUTER_SHADOW: <list of unused router files>

Per finding:
<filename>: <lines of code>, classified as NOT_WIRED|DEAD|SKIP
```

---

## Phase 2: Collect and Classify Results

After all 3 agents complete, compile their reports into a master findings table:

```
BACKEND_ROUTERS:
- api/diagnostics.py: 3 endpoints, NOT_WIRED
- api/analytics_agents.py: 2 endpoints, NOT_WIRED
...

HOOKPOINTS:
- BEFORE_LLM_CALL: not invoked, NOT_WIRED
- AFTER_LLM_RESPONSE: not invoked, NOT_WIRED
...

EXTENSIONS:
- LoggingExtension: defined, not registered, NOT_WIRED
- SecretMaskingExtension: defined, not registered, NOT_WIRED

FRONTEND_VIEWS:
- HomeView: orphaned, has content, NOT_WIRED
- AboutView: orphaned, has content, NOT_WIRED
...

FRONTEND_COMPONENTS:
- <ComponentName>: orphaned, has content, NOT_WIRED
...

FRONTEND_ROUTERS:
- src/router.ts: shadow file, not imported by main.ts, DEAD
```

**Counts:**
```
NOT_WIRED: <count> (code exists, not connected)
DEAD: <count> (code unused, safe to remove)
SKIP: <count> (intentional — tests, docs, fixtures)
```

---

## Phase 3: Deduplication Check

Before filing any issues, check if they already exist:

```bash
for finding in <all_findings>; do
  # Search for existing issue
  existing=$(gh issue list --state open --search "$finding" --json number)
  
  if [ -n "$existing" ]; then
    echo "SKIP: Issue already exists for $finding"
    mark as SKIP_DUPLICATE
  else
    echo "NEW: Ready to file issue for $finding"
    mark as READY_TO_FILE
  fi
done
```

Only file issues for READY_TO_FILE findings.

---

## Phase 4: Create GitHub Labels

Ensure labels exist for categorizing findings:

```bash
# Create dead-code label if missing
gh label create "dead-code" \
  --color "e4e669" \
  --description "Code with no call sites — safe to remove" 2>/dev/null || true

# Create not-wired label if missing
gh label create "not-wired" \
  --color "0075ca" \
  --description "Implemented but not connected to app — needs wiring or deletion decision" 2>/dev/null || true

# Ensure tech-debt label exists
gh label create "tech-debt" \
  --color "fbca04" \
  --description "Technical debt and cleanup" 2>/dev/null || true
```

---

## Phase 5: Batch File Issues

For each READY_TO_FILE finding, create a GitHub issue:

**For NOT_WIRED backend router:**
```
Title: feat(router): register unregistered router api/<module>

Type: Not Wired

File: autobot-backend/api/<module>.py
Endpoints:
- <METHOD> <path> — <description>
- ...

What's needed:
Add to autobot-backend/initialization/router_registry/feature_routers.py:
RouterConfig("api.<module>", "<module>_router", prefix="<prefix>", tags=["<tag>"])

Or to core_routers.py if it should fail-fast on import error.

Action: Decide whether to wire this router into the app or delete the file.

Labels: not-wired, tech-debt
```

**For NOT_WIRED HookPoint:**
```
Title: feat(hooks): wire hookpoint HOOK_NAME invocation

Type: Not Wired

Hook: HookPoint.HOOK_NAME (defined in extensions/hooks.py)
Invocation sites found: 0

Intended behavior (from name):
<Infer from hook name semantics, e.g., "Fire before LLM API call">

Suggested location:
<Location in codebase where hook should be emitted, e.g., llm_handler.py line X>

Code to add:
```python
extension_manager = get_extension_manager()
await extension_manager.invoke_hook(HookPoint.HOOK_NAME, context={...})
```

Action: Decide whether to wire this hook or remove it from the enum.

Labels: not-wired, tech-debt
```

**For DEAD code:**
```
Title: refactor(cleanup): remove dead code <filename>

Type: Dead Code

File: <path>
Lines: <count>
References found: 0

This file/function/component is not referenced anywhere in the codebase and can be safely removed.

Action: Delete this file and verify no tests break.

Labels: dead-code, tech-debt
```

**For NOT_WIRED frontend view:**
```
Title: feat(views): wire orphaned view <ViewName>

Type: Not Wired

File: <path>
Content: Real implementation (not placeholder)

This view is defined but not registered in router/index.ts. 

To wire it in, add to autobot-frontend/src/router/index.ts:
```javascript
{
  path: '<path>',
  name: '<name>',
  component: () => import('<path>')
}
```

Action: Decide whether to wire this view into the router or delete it.

Labels: not-wired, tech-debt
```

**Filing loop:**
```bash
for finding in <READY_TO_FILE>; do
  gh issue create \
    --title "<title>" \
    --body "<body>" \
    --label "not-wired,tech-debt"  # or "dead-code,tech-debt"
  
  echo "✅ Filed: $finding"
done
```

---

## Phase 6: Summary Report

After filing, present a summary to the user:

```
# Dead Code Audit — Complete

## Summary
- **Total findings:** X
- **Not Wired (needs decision):** X issues filed
- **Dead Code (safe to delete):** X issues filed
- **Skipped (intentional):** X

## By Category

### Backend Routers (Not Wired)
| File | Endpoints | Issue |
|------|-----------|-------|
| api/diagnostics.py | 3 | #XXXX |
| api/analytics_agents.py | 2 | #XXXX |

### HookPoints (Not Wired)
| Name | Invocations | Issue |
|------|-------------|-------|
| BEFORE_LLM_CALL | 0 | #XXXX |
| AFTER_TOOL_EXECUTE | 0 | #XXXX |

### Extensions (Not Wired)
| Name | Registered | Issue |
|------|-----------|-------|
| LoggingExtension | No | #XXXX |
| SecretMaskingExtension | No | #XXXX |

### Frontend Views (Orphaned)
| File | Lines | Issue |
|------|-------|-------|
| HomeView.vue | 45 | #XXXX |
| AboutView.vue | 38 | #XXXX |

### Frontend Routers (Shadow)
| File | Reason | Issue |
|------|--------|-------|
| src/router.ts | Not imported by main.ts | #XXXX |

## Next Steps

1. Review each issue: decide whether to wire it in or delete it
2. For "not wired" items that should be wired: update the code and close the issue
3. For "not wired" items that should be deleted: delete the file and close the issue
4. For "dead code" items: verify dependencies, delete, and close the issue

All issues are labeled `not-wired` or `dead-code` for filtering.
```

---

# Red Flags (STOP if you see these)

- **Deleting code without checking all references** — use `grep` to verify something is truly unreferenced before classifying as DEAD
- **Missing imports in registry check** — dynamic imports via `importlib` may hide router registrations; always check the actual registration files
- **Skipping test fixtures** — code in `tests/` or `*_test.py` that looks unreferenced is usually intentional; mark as SKIP
- **Filing duplicate issues** — check `gh issue list --search` before filing; dedup in Phase 3
- **Not verifying hook invocation sites** — must actually grep for `invoke_hook(HookPoint.X)` calls; don't just check enum usage

# Benefits

- **Visibility:** See exactly what's wired vs not wired in the codebase
- **Decision-making:** Issues allow team discussion before deleting or wiring
- **Debt tracking:** Clear labels (`not-wired`, `dead-code`) let you filter and prioritize cleanup
- **No auto-deletion:** Human always decides, reducing risk of removing code in active development

# Success Criteria

- [ ] All 3 agents complete their scans
- [ ] Findings classified (NOT_WIRED, DEAD, SKIP)
- [ ] Existing duplicates skipped (not re-filed)
- [ ] Labels created (dead-code, not-wired, tech-debt)
- [ ] All NOT_WIRED and DEAD findings filed as issues
- [ ] Summary report shows issue numbers
- [ ] No code was deleted (only filed for review)
