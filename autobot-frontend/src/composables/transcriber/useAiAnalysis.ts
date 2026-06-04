// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { ref, type Ref } from 'vue'
import { getBackendUrl } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useAiAnalysis')

export type AiAction = 'summarize' | 'key_facts' | 'protocol' | 'custom'

export function useAiAnalysis(recordingId: Ref<number>) {
  const result = ref('')
  const loading = ref(false)
  const error = ref<string | null>(null)
  const activeAction = ref<AiAction | ''>('')

  async function ask(action: AiAction, customQuestion?: string) {
    activeAction.value = action
    loading.value = true
    result.value = ''
    error.value = null

    const url = `${getBackendUrl()}/api/transcriber/recordings/${recordingId.value}/ai/ask`

    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          custom_question: action === 'custom' ? customQuestion : null,
        }),
      })

      const reader = resp.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('Response body reader not available')
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const text = decoder.decode(value)
        for (const line of text.split('\n')) {
          if (!line.startsWith('data:')) continue

          const data = line.slice(5).trim()
          if (data === '[DONE]') {
            loading.value = false
            return
          }

          try {
            const parsed = JSON.parse(data)
            if (parsed.content) {
              result.value += parsed.content
            }
            if (parsed.error) {
              error.value = parsed.error
              loading.value = false
              return
            }
          } catch {
            // Ignore JSON parse errors for malformed SSE frames
          }
        }
      }
    } catch (err) {
      logger.error('AI ask failed', err)
      error.value = 'Analysis failed. Please try again.'
    } finally {
      loading.value = false
    }
  }

  return {
    result,
    loading,
    error,
    activeAction,
    ask,
  }
}
