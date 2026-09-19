---
type: fix
scope: frontend
issue: 16933
pr: 0000
---
`/admin/pricing` and `/admin/mcp-servers` (#16825) merged with `hideInNav: true` but no matching entry in `navItems.ts`'s `adminMenuItems` — in this codebase `hideInNav: true` means "listed in the admin menu instead of the main nav", not "hidden", so both screens were reachable only by typing the URL directly. Added the missing `adminMenuItems` entries (with translations across all 11 locales) and extended `nav-items-coverage.test.ts` to check every `hideInNav` `/admin/*` route against `adminMenuItems`, which the existing coverage test structurally could not do — it short-circuits on `hideInNav: true` before reaching any allowlist or membership check. Proved by a test that removes a real `adminMenuItems` entry and confirms the new check would have caught it.
