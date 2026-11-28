---
type: fix
scope: backend
issue: 21403
pr: 21732
---
A conversation file upload now passes the content type the client declared to the file manager. One rule (`resolve_mime_type`) decides the stored type: the filename extension wins, and the declared type is used only for an extension with no known type, when it is a single well-formed type (never the generic octet-stream).
