<template>
  <BaseModal
    :close-label="t('ui.modal.closeDialog')"
    :modelValue="modelValue"
    @update:modelValue="$emit('update:modelValue', $event)"
    :title="t('settings.apiKeys.wizardTitle')"
    size="lg"
  >
    <!-- Step Indicators -->
    <div class="wizard-steps">
      <div
        v-for="step in steps"
        :key="step.number"
        class="step-dot"
        :class="{ active: currentStep === step.number, completed: currentStep > step.number }"
      >
        <span class="step-number">{{ step.number }}</span>
        <span class="step-label">{{ step.label }}</span>
      </div>
    </div>

    <!-- Step 1: Role Selection -->
    <div v-if="currentStep === 1" class="step-content">
      <p class="step-description">{{ t('settings.apiKeys.selectRolesDescription') }}</p>
      <div class="role-list">
        <label
          v-for="role in availableRoles"
          :key="role.id"
          class="role-card"
          :class="{ selected: selectedRoles.includes(role.id) }"
        >
          <input
            type="checkbox"
            :value="role.id"
            v-model="selectedRoles"
            class="role-checkbox"
          />
          <Icon :name="role.icon" />
          <div class="role-info">
            <span class="role-name">{{ role.name }}</span>
            <span class="role-desc">{{ role.description }}</span>
          </div>
        </label>
      </div>
    </div>

    <!-- Step 2: API Key Status & Configuration -->
    <div v-if="currentStep === 2" class="step-content">
      <p class="step-description">{{ t('settings.apiKeys.configureKeysDescription') }}</p>
      <div v-if="requiredKeys.length === 0" class="empty-state">
        <Icon name="check-circle" />
        <p>{{ t('settings.apiKeys.noKeysRequired') }}</p>
      </div>
      <div v-else class="key-list">
        <div
          v-for="key in requiredKeys"
          :key="key.envVar"
          class="key-card"
        >
          <div class="key-header">
            <div class="key-status">
              <Icon :name="key.configured ? 'check-circle' : 'times-circle'" :class="key.configured ? 'status-ok' : 'status-missing'" />
              <span class="key-name">{{ key.envVar }}</span>
              <span class="key-badge" :class="key.required ? 'required' : 'optional'">
                {{ key.required ? t('settings.apiKeys.required') : t('settings.apiKeys.optional') }}
              </span>
            </div>
            <span class="key-role">{{ key.roleName }}</span>
          </div>
          <div class="key-body">
            <p class="key-desc">{{ key.description }}</p>
            <div v-if="key.licenseUrl" class="license-link">
              <Icon name="external-link-alt" />
              <a :href="key.licenseUrl" target="_blank" rel="noopener noreferrer">
                {{ t('settings.apiKeys.acceptLicense') }}
              </a>
            </div>
            <div class="key-input-row">
              <input
                :type="key.visible ? 'text' : 'password'"
                v-model="key.value"
                :placeholder="key.configured ? '••••••••' : t('settings.apiKeys.enterKey')"
                class="key-input"
              />
              <button class="toggle-visibility" @click="key.visible = !key.visible">
                <Icon :name="key.visible ? 'eye-slash' : 'eye'" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Step 3: Summary -->
    <div v-if="currentStep === 3" class="step-content">
      <p class="step-description">{{ t('settings.apiKeys.summaryDescription') }}</p>
      <div class="summary-list">
        <div
          v-for="key in requiredKeys"
          :key="key.envVar"
          class="summary-item"
        >
          <Icon :name="keyStatus(key) === 'ready' ? 'check-circle' : 'exclamation-circle'" :class="keyStatus(key) === 'ready' ? 'status-ok' : 'status-warning'" />
          <span class="summary-name">{{ key.envVar }}</span>
          <span class="summary-status">{{ keyStatusLabel(key) }}</span>
        </div>
      </div>
      <div class="secrets-link">
        <Icon name="cog" />
        <router-link to="/settings/secrets">
          {{ t('settings.apiKeys.manageInSecrets') }}
        </router-link>
      </div>
    </div>

    <!-- Footer Actions -->
    <template #actions>
      <button
        v-if="currentStep > 1"
        class="btn-secondary"
        @click="prevStep"
      >
        <Icon name="arrow-left" /> {{ t('settings.apiKeys.back') }}
      </button>
      <div class="spacer"></div>
      <button
        v-if="currentStep < totalSteps"
        class="btn-primary"
        :disabled="!canProceed"
        @click="nextStep"
      >
        {{ t('settings.apiKeys.next') }} <Icon name="arrow-right" />
      </button>
      <button
        v-if="currentStep === totalSteps"
        class="btn-primary"
        @click="saveAndClose"
        :disabled="isSaving"
      >
        <i :class="isSaving ? 'fas fa-spinner fa-spin' : 'save'"></i>
        {{ t('settings.apiKeys.save') }}
      </button>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'
import { BaseModal } from '@autobot/ui'
import apiClient from '@/utils/ApiClient'

const logger = createLogger('ApiKeySetupWizard')
const { t } = useI18n()

defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: []
}>()

const currentStep = ref(1)
const totalSteps = 3
const isSaving = ref(false)
const selectedRoles = ref<string[]>([])

interface KeyEntry {
  envVar: string
  roleName: string
  roleId: string
  description: string
  licenseUrl: string
  required: boolean
  configured: boolean
  value: string
  visible: boolean
}

const steps = [
  { number: 1, label: t('settings.apiKeys.stepRoles') },
  { number: 2, label: t('settings.apiKeys.stepKeys') },
  { number: 3, label: t('settings.apiKeys.stepSummary') },
]

const availableRoles = [
  { id: 'tts-worker', name: 'TTS Worker', description: 'Text-to-speech with Pocket TTS', icon: 'microphone' as const },
  { id: 'ai-stack', name: 'AI Stack', description: 'Cloud LLM providers (OpenAI, Anthropic)', icon: 'brain' as const },
]

const roleKeyMapping: Record<string, Omit<KeyEntry, 'configured' | 'value' | 'visible'>[]> = {
  'tts-worker': [
    {
      envVar: 'HF_TOKEN',
      roleName: 'TTS Worker',
      roleId: 'tts-worker',
      description: 'HuggingFace token for gated model access',
      licenseUrl: 'https://huggingface.co/kyutai/pocket-tts',
      required: true,
    },
  ],
  'ai-stack': [
    {
      envVar: 'OPENAI_API_KEY',
      roleName: 'AI Stack',
      roleId: 'ai-stack',
      description: 'OpenAI API key for GPT models',
      licenseUrl: 'https://platform.openai.com/api-keys',
      required: false,
    },
    {
      envVar: 'ANTHROPIC_API_KEY',
      roleName: 'AI Stack',
      roleId: 'ai-stack',
      description: 'Anthropic API key for Claude models',
      licenseUrl: 'https://console.anthropic.com/',
      required: false,
    },
  ],
}

const requiredKeys = computed<KeyEntry[]>(() => {
  const keys: KeyEntry[] = []
  const seen = new Set<string>()
  for (const roleId of selectedRoles.value) {
    for (const mapping of roleKeyMapping[roleId] ?? []) {
      if (!seen.has(mapping.envVar)) {
        seen.add(mapping.envVar)
        keys.push({ ...mapping, configured: false, value: '', visible: false })
      }
    }
  }
  return keys
})

const canProceed = computed(() => {
  if (currentStep.value === 1) return selectedRoles.value.length > 0
  if (currentStep.value === 2) return true
  return true
})

function nextStep(): void {
  if (currentStep.value < totalSteps) currentStep.value++
}

function prevStep(): void {
  if (currentStep.value > 1) currentStep.value--
}

function keyStatus(key: KeyEntry): string {
  if (key.value) return 'ready'
  if (key.configured) return 'ready'
  return key.required ? 'missing' : 'skipped'
}

function keyStatusLabel(key: KeyEntry): string {
  const status = keyStatus(key)
  if (status === 'ready') return t('settings.apiKeys.statusReady')
  if (status === 'missing') return t('settings.apiKeys.statusMissing')
  return t('settings.apiKeys.statusSkipped')
}

async function saveAndClose(): Promise<void> {
  isSaving.value = true
  try {
    const keysToSave = requiredKeys.value.filter((k) => k.value)
    if (keysToSave.length > 0) {
      await saveKeys(keysToSave)
    }
    emit('saved')
    emit('update:modelValue', false)
  } catch (err) {
    logger.error('Failed to save API keys:', err)
  } finally {
    isSaving.value = false
  }
}

async function saveKeys(keys: KeyEntry[]): Promise<void> {
  // Base URL + auth resolved by apiClient (#12363). rawRequest keeps the
  // non-throwing per-key contract: a failure logs and continues to the next key.
  for (const key of keys) {
    const response = await apiClient.rawRequest(`/api/secrets/`, {
      method: 'POST',
      body: {
        name: key.envVar,
        value: key.value,
        secret_type: 'api_key',
        scope: 'general',
        description: key.description,
      },
    })
    if (!response.ok) {
      logger.error('Failed to save key %s: %s', key.envVar, response.statusText)
    }
  }
}
</script>

<style scoped>
.wizard-steps {
  display: flex;
  justify-content: center;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--border-default);
}

.step-dot {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-xs);
  opacity: 0.5;
  transition: opacity var(--duration-200);
}

.step-dot.active,
.step-dot.completed {
  opacity: 1;
}

.step-number {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--border-default);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 0.85rem;
}

.step-dot.active .step-number {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.step-dot.completed .step-number {
  background: var(--color-success);
  color: var(--text-on-success);
}

.step-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.step-content {
  min-height: 240px;
}

.step-description {
  color: var(--text-secondary);
  margin-bottom: var(--spacing-md);
}

.role-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.role-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: border-color var(--duration-200);
}

.role-card:hover {
  border-color: var(--color-primary);
}

.role-card.selected {
  border-color: var(--color-primary);
  background: var(--bg-tertiary);
}

.role-checkbox {
  display: none;
}

.role-card i {
  font-size: var(--text-2xl);
  color: var(--color-primary);
  width: 32px;
  text-align: center;
}

.role-info {
  display: flex;
  flex-direction: column;
}

.role-name {
  font-weight: 600;
}

.role-desc {
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.key-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.key-card {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.key-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-secondary);
}

.key-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.status-ok {
  color: var(--color-success);
}

.status-missing {
  color: var(--color-error);
}

.status-warning {
  color: var(--color-warning);
}

.key-name {
  font-family: monospace;
  font-weight: 600;
}

.key-badge {
  font-size: 0.7rem;
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
  text-transform: uppercase;
}

.key-badge.required {
  background: var(--color-error);
  color: var(--text-on-error);
}

.key-badge.optional {
  background: var(--border-default);
  color: var(--text-secondary);
}

.key-role {
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.key-body {
  padding: var(--spacing-md);
}

.key-desc {
  margin-bottom: var(--spacing-sm);
  font-size: 0.9rem;
  color: var(--text-secondary);
}

.license-link {
  margin-bottom: var(--spacing-sm);
}

.license-link a {
  color: var(--color-primary);
  text-decoration: none;
}

.license-link a:hover {
  text-decoration: underline;
}

.license-link i {
  margin-right: var(--spacing-xs);
  font-size: 0.8rem;
}

.key-input-row {
  display: flex;
  gap: var(--spacing-xs);
}

.key-input {
  flex: 1;
  padding: var(--spacing-sm);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: monospace;
}

.toggle-visibility {
  padding: var(--spacing-sm);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
}

.summary-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-lg);
}

.summary-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
}

.summary-name {
  font-family: monospace;
  font-weight: 600;
  flex: 1;
}

.summary-status {
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.secrets-link {
  text-align: center;
  padding: var(--spacing-md);
}

.secrets-link a {
  color: var(--color-primary);
  text-decoration: none;
}

.secrets-link a:hover {
  text-decoration: underline;
}

.empty-state {
  text-align: center;
  padding: var(--spacing-xl);
  color: var(--text-secondary);
}

.empty-state i {
  font-size: 2rem;
  color: var(--color-success);
  margin-bottom: var(--spacing-sm);
  display: block;
}

.spacer {
  flex: 1;
}

.btn-primary,
.btn-secondary {
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.btn-primary {
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: transparent;
  border: 1px solid var(--border-default);
  color: var(--text-primary);
}
</style>
