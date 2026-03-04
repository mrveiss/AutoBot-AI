<script setup lang="ts">
/**
 * ConnectorConfigModal - Create/edit connector wizard (Issue #1255)
 *
 * Multi-step wizard:
 *  1. Type selection (file_server, web_crawler, database)
 *  2. Configuration (dynamic form per type)
 *  3. Schedule & verification mode
 *  4. Name, test connection, save
 */

import { ref, computed, watch } from 'vue'
import type {
  ConnectorConfig,
  ConnectorType
} from '@/types/knowledgeBase'
import { knowledgeRepository } from '@/models/repositories/KnowledgeRepository'
import BaseModal from '@/components/ui/BaseModal.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'
import { useI18n } from 'vue-i18n'

const logger = createLogger('ConnectorConfigModal')
const { t } = useI18n()

const props = defineProps<{
  modelValue: boolean
  editConnector: ConnectorConfig | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [config: ConnectorConfig]
}>()

// =========================================================================
// Wizard State
// =========================================================================

const currentStep = ref(1)
const totalSteps = 4
const saving = ref(false)
const testing = ref(false)
const testResult = ref<{ success: boolean; message: string } | null>(null)
const saveError = ref<string | null>(null)

// Form fields
const connectorType = ref<ConnectorType>('file_server')
const connectorName = ref('')
const verificationMode = ref<'autonomous' | 'collaborative'>('autonomous')
const scheduleCron = ref<string | null>(null)
const scheduleOption = ref('manual')
const enabled = ref(true)

// File server config
const fsBasePath = ref('')
const fsIncludePatterns = ref('')
const fsExcludePatterns = ref('')
const fsMaxFileSizeMb = ref(50)

// Web crawler config
const wcUrls = ref('')
const wcMaxDepth = ref(3)

// Database config
const dbConnectionString = ref('')
const dbQuery = ref('')
const dbIdColumn = ref('id')
const dbContentColumns = ref('')
const dbTimestampColumn = ref('')

const isEditing = computed(() => props.editConnector !== null)

const modalTitle = computed(() =>
  isEditing.value ? t('knowledge.connectors.config.editTitle') : t('knowledge.connectors.config.addTitle')
)

// =========================================================================
// Type Definitions for Wizard Cards
// =========================================================================

const typeCards = computed(() => [
  {
    type: 'file_server' as ConnectorType,
    label: t('knowledge.connectors.config.typeFileServer'),
    description: t('knowledge.connectors.config.typeFileServerDesc')
  },
  {
    type: 'web_crawler' as ConnectorType,
    label: t('knowledge.connectors.config.typeWebCrawler'),
    description: t('knowledge.connectors.config.typeWebCrawlerDesc')
  },
  {
    type: 'database' as ConnectorType,
    label: t('knowledge.connectors.config.typeDatabase'),
    description: t('knowledge.connectors.config.typeDatabaseDesc')
  }
])

const scheduleOptions = computed(() => [
  { value: 'manual', label: t('knowledge.connectors.config.scheduleManual'), cron: null },
  { value: '15min', label: t('knowledge.connectors.config.schedule15min'), cron: '*/15 * * * *' },
  { value: 'hourly', label: t('knowledge.connectors.config.scheduleHourly'), cron: '0 * * * *' },
  { value: 'daily', label: t('knowledge.connectors.config.scheduleDaily'), cron: '0 0 * * *' },
  { value: 'weekly', label: t('knowledge.connectors.config.scheduleWeekly'), cron: '0 0 * * 0' }
])

// =========================================================================
// Populate form when editing
// =========================================================================

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    resetForm()

    if (props.editConnector) {
      populateFromConfig(props.editConnector)
      // Skip type selection when editing
      currentStep.value = 2
    }
  }
)

function populateFromConfig(cfg: ConnectorConfig) {
  connectorType.value = cfg.connector_type
  connectorName.value = cfg.name
  verificationMode.value = cfg.verification_mode
  enabled.value = cfg.enabled
  scheduleCron.value = cfg.schedule_cron

  // Reverse-map cron to schedule option
  const match = scheduleOptions.value.find(o => o.cron === cfg.schedule_cron)
  scheduleOption.value = match ? match.value : 'manual'

  const c = cfg.config || {}
  switch (cfg.connector_type) {
    case 'file_server':
      fsBasePath.value = c.base_path || ''
      fsIncludePatterns.value = (cfg.include_patterns || []).join(', ')
      fsExcludePatterns.value = (cfg.exclude_patterns || []).join(', ')
      fsMaxFileSizeMb.value = c.max_file_size_mb ?? 50
      break
    case 'web_crawler':
      wcUrls.value = (c.urls || []).join('\n')
      wcMaxDepth.value = c.max_depth ?? 3
      break
    case 'database':
      dbConnectionString.value = c.connection_string || ''
      dbQuery.value = c.query || ''
      dbIdColumn.value = c.id_column || 'id'
      dbContentColumns.value = (c.content_columns || []).join(', ')
      dbTimestampColumn.value = c.timestamp_column || ''
      break
  }
}

function resetForm() {
  currentStep.value = 1
  connectorType.value = 'file_server'
  connectorName.value = ''
  verificationMode.value = 'autonomous'
  scheduleOption.value = 'manual'
  scheduleCron.value = null
  enabled.value = true
  saving.value = false
  testing.value = false
  testResult.value = null
  saveError.value = null

  fsBasePath.value = ''
  fsIncludePatterns.value = ''
  fsExcludePatterns.value = ''
  fsMaxFileSizeMb.value = 50

  wcUrls.value = ''
  wcMaxDepth.value = 3

  dbConnectionString.value = ''
  dbQuery.value = ''
  dbIdColumn.value = 'id'
  dbContentColumns.value = ''
  dbTimestampColumn.value = ''
}

// =========================================================================
// Build Config
// =========================================================================

function buildPayload(): Partial<ConnectorConfig> {
  const base: Partial<ConnectorConfig> = {
    connector_type: connectorType.value,
    name: connectorName.value,
    verification_mode: verificationMode.value,
    schedule_cron: scheduleCron.value,
    enabled: enabled.value
  }

  switch (connectorType.value) {
    case 'file_server':
      base.config = {
        base_path: fsBasePath.value,
        max_file_size_mb: fsMaxFileSizeMb.value
      }
      base.include_patterns = splitTags(fsIncludePatterns.value)
      base.exclude_patterns = splitTags(fsExcludePatterns.value)
      break
    case 'web_crawler':
      base.config = {
        urls: wcUrls.value.split('\n').map(u => u.trim()).filter(Boolean),
        max_depth: wcMaxDepth.value
      }
      break
    case 'database':
      base.config = {
        connection_string: dbConnectionString.value,
        query: dbQuery.value,
        id_column: dbIdColumn.value,
        content_columns: splitTags(dbContentColumns.value),
        timestamp_column: dbTimestampColumn.value || undefined
      }
      break
  }

  return base
}

function splitTags(input: string): string[] {
  return input
    .split(',')
    .map(s => s.trim())
    .filter(Boolean)
}

// =========================================================================
// Validation
// =========================================================================

const canProceed = computed(() => {
  switch (currentStep.value) {
    case 1:
      return true // Type is always selected
    case 2:
      return isConfigValid.value
    case 3:
      return true // Schedule always has a default
    case 4:
      return connectorName.value.trim().length > 0
    default:
      return false
  }
})

const isConfigValid = computed(() => {
  switch (connectorType.value) {
    case 'file_server':
      return fsBasePath.value.trim().length > 0
    case 'web_crawler':
      return wcUrls.value.trim().length > 0
    case 'database':
      return (
        dbConnectionString.value.trim().length > 0 &&
        dbQuery.value.trim().length > 0
      )
    default:
      return false
  }
})

// =========================================================================
// Navigation
// =========================================================================

function nextStep() {
  if (currentStep.value < totalSteps) {
    currentStep.value++
  }
}

function prevStep() {
  if (currentStep.value > 1) {
    currentStep.value--
  }
}

function selectType(type: ConnectorType) {
  connectorType.value = type
  nextStep()
}

function onScheduleChange() {
  const opt = scheduleOptions.value.find(o => o.value === scheduleOption.value)
  scheduleCron.value = opt ? opt.cron : null
}

// =========================================================================
// Test & Save
// =========================================================================

async function testConnection() {
  if (!isEditing.value) return
  testing.value = true
  testResult.value = null
  try {
    const result = await knowledgeRepository.testConnector(
      props.editConnector!.connector_id
    )
    testResult.value = result
  } catch (error: any) {
    testResult.value = {
      success: false,
      message: error.message || 'Test failed'
    }
  } finally {
    testing.value = false
  }
}

async function handleSave() {
  saving.value = true
  saveError.value = null
  try {
    const payload = buildPayload()
    let result: ConnectorConfig

    if (isEditing.value && props.editConnector) {
      result = await knowledgeRepository.updateConnector(
        props.editConnector.connector_id,
        payload
      )
      logger.info('Connector updated: %s', result.connector_id)
    } else {
      result = await knowledgeRepository.createConnector(payload)
      logger.info('Connector created: %s', result.connector_id)
    }

    emit('saved', result)
    emit('update:modelValue', false)
  } catch (error: any) {
    saveError.value = error.message || t('knowledge.connectors.config.saveFailed')
    logger.error('Failed to save connector: %s', error)
  } finally {
    saving.value = false
  }
}

function closeModal() {
  emit('update:modelValue', false)
}
</script>

<template>
  <BaseModal
    :model-value="modelValue"
    :title="modalTitle"
    size="medium"
    @update:model-value="$emit('update:modelValue', $event)"
    @close="closeModal"
  >
    <!-- Step Indicator -->
    <div class="step-indicator">
      <div
        v-for="step in totalSteps"
        :key="step"
        class="step-dot"
        :class="{
          active: step === currentStep,
          completed: step < currentStep
        }"
      >
        {{ step }}
      </div>
    </div>

    <!-- Step 1: Type Selection -->
    <div v-if="currentStep === 1" class="step-content">
      <p class="step-description">
        {{ $t('knowledge.connectors.config.selectTypeDesc') }}
      </p>
      <div class="type-grid">
        <button
          v-for="card in typeCards"
          :key="card.type"
          class="type-card"
          :class="{ selected: connectorType === card.type }"
          @click="selectType(card.type)"
        >
          <!-- Type Icons -->
          <svg
            v-if="card.type === 'file_server'"
            class="type-card-icon"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
            />
          </svg>
          <svg
            v-else-if="card.type === 'web_crawler'"
            class="type-card-icon"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9"
            />
          </svg>
          <svg
            v-else
            class="type-card-icon"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"
            />
          </svg>
          <span class="type-card-label">{{ card.label }}</span>
          <span class="type-card-desc">{{ card.description }}</span>
        </button>
      </div>
    </div>

    <!-- Step 2: Configuration -->
    <div v-if="currentStep === 2" class="step-content">
      <p class="step-description">
        {{ $t('knowledge.connectors.config.configureDetailsDesc') }}
      </p>

      <!-- File Server Fields -->
      <template v-if="connectorType === 'file_server'">
        <div class="form-group">
          <label class="form-label" for="fs-base-path">
            {{ $t('knowledge.connectors.config.basePath') }}
          </label>
          <input
            id="fs-base-path"
            v-model="fsBasePath"
            type="text"
            class="form-input"
            placeholder="/data/documents"
          />
        </div>
        <div class="form-group">
          <label class="form-label" for="fs-include">
            {{ $t('knowledge.connectors.config.includePatterns') }}
          </label>
          <input
            id="fs-include"
            v-model="fsIncludePatterns"
            type="text"
            class="form-input"
            placeholder="*.pdf, *.md, *.txt"
          />
          <span class="form-hint">
            {{ $t('knowledge.connectors.config.commaSeparatedGlob') }}
          </span>
        </div>
        <div class="form-group">
          <label class="form-label" for="fs-exclude">
            {{ $t('knowledge.connectors.config.excludePatterns') }}
          </label>
          <input
            id="fs-exclude"
            v-model="fsExcludePatterns"
            type="text"
            class="form-input"
            placeholder="*.tmp, .git/*"
          />
          <span class="form-hint">
            {{ $t('knowledge.connectors.config.commaSeparatedGlob') }}
          </span>
        </div>
        <div class="form-group">
          <label class="form-label" for="fs-max-size">
            {{ $t('knowledge.connectors.config.maxFileSize') }}
          </label>
          <input
            id="fs-max-size"
            v-model.number="fsMaxFileSizeMb"
            type="number"
            class="form-input form-input-narrow"
            min="1"
            max="500"
          />
        </div>
      </template>

      <!-- Web Crawler Fields -->
      <template v-if="connectorType === 'web_crawler'">
        <div class="form-group">
          <label class="form-label" for="wc-urls">{{ $t('knowledge.connectors.config.urls') }}</label>
          <textarea
            id="wc-urls"
            v-model="wcUrls"
            class="form-textarea"
            rows="4"
            placeholder="https://example.com&#10;https://docs.example.com"
          ></textarea>
          <span class="form-hint">
            {{ $t('knowledge.connectors.config.oneUrlPerLine') }}
          </span>
        </div>
        <div class="form-group">
          <label class="form-label" for="wc-depth">
            {{ $t('knowledge.connectors.config.maxCrawlDepth') }}
          </label>
          <input
            id="wc-depth"
            v-model.number="wcMaxDepth"
            type="number"
            class="form-input form-input-narrow"
            min="1"
            max="10"
          />
        </div>
      </template>

      <!-- Database Fields -->
      <template v-if="connectorType === 'database'">
        <div class="form-group">
          <label class="form-label" for="db-conn">
            {{ $t('knowledge.connectors.config.connectionString') }}
          </label>
          <input
            id="db-conn"
            v-model="dbConnectionString"
            type="password"
            class="form-input"
            placeholder="postgresql://user:pass@host:5432/db"
          />
        </div>
        <div class="form-group">
          <label class="form-label" for="db-query">
            {{ $t('knowledge.connectors.config.sqlQuery') }}
          </label>
          <textarea
            id="db-query"
            v-model="dbQuery"
            class="form-textarea"
            rows="3"
            placeholder="SELECT id, title, body FROM articles WHERE updated_at > :last_sync"
          ></textarea>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label" for="db-id-col">
              {{ $t('knowledge.connectors.config.idColumn') }}
            </label>
            <input
              id="db-id-col"
              v-model="dbIdColumn"
              type="text"
              class="form-input"
              placeholder="id"
            />
          </div>
          <div class="form-group">
            <label class="form-label" for="db-ts-col">
              {{ $t('knowledge.connectors.config.timestampColumn') }}
            </label>
            <input
              id="db-ts-col"
              v-model="dbTimestampColumn"
              type="text"
              class="form-input"
              placeholder="updated_at"
            />
          </div>
        </div>
        <div class="form-group">
          <label class="form-label" for="db-content-cols">
            {{ $t('knowledge.connectors.config.contentColumns') }}
          </label>
          <input
            id="db-content-cols"
            v-model="dbContentColumns"
            type="text"
            class="form-input"
            placeholder="title, body, summary"
          />
          <span class="form-hint">
            {{ $t('knowledge.connectors.config.commaSeparatedColumns') }}
          </span>
        </div>
      </template>
    </div>

    <!-- Step 3: Schedule -->
    <div v-if="currentStep === 3" class="step-content">
      <p class="step-description">
        {{ $t('knowledge.connectors.config.scheduleDesc') }}
      </p>

      <div class="form-group">
        <label class="form-label">{{ $t('knowledge.connectors.config.syncSchedule') }}</label>
        <div class="schedule-options">
          <label
            v-for="opt in scheduleOptions"
            :key="opt.value"
            class="schedule-option"
            :class="{ active: scheduleOption === opt.value }"
          >
            <input
              type="radio"
              v-model="scheduleOption"
              :value="opt.value"
              class="sr-only"
              @change="onScheduleChange"
            />
            <span>{{ opt.label }}</span>
          </label>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label">{{ $t('knowledge.connectors.config.verificationMode') }}</label>
        <div class="mode-toggle">
          <button
            class="mode-btn"
            :class="{ active: verificationMode === 'autonomous' }"
            @click="verificationMode = 'autonomous'"
            type="button"
          >
            {{ $t('knowledge.connectors.config.autonomous') }}
          </button>
          <button
            class="mode-btn"
            :class="{ active: verificationMode === 'collaborative' }"
            @click="verificationMode = 'collaborative'"
            type="button"
          >
            {{ $t('knowledge.connectors.config.collaborative') }}
          </button>
        </div>
        <span class="form-hint">
          {{ $t('knowledge.connectors.config.verificationHint') }}
        </span>
      </div>

      <div class="form-group">
        <label class="toggle-row">
          <input
            type="checkbox"
            v-model="enabled"
            class="toggle-checkbox"
          />
          <span class="toggle-label">{{ $t('knowledge.connectors.config.enabled') }}</span>
        </label>
      </div>
    </div>

    <!-- Step 4: Name & Save -->
    <div v-if="currentStep === 4" class="step-content">
      <p class="step-description">
        {{ $t('knowledge.connectors.config.nameAndSaveDesc') }}
      </p>

      <div class="form-group">
        <label class="form-label" for="connector-name">
          {{ $t('knowledge.connectors.config.connectorName') }}
        </label>
        <input
          id="connector-name"
          v-model="connectorName"
          type="text"
          class="form-input"
          placeholder="e.g. Internal Docs, Product Blog"
        />
      </div>

      <!-- Test Connection (edit mode only) -->
      <div v-if="isEditing" class="test-section">
        <BaseButton
          variant="outline"
          size="sm"
          :loading="testing"
          @click="testConnection"
        >
          {{ $t('knowledge.connectors.config.testConnection') }}
        </BaseButton>
        <div v-if="testResult" class="test-result" :class="testResult.success ? 'test-ok' : 'test-fail'">
          {{ testResult.message }}
        </div>
      </div>

      <!-- Save Error -->
      <div v-if="saveError" class="save-error">
        {{ saveError }}
      </div>
    </div>

    <!-- Footer Actions -->
    <template #actions>
      <BaseButton
        v-if="currentStep > 1"
        variant="ghost"
        @click="prevStep"
      >
        {{ $t('knowledge.connectors.config.back') }}
      </BaseButton>
      <div class="actions-spacer"></div>
      <BaseButton variant="ghost" @click="closeModal">
        {{ $t('knowledge.connectors.config.cancel') }}
      </BaseButton>
      <BaseButton
        v-if="currentStep < totalSteps"
        variant="primary"
        :disabled="!canProceed"
        @click="nextStep"
      >
        {{ $t('knowledge.connectors.config.next') }}
      </BaseButton>
      <BaseButton
        v-if="currentStep === totalSteps"
        variant="primary"
        :loading="saving"
        :disabled="!canProceed"
        @click="handleSave"
      >
        {{ isEditing ? $t('knowledge.connectors.config.update') : $t('knowledge.connectors.config.create') }}
      </BaseButton>
    </template>
  </BaseModal>
</template>

<style scoped>
/* Step Indicator */
.step-indicator {
  display: flex;
  justify-content: center;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-5);
}

.step-dot {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  font-family: var(--font-mono);
  border: 1px solid var(--border-default);
  background: var(--bg-secondary);
  color: var(--text-tertiary);
  transition: all 150ms ease;
}

.step-dot.active {
  background: var(--color-info-bg);
  color: var(--color-info);
  border-color: var(--color-info);
}

.step-dot.completed {
  background: var(--color-success-bg);
  color: var(--color-success);
  border-color: var(--color-success);
}

/* Step Content */
.step-content {
  min-height: 200px;
}

.step-description {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: var(--spacing-5);
  font-family: var(--font-sans);
}

/* Type Selection Grid */
.type-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--spacing-4);
}

.type-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-5);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  background: var(--bg-secondary);
  cursor: pointer;
  transition: all 150ms cubic-bezier(0.4, 0, 0.2, 1);
  text-align: center;
}

.type-card:hover {
  border-color: var(--color-info);
  background: var(--color-info-bg);
}

.type-card.selected {
  border-color: var(--color-info);
  background: var(--color-info-bg);
  box-shadow: 0 0 0 1px var(--color-info);
}

.type-card-icon {
  width: 32px;
  height: 32px;
  color: var(--color-info);
}

.type-card-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-sans);
}

.type-card-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: var(--font-sans);
  line-height: 1.4;
}

/* Form Elements */
.form-group {
  margin-bottom: var(--spacing-4);
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: var(--spacing-1-5);
  font-family: var(--font-sans);
}

.form-input,
.form-textarea {
  width: 100%;
  padding: var(--spacing-2) var(--spacing-3);
  font-size: 14px;
  font-family: var(--font-sans);
  color: var(--text-primary);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 2px;
  transition: border-color 150ms ease;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--color-info);
  box-shadow: 0 0 0 1px var(--color-info);
}

.form-input-narrow {
  max-width: 120px;
}

.form-textarea {
  resize: vertical;
  min-height: 60px;
  font-family: var(--font-mono);
  font-size: 13px;
}

.form-hint {
  display: block;
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 4px;
  font-family: var(--font-sans);
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-4);
}

/* Schedule Options */
.schedule-options {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

.schedule-option {
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: 2px;
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--bg-secondary);
  cursor: pointer;
  transition: all 150ms ease;
  font-family: var(--font-sans);
}

.schedule-option:hover {
  border-color: var(--color-info);
  color: var(--text-primary);
}

.schedule-option.active {
  background: var(--color-info-bg);
  color: var(--color-info);
  border-color: var(--color-info);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  border: 0;
}

/* Mode Toggle */
.mode-toggle {
  display: flex;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-1);
}

.mode-btn {
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: 2px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  font-family: var(--font-sans);
  cursor: pointer;
  transition: all 150ms ease;
}

.mode-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.mode-btn.active {
  background: var(--color-info-bg);
  color: var(--color-info);
  border-color: var(--color-info);
}

/* Toggle Row */
.toggle-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  cursor: pointer;
}

.toggle-checkbox {
  width: 16px;
  height: 16px;
}

.toggle-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  font-family: var(--font-sans);
}

/* Test Section */
.test-section {
  margin-top: var(--spacing-4);
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  flex-wrap: wrap;
}

.test-result {
  font-size: 13px;
  font-family: var(--font-sans);
  padding: var(--spacing-1-5) var(--spacing-3);
  border-radius: 2px;
}

.test-ok {
  color: var(--color-success-dark);
  background: var(--color-success-bg);
}

.test-fail {
  color: var(--color-error-dark);
  background: var(--color-error-bg);
}

/* Save Error */
.save-error {
  margin-top: var(--spacing-3);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--color-error-bg);
  color: var(--color-error-dark);
  border-radius: 2px;
  font-size: 13px;
  font-family: var(--font-sans);
}

/* Actions spacer */
.actions-spacer {
  flex: 1;
}

/* Responsive */
@media (max-width: 768px) {
  .type-grid {
    grid-template-columns: 1fr;
  }

  .form-row {
    grid-template-columns: 1fr;
  }

  .schedule-options {
    flex-direction: column;
  }
}
</style>
