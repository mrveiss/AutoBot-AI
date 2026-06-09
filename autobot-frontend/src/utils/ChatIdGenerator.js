// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
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

  // Fallback: crypto.getRandomValues
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 1
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
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
