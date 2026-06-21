// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// ESLint test fixture for the #6784 `no-restricted-syntax` rule.
// Every line below SHOULD trigger the hardcoded-VM-IP rule when scanned
// directly. Wire-in: this fixture is excluded from the production lint
// step (see eslint.config.ts ignore list); it exists only for manual
// verification — `npx eslint --rule ... eslint-tests/` against this file.
//
// To verify locally:
//   cd autobot-frontend
//   npx eslint eslint-tests/no-hardcoded-vm-ip-deny.test.ts
//   # Expected: 6 errors (one per `// EXPECT-ERROR` line)

/* eslint-disable */

// EXPECT-ERROR: bare literal IP
const a = '172.16.168.20'

// EXPECT-ERROR: HTTP URL with literal IP
const b = 'http://172.16.168.21:5173'

// EXPECT-ERROR: HTTPS URL with literal IP
const c = 'https://172.16.168.20:8443/api'

// EXPECT-ERROR: literal in `||` fallback (the original anti-pattern)
const d = (import.meta.env as { VITE_BACKEND_HOST?: string }).VITE_BACKEND_HOST
  || 'http://172.16.168.20:8001'

// EXPECT-ERROR: literal in `??` fallback (newer null-coalescing form)
const e = (window as unknown as { __backend?: string }).__backend
  ?? 'http://172.16.168.20:8001'

// EXPECT-ERROR: template literal with literal IP
const f = `ws://172.16.168.21:5173/ws`

export { a, b, c, d, e, f }
