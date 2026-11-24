// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * MCP prompt templates for the composer's picker (MVA-2167, moved out of McpPromptPicker.vue, #18243):
 * list each bridge's prompts, pick one, fill its parameters, and render it to draft text. Failures are
 * locale keys (`error`, `formError`) so the component translates them; the kit and composables hold no text.
 */
import { computed, ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('McpPromptPicker')

export const MCP_BRIDGES = ['git', 'knowledge', 'filesystem'] as const
export type McpBridge = (typeof MCP_BRIDGES)[number]

export interface McpPromptArgument { name: string; description?: string; required?: boolean }
export interface McpPrompt { name: string; description?: string; arguments?: McpPromptArgument[] }
interface PromptMessage { role: string; content: unknown }
interface RenderedPrompt { description?: string; messages: PromptMessage[] }
export interface FormError { key: string; params?: Record<string, string> }

/** The text of one message's content: a string, `{ text }`, or an array of either. */
function contentText(content: unknown): string {
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    return content.map((c) => (typeof c === 'string' ? c : (c as { text?: string })?.text || '')).join('\n')
  }
  if (content && typeof content === 'object' && 'text' in content) return (content as { text?: string }).text ?? ''
  return ''
}

/** The draft text of a rendered prompt: its non-empty messages, blank-line separated. */
export function promptDraftText(response: RenderedPrompt): string {
  return response.messages
    .map((msg) => contentText(msg.content))
    .filter((text) => text.trim() !== '')
    .join('\n\n')
}

export function useMcpPrompts() {
  const api = useApiClient()
  const activeBridge = ref<McpBridge>('git')
  const loading = ref(false)
  const error = ref<string | null>(null)
  const promptsByBridge = ref<Record<McpBridge, McpPrompt[]>>({ git: [], knowledge: [], filesystem: [] })
  const selectedPrompt = ref<McpPrompt | null>(null)
  const formValues = ref<Record<string, string>>({})
  const formError = ref<FormError | null>(null)
  const insertLoading = ref(false)
  /** Bridges whose last request failed: kept apart from a bridge that answered with no prompts. */
  const failedBridges = ref<McpBridge[]>([])
  const currentPrompts = computed(() => promptsByBridge.value[activeBridge.value])

  async function loadBridge(bridge: McpBridge): Promise<void> {
    try {
      const response = await api.get<{ prompts: McpPrompt[] }>(`/api/${bridge}/mcp/prompts`)
      promptsByBridge.value[bridge] = response.prompts || []
    } catch (err) {
      logger.error(`Failed to load ${bridge} prompts:`, err)
      promptsByBridge.value[bridge] = []
      failedBridges.value.push(bridge)
    }
  }

  async function loadPrompts(): Promise<void> {
    loading.value = true
    error.value = null
    failedBridges.value = []
    try {
      await Promise.all(MCP_BRIDGES.map(loadBridge))
    } catch (err) {
      logger.error('Failed to load prompts:', err)
      error.value = 'chat.mcpPrompts.loadFailed'
    } finally {
      loading.value = false
    }
  }

  function selectPrompt(prompt: McpPrompt): void {
    selectedPrompt.value = prompt
    formValues.value = Object.fromEntries((prompt.arguments ?? []).map((arg) => [arg.name, '']))
    formError.value = null
  }

  function reset(): void {
    selectedPrompt.value = null
    formValues.value = {}
    formError.value = null
  }

  /** The first required parameter left empty, if any. */
  function missingRequired(prompt: McpPrompt): string | undefined {
    return (prompt.arguments ?? []).find((a) => a.required && !formValues.value[a.name]?.trim())?.name
  }

  /** Render the selected prompt; resolves with its draft text, or null when the form or the request failed. */
  async function renderSelected(): Promise<string | null> {
    const prompt = selectedPrompt.value
    if (!prompt) return null
    formError.value = null
    const missing = missingRequired(prompt)
    if (missing) {
      formError.value = { key: 'chat.mcpPrompts.requiredParam', params: { name: missing } }
      return null
    }
    insertLoading.value = true
    try {
      const response = await api.post<RenderedPrompt>(`/api/${activeBridge.value}/mcp/prompts/get`, {
        name: prompt.name,
        arguments: formValues.value,
      })
      return promptDraftText(response)
    } catch (err) {
      logger.error('Failed to get prompt:', err)
      formError.value = { key: 'chat.mcpPrompts.insertFailed' }
      return null
    } finally {
      insertLoading.value = false
    }
  }

  return {
    activeBridge, loading, error, selectedPrompt, formValues, formError, insertLoading, currentPrompts,
    promptsByBridge, failedBridges, loadPrompts, selectPrompt, renderSelected, reset,
  }
}
