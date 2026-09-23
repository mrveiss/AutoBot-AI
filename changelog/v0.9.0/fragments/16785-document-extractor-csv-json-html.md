---
type: feat
scope: backend
issue: 16785
pr: 16790
---
DocumentExtractor now handles .csv/.json/.html the same way the GUI upload path does (CSV as text, JSON re-serialised with indent=2, HTML via the shared sanitiser), so a file no longer gets ingested through the upload form and rejected when discovered by a connector or directory walk.
