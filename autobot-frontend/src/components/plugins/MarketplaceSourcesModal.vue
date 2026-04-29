<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div
        v-if="open"
        class="modal-backdrop"
        role="dialog"
        aria-modal="true"
        :aria-label="$t('views.marketplace.sources.title')"
        @click.self="onClose"
      >
        <div class="modal-card" @keydown.esc="onClose">
          <header class="modal-header">
            <h2 class="modal-title">{{ $t('views.marketplace.sources.title') }}</h2>
            <button class="modal-close" :aria-label="$t('common.close')" @click="onClose">
              <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" class="close-icon">
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </header>

          <div class="modal-body">
            <p class="hint">{{ $t('views.marketplace.sources.hint') }}</p>

            <!-- Existing sources list -->
            <ul v-if="sources.length > 0" class="sources-list">
              <li v-for="src in sources" :key="src.id" class="source-row">
                <div class="source-info">
                  <div class="source-name">
                    {{ src.name }}
                    <span v-if="src.is_builtin" class="builtin-badge">
                      {{ $t('views.marketplace.sources.builtin') }}
                    </span>
                  </div>
                  <div v-if="src.url" class="source-url">{{ src.url }}</div>
                  <div v-if="src.description" class="source-desc">{{ src.description }}</div>
                </div>
                <button
                  v-if="!src.is_builtin"
                  class="btn btn-danger"
                  :disabled="busy"
                  @click="onDelete(src.id)"
                >
                  {{ $t('common.remove') }}
                </button>
              </li>
            </ul>

            <!-- Add new source form -->
            <div class="add-form">
              <h3 class="add-title">{{ $t('views.marketplace.sources.addTitle') }}</h3>
              <label class="form-field">
                <span class="form-label">{{ $t('views.marketplace.sources.nameLabel') }}</span>
                <input
                  v-model.trim="newName"
                  type="text"
                  class="form-input"
                  maxlength="64"
                  :placeholder="$t('views.marketplace.sources.namePlaceholder')"
                />
              </label>
              <label class="form-field">
                <span class="form-label">{{ $t('views.marketplace.sources.urlLabel') }}</span>
                <input
                  v-model.trim="newUrl"
                  type="url"
                  class="form-input"
                  placeholder="https://example.com/plugins.json"
                  autocomplete="off"
                  spellcheck="false"
                />
              </label>
              <label class="form-field">
                <span class="form-label">
                  {{ $t('views.marketplace.sources.descLabel') }}
                  <span class="form-label-optional">{{ $t('common.optional') }}</span>
                </span>
                <input
                  v-model.trim="newDesc"
                  type="text"
                  class="form-input"
                  maxlength="200"
                />
              </label>

              <div v-if="error" class="error-banner" role="alert">
                {{ error }}
              </div>

              <button
                class="btn btn-primary"
                :disabled="!canAdd || busy"
                @click="onAdd"
              >
                {{ busy ? $t('views.marketplace.sources.adding') : $t('views.marketplace.sources.add') }}
              </button>
            </div>
          </div>

          <footer class="modal-footer">
            <button class="btn btn-ghost" @click="onClose">
              {{ $t('common.close') }}
            </button>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMarketplaceSources } from '@/composables/useMarketplaceSources'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'updated'): void
}>()

const { t } = useI18n()
const {
  sources,
  listSources,
  addSource,
  deleteSource,
  error: composableError,
} = useMarketplaceSources()

const newName = ref('')
const newUrl = ref('')
const newDesc = ref('')
const busy = ref(false)
const error = ref<string | null>(null)

const canAdd = computed(() => newName.value.length > 0 && newUrl.value.length > 0)

watch(
  () => props.open,
  async (isOpen) => {
    if (isOpen) {
      newName.value = ''
      newUrl.value = ''
      newDesc.value = ''
      error.value = null
      busy.value = false
      await listSources()
    }
  },
)

function onClose() {
  if (busy.value) return
  emit('close')
}

async function onAdd() {
  if (!canAdd.value || busy.value) return
  busy.value = true
  error.value = null
  try {
    const result = await addSource({
      name: newName.value,
      url: newUrl.value,
      description: newDesc.value || undefined,
    })
    if (result) {
      newName.value = ''
      newUrl.value = ''
      newDesc.value = ''
      emit('updated')
    } else {
      error.value = composableError.value || t('views.marketplace.sources.addFailed')
    }
  } finally {
    busy.value = false
  }
}

async function onDelete(id: string) {
  busy.value = true
  error.value = null
  try {
    const ok = await deleteSource(id)
    if (ok) {
      emit('updated')
    } else {
      error.value = composableError.value || t('views.marketplace.sources.removeFailed')
    }
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: var(--spacing-md);
}

.modal-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  width: 100%;
  max-width: 600px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-xl);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: 1px solid var(--border-default);
}

.modal-title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
}

.modal-close {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: var(--spacing-xs);
  border-radius: var(--radius-sm);
}

.modal-close:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.close-icon {
  width: 20px;
  height: 20px;
}

.modal-body {
  padding: var(--spacing-lg);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.hint {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.sources-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.source-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.source-info {
  flex: 1;
  min-width: 0;
}

.source-name {
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  gap: var(--spacing-xs);
  align-items: center;
}

.builtin-badge {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-info);
  background: var(--color-info-bg);
  padding: 2px var(--spacing-xs);
  border-radius: var(--radius-sm);
}

.source-url {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  word-break: break-all;
  margin-top: 2px;
}

.source-desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-top: var(--spacing-xs);
}

.add-form {
  border-top: 1px solid var(--border-default);
  padding-top: var(--spacing-md);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.add-title {
  margin: 0 0 var(--spacing-xs) 0;
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
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

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  padding: var(--spacing-md) var(--spacing-lg);
  border-top: 1px solid var(--border-default);
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

.btn-primary {
  background: var(--color-info);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  filter: brightness(1.1);
}

.btn-danger {
  background: var(--color-error);
  color: white;
}

.btn-danger:hover:not(:disabled) {
  filter: brightness(1.1);
}

.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 150ms ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
</style>
