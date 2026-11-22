<template>
  <div class="p-8 text-autobot-text-secondary" role="status" aria-live="polite">
    <p>{{ t('settings.providerAuth.callback.finishing') }}</p>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import ApiClient from '@/utils/ApiClient'
import type { components } from '@/types/generated/api'
import { createLogger } from '@/utils/debugUtils'
import { useNotificationBus } from '@/composables/useNotificationBus'
import { buildProviderRedirectUri, PROVIDER_OAUTH_SETTINGS_PATH } from '@/utils/providerOAuth'

const logger = createLogger('ProviderOAuthCallbackView')
const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const { showToast } = useNotificationBus()

function first(v: unknown): string {
  const x = Array.isArray(v) ? v[0] : v
  return typeof x === 'string' ? x : ''
}

async function finish(): Promise<void> {
  const providerError = first(route.query.error)
  const code = first(route.query.code)
  const state = first(route.query.state)
  let failure = ''
  if (providerError) {
    failure = first(route.query.error_description) || providerError
  } else if (!code || !state) {
    failure = t('settings.providerAuth.callback.missingParams')
  } else {
    try {
      const resp: components['schemas']['OAuthInitiateResponse'] = await ApiClient.post(
        '/api/llm-auth/oauth/callback',
        { state, code, redirect_uri: buildProviderRedirectUri() },
      )
      if (!resp.stored) failure = t('settings.providerAuth.callback.notStored')
    } catch (err: unknown) {
      failure = (err as Error).message || t('settings.providerAuth.callback.failed')
      logger.error('Provider OAuth callback failed', err)
    }
  }
  if (failure) {
    showToast(t('settings.providerAuth.callback.failedWith', { reason: failure }), 'error')
  } else {
    showToast(t('settings.providerAuth.callback.success'), 'success')
  }
  await router.replace({
    path: PROVIDER_OAUTH_SETTINGS_PATH,
    query: { tab: 'apikeys', oauth: failure ? 'error' : 'connected' },
  })
}

onMounted(finish)
</script>
