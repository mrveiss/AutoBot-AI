---
type: fix
scope: slm
issue: 22211
pr: 22230
---
The desktop server now serves one VNC desktop and no RDP. A one-off SLM migration assigns the `vnc` role to the node that carries the xrdp desktop purpose, the fleet update provisions it, VNC is verified listening, and only then is xrdp removed (refusing while an RDP session is live; `/etc/xrdp` is backed up; stored RDP credentials are kept). Roles may ship a `remove.yml` that `remove-role.yml` runs, and the VNC firewall rules open the real RFB port.
