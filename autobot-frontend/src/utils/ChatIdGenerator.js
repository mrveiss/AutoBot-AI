/**
 * Chat ID Generator - Ensures consistent UUID format across the application
 * Matches backend expected format for proper session management
 */

/**
 * Generate a UUID v4 format chat ID
 * Format: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
 * This matches the backend's UUID format for consistent session management
 */
export function generateChatId() {
  // Use crypto API if available (modern browsers)
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }

  // Fallback UUID v4 implementation
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0;
    const v = c == 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

/**
 * Generate a message ID in UUID format
 * For consistency with chat IDs and backend expectations
 */
export function generateMessageId() {
  return generateChatId();
}

/**
 * Generate a category ID in UUID format
 * For knowledge base category management
 */
export function generateCategoryId() {
  return generateChatId();
}

/**
 * Generate a document ID in UUID format
 * For knowledge base document tracking
 */
export function generateDocumentId() {
  return generateChatId();
}

/**
 * Validate if a string is a proper UUID format
 * Used to check if existing chat IDs are in the correct format
 */
export function isValidUUID(uuid) {
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  return uuidRegex.test(uuid);
}

/**
 * Convert old format chat IDs to UUID format
 * Used for migration of existing chat sessions
 */
export function migrateChatId(oldChatId) {
  if (isValidUUID(oldChatId)) {
    return oldChatId; // Already in correct format
  }

  // Generate new UUID for old format IDs
  return generateChatId();
}

export default {
  generateChatId,
  generateMessageId,
  generateDocumentId,
  generateCategoryId,
  isValidUUID,
  migrateChatId
};
