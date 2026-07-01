<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="preset-form-body">
    <!-- Error banner -->
    <div v-if="store.error" class="preset-error" role="alert">
      <Icon name="exclamation-triangle" />
      <span>{{ store.error }}</span>
    </div>

    <!-- Create / Edit form -->
    <section
      class="preset-form"
      :aria-label="editingId ? $t('chat.presets.editPreset') : $t('chat.presets.newPreset')"
    >
      <h3 class="form-title">
        {{ editingId ? $t('chat.presets.editPreset') : $t('chat.presets.newPreset') }}
      </h3>

      <div class="form-field">
        <label :for="nameFieldId" class="field-label">{{ $t('chat.presets.fieldName') }}</label>
        <input
          :id="nameFieldId"
          v-model="form.name"
          type="text"
          class="field-input"
          :placeholder="$t('chat.presets.namePlaceholder')"
          :aria-invalid="!!nameError"
          :aria-describedby="nameError ? `${nameFieldId}-error` : undefined"
          @input="nameError = ''"
        />
        <span v-if="nameError" :id="`${nameFieldId}-error`" class="field-error">{{ nameError }}</span>
      </div>

      <div class="form-field">
        <label :for="descriptionFieldId" class="field-label">{{ $t('chat.presets.fieldDescription') }}</label>
        <input
          :id="descriptionFieldId"
          v-model="form.description"
          type="text"
          class="field-input"
          :placeholder="$t('chat.presets.descriptionPlaceholder')"
        />
      </div>

      <div class="form-field">
        <label :for="contentFieldId" class="field-label">{{ $t('chat.presets.fieldContent') }}</label>
        <textarea
          :id="contentFieldId"
          v-model="form.content"
          class="field-textarea"
          rows="4"
          :placeholder="$t('chat.presets.contentPlaceholder')"
          :aria-invalid="!!contentError"
          :aria-describedby="contentError ? `${contentFieldId}-error` : undefined"
          @input="contentError = ''"
        />
        <span v-if="contentError" :id="`${contentFieldId}-error`" class="field-error">{{ contentError }}</span>
      </div>

      <div class="form-actions">
        <BaseButton v-if="editingId" variant="ghost" size="sm" @click="resetForm">
          {{ $t('chat.presets.cancel') }}
        </BaseButton>
        <BaseButton
          variant="primary"
          size="sm"
          :loading="isSaving"
          :disabled="isSaving"
          @click="savePreset"
        >
          {{ editingId ? $t('chat.presets.update') : $t('chat.presets.create') }}
        </BaseButton>
      </div>
    </section>

    <hr class="section-divider" />

    <!-- Preset list -->
    <section class="preset-list" :aria-label="$t('chat.presets.listLabel')">
      <div v-if="store.isLoading" class="list-loading" aria-live="polite">
        <Icon name="spinner" class="spin" aria-hidden="true" />
        {{ $t('chat.presets.loading') }}
      </div>

      <div v-else-if="store.sortedPresets.length === 0" class="list-empty">
        {{ $t('chat.presets.empty') }}
      </div>

      <div
        v-else
        v-for="preset in store.sortedPresets"
        :key="preset.id"
        class="preset-row"
        :class="{ 'is-editing': editingId === preset.id }"
      >
        <div class="preset-info">
          <span class="preset-name">/{{ preset.name }}</span>
          <span class="preset-desc">{{ preset.description }}</span>
        </div>
        <div class="preset-row-actions">
          <BaseButton
            variant="ghost"
            size="xs"
            :aria-label="$t('chat.presets.editAriaLabel', { name: preset.name })"
            :disabled="isSaving"
            @click="startEdit(preset)"
          >
            <Icon name="edit" />
          </BaseButton>
          <BaseButton
            variant="error"
            size="xs"
            :aria-label="$t('chat.presets.deleteAriaLabel', { name: preset.name })"
            :disabled="isSaving || deletingId === preset.id"
            :loading="deletingId === preset.id"
            @click="confirmDelete(preset.id, preset.name)"
          >
            <Icon name="trash" />
          </BaseButton>
        </div>
      </div>
    </section>

    <!-- Delete confirmation overlay -->
    <div
      v-if="deleteConfirm"
      class="delete-confirm-overlay"
      role="alertdialog"
      :aria-label="$t('chat.presets.deleteConfirmTitle')"
    >
      <div class="delete-confirm-card">
        <p class="delete-confirm-text">
          {{ $t('chat.presets.deleteConfirmMessage', { name: deleteConfirm.name }) }}
        </p>
        <div class="delete-confirm-actions">
          <BaseButton variant="ghost" size="sm" @click="deleteConfirm = null">
            {{ $t('chat.presets.cancel') }}
          </BaseButton>
          <BaseButton
            variant="error"
            size="sm"
            :loading="deletingId === deleteConfirm.id"
            @click="executeDelete(deleteConfirm.id)"
          >
            {{ $t('chat.presets.delete') }}
          </BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatPresetsStore } from '@/stores/useChatPresetsStore'
import BaseButton from '@/components/base/BaseButton.vue'
import Icon from '@/components/ui/Icon.vue'
import type { SlashCommandPreset } from '@/types/api'

const props = withDefaults(defineProps<{
  idPrefix?: string
}>(), {
  idPrefix: 'preset'
})

const { t } = useI18n()
const store = useChatPresetsStore()

const form = reactive({ name: '', description: '', content: '' })
const editingId = ref<string | null>(null)
const isSaving = ref(false)
const deletingId = ref<string | null>(null)
const nameError = ref('')
const contentError = ref('')
const deleteConfirm = ref<{ id: string; name: string } | null>(null)

const nameFieldId = computed(() => `${props.idPrefix}-name`)
const descriptionFieldId = computed(() => `${props.idPrefix}-description`)
const contentFieldId = computed(() => `${props.idPrefix}-content`)

onMounted(() => {
  if (store.presets.length === 0) {
    store.fetchPresets()
  }
})

function resetForm(): void {
  form.name = ''
  form.description = ''
  form.content = ''
  editingId.value = null
  nameError.value = ''
  contentError.value = ''
}

function startEdit(preset: SlashCommandPreset): void {
  editingId.value = preset.id
  form.name = preset.name
  form.description = preset.description
  form.content = preset.content
  nameError.value = ''
  contentError.value = ''
}

function validate(): boolean {
  let valid = true
  if (!form.name.trim()) {
    nameError.value = t('chat.presets.nameRequired')
    valid = false
  } else if (!/^[\w-]+$/.test(form.name.trim())) {
    nameError.value = t('chat.presets.nameInvalid')
    valid = false
  }
  if (!form.content.trim()) {
    contentError.value = t('chat.presets.contentRequired')
    valid = false
  }
  return valid
}

async function savePreset(): Promise<void> {
  if (!validate()) return
  isSaving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      description: form.description.trim(),
      content: form.content.trim(),
    }
    if (editingId.value) {
      await store.updatePreset(editingId.value, payload)
    } else {
      await store.createPreset(payload)
    }
    if (!store.error) resetForm()
  } finally {
    isSaving.value = false
  }
}

function confirmDelete(id: string, name: string): void {
  deleteConfirm.value = { id, name }
}

async function executeDelete(id: string): Promise<void> {
  deletingId.value = id
  try {
    await store.deletePreset(id)
    deleteConfirm.value = null
    if (editingId.value === id) resetForm()
  } finally {
    deletingId.value = null
  }
}
</script>

<style scoped>
.preset-form-body {
  position: relative;
}

.preset-error {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  margin-bottom: var(--spacing-4);
  background: var(--color-danger-subtle, #fef2f2);
  color: var(--color-error, #dc2626);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

.preset-form {
  margin-bottom: var(--spacing-4);
}

.form-title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-4);
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  margin-bottom: var(--spacing-3);
}

.field-label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
}

.field-input,
.field-textarea {
  width: 100%;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-family: inherit;
  transition: border-color var(--duration-150) var(--ease-in-out);
  box-sizing: border-box;
}

.field-input:focus,
.field-textarea:focus {
  outline: 2px solid var(--color-primary);
  outline-offset: 0;
  border-color: var(--color-primary);
}

.field-input[aria-invalid="true"],
.field-textarea[aria-invalid="true"] {
  border-color: var(--color-error, #dc2626);
}

.field-textarea {
  resize: vertical;
  min-height: 80px;
}

.field-error {
  font-size: var(--text-xs);
  color: var(--color-error, #dc2626);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-2);
}

.section-divider {
  border: none;
  border-top: 1px solid var(--border-default);
  margin: var(--spacing-4) 0;
}

.preset-list {
  position: relative;
}

.list-loading,
.list-empty {
  padding: var(--spacing-4);
  text-align: center;
  color: var(--text-secondary);
  font-size: var(--text-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.preset-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-3) var(--spacing-2);
  border-radius: var(--radius-md);
  transition: background var(--duration-150) var(--ease-in-out);
  gap: var(--spacing-3);
}

.preset-row:hover {
  background: var(--bg-secondary);
}

.preset-row.is-editing {
  background: var(--color-primary-subtle, #eff6ff);
  outline: 1px solid var(--color-primary);
}

.preset-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  min-width: 0;
  flex: 1;
}

.preset-name {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.preset-desc {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.preset-row-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  flex-shrink: 0;
}

.delete-confirm-overlay {
  position: absolute;
  inset: 0;
  background: var(--bg-overlay-light, rgba(255, 255, 255, 0.9));
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  z-index: 1;
}

.delete-confirm-card {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  box-shadow: var(--shadow-lg);
  max-width: 360px;
  width: 90%;
}

.delete-confirm-text {
  font-size: var(--text-sm);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-4);
}

.delete-confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-2);
}
</style>
