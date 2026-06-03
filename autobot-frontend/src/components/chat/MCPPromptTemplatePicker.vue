<template>
  <div class="mcp-prompt-picker">
    <!-- Trigger Button -->
    <button
      class="picker-trigger"
      :class="{ active: showPicker }"
      :title="'Insert prompt template'"
      @click="togglePicker"
    >
      <Icon name="lightbulb" />
      <span class="trigger-label">Templates</span>
    </button>

    <!-- Picker Dropdown -->
    <Teleport to="body">
      <div
        v-if="showPicker"
        class="picker-overlay"
        @click="closePicker"
      >
        <div
          class="picker-dropdown"
          :style="dropdownStyle"
          @click.stop
        >
          <div class="picker-header">
            <h3>Prompt Templates</h3>
            <button class="close-btn" @click="closePicker">
              <Icon name="times" />
            </button>
          </div>

          <!-- Loading State -->
          <div v-if="loading" class="picker-loading">
            <Icon name="spinner" class="animate-spin" />
            <p>Loading templates...</p>
          </div>

          <!-- Error State -->
          <div v-else-if="error" class="picker-error">
            <Icon name="exclamation-triangle" />
            <p>{{ error }}</p>
          </div>

          <!-- Template Selection -->
          <div v-else-if="!selectedTemplate" class="template-list">
            <div
              v-for="template in templates"
              :key="template.name"
              class="template-item"
              @click="selectTemplate(template)"
            >
              <div class="template-icon">
                <Icon name="file-alt" />
              </div>
              <div class="template-info">
                <div class="template-name">{{ template.name }}</div>
                <div v-if="template.description" class="template-description">
                  {{ template.description }}
                </div>
                <div v-if="template.arguments.length" class="template-args-count">
                  {{ template.arguments.length }} {{ template.arguments.length === 1 ? 'parameter' : 'parameters' }}
                </div>
              </div>
              <Icon name="chevron-right" class="template-arrow" />
            </div>
          </div>

          <!-- Parameter Form -->
          <div v-else class="parameter-form">
            <button class="back-btn" @click="backToList">
              <Icon name="arrow-left" />
              Back to templates
            </button>

            <div class="form-header">
              <h4>{{ selectedTemplate.name }}</h4>
              <p v-if="selectedTemplate.description">{{ selectedTemplate.description }}</p>
            </div>

            <form @submit.prevent="applyTemplate">
              <div
                v-for="arg in selectedTemplate.arguments"
                :key="arg.name"
                class="form-group"
              >
                <label :for="`arg-${arg.name}`" class="form-label">
                  {{ arg.name }}
                  <span v-if="arg.required" class="required-indicator">*</span>
                </label>
                <input
                  :id="`arg-${arg.name}`"
                  v-model="templateArgs[arg.name as string]"
                  type="text"
                  class="form-input"
                  :placeholder="arg.description as string || `Enter ${arg.name}`"
                  :required="arg.required as boolean"
                />
                <p v-if="arg.description" class="form-help">
                  {{ arg.description }}
                </p>
              </div>

              <div class="form-actions">
                <button
                  type="button"
                  class="btn-cancel"
                  @click="backToList"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  class="btn-apply"
                  :disabled="submitting"
                >
                  <Icon v-if="submitting" name="spinner" class="animate-spin" />
                  {{ submitting ? 'Applying...' : 'Apply Template' }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, type Ref } from 'vue'
import Icon from '@/components/common/Icon.vue'
import { useMCPResources, type MCPPromptTemplate } from '@/composables/useMCPResources'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('MCPPromptTemplatePicker')

interface Props {
  triggerRef?: HTMLElement | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'prompt-selected': [prompt: string]
}>()

const {
  loading,
  error,
  listPromptTemplates,
  getPromptTemplate
} = useMCPResources()

const showPicker = ref(false)
const templates: Ref<MCPPromptTemplate[]> = ref([])
const selectedTemplate: Ref<MCPPromptTemplate | null> = ref(null)
const templateArgs: Ref<Record<string, string>> = ref({})
const submitting = ref(false)
const pickerPosition = ref({ top: 0, left: 0 })

const dropdownStyle = computed(() => ({
  top: `${pickerPosition.value.top}px`,
  left: `${pickerPosition.value.left}px`
}))

onMounted(async () => {
  await loadTemplates()
})

async function loadTemplates() {
  try {
    const result = await listPromptTemplates()
    templates.value = result
  } catch (err) {
    logger.error('Failed to load prompt templates:', err)
  }
}

function togglePicker() {
  if (showPicker.value) {
    closePicker()
  } else {
    openPicker()
  }
}

function openPicker() {
  // Calculate position relative to trigger button
  if (props.triggerRef) {
    const rect = props.triggerRef.getBoundingClientRect()
    pickerPosition.value = {
      top: rect.bottom + 8,
      left: rect.left
    }
  }

  showPicker.value = true
  loadTemplates() // Refresh templates when opening
}

function closePicker() {
  showPicker.value = false
  selectedTemplate.value = null
  templateArgs.value = {}
}

function selectTemplate(template: MCPPromptTemplate) {
  selectedTemplate.value = template
  templateArgs.value = {}

  // Initialize args object
  template.arguments.forEach((arg) => {
    if (arg.name) {
      templateArgs.value[arg.name as string] = ''
    }
  })
}

function backToList() {
  selectedTemplate.value = null
  templateArgs.value = {}
}

async function applyTemplate() {
  if (!selectedTemplate.value) return

  submitting.value = true

  try {
    const result = await getPromptTemplate(
      selectedTemplate.value.name,
      templateArgs.value
    )

    if (result) {
      // Extract the prompt content from the messages
      const promptContent = result.messages
        .map(msg => msg.content)
        .join('\n\n')

      emit('prompt-selected', promptContent)
      closePicker()
    }
  } catch (err) {
    logger.error('Failed to apply template:', err)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.mcp-prompt-picker {
  position: relative;
}

.picker-trigger {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--text-sm);
  transition: all var(--duration-150) var(--ease-in-out);
}

.picker-trigger:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border-color: var(--color-primary);
}

.picker-trigger.active {
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-color: var(--color-primary);
}

.trigger-label {
  font-weight: 500;
}

.picker-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
}

.picker-dropdown {
  position: fixed;
  width: 400px;
  max-height: 600px;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.picker-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
}

.picker-header h3 {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: var(--spacing-1);
  border-radius: var(--radius-sm);
  transition: all var(--duration-150) var(--ease-in-out);
}

.close-btn:hover {
  color: var(--text-primary);
  background: var(--bg-tertiary);
}

.picker-loading,
.picker-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-3);
  padding: var(--spacing-8);
  color: var(--text-secondary);
}

.picker-error {
  color: var(--color-error);
}

.template-list {
  overflow-y: auto;
  max-height: 500px;
}

.template-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
  cursor: pointer;
  transition: background var(--duration-150) var(--ease-in-out);
}

.template-item:hover {
  background: var(--bg-secondary);
}

.template-item:last-child {
  border-bottom: none;
}

.template-icon {
  font-size: var(--text-xl);
  color: var(--color-info);
  flex-shrink: 0;
}

.template-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.template-name {
  font-weight: 600;
  color: var(--text-primary);
}

.template-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.template-args-count {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.template-arrow {
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.parameter-form {
  display: flex;
  flex-direction: column;
  max-height: 500px;
  overflow-y: auto;
  padding: var(--spacing-4);
}

.back-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2);
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: var(--text-sm);
  margin-bottom: var(--spacing-4);
  align-self: flex-start;
  border-radius: var(--radius-sm);
  transition: all var(--duration-150) var(--ease-in-out);
}

.back-btn:hover {
  color: var(--text-primary);
  background: var(--bg-tertiary);
}

.form-header {
  margin-bottom: var(--spacing-4);
}

.form-header h4 {
  margin: 0 0 var(--spacing-2) 0;
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.form-header p {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.form-group {
  margin-bottom: var(--spacing-4);
}

.form-label {
  display: block;
  margin-bottom: var(--spacing-2);
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
}

.required-indicator {
  color: var(--color-error);
}

.form-input {
  width: 100%;
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
  transition: all var(--duration-150) var(--ease-in-out);
}

.form-input:focus {
  outline: none;
  border-color: var(--color-primary);
  background: var(--bg-primary);
}

.form-help {
  margin: var(--spacing-1) 0 0 0;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-3);
  margin-top: var(--spacing-4);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-default);
}

.btn-cancel,
.btn-apply {
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-md);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-150) var(--ease-in-out);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.btn-cancel {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.btn-cancel:hover {
  background: var(--bg-tertiary);
  border-color: var(--color-primary);
}

.btn-apply {
  background: var(--color-primary);
  color: white;
  border: none;
}

.btn-apply:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn-apply:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
