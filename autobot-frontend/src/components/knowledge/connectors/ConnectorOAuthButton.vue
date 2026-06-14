<script setup lang="ts">
/**
 * ConnectorOAuthButton — "Connect <provider>" OAuth launcher (ADR-007 / #9019).
 *
 * Starts a backend OAuth flow, opens the provider authorization URL in a popup,
 * and listens for the backend callback's postMessage to receive the stored
 * `secret_id`. Emits `connected` with that reference so the parent connector
 * form can attach it — credentials never touch the frontend.
 */

import { ref, onBeforeUnmount } from 'vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { knowledgeRepository } from '@/models/repositories/KnowledgeRepository'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ConnectorOAuthButton')

const props = defineProps<{
  provider: string
  label: string
  scopes?: string[]
  disabled?: boolean
}>()

const emit = defineEmits<{
  connected: [payload: { secretId: string; connectorId: string; provider: string }]
  error: [message: string]
}>()

const connecting = ref(false)
let popup: Window | null = null
let messageHandler: ((e: MessageEvent) => void) | null = null

function callbackUrl(): string {
  // Absolute URL to the backend OAuth callback; host must be allow-listed
  // server-side (AUTOBOT_SSO_CALLBACK_HOSTS).
  return new URL(
    `${getApiBase()}/knowledge_base/connectors/oauth/callback`,
    window.location.origin
  ).href
}

function cleanup(): void {
  if (messageHandler) {
    window.removeEventListener('message', messageHandler)
    messageHandler = null
  }
  connecting.value = false
  popup = null
}

function onMessage(event: MessageEvent): void {
  // Only trust messages from our own origin (the backend callback page).
  if (event.origin !== window.location.origin) return
  const data = event.data
  if (!data || data.type !== 'connector-oauth') return

  if (data.ok && data.secret_id) {
    emit('connected', {
      secretId: data.secret_id,
      connectorId: data.connector_id ?? '',
      provider: data.provider ?? props.provider
    })
  } else {
    const message = data.error || 'oauth_failed'
    logger.warn('OAuth flow failed', message)
    emit('error', message)
  }
  try {
    popup?.close()
  } catch {
    /* popup may already be closed */
  }
  cleanup()
}

async function connect(): Promise<void> {
  if (connecting.value || props.disabled) return
  connecting.value = true
  try {
    const { authorize_url } = await knowledgeRepository.startConnectorOAuth(
      props.provider,
      callbackUrl(),
      props.scopes
    )
    messageHandler = onMessage
    window.addEventListener('message', messageHandler)
    popup = window.open(authorize_url, 'connector-oauth', 'width=600,height=720')
    if (!popup) {
      // Popup blocked — fall back to a full-page redirect.
      window.location.href = authorize_url
    }
  } catch (err) {
    logger.error('Failed to start OAuth flow', err)
    emit('error', err instanceof Error ? err.message : 'oauth_start_failed')
    cleanup()
  }
}

onBeforeUnmount(cleanup)
</script>

<template>
  <BaseButton
    variant="secondary"
    :disabled="disabled || connecting"
    :loading="connecting"
    @click="connect"
  >
    {{ connecting ? `Connecting to ${label}…` : `Connect ${label}` }}
  </BaseButton>
</template>
