// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useChatTranslation')

export interface TranslationResult {
  originalText: string
  translatedText: string
  targetLanguage: string
  sourceLanguage?: string
}

/**
 * Composable encapsulating the two translation API calls used by
 * TranslationShortcutPanel: translate text and detect language.
 */
export function useChatTranslation() {
  async function translateText(
    text: string,
    targetLanguage: string,
  ): Promise<{ translatedText: string } | { error: string }> {
    try {
      const result = await apiClient.post<{ status: string; response: string }>(
        `${getApiBase()}/translate`,
        { text, target_language: targetLanguage },
      )
      if (result.status === 'success') {
        return { translatedText: result.response }
      }
      return { error: result.response }
    } catch (err) {
      logger.error('Translation failed:', err)
      return { error: '' }
    }
  }

  async function detectLanguage(
    text: string,
  ): Promise<{ detectedLanguage: string } | { error: string }> {
    try {
      const result = await apiClient.post<{ status: string; response: string }>(
        `${getApiBase()}/detect-language`,
        { text },
      )
      if (result.status === 'success') {
        return { detectedLanguage: result.response }
      }
      return { error: result.response }
    } catch (err) {
      logger.error('Language detection failed:', err)
      return { error: '' }
    }
  }

  return { translateText, detectLanguage }
}
