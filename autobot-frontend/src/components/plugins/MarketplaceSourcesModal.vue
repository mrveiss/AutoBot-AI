<template>
  <BaseModal
    :model-value="open"
    :title="$t('views.marketplace.sources.title')"
    :close-label="$t('common.close')"
    :width="600"
    @close="onClose"
  >
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
          <BaseButton variant="error"
            v-if="!src.is_builtin"
            :disabled="busy"
            @click="onDelete(src.id)"
          >
            {{ $t('common.remove') }}
          </BaseButton>
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

        <BaseButton
          :disabled="!canAdd || busy"
          @click="onAdd"
        >
          {{ busy ? $t('views.marketplace.sources.adding') : $t('views.marketplace.sources.add') }}
        </BaseButton>
      </div>
    </div>

    <template #actions>
      <BaseButton variant="ghost" @click="onClose">
        {{ $t('common.close') }}
      </BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseModal, BaseButton } from '@autobot/ui'
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
/* #10882: overlay/header/footer chrome now provided by @autobot/ui BaseModal;
   only the body layout + form styling remain here. */
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
</style>
