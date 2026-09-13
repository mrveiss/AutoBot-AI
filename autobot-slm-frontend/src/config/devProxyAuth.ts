// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #16382: whether the dev proxy is allowed to inject X-Internal-API-Key.
 *
 * `autobot-backend/auth_middleware.py`'s `get_current_user` (and its SLM
 * mirror) treat that key as unconditional admin (`service:slm`) with no
 * session check at all. Injecting it into every `/autobot-api/*` request by
 * default — as this proxy used to — hands out backend admin to anyone who
 * can reach this dev server, and it binds to 0.0.0.0 (see `vite.config.ts`'s
 * `server.host`), so that is anyone on the same network, not just localhost.
 *
 * Defaults OFF. A dev flow that genuinely needs the service-auth bypass
 * (e.g. exercising the full SLM<->backend integration without logging in)
 * must opt in explicitly:
 *
 *   AUTOBOT_DEV_INJECT_INTERNAL_API_KEY=true AUTOBOT_INTERNAL_API_KEY=<key> npm run dev
 *
 * Never enable this on a machine reachable from outside your own workstation.
 *
 * Extracted out of `vite.config.ts` (rather than tested via that file
 * directly) because Vitest cannot cleanly import a `vite.config.ts` module
 * under test — importing it re-triggers Vite's own config-loading machinery.
 */
export function shouldInjectInternalApiKey(env: NodeJS.ProcessEnv = process.env): boolean {
  const optIn = env.AUTOBOT_DEV_INJECT_INTERNAL_API_KEY
  return optIn === 'true' && Boolean(env.AUTOBOT_INTERNAL_API_KEY)
}
