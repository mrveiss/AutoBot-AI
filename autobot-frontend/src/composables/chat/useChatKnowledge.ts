// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Whether answers draw on the knowledge base (RAG, #249) -- the one source for the composer's
 * "Use Knowledge" chip, the `use_knowledge` send option and the chat header's "Knowledge on/off"
 * sub-line (#18243). Module-level so the header and the composer read the same state; it was a
 * local ref inside ChatInput.vue, which the header could not see. On by default, as before.
 */
import { ref } from 'vue'

const enabled = ref(true)

export function useChatKnowledge() {
  return { enabled }
}
