---
type: fix
scope: backend
issue: 21990
---
The category quarantine index is now synced from the fact's stored metadata after an update, and a rebuild batch re-reads after its write and corrects any entry an update changed meanwhile.
