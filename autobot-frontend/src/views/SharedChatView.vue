<template>
  <div class="min-h-screen bg-autobot-bg-primary flex flex-col">
    <!-- Header bar -->
    <div class="border-b border-autobot-border bg-autobot-bg-secondary px-4 py-3 flex items-center gap-3">
      <span class="text-lg font-semibold text-autobot-text-primary">AutoBot</span>
      <span class="text-autobot-text-secondary text-sm">— {{ $t('chat.share.publicView') }}</span>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <div class="flex flex-col items-center gap-3 text-autobot-text-secondary">
        <Icon name="spinner" :spin="true" size="lg" />
        <span class="text-sm">{{ $t('common.loading') }}</span>
      </div>
    </div>

    <!-- Error / expired / not found -->
    <div v-else-if="error" class="flex-1 flex items-center justify-center p-6">
      <div class="max-w-sm w-full text-center space-y-3">
        <i class="fas fa-link-slash text-4xl text-autobot-text-secondary"></i>
        <p class="text-autobot-text-primary font-medium">{{ error }}</p>
      </div>
    </div>

    <!-- Password gate -->
    <div v-else-if="needsPassword" class="flex-1 flex items-center justify-center p-6">
      <div class="max-w-sm w-full space-y-4 bg-autobot-bg-card border border-autobot-border rounded-xl p-6">
        <div class="text-center space-y-1">
          <i class="fas fa-lock text-3xl text-autobot-primary"></i>
          <h2 class="text-lg font-semibold text-autobot-text-primary">{{ $t('chat.share.passwordGate') }}</h2>
          <p class="text-sm text-autobot-text-secondary">{{ $t('chat.share.passwordGateHint') }}</p>
        </div>
        <input
          v-model="passwordInput"
          type="password"
          class="w-full px-3 py-2 border border-autobot-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-electric-500 bg-autobot-bg-primary text-autobot-text-primary"
          :placeholder="$t('chat.share.enterPassword')"
          autocomplete="current-password"
          @keyup.enter="submitPassword"
        />
        <p v-if="passwordError" class="text-xs text-red-500">{{ passwordError }}</p>
        <button
          class="w-full py-2 rounded-lg bg-autobot-primary text-white text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
          :disabled="unlocking || !passwordInput.trim()"
          @click="submitPassword"
        >
          {{ unlocking ? $t('common.loading') : $t('chat.share.unlock') }}
        </button>
      </div>
    </div>

    <!-- Conversation -->
    <div v-else class="flex-1 overflow-y-auto">
      <div class="max-w-3xl mx-auto px-4 py-6 space-y-4">
        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          class="flex"
          :class="msg.role === 'user' ? 'justify-end' : 'justify-start'"
        >
          <div
            class="max-w-[85%] px-4 py-3 rounded-2xl text-sm whitespace-pre-wrap"
            :class="msg.role === 'user'
              ? 'bg-autobot-primary text-white rounded-br-sm'
              : 'bg-autobot-bg-card border border-autobot-border text-autobot-text-primary rounded-bl-sm'"
          >
            {{ msg.content }}
          </div>
        </div>

        <div v-if="messages.length === 0" class="text-center py-12 text-autobot-text-secondary text-sm">
          {{ $t('chat.share.emptyConversation') }}
        </div>
      </div>
    </div>

    <!-- Footer note -->
    <div class="border-t border-autobot-border px-4 py-2 text-center text-xs text-autobot-text-secondary">
      {{ $t('chat.share.readOnlyNote') }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import ApiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import Icon from '@/components/ui/Icon.vue'

const { t } = useI18n()
const route = useRoute()
const logger = createLogger('SharedChatView')

interface Message {
  role: string
  content: string
  created_at?: string | null
}

const loading = ref(true)
const error = ref('')
const needsPassword = ref(false)
const passwordInput = ref('')
const passwordError = ref('')
const unlocking = ref(false)
const messages = ref<Message[]>([])

const token = route.params.token as string

const handleResponse = (data: Record<string, unknown>) => {
  const payload = (data as any)?.data ?? data
  if (payload?.has_password && (!payload.messages || payload.messages.length === 0)) {
    needsPassword.value = true
    return
  }
  messages.value = payload?.messages ?? []
  needsPassword.value = false
}

onMounted(async () => {
  try {
    const result = await ApiClient.get<any>(`${getApiBase()}/chat/shared/${token}`)
    handleResponse(result)
  } catch (err: any) {
    const status = err?.response?.status ?? err?.status
    if (status === 404) {
      error.value = t('chat.share.linkNotFound')
    } else if (status === 410) {
      error.value = t('chat.share.linkExpired')
    } else {
      error.value = t('errors.genericError')
      logger.error('Failed to load shared chat:', err)
    }
  } finally {
    loading.value = false
  }
})

const submitPassword = async () => {
  if (!passwordInput.value.trim() || unlocking.value) return
  unlocking.value = true
  passwordError.value = ''
  try {
    const result = await ApiClient.post<any>(`${getApiBase()}/chat/shared/${token}/access`, {
      password: passwordInput.value.trim(),
    })
    handleResponse(result)
  } catch (err: any) {
    const status = err?.response?.status ?? err?.status
    if (status === 401) {
      passwordError.value = t('chat.share.wrongPassword')
    } else {
      passwordError.value = t('errors.genericError')
      logger.error('Failed to unlock shared chat:', err)
    }
  } finally {
    unlocking.value = false
  }
}
</script>
