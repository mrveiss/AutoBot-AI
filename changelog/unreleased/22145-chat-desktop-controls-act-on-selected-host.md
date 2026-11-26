---
type: fix
scope: backend
issue: 22145
pr: 0000
---
The chat Desktop controls (click, type, key, scroll, drag, clipboard, screenshot, control lock) now act on the /secrets host being shown, over that host's own VNC endpoint with its stored VNC password, instead of AutoBot's own display. A fleet node id or an unknown id is refused. An infrastructure host with no username or capabilities is rejected with a clear message instead of defaulting to root and ssh. The desktop control lock and the noVNC client URLs now use the canonical API base and an https scheme, and the SLM noVNC tool connects to the selected fleet endpoint instead of faking the connection.
