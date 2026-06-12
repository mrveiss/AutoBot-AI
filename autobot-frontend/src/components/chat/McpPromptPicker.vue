<template>
  <div class="mcp-prompt-picker">
    <BaseButton
      variant="ghost"
      size="xs"
      @click="showModal = true"
      class="action-btn"
      :disabled="disabled"
      :aria-label="$t('chat.input.selectPromptTemplate', 'Select prompt template')"
    >
      <Icon name="list-alt" />
    </BaseButton>

    <BaseModal
      v-if="showModal"
      :model-value="showModal"
      title="Prompt Templates"
      @update:model-value="showModal = $event"
      @close="showModal = false"
      size="lg"
    >
      <template #header>
        <h3>Prompt Templates</h3>
      </template>

      <div v-if="loading" class="loading-state">
        <Icon name="spinner" spin />
        <span>Loading templates...</span>
      </div>

      <div v-else-if="error" class="error-state">
        <Icon name="exclamation-triangle" />
        <p>{{ error }}</p>
        <BaseButton @click="loadPrompts" variant="primary" size="sm">
          Retry
        </BaseButton>
      </div>

      <div v-else-if="!selectedPrompt" class="prompts-container">
        <!-- Bridge Selector -->
        <div class="bridge-selector">
          <label>Source:</label>
          <select v-model="activeBridge" class="bridge-select">
            <option value="git">Git</option>
            <option value="knowledge">Knowledge</option>
            <option value="filesystem">Filesystem</option>
          </select>
        </div>

        <!-- Prompts List -->
        <div v-if="currentPrompts.length === 0" class="empty-state">
          <Icon name="file-alt" />
          <p>No templates available from {{ activeBridge }} bridge</p>
        </div>

        <div v-else class="prompts-list">
          <div
            v-for="prompt in currentPrompts"
            :key="prompt.name"
            class="prompt-item"
            @click="selectPrompt(prompt)"
          >
            <div class="prompt-header">
              <div class="prompt-name">{{ prompt.name }}</div>
              <Icon name="chevron-right" />
            </div>
            <div v-if="prompt.description" class="prompt-description">
              {{ prompt.description }}
            </div>
            <div v-if="prompt.arguments && prompt.arguments.length > 0" class="prompt-args">
              <span class="args-label">Parameters:</span>
              <span
                v-for="arg in prompt.arguments"
                :key="arg.name"
                class="arg-badge"
              >
                {{ arg.name }}{{ arg.required ? '*' : '' }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Prompt Parameters Form -->
      <div v-else class="prompt-form">
        <div class="form-header">
          <BaseButton @click="selectedPrompt = null" variant="ghost" size="sm">
            <Icon name="arrow-left" /> Back
          </BaseButton>
          <h4>{{ selectedPrompt.name }}</h4>
        </div>

        <p v-if="selectedPrompt.description" class="form-description">
          {{ selectedPrompt.description }}
        </p>

        <div class="form-fields">
          <div
            v-for="arg in selectedPrompt.arguments"
            :key="arg.name"
            class="form-field"
          >
            <label :for="`arg-${arg.name}`" class="field-label">
              {{ arg.name }}
              <span v-if="arg.required" class="required">*</span>
            </label>
            <p v-if="arg.description" class="field-description">
              {{ arg.description }}
            </p>
            <input
              :id="`arg-${arg.name}`"
              v-model="formValues[arg.name]"
              type="text"
              class="field-input"
              :required="arg.required"
              :placeholder="arg.description || arg.name"
            />
          </div>
        </div>

        <div v-if="formError" class="form-error">
          <Icon name="exclamation-triangle" />
          <span>{{ formError }}</span>
        </div>
      </div>

      <template #footer>
        <div class="modal-footer">
          <BaseButton @click="closeModal" variant="ghost">
            Cancel
          </BaseButton>
          <BaseButton
            v-if="selectedPrompt"
            @click="insertPrompt"
            variant="primary"
            :disabled="insertLoading"
          >
            <Icon v-if="insertLoading" name="spinner" spin />
            Insert Template
          </BaseButton>
        </div>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useApiClient } from '@/plugins/api'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import Icon from '@/components/ui/Icon.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('McpPromptPicker')
const api = useApiClient()

interface Props {
  disabled?: boolean
}

defineProps<Props>()

interface PromptArgument {
  name: string
  description?: string
  required?: boolean
}

interface McpPrompt {
  name: string
  description?: string
  arguments?: PromptArgument[]
}

interface PromptMessage {
  role: string
  content: {
    type: string
    text?: string
  }
}

const emit = defineEmits<{
  (e: 'insert', text: string): void
}>()

const bridges = ['git', 'knowledge', 'filesystem'] as const
type Bridge = typeof bridges[number]

const showModal = ref(false)
const activeBridge = ref<Bridge>('git')
const loading = ref(false)
const error = ref<string | null>(null)
const promptsByBridge = ref<Record<Bridge, McpPrompt[]>>({
  git: [],
  knowledge: [],
  filesystem: []
})

const selectedPrompt = ref<McpPrompt | null>(null)
const formValues = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
const insertLoading = ref(false)

const currentPrompts = computed(() => promptsByBridge.value[activeBridge.value])

watch(showModal, (show: boolean) => {
  if (show && Object.keys(promptsByBridge.value.git).length === 0) {
    loadPrompts()
  }
})

async function loadPrompts() {
  loading.value = true
  error.value = null

  try {
    await Promise.all(
      bridges.map(async (bridge) => {
        try {
          const response = await api.get<{ prompts: McpPrompt[] }>(
            `/api/${bridge}/mcp/prompts`
          )
          promptsByBridge.value[bridge] = response.prompts || []
        } catch (err) {
          logger.error(`Failed to load ${bridge} prompts:`, err)
          promptsByBridge.value[bridge] = []
        }
      })
    )
  } catch (err) {
    logger.error('Failed to load prompts:', err)
    error.value = 'Failed to load prompt templates. Please try again.'
  } finally {
    loading.value = false
  }
}

function selectPrompt(prompt: McpPrompt) {
  selectedPrompt.value = prompt
  formValues.value = {}
  formError.value = null

  if (prompt.arguments) {
    prompt.arguments.forEach((arg) => {
      formValues.value[arg.name] = ''
    })
  }
}

async function insertPrompt() {
  if (!selectedPrompt.value) return

  formError.value = null

  const requiredArgs = selectedPrompt.value.arguments?.filter((a: PromptArgument) => a.required) || []
  for (const arg of requiredArgs) {
    if (!formValues.value[arg.name]?.trim()) {
      formError.value = `Please fill in required parameter: ${arg.name}`
      return
    }
  }

  insertLoading.value = true

  try {
    const response = await api.post<{
      description?: string
      messages: PromptMessage[]
    }>(
      `/api/${activeBridge.value}/mcp/prompts/get`,
      {
        name: selectedPrompt.value.name,
        arguments: formValues.value
      }
    )

    const promptText = response.messages
      .map((msg) => {
        if (typeof msg.content === 'string') {
          return msg.content
        }
        if (msg.content && typeof msg.content === 'object') {
          if ('text' in msg.content) {
            return msg.content.text
          }
          if (Array.isArray(msg.content)) {
            return msg.content
              .map((c: any) => (typeof c === 'string' ? c : c.text || ''))
              .join('\n')
          }
        }
        return ''
      })
      .filter((text): text is string => typeof text === 'string' && text.trim() !== '')
      .join('\n\n')

    emit('insert', promptText)
    closeModal()
  } catch (err) {
    logger.error('Failed to get prompt:', err)
    formError.value = 'Failed to load prompt template. Please try again.'
  } finally {
    insertLoading.value = false
  }
}

function closeModal() {
  showModal.value = false
  selectedPrompt.value = null
  formValues.value = {}
  formError.value = null
}
</script>

<style scoped>
.loading-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem;
  gap: 1rem;
}

.bridge-selector {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

.bridge-selector label {
  font-weight: 500;
  color: var(--autobot-text-primary);
}

.bridge-select {
  flex: 1;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--autobot-border-color);
  border-radius: 0.375rem;
  background: var(--autobot-bg-primary);
  color: var(--autobot-text-primary);
  font-size: 0.875rem;
}

.prompts-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-height: 60vh;
  overflow-y: auto;
}

.prompt-item {
  padding: 1rem;
  background: var(--autobot-bg-secondary);
  border: 1px solid var(--autobot-border-color);
  border-radius: 0.5rem;
  cursor: pointer;
  transition: all 0.2s;
}

.prompt-item:hover {
  border-color: var(--autobot-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.prompt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.prompt-name {
  font-weight: 600;
  color: var(--autobot-text-primary);
}

.prompt-description {
  color: var(--autobot-text-secondary);
  font-size: 0.875rem;
  margin-bottom: 0.75rem;
}

.prompt-args {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.args-label {
  font-size: 0.75rem;
  color: var(--autobot-text-secondary);
  font-weight: 500;
}

.arg-badge {
  display: inline-block;
  padding: 0.125rem 0.5rem;
  background: var(--autobot-bg-tertiary);
  border-radius: 0.25rem;
  font-size: 0.75rem;
  color: var(--autobot-text-primary);
  font-family: 'Monaco', 'Courier New', monospace;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem;
  gap: 1rem;
  color: var(--autobot-text-secondary);
}

.prompt-form {
  max-height: 60vh;
  overflow-y: auto;
}

.form-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}

.form-header h4 {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--autobot-text-primary);
}

.form-description {
  padding: 0.75rem;
  background: var(--autobot-bg-secondary);
  border-radius: 0.375rem;
  color: var(--autobot-text-secondary);
  font-size: 0.875rem;
  margin-bottom: 1.5rem;
}

.form-fields {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.field-label {
  font-weight: 500;
  color: var(--autobot-text-primary);
  font-size: 0.875rem;
}

.required {
  color: var(--autobot-error);
}

.field-description {
  font-size: 0.75rem;
  color: var(--autobot-text-secondary);
  margin-top: -0.25rem;
}

.field-input {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--autobot-border-color);
  border-radius: 0.375rem;
  background: var(--autobot-bg-primary);
  color: var(--autobot-text-primary);
  font-size: 0.875rem;
}

.field-input:focus {
  outline: none;
  border-color: var(--autobot-primary);
}

.form-error {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  background: var(--autobot-error-bg, #fee);
  border: 1px solid var(--autobot-error, #f44);
  border-radius: 0.375rem;
  color: var(--autobot-error);
  font-size: 0.875rem;
  margin-top: 1rem;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}
</style>
