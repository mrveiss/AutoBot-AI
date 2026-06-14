// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// ESLint test fixture for the #6784 `no-restricted-syntax` rule.
// Every line below MUST NOT trigger the hardcoded-VM-IP rule.
// Loopback / RFC 1918 example space / SSOT lookups are all legitimate.
//
// To verify locally:
//   cd autobot-frontend
//   npx eslint eslint-tests/no-hardcoded-vm-ip-allow.test.ts
//   # Expected: 0 errors

/* eslint-disable */

// Loopback — fine for single-host installs (default in SSOT, see #2953)
const loopback = '127.0.0.1'

// RFC 1918 example space (192.168.x.x) — used in tests, SSRF guards, i18n placeholders
const exampleSpace = '192.168.1.100'
const subnetExample = '192.168.0.0/16'

// SSOT lookup — the canonical fallback pattern
const main = (import.meta.env as { VITE_BACKEND_HOST?: string }).VITE_BACKEND_HOST
  || window.location.hostname

// Template literal using SSOT — no embedded IP literal
const ssotUrl = `https://${window.location.hostname}/api`

// IPs in adjacent ranges (172.16.169.X, 172.17.X, 172.31.X) are NOT
// blocked by this rule — only AutoBot's deployment range 172.16.168.X.
// Defensive: if you genuinely have IPs from those ranges, file a follow-up
// issue to extend the regex.
const otherPrivate = '10.0.0.1'

export { loopback, exampleSpace, subnetExample, main, ssotUrl, otherPrivate }
