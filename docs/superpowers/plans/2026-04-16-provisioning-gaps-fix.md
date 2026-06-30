# Provisioning Gaps Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four Ansible provisioning gaps so a fresh deployment produces a fully working AutoBot stack with no manual post-provisioning steps.

**Architecture:** Each fix is a targeted change to either an Ansible role file (tasks/defaults/template) or the Python validation middleware. No new abstractions introduced. All changes follow existing patterns in the files they touch.

**Tech Stack:** Ansible (YAML), Jinja2 templates, Python 3.14, pytest, FastAPI TestClient

**Spec:** `docs/superpowers/specs/2026-04-16-provisioning-gaps-fix-design.md`

---

## File Map

| File | Change |
|------|--------|
| `autobot-slm-backend/ansible/roles/browser/tasks/main.yml` | Remove wrong Python playwright install; add browsers-dir + Node.js install + ownership tasks after npm install |
| `autobot-slm-backend/ansible/roles/browser/templates/playwright.service.j2` | Add `PLAYWRIGHT_BROWSERS_PATH` env var |
| `autobot-slm-backend/ansible/roles/ai-stack/defaults/main.yml` | Add three model name defaults |
| `autobot-slm-backend/ansible/roles/ai-stack/templates/ai-stack.env.j2` | Add three `AUTOBOT_*_MODEL` lines |
| `autobot-backend/middleware/validation_middleware.py` | Add `_BODY_SCAN_EXEMPT_RE` + extend `_is_exempt` |
| `autobot-backend/middleware/validation_middleware_test.py` | Add test: save path bypasses body scan; shell content in save → 200 |
| `autobot-slm-backend/ansible/roles/backend/templates/backend.env.j2` | Add `AUTOBOT_TLS_CA_PATH` line |

---

## Task 1: Fix Playwright browser install in Ansible browser role

**Files:**
- Modify: `autobot-slm-backend/ansible/roles/browser/tasks/main.yml:140-160`

The existing task at line 140 uses the Python pip `playwright` CLI, which installs browsers under the root user's `~/.cache/`. The Node.js service (`playwright-server.js`) looks for browsers at `PLAYWRIGHT_BROWSERS_PATH`. These two things never connect.

Fix: remove the wrong task; add three new tasks after the `npm install` step (line 160) — create the shared browsers dir, install via `node_modules/.bin/playwright install chromium` as root with the env var set, then fix ownership so the `autobot` service user can execute the binaries.

- [ ] **Step 1: Remove the wrong Python playwright browser install task**

In `autobot-slm-backend/ansible/roles/browser/tasks/main.yml`, delete lines 140–144:
```yaml
- name: "Browser | Install Playwright browsers"
  command: playwright install chromium firefox
  become: yes
  changed_when: false
  tags: ['browser', 'packages']
```

- [ ] **Step 2: Add the three replacement tasks after the npm install task (after line 160)**

Insert immediately after the `"Browser | Install Node.js dependencies for browser worker"` task (the one ending at line 160):

```yaml
- name: "Browser | Create Playwright browsers directory"
  ansible.builtin.file:
    path: /opt/autobot/autobot-browser-worker/browsers
    state: directory
    owner: autobot
    group: autobot
    mode: "0755"
  become: yes
  tags: ['browser', 'packages']

- name: "Browser | Install Playwright chromium browser via Node.js"
  ansible.builtin.command:
    cmd: node_modules/.bin/playwright install chromium
    chdir: /opt/autobot/autobot-browser-worker
  become: yes
  environment:
    PLAYWRIGHT_BROWSERS_PATH: /opt/autobot/autobot-browser-worker/browsers
  changed_when: false
  when: _browser_worker_dir.stat.exists | default(false)
  tags: ['browser', 'packages']

- name: "Browser | Fix Playwright browsers directory ownership"
  ansible.builtin.file:
    path: /opt/autobot/autobot-browser-worker/browsers
    state: directory
    owner: autobot
    group: autobot
    recurse: true
  become: yes
  when: _browser_worker_dir.stat.exists | default(false)
  tags: ['browser', 'packages']
```

- [ ] **Step 3: Verify syntax**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI
ansible-lint autobot-slm-backend/ansible/roles/browser/tasks/main.yml 2>&1 | head -20
```

Expected: no errors (warnings about `command` vs `shell` are acceptable).

- [ ] **Step 4: Commit**

```bash
git add autobot-slm-backend/ansible/roles/browser/tasks/main.yml
git commit -m "fix(ansible): install Playwright browsers via Node.js to shared path"
```

---

## Task 2: Add PLAYWRIGHT_BROWSERS_PATH to playwright systemd service template

**Files:**
- Modify: `autobot-slm-backend/ansible/roles/browser/templates/playwright.service.j2`

Without this env var the running `playwright-server.js` process uses the default per-user home lookup and never finds the browsers installed in Task 1.

- [ ] **Step 1: Add the env var to the service template**

In `autobot-slm-backend/ansible/roles/browser/templates/playwright.service.j2`, find the `[Service]` Environment block:

```ini
# Environment
Environment="PLAYWRIGHT_PORT={{ playwright_port }}"
Environment="BROWSER_TIMEOUT={{ browser_timeout }}"
Environment="HEADLESS={{ headless_mode | lower }}"
Environment="DISPLAY={{ vnc_display }}"
```

Add one line immediately after `Environment="DISPLAY={{ vnc_display }}"`:

```ini
Environment="PLAYWRIGHT_BROWSERS_PATH=/opt/autobot/autobot-browser-worker/browsers"
```

The full block should look like:
```ini
# Environment
Environment="PLAYWRIGHT_PORT={{ playwright_port }}"
Environment="BROWSER_TIMEOUT={{ browser_timeout }}"
Environment="HEADLESS={{ headless_mode | lower }}"
Environment="DISPLAY={{ vnc_display }}"
Environment="PLAYWRIGHT_BROWSERS_PATH=/opt/autobot/autobot-browser-worker/browsers"
```

- [ ] **Step 2: Verify the live service picks it up (on the deployed host)**

```bash
grep PLAYWRIGHT_BROWSERS_PATH /etc/systemd/system/autobot-playwright.service
```

Expected: `Environment="PLAYWRIGHT_BROWSERS_PATH=/opt/autobot/autobot-browser-worker/browsers"`

After Ansible re-deploys, verify:
```bash
systemctl restart autobot-playwright
sleep 5
curl -s http://127.0.0.1:9001/health | python3 -m json.tool
```

Expected: `"browser_connected": true`

- [ ] **Step 3: Commit**

```bash
git add autobot-slm-backend/ansible/roles/browser/templates/playwright.service.j2
git commit -m "fix(ansible): set PLAYWRIGHT_BROWSERS_PATH in playwright systemd service"
```

---

## Task 3: Add AI Stack agent model defaults and template vars

**Files:**
- Modify: `autobot-slm-backend/ansible/roles/ai-stack/defaults/main.yml`
- Modify: `autobot-slm-backend/ansible/roles/ai-stack/templates/ai-stack.env.j2`

`get_agent_model_explicit()` in `ssot_config.py` reads `AUTOBOT_{AGENT}_MODEL` and raises `AgentConfigurationError` if missing. The template sets providers and endpoints but not model names. All three agents (`chat`, `rag`, `classification`) fail at startup → `"agents": []`.

Default values match the constants in `autobot-backend/autobot_shared/ssot_config.py`:
- `DEFAULT_LLM_MODEL = "qwen3.5:9b"` (used for chat/quality)
- `INSTRUCTION_MODEL = "mistral:7b-instruct"` (used for rag)
- `CLASSIFICATION_MODEL = "gemma2:2b"` (used for classification)

- [ ] **Step 1: Add model defaults to defaults/main.yml**

In `autobot-slm-backend/ansible/roles/ai-stack/defaults/main.yml`, append at the end of the file (after `ai_redis_password`):

```yaml
# Agent LLM model names — must match AUTOBOT_*_MODEL expected by get_agent_model_explicit()
# Defaults mirror ssot_config.py constants; override in inventory for different models.
ai_chat_model: "qwen3.5:9b"
ai_rag_model: "mistral:7b-instruct"
ai_classification_model: "gemma2:2b"
```

- [ ] **Step 2: Add model vars to ai-stack.env.j2**

In `autobot-slm-backend/ansible/roles/ai-stack/templates/ai-stack.env.j2`, find the endpoint block at the end:
```
AUTOBOT_CHAT_ENDPOINT={{ ai_chat_endpoint }}
AUTOBOT_RAG_ENDPOINT={{ ai_rag_endpoint }}
AUTOBOT_CLASSIFICATION_ENDPOINT={{ ai_classification_endpoint }}
```

Add after it:
```
# Agent LLM model names (required by get_agent_model_explicit — no fallback)
AUTOBOT_CHAT_MODEL={{ ai_chat_model }}
AUTOBOT_RAG_MODEL={{ ai_rag_model }}
AUTOBOT_CLASSIFICATION_MODEL={{ ai_classification_model }}
```

- [ ] **Step 3: Verify the live service picks up the models (on deployed host)**

After Ansible re-deploys:
```bash
grep AUTOBOT_CHAT_MODEL /opt/autobot/autobot-ai-stack/.env
grep AUTOBOT_RAG_MODEL /opt/autobot/autobot-ai-stack/.env
grep AUTOBOT_CLASSIFICATION_MODEL /opt/autobot/autobot-ai-stack/.env
```

Expected: all three lines present with non-empty values.

Then verify agents load:
```bash
systemctl restart autobot-ai-stack
sleep 10
curl -s http://127.0.0.1:8080/ | python3 -m json.tool
```

Expected: `"agents"` list contains `"chat"`, `"rag"`, `"classification"` (not empty).

- [ ] **Step 4: Commit**

```bash
git add autobot-slm-backend/ansible/roles/ai-stack/defaults/main.yml
git add autobot-slm-backend/ansible/roles/ai-stack/templates/ai-stack.env.j2
git commit -m "fix(ansible): add missing AUTOBOT_*_MODEL vars to ai-stack env template"
```

---

## Task 4: Fix command injection false positive on /chats/{id}/save

**Files:**
- Modify: `autobot-backend/middleware/validation_middleware.py`
- Modify: `autobot-backend/middleware/validation_middleware_test.py`

`ValidationMiddleware._scan_body_strings` recurses into all string fields including stored AI responses and web search results. Shell command text in those results (e.g., `| curl`, `| cat`, `| ls`) triggers the command injection pattern → 400 → chat history lost silently.

`/chats/{id}/save` is a storage endpoint — it receives already-processed content, stores it, never executes it. Injection scanning on stored content is a false positive. The user input entry point (`/chats/{id}/message`) is a different path and stays protected.

- [ ] **Step 1: Write the failing test**

In `autobot-backend/middleware/validation_middleware_test.py`, add a new test fixture and two tests at the end of the file:

```python
# ---------------------------------------------------------------------------
# Storage-path exemption — /api/chats/{id}/save bypasses body scan
# ---------------------------------------------------------------------------

import uuid as _uuid

@pytest.fixture()
def save_client() -> TestClient:
    """Client with a /api/chats/{id}/save endpoint registered."""
    app = _make_app()

    @app.post("/api/chats/{chat_id}/save")
    async def save_endpoint(chat_id: str):
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


def test_save_path_allows_shell_command_content(save_client: TestClient) -> None:
    """Web search results and AI responses with shell patterns must not block saves."""
    chat_id = str(_uuid.uuid4())
    resp = save_client.post(
        f"/api/chats/{chat_id}/save",
        json={
            "messages": [
                {
                    "role": "assistant",
                    "content": (
                        "You can list files with `ls -la` or pipe output: "
                        "cat /etc/hosts | curl -s http://example.com"
                    ),
                }
            ]
        },
    )
    assert resp.status_code == 200


def test_non_save_chat_path_still_blocked(save_client: TestClient) -> None:
    """Injection in /api/chats/{id}/message must still be blocked."""
    chat_id = str(_uuid.uuid4())
    resp = save_client.post(
        f"/api/chats/{chat_id}/message",
        json={"content": "foo; rm -rf /"},
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/autobot-backend
python -m pytest middleware/validation_middleware_test.py::test_save_path_allows_shell_command_content middleware/validation_middleware_test.py::test_non_save_chat_path_still_blocked -v 2>&1 | tail -20
```

Expected: `test_save_path_allows_shell_command_content` FAILS with 400, `test_non_save_chat_path_still_blocked` FAILS (endpoint not registered returns 404, not 400).

- [ ] **Step 3: Add the exempt regex and update _is_exempt**

In `autobot-backend/middleware/validation_middleware.py`:

After the `_EXEMPT_PREFIXES` block (around line 66), add:

```python
# Paths that bypass body-content scanning only (not prefix-exempt, but storage-only).
# /api/chats/{uuid}/save stores already-processed AI/search content that legitimately
# contains shell command patterns. Injection scanning on stored content is a false
# positive. The input entry point (/chats/{id}/message) is NOT matched here.
_BODY_SCAN_EXEMPT_RE: Final[re.Pattern[str]] = re.compile(
    r"^/api/chats/[^/]+/save$"
)
```

Then update `_is_exempt` (around line 113) to:

```python
def _is_exempt(path: str) -> bool:
    """Return True when *path* should bypass validation."""
    return any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES) or bool(
        _BODY_SCAN_EXEMPT_RE.match(path)
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/autobot-backend
python -m pytest middleware/validation_middleware_test.py -v 2>&1 | tail -30
```

Expected: all tests PASS including the two new ones.

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/middleware/validation_middleware.py
git add autobot-backend/middleware/validation_middleware_test.py
git commit -m "fix(middleware): exempt /chats/{id}/save from command injection body scan"
```

---

## Task 5: Add AUTOBOT_TLS_CA_PATH to backend env template

**Files:**
- Modify: `autobot-slm-backend/ansible/roles/backend/templates/backend.env.j2`

`backend.env.j2` hardcodes `AUTOBOT_SLM_TLS_ENABLED=true` but never sets `AUTOBOT_TLS_CA_PATH`. The `slm_client.py` fallback chain tries `AUTOBOT_TLS_CA_PATH` first, then `AUTOBOT_SKIP_TLS_VERIFY`, then `certs/ca/ca-cert.pem` (relative, wrong path), then system trust store. The SLM uses a self-signed cert not in the system trust store → every fresh deployment fails WebSocket voice streaming.

`enable-tls.yml` deploys the CA cert to `/etc/autobot/certs/ca-cert.pem`. Setting `AUTOBOT_TLS_CA_PATH` to that path is always safe: if the file doesn't exist the code falls through gracefully.

- [ ] **Step 1: Add AUTOBOT_TLS_CA_PATH to backend.env.j2**

In `autobot-slm-backend/ansible/roles/backend/templates/backend.env.j2`, find line 43:
```
AUTOBOT_SLM_TLS_ENABLED=true
```

Add the CA path line immediately after it:
```
AUTOBOT_SLM_TLS_ENABLED=true
AUTOBOT_TLS_CA_PATH=/etc/autobot/certs/ca-cert.pem
```

- [ ] **Step 2: Verify on deployed host (after Ansible re-deploy)**

```bash
grep AUTOBOT_TLS_CA_PATH /etc/autobot/autobot-backend.env
```

Expected: `AUTOBOT_TLS_CA_PATH=/etc/autobot/certs/ca-cert.pem`

If `enable-tls.yml` has been run:
```bash
ls -la /etc/autobot/certs/ca-cert.pem
```

Expected: file exists and is readable.

Then restart backend and watch for SSL errors stopping:
```bash
systemctl restart autobot-backend
sleep 5
journalctl -u autobot-backend -n 20 --no-pager | grep -i "ssl\|cert\|websocket" | head -10
```

Expected: no `CERTIFICATE_VERIFY_FAILED` lines.

- [ ] **Step 3: Commit**

```bash
git add autobot-slm-backend/ansible/roles/backend/templates/backend.env.j2
git commit -m "fix(ansible): add AUTOBOT_TLS_CA_PATH to backend env for SLM WebSocket SSL"
```

---

## Task 6: Create PR

- [ ] **Step 1: Verify all changes are on branch**

```bash
git log origin/Dev_new_gui..HEAD --oneline
```

Expected: 5 commits (one per fix).

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin HEAD
```

Then use the `pr` skill or:
```bash
gh pr create \
  --base Dev_new_gui \
  --title "fix(provisioning): four out-of-box gaps — Playwright, AI Stack models, /save injection, SLM TLS" \
  --body "$(cat <<'EOF'
## Summary

Fixes four Ansible/code gaps that break AutoBot on a fresh `deploy-base` provisioning run:

- **Playwright browsers not installed**: Ansible was using Python's `playwright install` (wrong tool) as root (wrong user). Now uses `node_modules/.bin/playwright install chromium` with `PLAYWRIGHT_BROWSERS_PATH=/opt/autobot/autobot-browser-worker/browsers` + ownership fix. Service template updated to set the same env var.
- **AI Stack agents fail to load**: `ai-stack.env.j2` was missing `AUTOBOT_CHAT_MODEL`, `AUTOBOT_RAG_MODEL`, `AUTOBOT_CLASSIFICATION_MODEL`. All three agents raised `AgentConfigurationError` at startup → `"agents": []` indefinitely. Defaults added to `defaults/main.yml`; vars added to template.
- **Command injection false positive on `/chats/{id}/save`**: `ValidationMiddleware` recursed into stored AI/search content triggering shell pattern matches → 400 → silent chat history loss. Added `_BODY_SCAN_EXEMPT_RE` exempting only the save path; `/message` remains protected.
- **SLM WebSocket SSL fails on fresh install**: `backend.env.j2` set `AUTOBOT_SLM_TLS_ENABLED=true` but never set `AUTOBOT_TLS_CA_PATH`. The `slm_client.py` fallback exhausted without finding a trusted CA for the self-signed SLM cert. Added `AUTOBOT_TLS_CA_PATH=/etc/autobot/certs/ca-cert.pem` (safe — code handles missing file gracefully).

## Test plan

- [ ] Run `autobot-backend` middleware tests: `python -m pytest middleware/validation_middleware_test.py -v`
- [ ] After reprovisioning browser VM: `curl -s http://127.0.0.1:9001/health` → `"browser_connected": true`
- [ ] After reprovisioning AI Stack VM: `curl -s http://127.0.0.1:8080/` → `"agents"` list non-empty
- [ ] After reprovisioning backend: no `CERTIFICATE_VERIFY_FAILED` in `journalctl -u autobot-backend`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**Spec coverage:**
- ✅ Fix 1 (Playwright) → Tasks 1 + 2
- ✅ Fix 2 (AI Stack model vars) → Task 3
- ✅ Fix 3 (injection false positive) → Task 4
- ✅ Fix 4 (TLS CA path) → Task 5

**Placeholder scan:** No TBDs, all code blocks complete.

**Type consistency:** No shared types across tasks. Each task touches independent files.

**Edge case — Task 4 test fixture:** The `save_client` fixture registers `/api/chats/{chat_id}/save` on the test app but NOT `/api/chats/{chat_id}/message`, so `test_non_save_chat_path_still_blocked` will get a 404 (unregistered path) not a 400. Fix: register the message endpoint in the fixture too, or simply use the base `client` fixture for that test (which has `/api/test` — sufficient to prove injection is still blocked on non-exempt paths). The test is rewritten below to use `client` for the second case.

**Corrected test (replace Step 1 in Task 4 with this):**

```python
def test_non_save_chat_path_still_blocked(client: TestClient) -> None:
    """Injection on any non-exempt path must still be blocked."""
    resp = client.post(
        "/api/test",
        json={"content": "foo; rm -rf /"},
    )
    assert resp.status_code == 400
```
