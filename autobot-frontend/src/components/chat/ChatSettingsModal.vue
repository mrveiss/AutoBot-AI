<template>
  <div v-if="show" class="settings-modal-overlay" @click="$emit('close')">
    <div class="settings-modal" @click.stop>
      <div class="settings-header">
        <h3>{{ $t('chat.settings.title') }}</h3>
        <button @click="$emit('close')" class="close-btn" :aria-label="$t('common.close')">
          <Icon name="times" />
        </button>
      </div>

      <div class="settings-body">
        <!-- Context Overflow Protection Setting -->
        <div class="setting-group">
          <label class="setting-label" for="context-overflow-select">
            {{ $t('chat.settings.contextOverflowLabel') }}
          </label>
          <p class="setting-description">
            {{ $t('chat.settings.contextOverflowDescription') }}
          </p>
          <select
            id="context-overflow-select"
            v-model="localMode"
            @change="updateMode"
            class="setting-select"
          >
            <option value="auto">{{ $t('chat.settings.contextOverflowAuto') }}</option>
            <option value="warn">{{ $t('chat.settings.contextOverflowWarn') }}</option>
            <option value="disabled">{{ $t('chat.settings.contextOverflowDisabled') }}</option>
          </select>
        </div>

        <!-- Reasoning Effort Setting (#9460/#9471) -->
        <div class="setting-group">
          <label class="setting-label" for="reasoning-effort-select">
            {{ $t('chat.settings.reasoningEffortLabel') }}
          </label>
          <p class="setting-description">
            {{ $t('chat.settings.reasoningEffortDescription') }}
          </p>
          <select
            id="reasoning-effort-select"
            v-model="localEffort"
            @change="updateEffort"
            class="setting-select"
          >
            <option value="auto">{{ $t('chat.settings.reasoningEffortAuto') }}</option>
            <option value="low">{{ $t('chat.settings.reasoningEffortLow') }}</option>
            <option value="medium">{{ $t('chat.settings.reasoningEffortMedium') }}</option>
            <option value="high">{{ $t('chat.settings.reasoningEffortHigh') }}</option>
          </select>
        </div>

        <!-- TASK 10: Message Display toggles (moved here from the chat sidebar) -->
        <div class="setting-group">
          <label class="setting-label">{{ $t('chat.sidebar.messageDisplay') }}</label>
          <div class="display-toggles">
            <label
              v-for="setting in displaySettingsConfig"
              :key="setting.key"
              class="display-toggle"
            >
              <input
                type="checkbox"
                :checked="getSetting(setting.key)"
                @change="setSetting(setting.key, ($event.target as HTMLInputElement).checked)"
              />
              <span>{{ setting.label }}</span>
            </label>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '@/components/ui/Icon.vue'
import { usePreferences } from '@/composables/usePreferences'
import { useDisplaySettings, type DisplaySettings } from '@/composables/useDisplaySettings'

interface Props {
  show: boolean
}

interface Emits {
  (e: 'close'): void
}

const props = defineProps<Props>()
defineEmits<Emits>()

const { t } = useI18n()
const { contextOverflowMode, setContextOverflowMode, reasoningEffort, setReasoningEffort } = usePreferences()

// TASK 10: Message Display settings, relocated from the chat sidebar. Uses the
// shared useDisplaySettings singleton, so toggles stay in sync with rendering.
const { getSetting, setSetting } = useDisplaySettings()
const displaySettingsConfig = computed<{ key: keyof DisplaySettings; label: string }[]>(() => [
  { key: 'showThoughts', label: t('chat.sidebar.showThoughts') },
  { key: 'showJson', label: t('chat.sidebar.showMetadata') },
  { key: 'showUtility', label: t('chat.sidebar.showUtility') },
  { key: 'showPlanning', label: t('chat.sidebar.showPlanning') },
  { key: 'showDebug', label: t('chat.sidebar.showDebug') },
  { key: 'showSources', label: t('chat.sidebar.showSources') },
  { key: 'autoScroll', label: t('chat.sidebar.autoScroll') },
])
const localMode = ref(contextOverflowMode.value)
const localEffort = ref(reasoningEffort.value)

watch(() => props.show, (isShown) => {
  if (isShown) {
    localMode.value = contextOverflowMode.value
    localEffort.value = reasoningEffort.value
  }
})

function updateMode() {
  setContextOverflowMode(localMode.value)
}

function updateEffort() {
  setReasoningEffort(localEffort.value)
}
</script>

<style scoped>
.settings-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.settings-modal {
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl);
  width: 90%;
  max-width: 500px;
  max-height: 80vh;
  /* #10750 C2: keep header fixed; scroll only the body (below) */
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.settings-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border-color);
}

.settings-header h3 {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 0.5rem;
  border-radius: var(--radius-md);
  transition: all 0.2s;
}

.close-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.settings-body {
  padding: 1.5rem;
  /* #10750 C2: this is the single scroll region */
  overflow-y: auto;
  min-height: 0;
}

.setting-group {
  margin-bottom: 1.5rem;
}

.setting-group:last-child {
  margin-bottom: 0;
}

.setting-label {
  display: block;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.setting-description {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin-bottom: 0.75rem;
}

.setting-select {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
}

.setting-select:hover {
  border-color: var(--color-primary);
}

.setting-select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

/* TASK 10: Message Display toggle list */
.display-toggles {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.display-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.display-toggle input {
  cursor: pointer;
}
</style>
