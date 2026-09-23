---
type: security
scope: secrets
issue: 13708
pr: 0000
---
New content-scanning credential redactor (`autobot_shared.secret_redaction.scan_content_for_credentials`/`redact_content`) closes the gap in the existing name-keyed redactor: it can now catch a credential sitting in free text (a signup email's "your password is X", a pasted API key, a PEM block, a basic-auth URL) with no field name to key on. Wired into `llm_shared.credential_redaction.redact_string` (so `llc/api/replay.py`'s `?redact_pii=true` path and every other caller get it automatically) and into `knowledge/connectors/content_extraction.py`'s DOCX/PDF text extraction, so a credential is masked before it can be persisted or indexed into Chroma — a vector-store copy can't be revoked the way a vault row can. Calibrated against real random secrets, UUIDs, commit SHAs and code snippets to keep the false-positive rate down (a forwarded code snippet or a base64 image must not quarantine an entire email thread).
