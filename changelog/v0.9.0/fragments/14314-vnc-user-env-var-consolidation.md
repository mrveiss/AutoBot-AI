---
type: fix
scope: infrastructure
issue: 14314
pr: 0
---
The vnc ansible role and the `fix-vnc-desktop.sh` / `fix-vnc-wsl.sh` recovery scripts read different environment variables for the VNC account (`VNC_USER` vs `AUTOBOT_VNC_USER`), so setting one silently did nothing on the other path. All three now resolve `VNC_USER` first, with `AUTOBOT_VNC_USER` kept as a deprecated fallback alias for one release.
