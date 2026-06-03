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
          <label class="setting-label">
            {{ $t('chat.settings.contextOverflowLabel') }}
          </label>
          <p class="setting-description">
            {{ $t('chat.settings.contextOverflowDescription') }}
          </p>
          <select
            v-model="localMode"
            @change="updateMode"
            class="setting-select"
          >
            <option value="auto">{{ $t('chat.settings.contextOverflowAuto') }}</option>
            <option value="warn">{{ $t('chat.settings.contextOverflowWarn') }}</option>
            <option value="disabled">{{ $t('chat.settings.contextOverflowDisabled') }}</option>
          </select>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import Icon from '@/components/ui/Icon.vue'
import { usePreferences } from '@/composables/usePreferences'

interface Props {
  show: boolean
}

interface Emits {
  (e: 'close'): void
}

const props = defineProps<Props>()
defineEmits<Emits>()

const { contextOverflowMode, setContextOverflowMode } = usePreferences()
const localMode = ref(contextOverflowMode.value)

watch(() => props.show, (isShown) => {
  if (isShown) {
    localMode.value = contextOverflowMode.value
  }
})

function updateMode() {
  setContextOverflowMode(localMode.value)
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
  overflow: auto;
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
</style>
