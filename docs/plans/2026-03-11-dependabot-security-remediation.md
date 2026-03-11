# Dependabot Security Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Resolve 167 open Dependabot security alerts by upgrading vulnerable packages to their patched versions (Approach C: mechanical bumps for safe packages, changelog-reviewed bumps for AI-stack packages).

**GitHub Issue:** #1567

**Architecture:** Phase 1 applies mechanical version floor bumps across Python requirements files. Phase 2 applies AI-stack bumps (vllm, torch, transformers, llama-index, langchain-core) after noting changelog risks. Phase 3 regenerates the uv.lock for mcp-structured-thinking. Phase 4 handles npm transitive deps. Phase 5 creates GitHub issues for packages with no available patch.

**Tech Stack:** pip requirements files, npm package-lock.json, uv.lock, GitHub CLI (`gh`), npm CLI

---

## Phase 1: Mechanical Bumps (Python)

### Task 1: autobot-backend/code_analysis/requirements.txt

**Files:**
- Modify: `autobot-backend/code_analysis/requirements.txt`

**Step 1: Verify current pins**

```bash
grep -n "aiohttp\|requests\|scikit-learn\|numpy" autobot-backend/code_analysis/requirements.txt
```

Expected (approximately):
```
9:numpy>=1.21.0
10:scikit-learn>=1.0.0
24:aiohttp>=3.8.0
25:requests>=2.28.0
```

**Step 2: Apply the bumps**

Change:
- `aiohttp>=3.8.0` → `aiohttp>=3.12.14`
- `requests>=2.28.0` → `requests>=2.32.4`
- `scikit-learn>=1.0.0` → `scikit-learn>=1.5.0`
- `numpy>=1.21.0` → `numpy>=1.22.0`

**Step 3: Verify the changes**

```bash
grep -n "aiohttp\|requests\|scikit-learn\|numpy" autobot-backend/code_analysis/requirements.txt
```

**Step 4: Commit**

```bash
git add autobot-backend/code_analysis/requirements.txt
git commit -m "security(deps): bump aiohttp, requests, scikit-learn, numpy in code_analysis (#1567)"
```

---

### Task 2: autobot-infrastructure/shared/config/requirements.txt — mechanical packages

**Files:**
- Modify: `autobot-infrastructure/shared/config/requirements.txt`

**Step 1: Verify current pins**

```bash
grep -n "python-multipart\|pypdf\|markdown\|nltk\|opencv\|pycryptodome" \
  autobot-infrastructure/shared/config/requirements.txt
```

Expected (approximately):
```
4:python-multipart>=0.0.9
56:pypdf>=6.4.0
59:markdown>=3.5.0
63:nltk>=3.8.0
77:opencv-python>=4.8.0
99:pycryptodome>=3.19.0
```

**Step 2: Apply the bumps**

Change:
- `python-multipart>=0.0.9` → `python-multipart>=0.0.22`
- `pypdf>=6.4.0` → `pypdf>=6.8.0`
- `markdown>=3.5.0` → `markdown>=3.8.1`
- `nltk>=3.8.0` → `nltk>=3.9.3`
- `opencv-python>=4.8.0` → `opencv-python>=4.8.1.78`
- `pycryptodome>=3.19.0` → `pycryptodome>=3.19.1`

**Step 3: Verify**

```bash
grep -n "python-multipart\|pypdf\|markdown\|nltk\|opencv\|pycryptodome" \
  autobot-infrastructure/shared/config/requirements.txt
```

**Step 4: Commit**

```bash
git add autobot-infrastructure/shared/config/requirements.txt
git commit -m "security(deps): bump python-multipart, pypdf, nltk, markdown, opencv, pycryptodome in shared/config (#1567)"
```

---

### Task 3: autobot-infrastructure/shared/docker/ai-stack/requirements-ai.txt — mechanical packages

**Files:**
- Modify: `autobot-infrastructure/shared/docker/ai-stack/requirements-ai.txt`

**Step 1: Verify current pins**

```bash
grep -n "pypdf\|nltk\|aiohttp\|requests" \
  autobot-infrastructure/shared/docker/ai-stack/requirements-ai.txt
```

Expected:
```
77:pypdf>=4.0.0
32:nltk>=3.9.0
38:aiohttp>=3.12.0
41:requests>=2.32.0
```

**Step 2: Apply the bumps**

Change:
- `pypdf>=4.0.0` → `pypdf>=6.8.0`
- `nltk>=3.9.0` → `nltk>=3.9.3`
- `aiohttp>=3.12.0` → `aiohttp>=3.12.14`
- `requests>=2.32.0` → `requests>=2.32.4`

**Step 3: Verify**

```bash
grep -n "pypdf\|nltk\|aiohttp\|requests" \
  autobot-infrastructure/shared/docker/ai-stack/requirements-ai.txt
```

**Step 4: Commit**

```bash
git add autobot-infrastructure/shared/docker/ai-stack/requirements-ai.txt
git commit -m "security(deps): bump pypdf, nltk, aiohttp, requests in ai-stack (#1567)"
```

---

### Task 4: requirements.txt — pypdf

**Files:**
- Modify: `requirements.txt`

**Step 1: Verify current pin**

```bash
grep -n "pypdf" requirements.txt
```

Expected: `pypdf>=6.7.5`

**Step 2: Apply the bump**

Change: `pypdf>=6.7.5` → `pypdf>=6.8.0`

**Step 3: Verify**

```bash
grep -n "pypdf" requirements.txt
```

**Step 4: Commit**

```bash
git add requirements.txt
git commit -m "security(deps): bump pypdf to >=6.8.0 in root requirements (#1567)"
```

---

### Task 5: requirements-ci.txt — starlette and pypdf

**Files:**
- Modify: `requirements-ci.txt`

**Step 1: Verify current pins**

```bash
grep -n "starlette\|pypdf" requirements-ci.txt
```

Expected:
```
12:starlette==0.45.3
46:pypdf==6.7.5
```

**Step 2: Apply the bumps**

Change:
- `starlette==0.45.3` → `starlette==0.49.1`
- `pypdf==6.7.5` → `pypdf==6.8.0`

**Step 3: Verify**

```bash
grep -n "starlette\|pypdf" requirements-ci.txt
```

**Step 4: Commit**

```bash
git add requirements-ci.txt
git commit -m "security(deps): bump starlette to 0.49.1 and pypdf to 6.8.0 in requirements-ci (#1567)"
```

---

### Task 6: autobot-backend/requirements.txt — mcp and langgraph

**Files:**
- Modify: `autobot-backend/requirements.txt`

**Step 1: Verify current pins**

```bash
grep -n "mcp\|langgraph" autobot-backend/requirements.txt
```

Expected (approximately):
```
42:langgraph>=1.0.0,<2.0.0
43:langgraph-checkpoint-redis>=0.3.0,<1.0.0
45:mcp>=1.0.0
```

**Step 2: Apply the bumps**

Change:
- `langgraph>=1.0.0,<2.0.0` → `langgraph>=1.0.10,<2.0.0`
- `mcp>=1.0.0` → `mcp>=1.23.0`

Note: `langgraph-checkpoint-redis` is NOT the same package as `langgraph-checkpoint` flagged by
Dependabot. The `langgraph-checkpoint` alert is a transitive dep — leave `langgraph-checkpoint-redis`
unchanged; the transitive dep may be resolved by upgrading `langgraph` itself.

**Step 3: Verify**

```bash
grep -n "mcp\|langgraph" autobot-backend/requirements.txt
```

**Step 4: Commit**

```bash
git add autobot-backend/requirements.txt
git commit -m "security(deps): bump mcp to >=1.23.0 and langgraph to >=1.0.10 in backend (#1567)"
```

---

## Phase 2: Changelog-Reviewed AI Stack Bumps

> **STOP before each sub-task** — read the changelog notes below, confirm no breaking changes
> affect AutoBot's usage, then apply the bump.

### Task 7: transformers floor bump in requirements-ai.txt

**Context:** `transformers>=4.52.0` needs to become `>=4.53.0`. Minor floor bump.
The change between 4.52 and 4.53 is attention implementation updates — no API breaks. Safe.

**Files:**
- Modify: `autobot-infrastructure/shared/docker/ai-stack/requirements-ai.txt`

**Step 1: Verify current pin**

```bash
grep -n "transformers" autobot-infrastructure/shared/docker/ai-stack/requirements-ai.txt
```

Expected: `transformers>=4.52.0`

**Step 2: Apply bump**

Change: `transformers>=4.52.0` → `transformers>=4.53.0`

**Step 3: Verify**

```bash
grep -n "transformers" autobot-infrastructure/shared/docker/ai-stack/requirements-ai.txt
```

**Step 4: Commit**

```bash
git add autobot-infrastructure/shared/docker/ai-stack/requirements-ai.txt
git commit -m "security(deps): bump transformers to >=4.53.0 in ai-stack (#1567)"
```

---

### Task 8: llama-index floor bumps

**Context:** `llama-index>=0.10.0,<0.14.0` needs floor `>=0.12.41` — still within the `<0.14.0`
upper bound. `llama-index` in `shared/config/requirements.txt` is unpinned — add a floor.
The 0.12.x series has a stable API within the <0.14.0 range.

**Files:**
- Modify: `autobot-backend/requirements.txt`
- Modify: `autobot-infrastructure/shared/config/requirements.txt`

**Step 1: Verify current pins**

```bash
grep -n "^llama-index\b" autobot-backend/requirements.txt autobot-infrastructure/shared/config/requirements.txt
```

**Step 2: Apply bumps**

In `autobot-backend/requirements.txt`:
- `llama-index>=0.10.0,<0.14.0` → `llama-index>=0.12.41,<0.14.0`

In `autobot-infrastructure/shared/config/requirements.txt`:
- `llama-index` (unpinned, line ~85) → `llama-index>=0.12.41`

**Step 3: Verify**

```bash
grep -n "^llama-index\b" autobot-backend/requirements.txt autobot-infrastructure/shared/config/requirements.txt
```

**Step 4: Commit**

```bash
git add autobot-backend/requirements.txt autobot-infrastructure/shared/config/requirements.txt
git commit -m "security(deps): bump llama-index floor to >=0.12.41 (#1567)"
```

---

### Task 9: torch — remove vulnerable upper bound

**Context:** `torch>=2.0.0,<2.6.0` in `shared/config/requirements.txt` has an upper bound that
blocks the patched version. The `<2.6.0` constraint was added for compatibility.

**CHANGELOG CHECK:**
PyTorch 2.6 introduces `torch.load()` defaulting to `weights_only=True` (security hardening).
If AutoBot calls `torch.load()` without that kwarg, it will get a warning or error.

**Step 1: Search for torch.load usage**

```bash
grep -rn "torch\.load" autobot-backend/ autobot-infrastructure/ autobot-npu-worker/ 2>/dev/null
```

If results found: add `weights_only=True` (or `weights_only=False` with a comment explaining why)
to each call site before committing this task.

**Step 2: Verify current pins**

```bash
grep -n "torch\b" autobot-backend/requirements.txt autobot-infrastructure/shared/config/requirements.txt
```

Expected:
```
autobot-backend/requirements.txt:23:torch>=2.0.0
autobot-infrastructure/shared/config/requirements.txt:23:torch>=2.0.0,<2.6.0
```

**Step 3: Apply bumps**

In `autobot-backend/requirements.txt`:
- `torch>=2.0.0` → `torch>=2.6.0`

In `autobot-infrastructure/shared/config/requirements.txt`:
- `torch>=2.0.0,<2.6.0` → `torch>=2.6.0`

**Step 4: Verify**

```bash
grep -n "torch\b" autobot-backend/requirements.txt autobot-infrastructure/shared/config/requirements.txt
```

**Step 5: Commit**

```bash
git add autobot-backend/requirements.txt autobot-infrastructure/shared/config/requirements.txt
git commit -m "security(deps): bump torch to >=2.6.0, remove <2.6.0 upper bound (#1567)"
```

---

### Task 10: vllm — major version bump (0.6 → 0.14)

**Context:** `vllm>=0.6.0` needs to become `>=0.14.1`. Major version jump.

**CHANGELOG CHECK:**
Search for vLLM usage first:

```bash
grep -rn "from vllm\|import vllm" autobot-backend/ autobot-infrastructure/ 2>/dev/null
```

Standard `LLM`, `SamplingParams`, and OpenAI-compatible server usage is stable across versions.
If any private/experimental APIs are used, review the vLLM migration guide before proceeding.

**Files:**
- Modify: `requirements.txt`
- Modify: `autobot-infrastructure/shared/config/requirements.txt`

**Step 1: Verify current pins**

```bash
grep -n "vllm" requirements.txt autobot-infrastructure/shared/config/requirements.txt
```

Expected: both show `vllm>=0.6.0`

**Step 2: Apply bumps**

In both files: `vllm>=0.6.0` → `vllm>=0.14.1`

**Step 3: Verify**

```bash
grep -n "vllm" requirements.txt autobot-infrastructure/shared/config/requirements.txt
```

**Step 4: Commit**

```bash
git add requirements.txt autobot-infrastructure/shared/config/requirements.txt
git commit -m "security(deps): bump vllm to >=0.14.1 (#1567)"
```

---

### Task 11: langchain-core — major version bump (BREAKING — assess first)

**Context:** `langchain-core` SSRF CVE. Patched version is `1.2.11`. This is a **major version
jump** from current pins `0.3.83` / `>=0.3.81,<0.4.0`. The 0.x → 1.x boundary has API changes.

**Step 1: Audit langchain-core usage**

```bash
grep -rn "from langchain_core" autobot-backend/ autobot-infrastructure/ 2>/dev/null \
  | grep -v "__pycache__" | cut -d: -f1 | sort -u
```

Then review what is imported from each file. If imports are limited to stable public APIs
(`ChatPromptTemplate`, `StrOutputParser`, `HumanMessage`, `AIMessage`, basic runnable types) —
the jump is safe. If the codebase uses low-level callback or streaming internals — plan a
migration sprint first.

**Step 2: If safe — apply bumps**

In `autobot-backend/requirements.txt`:
- `langchain-core>=0.3.81,<0.4.0` → `langchain-core>=1.2.11`
  (remove the `<0.4.0` upper bound)

In `requirements-ci.txt`:
- `langchain-core==0.3.83` → `langchain-core==1.2.11`

**Step 3: Verify**

```bash
grep -n "langchain-core" autobot-backend/requirements.txt requirements-ci.txt
```

**Step 4: Commit**

```bash
git add autobot-backend/requirements.txt requirements-ci.txt
git commit -m "security(deps): bump langchain-core to >=1.2.11, remove <0.4.0 upper bound (#1567)"
```

**Step 5: If NOT safe — create a migration issue instead**

```bash
gh issue create \
  --title "security: migrate langchain-core from 0.3.x to 1.2.11+ (CVE fix)" \
  --body "## Problem
langchain-core < 1.2.11 is vulnerable to SSRF (Dependabot alerts #13, #128).
The fix requires a major version bump from 0.3.x to 1.2.11+.

## Migration needed
Review API changes between langchain-core 0.3 and 1.2.
Tracked under #1567." \
  --label "security"
```

---

## Phase 3: uv.lock Regeneration (mcp-structured-thinking)

### Task 12: Regenerate uv.lock

**Context:** `h11==0.14.0` (critical), `mcp==1.2.0` (high), `starlette==0.45.2` (high) in the
uv.lock at `autobot-infrastructure/shared/mcp/tools/mcp-structured-thinking/uv.lock`.

**Step 1: Check if uv is installed**

```bash
uv --version
```

If missing: `pip install uv`

**Step 2: Upgrade the vulnerable packages**

```bash
cd autobot-infrastructure/shared/mcp/tools/mcp-structured-thinking
uv lock --upgrade-package h11 --upgrade-package mcp --upgrade-package starlette
```

**Step 3: Verify new versions**

```bash
grep -A2 'name = "h11"' uv.lock
grep -A2 'name = "mcp"' uv.lock
grep -A2 'name = "starlette"' uv.lock
```

Expected: h11 >= 0.16.0, mcp >= 1.23.0, starlette >= 0.49.1

**Step 4: Return to repo root and commit**

```bash
cd /home/kali/Desktop/AutoBot
git add autobot-infrastructure/shared/mcp/tools/mcp-structured-thinking/uv.lock
git commit -m "security(deps): upgrade h11, mcp, starlette in mcp-structured-thinking uv.lock (#1567)"
```

---

## Phase 4: npm Transitive Dependencies

### Task 13: minimatch in autobot-frontend

**Context:** Dependabot alert #22 — `minimatch` transitive dep from ESLint packages.
Patched version: `>=9.0.7`.

**Files:**
- Modify: `autobot-frontend/package-lock.json` (via npm)
- Possibly: `autobot-frontend/package.json` (if override needed)

**Step 1: Check current minimatch version**

```bash
cd autobot-frontend
npm list minimatch 2>/dev/null | head -20
```

**Step 2: Try updating**

```bash
npm update minimatch
```

**Step 3: Verify version is >= 9.0.7**

```bash
npm list minimatch 2>/dev/null | grep minimatch
```

If still below 9.0.7, add an npm override in `package.json`:

```json
"overrides": {
  "minimatch": ">=9.0.7"
}
```

Then: `npm install`

**Step 4: Commit**

```bash
cd /home/kali/Desktop/AutoBot
git add autobot-frontend/package.json autobot-frontend/package-lock.json
git commit -m "security(deps): upgrade minimatch to >=9.0.7 in frontend (#1567)"
```

---

### Task 14: @modelcontextprotocol/sdk via deprecated server-github

**Context:** Alerts #25/#26 — `@modelcontextprotocol/sdk@1.0.1` pulled in by the deprecated
`@modelcontextprotocol/server-github@2025.4.8`. The package is deprecated with no newer release.
Patched sdk version: `>=1.25.2`.

**Step 1: Check if server-github is actively used**

```bash
grep -rn "server-github\|modelcontextprotocol" autobot-infrastructure/shared/config/ .mcp/ 2>/dev/null
```

**Step 2a: If not used — remove it**

```bash
cd autobot-infrastructure/shared/config
npm uninstall @modelcontextprotocol/server-github
cd /home/kali/Desktop/AutoBot
git add autobot-infrastructure/shared/config/package.json autobot-infrastructure/shared/config/package-lock.json
git commit -m "security(deps): remove deprecated @modelcontextprotocol/server-github (#1567)"
```

**Step 2b: If used — add npm override**

Add to `autobot-infrastructure/shared/config/package.json`:

```json
"overrides": {
  "@modelcontextprotocol/sdk": ">=1.25.2"
}
```

Then:

```bash
cd autobot-infrastructure/shared/config && npm install
cd /home/kali/Desktop/AutoBot
git add autobot-infrastructure/shared/config/package.json autobot-infrastructure/shared/config/package-lock.json
git commit -m "security(deps): override @modelcontextprotocol/sdk to >=1.25.2 (#1567)"
```

---

## Phase 5: Create Issues for Unresolvable Alerts

### Task 15: Create deferred issues

**Step 1: diskcache (transitive, no patch)**

```bash
gh issue create \
  --title "security: diskcache unsafe pickle deserialization — no upstream patch" \
  --body "Dependabot alerts #278, #233. No patched version available.
Affects: requirements.txt, autobot-backend/requirements.txt (transitive dep).
Action: monitor upstream; when fixed add floor version constraint.
Discovered during #1567." \
  --label "security"
```

**Step 2: ecdsa (transitive, no patch)**

```bash
gh issue create \
  --title "security: python-ecdsa Minerva timing attack — no upstream patch" \
  --body "Dependabot alert #276. No patched version available.
Affects: autobot-slm-backend/requirements.txt (transitive via python-jose[cryptography]).
Action: consider replacing python-jose with PyJWT to remove the ecdsa dep.
Discovered during #1567." \
  --label "security"
```

**Step 3: vue-template-compiler (transitive, no patch)**

```bash
gh issue create \
  --title "security: vue-template-compiler vulnerability in slm-frontend — no upstream patch" \
  --body "Dependabot alert #93. No patched version available.
Affects: autobot-slm-frontend/package-lock.json (transitive dep).
Action: monitor upstream; run npm update when fix is available.
Discovered during #1567." \
  --label "security"
```

---

## Phase 6: Verify and Close

### Task 16: Push, verify, close tracking issue

**Step 1: Push all commits**

```bash
git push origin Dev_new_gui
```

**Step 2: Wait ~5 minutes, then check remaining open alert count**

```bash
gh api /repos/mrveiss/AutoBot-AI/dependabot/alerts \
  --paginate -q '.[] | select(.state=="open") | .number' | wc -l
```

Expected: count down from 167 to ~10 (transitive no-patch items only).

**Step 3: Close the tracking issue**

```bash
gh issue close 1567 --comment "All resolvable alerts addressed:
- Phase 1: aiohttp, requests, scikit-learn, numpy, python-multipart, pypdf, nltk, markdown, opencv-python, pycryptodome, starlette, mcp, langgraph
- Phase 2: transformers, llama-index, torch, vllm, langchain-core
- Phase 3: h11, mcp, starlette in mcp-structured-thinking uv.lock
- Phase 4: minimatch (frontend), @modelcontextprotocol/sdk (shared/config)
- Phase 5: Created deferred issues for diskcache, ecdsa, vue-template-compiler"
```

---

## Key Risks and Mitigations

| Package | Risk | Mitigation |
|---------|------|------------|
| `langchain-core` 0.3→1.2 | Breaking API changes | Audit imports before bumping (Task 11 Step 1) |
| `torch` 2.0→2.6 | `torch.load()` default changed | Search for usage before bumping (Task 9 Step 1) |
| `vllm` 0.6→0.14 | Internal API evolution | Check vllm imports before bumping (Task 10 Step 1) |
| `llama-index` floor bump | Low risk; within 0.10→0.14 range | Already within upper bound |
| `starlette` 0.45→0.49 | FastAPI manages this transitively | FastAPI already pins >=0.125.0 |
