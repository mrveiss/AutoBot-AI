---
type: fix
scope: docs
issue: 15151
pr: 0000
---
`CONFIGURATION_GUIDE.md`'s three Playwright/VNC env-var names were dead (nothing read them); corrected to the real `AUTOBOT_BROWSER_SERVICE_HOST`/`_PORT`/`AUTOBOT_VNC_PORT` and registered all three in `env_registry.py`.
