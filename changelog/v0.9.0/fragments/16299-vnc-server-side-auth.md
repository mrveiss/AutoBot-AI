---
type: security
scope: desktop
issue: 16299
pr: 0000
---
The backend now answers the real VNC server's password challenge itself and offers the browser security-type "None", so noVNC never sees or needs a password — closes the `VITE_*_VNC_PASSWORD` leak (compiled into every browser's bundle). The password is provisioned once by Ansible and read at connection time from the canonical secrets system; a missing secret fails the connection closed rather than falling back to no auth.
