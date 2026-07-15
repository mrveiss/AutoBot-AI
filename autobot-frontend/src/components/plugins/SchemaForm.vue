<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  SchemaForm Component
  Issue #11522 - Schema-driven config form renderer for plugin and skill config.

  Renders a form from a JSON Schema `properties` map.
  Supports: string, number/integer, boolean, enum (select), array of scalars (tag input).
  Honors: default, required, description, title.
  Emits update:modelValue (v-model compatible).
  Falls back to raw-JSON textarea for unsupported shapes (nested objects without
  renderable properties, or schemas without a `properties` key).
-->
<template>
  <div class="schema-form">
    <template v-if="hasRenderableFields">
      <div
        v-for="[key, fieldSchema] in renderableFields"
        :key="key"
        class="schema-field"
      >
        <label :for="`sf-${key}`" class="field-label">
          {{ fieldLabel(key, fieldSchema) }}
          <span v-if="isRequired(key)" class="required-mark" :aria-label="t('components.schemaForm.requiredMark')">*</span>
        </label>

        <p v-if="fieldSchema.description" class="field-description">
          {{ fieldSchema.description }}
        </p>

        <!-- Boolean toggle -->
        <input
          v-if="fieldSchema.type === 'boolean'"
          :id="`sf-${key}`"
          type="checkbox"
          :checked="Boolean(localValue[key] ?? fieldSchema.default ?? false)"
          class="field-checkbox"
          @change="onCheckbox(key, ($event.target as HTMLInputElement).checked)"
        />

        <!-- Enum select -->
        <select
          v-else-if="fieldSchema.enum"
          :id="`sf-${key}`"
          class="field-select"
          :value="String(localValue[key] ?? fieldSchema.default ?? '')"
          @change="onSelect(key, fieldSchema, ($event.target as HTMLSelectElement).value)"
        >
          <option value="" disabled>{{ t('components.schemaForm.selectPlaceholder') }}</option>
          <option
            v-for="opt in fieldSchema.enum"
            :key="String(opt)"
            :value="String(opt)"
          >
            {{ String(opt) }}
          </option>
        </select>

        <!-- Number / integer -->
        <input
          v-else-if="fieldSchema.type === 'number' || fieldSchema.type === 'integer'"
          :id="`sf-${key}`"
          type="number"
          class="field-input"
          :value="localValue[key] ?? fieldSchema.default ?? ''"
          :required="isRequired(key)"
          @input="onNumber(key, ($event.target as HTMLInputElement).value)"
        />

        <!-- Array of scalars (tag input) -->
        <div v-else-if="fieldSchema.type === 'array'" class="field-tags">
          <div class="tags-list">
            <span
              v-for="(tag, idx) in arrayValue(key)"
              :key="idx"
              class="tag"
            >
              {{ tag }}
              <button type="button" class="tag-remove" @click="removeTag(key, idx)" :aria-label="t('components.schemaForm.removeTag')">×</button>
            </span>
          </div>
          <input
            :id="`sf-${key}`"
            type="text"
            class="field-input tags-input"
            :placeholder="t('components.schemaForm.addTagPlaceholder')"
            @keydown.enter.prevent="addTag(key, fieldSchema, ($event.target as HTMLInputElement).value); ($event.target as HTMLInputElement).value = ''"
          />
        </div>

        <!-- String (default) -->
        <input
          v-else
          :id="`sf-${key}`"
          type="text"
          class="field-input"
          :value="String(localValue[key] ?? fieldSchema.default ?? '')"
          :required="isRequired(key)"
          @input="onText(key, ($event.target as HTMLInputElement).value)"
        />
      </div>
    </template>

    <!-- Fallback: raw JSON textarea for schemas SchemaForm can't render -->
    <template v-else>
      <p class="fallback-hint">{{ t('components.schemaForm.rawJsonFallback') }}</p>
      <textarea
        class="field-json"
        :value="rawJson"
        rows="6"
        spellcheck="false"
        :aria-label="t('components.schemaForm.rawJsonLabel')"
        @input="onRawJson(($event.target as HTMLTextAreaElement).value)"
      />
      <p v-if="jsonError" class="json-error">{{ jsonError }}</p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SchemaForm')
const { t } = useI18n()

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface JsonSchemaProperty {
  type?: string
  title?: string
  description?: string
  default?: unknown
  enum?: unknown[]
  items?: { type?: string }
}

export interface JsonSchema {
  type?: string
  properties?: Record<string, JsonSchemaProperty>
  required?: string[]
}

// ---------------------------------------------------------------------------
// Props / Emits
// ---------------------------------------------------------------------------

const props = defineProps<{
  schema: JsonSchema
  modelValue: Record<string, unknown>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, unknown>]
}>()

// ---------------------------------------------------------------------------
// Local reactive state
// ---------------------------------------------------------------------------

const localValue = ref<Record<string, unknown>>({ ...props.modelValue })

watch(
  () => props.modelValue,
  (v: Record<string, unknown>) => {
    localValue.value = { ...v }
  },
)

// ---------------------------------------------------------------------------
// Schema analysis
// ---------------------------------------------------------------------------

const renderableFields = computed<[string, JsonSchemaProperty][]>(() => {
  const props_ = props.schema?.properties ?? {}
  return (Object.entries(props_) as [string, JsonSchemaProperty][]).filter(([, s]) => isRenderable(s))
})

const hasRenderableFields = computed(() => renderableFields.value.length > 0)

function isRenderable(s: JsonSchemaProperty): boolean {
  if (s.enum) return true
  const type = s.type
  if (!type) return false
  if (['string', 'number', 'integer', 'boolean'].includes(type)) return true
  if (type === 'array') return true
  return false
}

function isRequired(key: string): boolean {
  return (props.schema.required ?? []).includes(key)
}

function fieldLabel(key: string, s: JsonSchemaProperty): string {
  return s.title ?? key
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function emit_(key: string, value: unknown) {
  const next = { ...localValue.value, [key]: value }
  localValue.value = next
  emit('update:modelValue', next)
}

function onText(key: string, value: string) {
  emit_(key, value)
}

function onNumber(key: string, value: string) {
  const parsed = value === '' ? undefined : Number(value)
  emit_(key, parsed)
}

function onCheckbox(key: string, checked: boolean) {
  emit_(key, checked)
}

function onSelect(key: string, s: JsonSchemaProperty, value: string) {
  // Recover the original (possibly non-string) enum member: the DOM only
  // gives us strings, but the schema may declare numeric/boolean enums.
  const original = (s.enum ?? []).find((o) => String(o) === value)
  emit_(key, original !== undefined ? original : value)
}

function coerceScalar(v: string, type?: string): unknown {
  if (type === 'number' || type === 'integer') {
    const n = Number(v)
    return Number.isNaN(n) ? v : n
  }
  if (type === 'boolean') return v === 'true'
  return v
}

function arrayValue(key: string): unknown[] {
  const v = localValue.value[key]
  if (Array.isArray(v)) return v as unknown[]
  return []
}

function addTag(key: string, s: JsonSchemaProperty, tag: string) {
  const trimmed = tag.trim()
  if (!trimmed) return
  const current = arrayValue(key)
  emit_(key, [...current, coerceScalar(trimmed, s.items?.type)])
}

function removeTag(key: string, idx: number) {
  const current = arrayValue(key)
  const next = current.filter((_, i) => i !== idx)
  emit_(key, next)
}

// ---------------------------------------------------------------------------
// Raw-JSON fallback
// ---------------------------------------------------------------------------

const rawJson = ref(JSON.stringify(props.modelValue, null, 2))
const jsonError = ref('')

watch(
  () => props.modelValue,
  (v: Record<string, unknown>) => {
    rawJson.value = JSON.stringify(v, null, 2)
    jsonError.value = ''
  },
)

function onRawJson(text: string) {
  rawJson.value = text
  try {
    const parsed = JSON.parse(text)
    jsonError.value = ''
    emit('update:modelValue', parsed)
    localValue.value = parsed
  } catch {
    jsonError.value = t('components.schemaForm.invalidJson')
    logger.warn('SchemaForm raw JSON parse error')
  }
}
</script>

<style scoped>
.schema-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md, 1rem);
}

.schema-field {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs, 0.25rem);
}

.field-label {
  font-size: var(--text-sm, 0.875rem);
  font-weight: 600;
  color: var(--text-primary, #111);
}

.required-mark {
  color: var(--color-error, #ef4444);
  margin-left: 2px;
}

.field-description {
  font-size: var(--text-xs, 0.75rem);
  color: var(--text-secondary, #6b7280);
  margin: 0;
}

.field-input,
.field-select,
.field-json {
  width: 100%;
  background: var(--bg-secondary, #f9fafb);
  border: 1px solid var(--border-default, #e5e7eb);
  border-radius: var(--radius-md, 0.375rem);
  padding: var(--spacing-xs, 0.25rem) var(--spacing-sm, 0.5rem);
  font-size: var(--text-sm, 0.875rem);
  color: var(--text-primary, #111);
  box-sizing: border-box;
}

.field-input:focus,
.field-select:focus,
.field-json:focus {
  outline: none;
  border-color: var(--color-primary, #6366f1);
}

.field-checkbox {
  width: 1rem;
  height: 1rem;
  accent-color: var(--color-primary, #6366f1);
  cursor: pointer;
}

.field-tags {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs, 0.25rem);
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1, 0.25rem);
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--bg-tertiary, #f3f4f6);
  border: 1px solid var(--border-default, #e5e7eb);
  border-radius: var(--radius-default, 0.25rem);
  padding: 2px var(--spacing-1-5, 0.375rem);
  font-size: var(--text-xs, 0.75rem);
  color: var(--text-secondary, #6b7280);
}

.tag-remove {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-secondary, #9ca3af);
  padding: 0;
  font-size: 0.875rem;
  line-height: 1;
}

.tag-remove:hover {
  color: var(--color-error, #ef4444);
}

.tags-input {
  margin-top: var(--spacing-xs, 0.25rem);
}

.fallback-hint {
  font-size: var(--text-xs, 0.75rem);
  color: var(--text-secondary, #6b7280);
  margin: 0;
  font-style: italic;
}

.field-json {
  font-family: var(--font-mono, monospace);
  font-size: var(--text-xs, 0.75rem);
  resize: vertical;
}

.json-error {
  font-size: var(--text-sm, 0.875rem);
  color: var(--color-error, #ef4444);
  margin: 0;
}
</style>
