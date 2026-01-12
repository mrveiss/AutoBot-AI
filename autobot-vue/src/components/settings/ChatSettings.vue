<template>
  <div v-if="chatSettings && isSettingsLoaded" class="settings-section">
    <h3>Chat Settings</h3>
    <div class="setting-item">
      <label for="auto-scroll">Auto Scroll to Bottom</label>
      <input
        id="auto-scroll"
        type="checkbox"
        :checked="chatSettings.auto_scroll"
        @change="handleCheckboxChange('auto_scroll')"
      />
    </div>
    <div class="setting-item">
      <label for="max-messages">Max Messages</label>
      <input
        id="max-messages"
        type="number"
        :value="chatSettings.max_messages"
        min="10"
        max="1000"
        @input="handleNumberInputChange('max_messages')"
      />
    </div>
    <div class="setting-item">
      <label for="message-retention">Message Retention (Days)</label>
      <input
        id="message-retention"
        type="number"
        :value="chatSettings.message_retention_days"
        min="1"
        max="365"
        @input="handleNumberInputChange('message_retention_days')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
interface ChatSettings {
  auto_scroll: boolean
  max_messages: number
  message_retention_days: number
}

interface Props {
  chatSettings: ChatSettings | null
  isSettingsLoaded: boolean
}

interface Emits {
  (e: 'setting-changed', key: string, value: any): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const updateSetting = (key: string, value: any) => {
  emit('setting-changed', key, value)
}

// Issue #156 Fix: Typed event handlers to replace inline $event.target usage
const handleCheckboxChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateSetting(key, target.checked)
}

const handleNumberInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateSetting(key, parseInt(target.value))
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.settings-section {
  margin-bottom: var(--spacing-8);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-6);
  box-shadow: var(--shadow-sm);
}

.settings-section h3 {
  margin: 0 0 var(--spacing-5) 0;
  color: var(--text-primary);
  font-weight: var(--font-semibold);
  font-size: var(--text-lg);
  border-bottom: 2px solid var(--color-primary);
  padding-bottom: var(--spacing-2);
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-4);
  padding: var(--spacing-3) 0;
  border-bottom: 1px solid var(--border-subtle);
}

.setting-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.setting-item label {
  font-weight: var(--font-medium);
  color: var(--text-primary);
  flex: 1;
  margin-right: var(--spacing-4);
  cursor: pointer;
}

.setting-item input[type="checkbox"] {
  width: 20px;
  height: 20px;
  cursor: pointer;
  accent-color: var(--color-primary);
}

.setting-item input[type="number"] {
  width: 100px;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  transition: border-color var(--duration-200) var(--ease-in-out);
}

.setting-item input[type="number"]:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--ring-primary);
}

.setting-item input[type="number"]:invalid {
  border-color: var(--color-error);
  box-shadow: var(--ring-error);
}

/* Mobile responsive */
@media (max-width: 768px) {
  .settings-section {
    padding: var(--spacing-4);
    margin-bottom: var(--spacing-5);
  }

  .setting-item {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-2);
  }

  .setting-item label {
    margin-right: 0;
    margin-bottom: var(--spacing-1);
  }

  .setting-item input[type="number"] {
    width: 100%;
  }
}
</style>