-- Conversation-Specific File Management Schema
-- Manages file uploads, associations with chat sessions, and metadata tracking
-- Database: data/conversation_files.db (SQLite)

-- ============================================================================
-- CRITICAL: Enable Foreign Keys Globally
-- ============================================================================
-- Must be set BEFORE any table creation to ensure referential integrity
-- This setting persists for all future connections to this database
PRAGMA foreign_keys = ON;

-- ============================================================================
-- CORE TABLES
-- ============================================================================

-- conversation_files: Main table tracking all uploaded files
CREATE TABLE IF NOT EXISTS conversation_files (
    file_id TEXT PRIMARY KEY,                      -- UUID v4 for unique file identification
    session_id TEXT NOT NULL,                      -- Chat session identifier
    original_filename TEXT NOT NULL,               -- Original filename from upload
    stored_filename TEXT NOT NULL UNIQUE,          -- Unique storage filename (prevents collisions)
    file_path TEXT NOT NULL,                       -- Full path to stored file
    file_size INTEGER NOT NULL,                    -- File size in bytes
    file_hash TEXT NOT NULL,                       -- SHA-256 hash for deduplication and integrity
    mime_type TEXT,                                -- MIME type (e.g., 'image/png', 'application/pdf')
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    uploaded_by TEXT,                              -- User identifier (optional for multi-user support)
    is_deleted INTEGER DEFAULT 0,                  -- Soft delete flag (0=active, 1=deleted)
    deleted_at TIMESTAMP NULL,                     -- Deletion timestamp

    -- Constraints
    CHECK (file_size >= 0),
    CHECK (is_deleted IN (0, 1))
);

-- file_metadata: Extended metadata for uploaded files
CREATE TABLE IF NOT EXISTS file_metadata (
    metadata_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT NOT NULL,                         -- Foreign key to conversation_files
    metadata_key TEXT NOT NULL,                    -- Metadata key (e.g., 'width', 'duration', 'author')
    metadata_value TEXT,                           -- Metadata value (stored as text for flexibility)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    FOREIGN KEY (file_id) REFERENCES conversation_files(file_id) ON DELETE CASCADE,
    UNIQUE (file_id, metadata_key)                 -- Prevent duplicate keys for same file
);

-- session_file_associations: Explicit many-to-many relationship between sessions and files
CREATE TABLE IF NOT EXISTS session_file_associations (
    association_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,                      -- Chat session identifier
    file_id TEXT NOT NULL,                         -- Foreign key to conversation_files
    association_type TEXT DEFAULT 'upload',        -- Type: 'upload', 'reference', 'generated'
    message_id TEXT,                               -- Optional: specific message that referenced file
    associated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    FOREIGN KEY (file_id) REFERENCES conversation_files(file_id) ON DELETE CASCADE,
    UNIQUE (session_id, file_id, message_id)       -- Prevent duplicate associations
);

-- file_access_log: Audit trail for file access and operations
CREATE TABLE IF NOT EXISTS file_access_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT NOT NULL,                         -- Foreign key to conversation_files
    access_type TEXT NOT NULL,                     -- Type: 'upload', 'download', 'view', 'delete'
    accessed_by TEXT,                              -- User identifier
    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    access_metadata TEXT,                          -- JSON for additional context (IP, user agent, etc.)

    -- Constraints
    FOREIGN KEY (file_id) REFERENCES conversation_files(file_id) ON DELETE CASCADE,
    CHECK (access_type IN ('upload', 'download', 'view', 'delete', 'restore'))
);

-- file_cleanup_queue: Queue for scheduled file cleanup operations
CREATE TABLE IF NOT EXISTS file_cleanup_queue (
    cleanup_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT NOT NULL,                         -- Foreign key to conversation_files
    session_id TEXT NOT NULL,                      -- Session identifier for batch operations
    scheduled_deletion_time TIMESTAMP NOT NULL,    -- When file should be deleted
    cleanup_reason TEXT DEFAULT 'session_ended',   -- Reason: 'session_ended', 'user_request', 'expired'
    is_processed INTEGER DEFAULT 0,                -- Processing status (0=pending, 1=processed)
    processed_at TIMESTAMP NULL,                   -- When cleanup was processed

    -- Constraints
    FOREIGN KEY (file_id) REFERENCES conversation_files(file_id) ON DELETE CASCADE,
    CHECK (is_processed IN (0, 1)),
    CHECK (cleanup_reason IN ('session_ended', 'user_request', 'expired', 'space_limit'))
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Performance indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_conversation_files_session
    ON conversation_files(session_id, is_deleted);

CREATE INDEX IF NOT EXISTS idx_conversation_files_hash
    ON conversation_files(file_hash, is_deleted);

CREATE INDEX IF NOT EXISTS idx_conversation_files_uploaded_at
    ON conversation_files(uploaded_at DESC);

CREATE INDEX IF NOT EXISTS idx_file_metadata_file_id
    ON file_metadata(file_id);

CREATE INDEX IF NOT EXISTS idx_session_associations_session
    ON session_file_associations(session_id);

CREATE INDEX IF NOT EXISTS idx_session_associations_file
    ON session_file_associations(file_id);

CREATE INDEX IF NOT EXISTS idx_file_access_log_file
    ON file_access_log(file_id, accessed_at DESC);

CREATE INDEX IF NOT EXISTS idx_cleanup_queue_processed
    ON file_cleanup_queue(is_processed, scheduled_deletion_time);

-- ============================================================================
-- TRIGGERS
-- ============================================================================

-- Trigger: Auto-update deleted_at timestamp on soft delete
CREATE TRIGGER IF NOT EXISTS trg_conversation_files_soft_delete
AFTER UPDATE OF is_deleted ON conversation_files
WHEN NEW.is_deleted = 1 AND OLD.is_deleted = 0
BEGIN
    UPDATE conversation_files
    SET deleted_at = CURRENT_TIMESTAMP
    WHERE file_id = NEW.file_id;
END;

-- Trigger: Audit log entry on file upload
CREATE TRIGGER IF NOT EXISTS trg_conversation_files_upload_log
AFTER INSERT ON conversation_files
BEGIN
    INSERT INTO file_access_log (file_id, access_type, accessed_by, access_metadata)
    VALUES (NEW.file_id, 'upload', NEW.uploaded_by,
            json_object('file_size', NEW.file_size, 'mime_type', NEW.mime_type));
END;

-- Trigger: Auto-create cleanup queue entry on session association
CREATE TRIGGER IF NOT EXISTS trg_session_association_cleanup_schedule
AFTER INSERT ON session_file_associations
BEGIN
    INSERT INTO file_cleanup_queue (file_id, session_id, scheduled_deletion_time, cleanup_reason)
    VALUES (NEW.file_id, NEW.session_id,
            datetime('now', '+30 days'), 'session_ended');
END;

-- ============================================================================
-- VIEWS
-- ============================================================================

-- View: Active files with session count
CREATE VIEW IF NOT EXISTS v_active_files AS
SELECT
    cf.file_id,
    cf.session_id,
    cf.original_filename,
    cf.file_size,
    cf.file_hash,
    cf.mime_type,
    cf.uploaded_at,
    cf.uploaded_by,
    COUNT(DISTINCT sfa.session_id) as session_count,
    MAX(sfa.associated_at) as last_associated_at
FROM conversation_files cf
LEFT JOIN session_file_associations sfa ON cf.file_id = sfa.file_id
WHERE cf.is_deleted = 0
GROUP BY cf.file_id;

-- View: Session file summary
CREATE VIEW IF NOT EXISTS v_session_file_summary AS
SELECT
    sfa.session_id,
    COUNT(DISTINCT sfa.file_id) as total_files,
    SUM(cf.file_size) as total_size,
    MIN(sfa.associated_at) as first_file_added,
    MAX(sfa.associated_at) as last_file_added
FROM session_file_associations sfa
JOIN conversation_files cf ON sfa.file_id = cf.file_id
WHERE cf.is_deleted = 0
GROUP BY sfa.session_id;

-- View: Pending cleanup operations
CREATE VIEW IF NOT EXISTS v_pending_cleanups AS
SELECT
    fcq.cleanup_id,
    fcq.file_id,
    fcq.session_id,
    cf.original_filename,
    cf.file_size,
    fcq.scheduled_deletion_time,
    fcq.cleanup_reason,
    CAST((julianday(fcq.scheduled_deletion_time) - julianday('now')) * 24 * 60 AS INTEGER) as minutes_until_deletion
FROM file_cleanup_queue fcq
JOIN conversation_files cf ON fcq.file_id = cf.file_id
WHERE fcq.is_processed = 0
  AND fcq.scheduled_deletion_time <= datetime('now', '+7 days')
ORDER BY fcq.scheduled_deletion_time ASC;

-- ============================================================================
-- ANALYTICS QUERIES (Commented as examples)
-- ============================================================================

-- Total storage used per session:
-- SELECT session_id, SUM(file_size) as total_storage
-- FROM conversation_files
-- WHERE is_deleted = 0
-- GROUP BY session_id;

-- Most accessed files:
-- SELECT cf.file_id, cf.original_filename, COUNT(fal.log_id) as access_count
-- FROM conversation_files cf
-- JOIN file_access_log fal ON cf.file_id = fal.file_id
-- WHERE cf.is_deleted = 0
-- GROUP BY cf.file_id
-- ORDER BY access_count DESC
-- LIMIT 10;

-- Files without session associations (orphaned):
-- SELECT cf.file_id, cf.original_filename, cf.uploaded_at
-- FROM conversation_files cf
-- LEFT JOIN session_file_associations sfa ON cf.file_id = sfa.file_id
-- WHERE sfa.association_id IS NULL
--   AND cf.is_deleted = 0;
