// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { ref, toValue, type MaybeRefOrGetter } from 'vue'
import { getBackendUrl } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useAiAnalysis')

export type AiAnalysisAction = 'summarize' | 'key_facts' | 'protocol' | 'custom'

export interface AskOptions {
  action: AiAnalysisAction
  customQuestion?: string
}

/**
 * Composable for AI analysis SSE streaming
 * Handles fetch-based SSE stream parsing for transcriber AI analysis
 */
export function useAiAnalysis(recordingId: MaybeRefOrGetter<number>) {
  const streaming = ref(false)
  const content = ref('')
  const activeAction = ref<AiAnalysisAction | ''>('')

  async function ask(options: AskOptions) {
    const { action, customQuestion } = options
    activeAction.value = action
    streaming.value = true
    content.value = ''

    const url = `${getBackendUrl()}/api/transcriber/recordings/${toValue(recordingId)}/ai/ask`

    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          custom_question: action === 'custom' ? customQuestion : null
        }),
      })

      const reader = resp.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('No response body reader available')
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const text = decoder.decode(value)
        for (const line of text.split('\n')) {
          if (!line.startsWith('data:')) continue

          const data = line.slice(5).trim()
          if (data === '[DONE]') {
            streaming.value = false
            return
          }

          try {
            const parsed = JSON.parse(data)
            if (parsed.content) {
              content.value += parsed.content
            }
            if (parsed.error) {
              content.value = `Error: ${parsed.error}`
              streaming.value = false
              return
            }
          } catch {
            // Ignore malformed JSON in SSE stream
          }
        }
      }
    } catch (err) {
      logger.error('AI ask failed', err)
      content.value = 'Analysis failed. Please try again.'
    } finally {
      streaming.value = false
    }
  }

  return {
    streaming,
    content,
    activeAction,
    ask,
  }
}
