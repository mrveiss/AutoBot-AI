<template>
  <BaseModal
    :model-value="visible"
    :title="$t('analytics.sources.shareSource')"
    size="sm"
    @close="$emit('close')"
  >
    <template #title>
      <span class="modal-title-inner">
        <Icon name="share-alt" />
        {{ $t('analytics.sources.shareSource') }}
      </span>
    </template>

            <!-- Source info -->
            <div v-if="source" class="source-info-bar">
              <i :class="source.source_type === 'github' ? 'github' : 'folder'"></i>
              <div>
                <div class="source-name">{{ source.name }}</div>
                <div class="source-detail">{{ source.repo ?? source.clone_path }}</div>
              </div>
            </div>

            <!-- Access Level -->
            <div class="form-group">
              <label class="form-label">{{ $t('analytics.sources.form.accessLevel') }}</label>
              <div class="access-selector">
                <label
                  v-for="level in accessLevels"
                  :key="level.value"
                  class="access-option"
                  :class="{ 'access-option--active': form.access === level.value }"
                >
                  <input
                    type="radio"
                    :value="level.value"
                    v-model="form.access"
                    class="sr-only"
                  />
                  <Icon :name="level.icon" />
                  <span>{{ level.label }}</span>
                  <small>{{ level.description }}</small>
                </label>
              </div>
            </div>

            <!-- User IDs for shared access -->
            <div v-if="form.access === 'shared'" class="form-group">
              <label class="form-label" for="share-user-ids">
                {{ $t('analytics.sources.share.userIds') }}
                <span class="form-label-hint">({{ $t('analytics.sources.share.userIdsHint') }})</span>
              </label>
              <textarea
                id="share-user-ids"
                v-model="userIdsText"
                class="form-textarea"
                placeholder="user1&#10;user2&#10;user3"
                rows="4"
                autocomplete="off"
              ></textarea>
              <span class="form-hint">
                <Icon name="info-circle" />
                {{ $t('analytics.sources.share.userIdsHelp') }}
              </span>
            </div>

            <!-- Current shared_with display -->
            <div v-if="currentSharedWith.length > 0" class="shared-with-section">
              <div class="form-label">{{ $t('analytics.sources.share.currentlySharedWith') }}:</div>
              <div class="shared-tags">
                <span v-for="uid in currentSharedWith" :key="uid" class="shared-tag">
                  <Icon name="user" />
                  {{ uid }}
                </span>
              </div>
            </div>

            <!-- Submit error -->
            <div v-if="submitError" class="submit-error">
              <Icon name="exclamation-triangle" />
              {{ submitError }}
            </div>

    <template #actions>
      <button class="btn-cancel" @click="$emit('close')" type="button">{{ $t('analytics.sources.form.cancel') }}</button>
      <button
        class="btn-submit"
        @click="handleSubmit"
        :disabled="submitting || !source"
        type="button"
      >
        <i :class="submitting ? 'fas fa-spinner fa-spin' : 'save'"></i>
        {{ submitting ? $t('analytics.sources.form.saving') : $t('analytics.sources.share.updateAccess') }}
      </button>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * ShareSourceModal Component
 *
 * Access control dialog for code sources.
 * Issue #1133: Code Source Registry for codebase analytics.
 */

import Icon from '@/components/ui/Icon.vue'
import { BaseModal } from '@autobot/ui'
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { shareCodeSource } from '@/composables/analytics/useSourceRegistry'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ShareSourceModal')
const { t } = useI18n()

// ---- Types ----------------------------------------------------------------

import type { CodeSource } from '@/types/analytics'

// ---- Props & Emits --------------------------------------------------------

interface Props {
  visible: boolean
  source: CodeSource | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'saved', source: CodeSource): void
  (e: 'close'): void
}>()

// ---- Constants ------------------------------------------------------------

const accessLevels = computed(() => [
  {
    value: 'private' as const,
    label: t('analytics.sources.access.private'),
    icon: 'lock' as const,
    description: t('analytics.sources.access.onlyYou')
  },
  {
    value: 'shared' as const,
    label: t('analytics.sources.access.shared'),
    icon: 'users' as const,
    description: t('analytics.sources.access.specificUsers')
  },
  {
    value: 'public' as const,
    label: t('analytics.sources.access.public'),
    icon: 'globe' as const,
    description: t('analytics.sources.access.allUsers')
  }
])

// ---- State ----------------------------------------------------------------

const form = ref({
  access: 'private' as 'private' | 'shared' | 'public'
})
const userIdsText = ref('')
const submitError = ref<string | null>(null)
const submitting = ref(false)

// ---- Computed -------------------------------------------------------------

const currentSharedWith = computed<string[]>(() =>
  props.source?.shared_with ?? []
)

const parsedUserIds = computed<string[]>(() =>
  userIdsText.value
    .split(/[\n,]+/)
    .map(s => s.trim())
    .filter(s => s.length > 0)
)

// ---- Actions --------------------------------------------------------------

async function handleSubmit() {
  if (!props.source) return
  submitting.value = true
  submitError.value = null

  try {
    const saved = await shareCodeSource(props.source.id, {
      access: form.value.access,
      user_ids: parsedUserIds.value
    })
    logger.info('Access updated for source:', saved.name)
    emit('saved', saved)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error('Share update failed:', msg)
    submitError.value = `Update failed: ${msg}`
  } finally {
    submitting.value = false
  }
}

// ---- Lifecycle ------------------------------------------------------------

watch(() => props.visible, (visible) => {
  if (visible && props.source) {
    form.value.access = props.source.access
    userIdsText.value = (props.source.shared_with ?? []).join('\n')
    submitError.value = null
  }
}, { immediate: true })

watch(() => props.source, (source) => {
  if (source && props.visible) {
    form.value.access = source.access
    userIdsText.value = (source.shared_with ?? []).join('\n')
  }
})
</script>

<style scoped src="@/design-system/styles/source-modal-shared.css"></style>

<style scoped>
/* Issue #1133: Share Source Modal */

.modal-title-inner {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.modal-title-inner i {
  color: var(--color-success);
}

/* Source info bar */
.source-info-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-3) var(--spacing-4);
  border: 1px solid var(--border-subtle);
}

.source-info-bar i {
  font-size: var(--text-xl);
  color: var(--color-info);
  flex-shrink: 0;
}

.source-name {
  font-weight: var(--font-semibold);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.source-detail {
  font-size: var(--text-xs);
  color: var(--text-muted);
  font-family: var(--font-mono, monospace);
}

.form-label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  display: flex;
  align-items: baseline;
  gap: var(--spacing-1-5);
}

.form-label-hint {
  font-size: var(--text-xs);
  color: var(--text-muted);
  font-weight: var(--font-normal);
}

.form-textarea {
  padding: var(--spacing-2-5) var(--spacing-4);
  background: var(--bg-tertiary-alpha);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  color: var(--text-on-primary);
  font-size: var(--text-sm);
  font-family: var(--font-mono, monospace);
  resize: vertical;
  width: 100%;
  transition: border-color var(--duration-200);
}

.form-textarea:focus {
  outline: none;
  border-color: var(--color-info);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15);
}

.form-textarea:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* Shared-with section */
.shared-with-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.shared-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1-5);
}

.shared-tag {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  background: rgba(59, 130, 246, 0.12);
  color: var(--color-info);
  font-size: var(--text-xs);
  padding: var(--spacing-1) var(--spacing-2-5);
  border-radius: var(--radius-full);
}

.btn-submit {
  padding: var(--spacing-2-5) var(--spacing-5);
  background: var(--color-success);
  border: none;
  border-radius: var(--radius-lg);
  color: var(--bg-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  transition: opacity var(--duration-200);
}

.btn-submit:hover:not(:disabled) {
  opacity: 0.85;
}
</style>
