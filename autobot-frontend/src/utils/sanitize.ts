// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Re-export of the single DOMPurify-backed sanitiser kept in the shared kit
 * (#2847, #19118). Every v-html binding MUST go through these functions.
 */
export {
  sanitizeChatHtml,
  sanitizeKnowledgeHtml,
  sanitizeHtml,
  escapeHtml,
} from '@autobot/ui'
