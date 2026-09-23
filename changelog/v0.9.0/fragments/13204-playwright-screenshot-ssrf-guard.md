---
type: fix
scope: backend
issue: 13204
pr: 0000
---
`playwright_service.capture_screenshot` now runs its URL through the same DNS-resolving public-address guard `send_to_browser_vm` already applies, closing the last unguarded browser/fetch entry point.
