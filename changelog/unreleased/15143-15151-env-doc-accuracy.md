---
type: fix
scope: infra
issue: 15143
---
`detect-environment.sh` used to name an env file nothing tracks or generates for four of its five branches, silently exporting nothing; it now maps every branch to a real, generated file and fails loudly if one goes missing. `docs/guides/CONFIGURATION_GUIDE.md` documented nine `AUTOBOT_*` knobs (including `AUTOBOT_PLAYWRIGHT_HOST`/`AUTOBOT_PLAYWRIGHT_API_PORT`) that had no code reading them anywhere and one (`AUTOBOT_PLAYWRIGHT_VNC_PORT`) that was a misspelling of the real `AUTOBOT_VNC_PORT`; the dead ones are removed and the misnamed one corrected.
