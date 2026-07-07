<template>
  <BaseModal
    :model-value="visible"
    :title="$t('chat.share.title')"
    size="md"
    @update:model-value="$emit('update:visible', $event)"
    @close="handleCancel"
  >
    <template #default>
      <div class="p-4 space-y-4 max-h-[70vh] overflow-y-auto">
        <!-- Mode tabs -->
        <div class="flex border border-autobot-border rounded-lg overflow-hidden">
          <button
            class="flex-1 py-2 text-sm font-medium transition-colors"
            :class="mode === 'users' ? 'bg-autobot-primary text-white' : 'bg-autobot-bg-secondary text-autobot-text-secondary hover:bg-autobot-bg-tertiary'"
            @click="mode = 'users'"
          >
            {{ $t('chat.share.shareWithUsers') }}
          </button>
          <button
            class="flex-1 py-2 text-sm font-medium transition-colors"
            :class="mode === 'link' ? 'bg-autobot-primary text-white' : 'bg-autobot-bg-secondary text-autobot-text-secondary hover:bg-autobot-bg-tertiary'"
            @click="mode = 'link'"
          >
            {{ $t('chat.share.publicLink') }}
          </button>
        </div>

        <!-- ===== User-share mode ===== -->
        <template v-if="mode === 'users'">
          <div>
            <label class="block text-sm font-medium text-autobot-text-primary mb-1">
              {{ $t('chat.share.shareWith') }}
            </label>
            <input
              v-model="recipientInput"
              type="text"
              class="w-full px-3 py-2 border border-autobot-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-electric-500"
              :placeholder="$t('chat.share.recipientPlaceholder')"
              @keyup.enter="addRecipient"
            />
            <div v-if="recipients.length > 0" class="flex flex-wrap gap-1.5 mt-2">
              <span
                v-for="r in recipients"
                :key="r"
                class="inline-flex items-center gap-1 px-2 py-0.5 bg-autobot-bg-tertiary text-autobot-text-secondary text-xs rounded-full"
              >
                {{ r }}
                <button class="hover:text-red-600" @click="removeRecipient(r)">
                  <i class="fas fa-times text-xs"></i>
                </button>
              </span>
            </div>
          </div>

          <!-- Include Knowledge Toggle -->
          <label class="flex items-center gap-2 cursor-pointer">
            <input
              v-model="includeKnowledge"
              type="checkbox"
              class="rounded border-autobot-border text-autobot-primary focus:ring-autobot-primary"
            />
            <span class="text-sm text-autobot-text-primary">{{ $t('chat.share.includeKnowledge') }}</span>
          </label>

          <!-- KB Facts Preview -->
          <div v-if="includeKnowledge" class="space-y-2">
            <div v-if="factsLoading" class="flex items-center gap-2 text-sm text-autobot-text-secondary p-3">
              <Icon name="spinner" :spin="true" />
              {{ $t('chat.share.loadingFacts') }}
            </div>

            <div v-else-if="facts.length === 0" class="text-sm text-autobot-text-secondary p-3 bg-autobot-bg-secondary rounded-lg">
              {{ $t('chat.share.noFactsFound') }}
            </div>

            <template v-else>
              <div class="flex items-center justify-between">
                <p class="text-sm font-medium text-autobot-text-primary">
                  {{ $t('chat.share.factsSelected', { selected: factSelection.selectedCount.value, total: facts.length }) }}
                </p>
                <button
                  class="text-xs text-autobot-primary hover:text-autobot-text-secondary"
                  @click="toggleAllFacts"
                >
                  {{ factSelection.allSelected.value ? $t('chat.share.deselectAll') : $t('chat.share.selectAll') }}
                </button>
              </div>

              <div class="space-y-1.5 max-h-48 overflow-y-auto border border-autobot-border rounded-lg p-2 bg-autobot-bg-card">
                <div
                  v-for="fact in facts"
                  :key="fact.id"
                  class="flex items-start gap-2 p-2 rounded hover:bg-autobot-bg-tertiary transition-colors cursor-pointer"
                  @click="factSelection.toggle(fact)"
                >
                  <input
                    type="checkbox"
                    :checked="factSelection.isSelected(fact)"
                    class="mt-1 rounded border-autobot-border text-autobot-primary focus:ring-autobot-primary"
                    @click.stop="factSelection.toggle(fact)"
                  />
                  <div class="flex-1 min-w-0">
                    <p class="text-sm text-autobot-text-primary line-clamp-2">{{ fact.content }}</p>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </template>

        <!-- ===== Public link mode ===== -->
        <template v-else>
          <!-- Existing link display -->
          <div v-if="createdLink" class="space-y-3">
            <div class="p-3 bg-autobot-bg-secondary rounded-lg border border-autobot-border">
              <p class="text-xs text-autobot-text-secondary mb-1">{{ $t('chat.share.linkReady') }}</p>
              <div class="flex items-center gap-2">
                <input
                  :value="shareLinkUrl"
                  readonly
                  class="flex-1 text-sm bg-transparent border-none outline-none text-autobot-text-primary font-mono truncate"
                />
                <button
                  class="shrink-0 text-xs px-2 py-1 rounded bg-autobot-primary text-white hover:opacity-90 transition-opacity"
                  @click="copyLink"
                >
                  {{ copied ? $t('common.copied') : $t('common.copy') }}
                </button>
              </div>
            </div>
            <div v-if="createdLink.has_password" class="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400">
              <i class="fas fa-lock"></i>
              {{ $t('chat.share.linkPasswordProtected') }}
            </div>
            <div v-if="createdLink.expires_at" class="flex items-center gap-1.5 text-xs text-autobot-text-secondary">
              <i class="fas fa-clock"></i>
              {{ $t('chat.share.linkExpires', { date: formatExpiry(createdLink.expires_at) }) }}
            </div>
            <button
              class="text-xs text-red-600 hover:text-red-700 flex items-center gap-1"
              :disabled="revoking"
              @click="revokeLink"
            >
              <i class="fas fa-trash-alt"></i>
              {{ revoking ? $t('chat.share.revoking') : $t('chat.share.revokeLink') }}
            </button>
          </div>

          <!-- Link creation form -->
          <div v-else class="space-y-3">
            <div>
              <label class="block text-sm font-medium text-autobot-text-primary mb-1">
                {{ $t('chat.share.optionalPassword') }}
              </label>
              <input
                v-model="linkPassword"
                type="password"
                class="w-full px-3 py-2 border border-autobot-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-electric-500"
                :placeholder="$t('chat.share.passwordPlaceholder')"
                autocomplete="new-password"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-autobot-text-primary mb-1">
                {{ $t('chat.share.expiry') }}
              </label>
              <select
                v-model="expirySeconds"
                class="w-full px-3 py-2 border border-autobot-border rounded-md text-sm bg-autobot-bg-card text-autobot-text-primary focus:outline-none focus:ring-2 focus:ring-electric-500"
              >
                <option :value="null">{{ $t('chat.share.expiryNever') }}</option>
                <option :value="3600">{{ $t('chat.share.expiry1h') }}</option>
                <option :value="86400">{{ $t('chat.share.expiry1d') }}</option>
                <option :value="604800">{{ $t('chat.share.expiry7d') }}</option>
                <option :value="2592000">{{ $t('chat.share.expiry30d') }}</option>
              </select>
            </div>
          </div>
        </template>
      </div>
    </template>

    <template #actions>
      <BaseButton variant="secondary" @click="handleCancel">
        {{ $t('common.cancel') }}
      </BaseButton>

      <!-- User share submit -->
      <BaseButton
        v-if="mode === 'users'"
        variant="primary"
        :disabled="recipients.length === 0 || sharing"
        :loading="sharing"
        @click="handleShare"
      >
        {{ sharing ? $t('chat.share.sharing') : $t('chat.share.share') }}
      </BaseButton>

      <!-- Link create / done -->
      <BaseButton
        v-else-if="!createdLink"
        variant="primary"
        :loading="creatingLink"
        @click="handleCreateLink"
      >
        {{ creatingLink ? $t('chat.share.creating') : $t('chat.share.createLink') }}
      </BaseButton>

      <BaseButton
        v-else
        variant="secondary"
        @click="resetLinkForm"
      >
        {{ $t('chat.share.createAnother') }}
      </BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { BaseModal } from '@autobot/ui'
import BaseButton from '@/components/base/BaseButton.vue'
import ApiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import { useBatchSelection } from '@/composables/useBatchSelection'
import Icon from '@/components/ui/Icon.vue'

const logger = createLogger('ShareConversationDialog')

interface ShareFact {
  id: string
  content: string
  full_content: string
  metadata: Record<string, unknown>
}

interface SharedLinkData {
  token: string
  session_id: string
  has_password: boolean
  expires_at: string | null
  created_at: string
}

const props = defineProps<{
  visible: boolean
  sessionId: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'shared', result: Record<string, unknown>): void
  (e: 'cancel'): void
}>()

// ---- shared state ----
const mode = ref<'users' | 'link'>('users')

// ---- user share ----
const recipientInput = ref('')
const recipients = ref<string[]>([])
const includeKnowledge = ref(false)
const facts = ref<ShareFact[]>([])
const factsLoading = ref(false)
const factSelection = useBatchSelection<ShareFact, string>(facts, (f) => f.id)
const sharing = ref(false)

// ---- link share ----
const linkPassword = ref('')
const expirySeconds = ref<number | null>(null)
const createdLink = ref<SharedLinkData | null>(null)
const creatingLink = ref(false)
const revoking = ref(false)
const copied = ref(false)

const shareLinkUrl = computed(() => {
  if (!createdLink.value) return ''
  return `${window.location.origin}/shared/${createdLink.value.token}`
})

// ---- user share methods ----
const addRecipient = () => {
  const val = recipientInput.value.trim()
  if (val && !recipients.value.includes(val)) recipients.value.push(val)
  recipientInput.value = ''
}

const removeRecipient = (r: string) => {
  recipients.value = recipients.value.filter(x => x !== r)
}

const toggleAllFacts = () => {
  if (factSelection.allSelected.value) factSelection.clear()
  else factSelection.selectAll()
}

const loadFacts = async () => {
  if (!props.sessionId) return
  factsLoading.value = true
  try {
    const data = await ApiClient.get<{ data?: { facts?: ShareFact[] } }>(`${getApiBase()}/chat/sessions/${props.sessionId}/share/preview`)
    facts.value = data?.data?.facts || []
    factSelection.selectAll()
  } catch (err) {
    logger.error('Failed to load share preview:', err)
    facts.value = []
  } finally {
    factsLoading.value = false
  }
}

const handleShare = async () => {
  if (recipients.value.length === 0) return
  sharing.value = true
  try {
    const body: Record<string, unknown> = {
      share_with: recipients.value,
      include_knowledge: includeKnowledge.value,
    }
    if (includeKnowledge.value && factSelection.selectedCount.value > 0) {
      body.knowledge_facts = Array.from(factSelection.selected.value)
    }
    const result = await ApiClient.post<{ data?: Record<string, unknown> }>(`${getApiBase()}/chat/sessions/${props.sessionId}/share`, body)
    emit('shared', result?.data || {})
    emit('update:visible', false)
  } catch (err) {
    logger.error('Failed to share session:', err)
  } finally {
    sharing.value = false
  }
}

// ---- link share methods ----
const handleCreateLink = async () => {
  creatingLink.value = true
  try {
    const body: Record<string, unknown> = {}
    if (linkPassword.value.trim()) body.password = linkPassword.value.trim()
    if (expirySeconds.value) body.expires_in_seconds = expirySeconds.value

    const result = await ApiClient.post<SharedLinkData & { data?: SharedLinkData }>(
      `${getApiBase()}/chat/sessions/${props.sessionId}/share-link`,
      body
    )
    createdLink.value = result?.data || result
  } catch (err) {
    logger.error('Failed to create shared link:', err)
  } finally {
    creatingLink.value = false
  }
}

const revokeLink = async () => {
  if (!createdLink.value) return
  revoking.value = true
  try {
    await ApiClient.delete(
      `${getApiBase()}/chat/sessions/${props.sessionId}/share-link/${createdLink.value.token}`
    )
    createdLink.value = null
    linkPassword.value = ''
    expirySeconds.value = null
  } catch (err) {
    logger.error('Failed to revoke shared link:', err)
  } finally {
    revoking.value = false
  }
}

const copyLink = async () => {
  if (!shareLinkUrl.value) return
  try {
    await navigator.clipboard.writeText(shareLinkUrl.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    logger.error('Clipboard write failed')
  }
}

const resetLinkForm = () => {
  createdLink.value = null
  linkPassword.value = ''
  expirySeconds.value = null
}

const formatExpiry = (iso: string) => new Date(iso).toLocaleString()

// ---- lifecycle ----
watch(() => props.visible, (val) => {
  if (!val) return
  recipients.value = []
  recipientInput.value = ''
  includeKnowledge.value = false
  facts.value = []
  factSelection.clear()
  mode.value = 'users'
  createdLink.value = null
  linkPassword.value = ''
  expirySeconds.value = null
  copied.value = false
})

watch(includeKnowledge, (val) => {
  if (val && facts.value.length === 0) loadFacts()
})

const handleCancel = () => {
  emit('cancel')
  emit('update:visible', false)
}
</script>
