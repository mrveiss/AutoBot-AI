<template>
  <BaseModal
    :model-value="open"
    :title="$t('views.plugins.install.title')"
    :close-label="$t('common.close')"
    :width="520"
    @close="onClose"
  >
    <div ref="pluginTablistRef" class="modal-tabs" role="tablist">
      <button
        v-bind="tabAttrs('zip')"
        class="modal-tab"
        :class="{ active: activeTab === 'zip' }"
        @click="activeTab = 'zip'"
        @keydown="handleTabKeydown"
      >
        {{ $t('views.plugins.install.zipTab') }}
      </button>
      <button
        v-bind="tabAttrs('git')"
        class="modal-tab"
        :class="{ active: activeTab === 'git' }"
        @click="activeTab = 'git'"
        @keydown="handleTabKeydown"
      >
        {{ $t('views.plugins.install.gitTab') }}
      </button>
    </div>

    <div class="modal-body">
      <!-- ZIP tab -->
      <div v-if="activeTab === 'zip'" v-bind="panelAttrs('zip')" class="tab-pane">
        <p class="hint">{{ $t('views.plugins.install.zipHint') }}</p>
        <label class="file-drop" :class="{ 'has-file': zipFile }">
          <input
            type="file"
            accept=".zip,application/zip"
            class="file-input"
            @change="onFileChange"
          />
          <svg
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            class="drop-icon"
            aria-hidden="true"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="1.5"
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
            />
          </svg>
          <span v-if="!zipFile" class="drop-label">
            {{ $t('views.plugins.install.zipPickFile') }}
          </span>
          <span v-else class="drop-label">
            {{ zipFile.name }}
          </span>
        </label>
      </div>

      <!-- Git tab -->
      <div v-if="activeTab === 'git'" v-bind="panelAttrs('git')" class="tab-pane">
        <p class="hint">{{ $t('views.plugins.install.gitHint') }}</p>
        <label class="form-field">
          <span class="form-label">{{ $t('views.plugins.install.gitUrlLabel') }}</span>
          <input
            v-model.trim="gitUrl"
            type="url"
            class="form-input"
            placeholder="https://github.com/owner/repo.git"
            autocomplete="off"
            spellcheck="false"
          />
        </label>
        <label class="form-field">
          <span class="form-label">
            {{ $t('views.plugins.install.gitRefLabel') }}
            <span class="form-label-optional">{{ $t('common.optional') }}</span>
          </span>
          <input
            v-model.trim="gitRef"
            type="text"
            class="form-input"
            placeholder="main"
            autocomplete="off"
            spellcheck="false"
          />
        </label>
      </div>

      <div v-if="error" class="error-banner" role="alert">
        {{ error }}
      </div>
      <div v-if="successMessage" class="success-banner" role="status">
        {{ successMessage }}
      </div>
    </div>

    <template #actions>
      <button class="btn btn-ghost" :disabled="busy" @click="onClose">
        {{ $t('common.cancel') }}
      </button>
      <button class="btn btn-primary" :disabled="!canSubmit || busy" @click="submit">
        {{ busy ? $t('views.plugins.install.installing') : $t('views.plugins.install.install') }}
      </button>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseModal } from '@autobot/ui'
import { usePlugins } from '@/composables/usePlugins'
import { useTabs } from '@/composables/useTabs'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'installed', payload: { name: string; version: string }): void
}>()

const { t } = useI18n()
const { installFromZip, installFromGit, error: composableError } = usePlugins()
let closeTimer: ReturnType<typeof setTimeout> | null = null

const PLUGIN_TAB_IDS = ['zip', 'git'] as const
const { activeTab, tabAttrs, panelAttrs, handleKeydown: handleTabKeydown, tablistRef: pluginTablistRef } =
  useTabs(PLUGIN_TAB_IDS)
const zipFile = ref<File | null>(null)
const gitUrl = ref('')
const gitRef = ref('')
const busy = ref(false)
const error = ref<string | null>(null)
const successMessage = ref<string | null>(null)

const canSubmit = computed(() => {
  if (activeTab.value === 'zip') return zipFile.value !== null
  return gitUrl.value.length > 0
})

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      activeTab.value = 'zip'
      zipFile.value = null
      gitUrl.value = ''
      gitRef.value = ''
      error.value = null
      successMessage.value = null
      busy.value = false
    }
  },
)

function onFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  zipFile.value = target.files?.[0] ?? null
  error.value = null
}

function onClose() {
  if (busy.value) return
  emit('close')
}

async function submit() {
  if (!canSubmit.value || busy.value) return
  busy.value = true
  error.value = null
  successMessage.value = null
  try {
    const result =
      activeTab.value === 'zip' && zipFile.value
        ? await installFromZip(zipFile.value)
        : await installFromGit(gitUrl.value, gitRef.value || undefined)
    if (result) {
      successMessage.value = `${result.name} v${result.version}`
      emit('installed', result)
      closeTimer = setTimeout(() => emit('close'), 800)
    } else {
      error.value = composableError.value || t('views.plugins.install.failed')
    }
  } finally {
    busy.value = false
  }
}

onUnmounted(() => {
  if (closeTimer) {
    clearTimeout(closeTimer)
    closeTimer = null
  }
})
</script>

<style scoped>
/* #10882: overlay/header/footer chrome now provided by @autobot/ui BaseModal;
   the install tabs + form body remain here. */
.modal-tabs {
  display: flex;
  border-bottom: 1px solid var(--border-default);
  margin-bottom: var(--spacing-md);
}

.modal-tab {
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-secondary);
  padding: var(--spacing-sm) var(--spacing-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: color var(--duration-150), border-color var(--duration-150);
}

.modal-tab.active {
  color: var(--color-info);
  border-bottom-color: var(--color-info);
}

.modal-body {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.hint {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.file-drop {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  border: 1.5px dashed var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-xl);
  cursor: pointer;
  transition: border-color var(--duration-150), background var(--duration-150);
}

.file-drop:hover,
.file-drop.has-file {
  border-color: var(--color-info);
  background: var(--bg-tertiary);
}

.file-input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.drop-icon {
  width: 32px;
  height: 32px;
  color: var(--text-tertiary);
}

.drop-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  text-align: center;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.form-label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  display: flex;
  gap: var(--spacing-xs);
  align-items: baseline;
}

.form-label-optional {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  font-weight: 400;
}

.form-input {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-sm) var(--spacing-md);
  font-size: var(--text-sm);
  color: var(--text-primary);
  font-family: var(--font-mono);
}

.form-input:focus {
  outline: none;
  border-color: var(--color-info);
}

.error-banner {
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  color: var(--color-error);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

.success-banner {
  background: var(--color-success-bg);
  border: 1px solid var(--color-success-border);
  color: var(--color-success);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

.btn {
  padding: var(--spacing-sm) var(--spacing-md);
  font-size: var(--text-sm);
  font-weight: 500;
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  cursor: pointer;
  transition: background var(--duration-150);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-ghost {
  background: transparent;
  border-color: var(--border-default);
  color: var(--text-primary);
}

.btn-ghost:hover:not(:disabled) {
  background: var(--bg-tertiary);
}

.btn-primary {
  background: var(--color-info);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  filter: brightness(1.1);
}
</style>
