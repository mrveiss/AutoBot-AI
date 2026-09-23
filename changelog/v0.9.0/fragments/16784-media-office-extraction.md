---
type: fix
scope: backend
issue: 16784
pr: 0000
---
The media document pipeline no longer decodes spreadsheets, presentations and OpenDocument files as plain text. extract_document dispatched pdf and docx and fell through to extract_plain_text for everything else, so a verified office document arrived downstream as binary noise presented as document text — into the knowledge base, and into prompts through retrieval. It now delegates to the parsers utils/document_parser.py already owns, and raises an error naming the format when they cannot read it, so nothing downstream has to tell a bad document apart from one this path could not read. A missing parser library is checked before delegating so it stays a dependency error rather than being reported as a bad upload.
