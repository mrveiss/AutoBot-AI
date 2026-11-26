// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/** Debug check that the chat store and its localStorage copy agree; split out of useChatStore (#21357 size ceiling). */

import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ChatStorePersistence')

export function debugPersistenceState(sessions: { id: string }[], currentSessionId: string | null): void {
  try {
    const persistedData = localStorage.getItem('autobot-chat-store')
    if (persistedData) {
      const parsed = JSON.parse(persistedData)
      logger.debug('📊 Persistence Debug:')
      logger.debug(`  Store sessions: ${sessions.length}`)
      logger.debug(`  Persisted sessions: ${parsed.sessions?.length || 0}`)
      logger.debug(`  Store currentSessionId: ${currentSessionId}`)
      logger.debug(`  Persisted currentSessionId: ${parsed.currentSessionId}`)

      // Check for specific session IDs
      const storeIds = sessions.map(s => s.id)
      const persistedIds = parsed.sessions?.map((s: { id: string }) => s.id) || []
      logger.debug(`  Store IDs: [${storeIds.join(', ')}]`)
      logger.debug(`  Persisted IDs: [${persistedIds.join(', ')}]`)

      // Find discrepancies
      const missingFromPersisted = storeIds.filter(id => !persistedIds.includes(id))
      const extraInPersisted = persistedIds.filter((id: string) => !storeIds.includes(id))

      if (missingFromPersisted.length > 0) {
        logger.warn(`⚠️ Sessions in store but not persisted: [${missingFromPersisted.join(', ')}]`)
      }
      if (extraInPersisted.length > 0) {
        logger.warn(`⚠️ Sessions persisted but not in store: [${extraInPersisted.join(', ')}]`)
      }

      if (missingFromPersisted.length === 0 && extraInPersisted.length === 0) {
        logger.debug('✅ Store and persistence are in sync')
      }
    } else {
      logger.debug('📊 No persisted data found in localStorage')
    }
  } catch (error) {
    logger.error('❌ Error checking persistence state:', error)
  }
}
