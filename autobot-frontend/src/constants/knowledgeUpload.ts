// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * What `POST /knowledge_base/upload` actually accepts (#17528).
 *
 * These were previously spelled out inside `KnowledgeUpload.vue`, and the spelling had
 * drifted from the server's in both directions: the picker offered `.doc`, `.yaml`,
 * `.yml` and `.xml`, which the endpoint rejects with a 400 after the upload, and it hid
 * all five office types `#16775` had added server-side. Neither direction announced
 * itself — one wasted a round trip to say no, the other simply made a supported format
 * look unsupported.
 *
 * Kept here rather than in the component so a guard can compare them against
 * `autobot-backend/api/knowledge.py` and fail when they drift again; the component is
 * not the right place for a value the backend owns.
 */

/**
 * Mirror of `ALLOWED_EXTENSIONS` in `autobot-backend/api/knowledge.py`, which is
 * `{".txt", ".md", ".pdf", ".docx", ".json", ".csv", ".html"} | OFFICE_EXTENSIONS`.
 *
 * Sorted, lowercase, leading dot — the form the server compares against after
 * `os.path.splitext(filename.lower())`.
 */
export const KNOWLEDGE_UPLOAD_EXTENSIONS: readonly string[] = [
  '.csv',
  '.docx',
  '.html',
  '.json',
  '.md',
  '.odp',
  '.ods',
  '.odt',
  '.pdf',
  '.pptx',
  '.txt',
  '.xlsx'
] as const

/**
 * Mirror of `MAX_FILE_SIZE_MB` in `autobot-backend/api/knowledge.py`.
 *
 * Checking it client-side is a courtesy, not the enforcement: the server rejects an
 * oversize upload with 400 regardless. It never truncates, so a file over this size is
 * refused whole.
 */
export const KNOWLEDGE_UPLOAD_MAX_MB = 10

/** The same limit in bytes, for comparing against `File.size`. */
export const KNOWLEDGE_UPLOAD_MAX_BYTES = KNOWLEDGE_UPLOAD_MAX_MB * 1024 * 1024

/** The value for an `<input type="file">` `accept` attribute. */
export const KNOWLEDGE_UPLOAD_ACCEPT = KNOWLEDGE_UPLOAD_EXTENSIONS.join(',')
