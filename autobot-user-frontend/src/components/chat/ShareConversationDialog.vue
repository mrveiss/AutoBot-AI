<template>
  <BaseModal
    :model-value="visible"
    title="Share Conversation"
    size="medium"
    @update:model-value="$emit('update:visible', $event)"
    @close="handleCancel"
  >
    <template #default>
      <div class="p-4 space-y-4 max-h-[70vh] overflow-y-auto">
        <!-- Recipients Input -->
        <div>
          <label class="block text-sm font-medium text-blueGray-700 mb-1">
            Share with (user IDs)
          </label>
          <input
            v-model="recipientInput"
            type="text"
            class="w-full px-3 py-2 border border-autobot-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-electric-500"
            placeholder="Enter user ID and press Enter"
            @keyup.enter="addRecipient"
          />
          <div v-if="recipients.length > 0" class="flex flex-wrap gap-1.5 mt-2">
            <span
              v-for="r in recipients"
              :key="r"
              class="inline-flex items-center gap-1 px-2 py-0.5 bg-autobot-bg-tertiary text-autobot-text-secondary text-xs rounded-full"
            >
              {{ r }}
              <button
                class="hover:text-red-600"
                @click="removeRecipient(r)"
              >
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
          <span class="text-sm text-blueGray-700">Include knowledge created in this conversation</span>
        </label>

        <!-- KB Facts Preview -->
        <div v-if="includeKnowledge" class="space-y-2">
          <div v-if="factsLoading" class="flex items-center gap-2 text-sm text-blueGray-500 p-3">
            <i class="fas fa-spinner fa-spin"></i>
            Loading knowledge facts...
          </div>

          <div v-else-if="facts.length === 0" class="text-sm text-blueGray-500 p-3 bg-autobot-bg-secondary rounded-lg">
            No knowledge facts found in this conversation.
          </div>

          <template v-else>
            <div class="flex items-center justify-between">
              <p class="text-sm font-medium text-blueGray-700">
                {{ selectedFactIds.size }} of {{ facts.length }} facts selected
              </p>
              <button
                class="text-xs text-autobot-primary hover:text-autobot-text-secondary"
                @click="toggleAllFacts"
              >
                {{ selectedFactIds.size === facts.length ? 'Deselect All' : 'Select All' }}
              </button>
            </div>

            <div class="space-y-1.5 max-h-48 overflow-y-auto border border-autobot-border rounded-lg p-2 bg-autobot-bg-card">
              <div
                v-for="fact in facts"
                :key="fact.id"
                class="flex items-start gap-2 p-2 rounded hover:bg-autobot-bg-tertiary transition-colors cursor-pointer"
                @click="toggleFact(fact.id)"
              >
                <input
                  type="checkbox"
                  :checked="selectedFactIds.has(fact.id)"
                  class="mt-1 rounded border-autobot-border text-autobot-primary focus:ring-autobot-primary"
                  @click.stop="toggleFact(fact.id)"
                />
                <div class="flex-1 min-w-0">
                  <p class="text-sm text-autobot-text-primary line-clamp-2">{{ fact.content }}</p>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </template>

    <template #actions>
      <BaseButton variant="secondary" @click="handleCancel">
        Cancel
      </BaseButton>
      <BaseButton
        variant="primary"
        :disabled="recipients.length === 0 || sharing"
        :loading="sharing"
        @click="handleShare"
      >
        {{ sharing ? 'Sharing...' : 'Share' }}
      </BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ShareConversationDialog')

interface ShareFact {
  id: string
  content: string
  full_content: string
  metadata: Record<string, unknown>
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

const recipientInput = ref('')
const recipients = ref<string[]>([])
const includeKnowledge = ref(false)
const facts = ref<ShareFact[]>([])
const factsLoading = ref(false)
const selectedFactIds = ref(new Set<string>())
const sharing = ref(false)

const addRecipient = () => {
  const val = recipientInput.value.trim()
  if (val && !recipients.value.includes(val)) {
    recipients.value.push(val)
  }
  recipientInput.value = ''
}

const removeRecipient = (r: string) => {
  recipients.value = recipients.value.filter(x => x !== r)
}

const toggleFact = (id: string) => {
  if (selectedFactIds.value.has(id)) {
    selectedFactIds.value.delete(id)
  } else {
    selectedFactIds.value.add(id)
  }
  selectedFactIds.value = new Set(selectedFactIds.value)
}

const toggleAllFacts = () => {
  if (selectedFactIds.value.size === facts.value.length) {
    selectedFactIds.value = new Set()
  } else {
    selectedFactIds.value = new Set(facts.value.map(f => f.id))
  }
}

const loadFacts = async () => {
  if (!props.sessionId) return
  factsLoading.value = true
  try {
    const data = await ApiClient.get(
      `/api/chat/sessions/${props.sessionId}/share/preview`
    )
    facts.value = data?.data?.facts || []
    selectedFactIds.value = new Set(facts.value.map(f => f.id))
  } catch (err) {
    logger.error('Failed to load share preview:', err)
    facts.value = []
  } finally {
    factsLoading.value = false
  }
}

watch(() => props.includeKnowledge, (val) => {
  if (val && facts.value.length === 0) {
    loadFacts()
  }
})

watch(() => props.visible, (val) => {
  if (val) {
    recipients.value = []
    recipientInput.value = ''
    includeKnowledge.value = false
    facts.value = []
    selectedFactIds.value = new Set()
  }
})

// Also reload facts when includeKnowledge toggled on
watch(includeKnowledge, (val) => {
  if (val && facts.value.length === 0) {
    loadFacts()
  }
})

const handleShare = async () => {
  if (recipients.value.length === 0) return
  sharing.value = true
  try {
    const body: Record<string, unknown> = {
      share_with: recipients.value,
      include_knowledge: includeKnowledge.value,
    }
    if (includeKnowledge.value && selectedFactIds.value.size > 0) {
      body.knowledge_facts = Array.from(selectedFactIds.value)
    }
    const result = await ApiClient.post(
      `/api/chat/sessions/${props.sessionId}/share`,
      body
    )
    emit('shared', result?.data || {})
    emit('update:visible', false)
  } catch (err) {
    logger.error('Failed to share session:', err)
  } finally {
    sharing.value = false
  }
}

const handleCancel = () => {
  emit('cancel')
  emit('update:visible', false)
}
</script>
