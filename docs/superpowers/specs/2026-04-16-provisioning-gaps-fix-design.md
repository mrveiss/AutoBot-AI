# Provisioning Gaps Fix — Design Spec
**Date:** 2026-04-16  
**Session:** systematic-debugging of session b1ecb7b0  
**Status:** Approved

## Problem

Four provisioning bugs mean a fresh Ansible deployment leaves AutoBot broken out of the box. None require code logic changes — all are configuration/template gaps.

## Fix 1: Playwright Chromium Not Installed

**Root cause (two sub-bugs):**
1. Ansible runs `playwright install` (Python pip's CLI) as root. The service runs `playwright-server.js` (Node.js), which requires `npx playwright install`.
2. Browsers install under the running user's home (`/root/.cache/`). The service runs as `autobot` → browser binary not found at `/home/autobot/.cache/ms-playwright/`.
3. `playwright.service.j2` does not set `PLAYWRIGHT_BROWSERS_PATH`, so the Node.js process uses its default home-based lookup.

**Changes:**
- `autobot-slm-backend/ansible/roles/browser/tasks/main.yml`:
  - Add task to create `/opt/autobot/autobot-browser-worker/browsers` dir owned by `autobot:autobot`.
  - Replace `playwright install chromium firefox` task with `PLAYWRIGHT_BROWSERS_PATH=... npx playwright install chromium` run as `autobot` user, with `creates:` guard.
- `autobot-slm-backend/ansible/roles/browser/templates/playwright.service.j2`:
  - Add `Environment="PLAYWRIGHT_BROWSERS_PATH=/opt/autobot/autobot-browser-worker/browsers"`.

## Fix 2: AI Stack Agents Fail to Initialize

**Root cause:** `ai-stack.env.j2` sets providers and endpoints but omits `AUTOBOT_CHAT_MODEL`, `AUTOBOT_RAG_MODEL`, `AUTOBOT_CLASSIFICATION_MODEL`. All three agents raise `AgentConfigurationError` at startup → `"agents": []` forever.

**Changes:**
- `autobot-slm-backend/ansible/roles/ai-stack/defaults/main.yml`:
  - Add `ai_chat_model: "qwen3.5:9b"`, `ai_rag_model: "mistral:7b-instruct"`, `ai_classification_model: "gemma2:2b"` (matching `ssot_config.py` constants).
- `autobot-slm-backend/ansible/roles/ai-stack/templates/ai-stack.env.j2`:
  - Add `AUTOBOT_CHAT_MODEL=`, `AUTOBOT_RAG_MODEL=`, `AUTOBOT_CLASSIFICATION_MODEL=`.

## Fix 3: Command Injection False Positive on `/chats/{id}/save`

**Root cause:** `ValidationMiddleware._scan_body_strings` recurses into all string fields including stored AI responses and web search results. Legitimate content (`| curl`, `| cat`, `| ls`) triggers the command injection pattern → 400 on save → **chat history lost silently**.

`/chats/{id}/message` and `/chats/{id}/save` share the `/api/chats/` prefix, so a prefix exemption would also exempt user input. A suffix-based exemption is required.

**Change:**
- `autobot-backend/middleware/validation_middleware.py`:
  - Add `_BODY_SCAN_EXEMPT_RE` compiled regex matching `/api/chats/{uuid}/save`.
  - Extend `_is_exempt` to return `True` when the regex matches.

## Fix 4: SLM WebSocket SSL Fails After Fresh Provisioning

**Root cause:** `backend.env.j2` hardcodes `AUTOBOT_SLM_TLS_ENABLED=true` but never sets `AUTOBOT_TLS_CA_PATH`. `enable-tls.yml` deploys the CA cert to `/etc/autobot/certs/ca-cert.pem` but is a separate playbook not run during standard provisioning. The code's fallback path (`certs/ca/ca-cert.pem` relative to project root) does not match that location.

User decision: always use the default path (`/etc/autobot/certs/ca-cert.pem`). The code already handles "file not present" gracefully (falls through to system trust store), so this is safe on installs where TLS hasn't been set up yet.

**Change:**
- `autobot-slm-backend/ansible/roles/backend/templates/backend.env.j2`:
  - Add `AUTOBOT_TLS_CA_PATH=/etc/autobot/certs/ca-cert.pem`.

## Files Changed

| File | Change |
|------|--------|
| `autobot-slm-backend/ansible/roles/browser/tasks/main.yml` | Fix Playwright install command + add browsers dir task |
| `autobot-slm-backend/ansible/roles/browser/templates/playwright.service.j2` | Add `PLAYWRIGHT_BROWSERS_PATH` env var |
| `autobot-slm-backend/ansible/roles/ai-stack/defaults/main.yml` | Add model name defaults |
| `autobot-slm-backend/ansible/roles/ai-stack/templates/ai-stack.env.j2` | Add `AUTOBOT_*_MODEL` vars |
| `autobot-backend/middleware/validation_middleware.py` | Exempt `/chats/{id}/save` from body scanning |
| `autobot-slm-backend/ansible/roles/backend/templates/backend.env.j2` | Add `AUTOBOT_TLS_CA_PATH` |

## Non-Goals

- No changes to AI Stack Python code (agent init logic stays as-is).
- No changes to TLS enforcement level — `AUTOBOT_SLM_TLS_ENABLED` stays `true`.
- Voice SSL is only fixed at the CA path layer; full mTLS cert rotation is out of scope.
