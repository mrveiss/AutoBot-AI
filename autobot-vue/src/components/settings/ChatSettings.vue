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
.settings-section {
  margin-bottom: 30px;
  background: #ffffff;
  border: 1px solid #e1e5e9;
  border-radius: 8px;
  padding: 24px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.settings-section h3 {
  margin: 0 0 20px 0;
  color: #2c3e50;
  font-weight: 600;
  font-size: 18px;
  border-bottom: 2px solid #3498db;
  padding-bottom: 8px;
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 12px 0;
  border-bottom: 1px solid #f0f0f0;
}

.setting-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.setting-item label {
  font-weight: 500;
  color: #34495e;
  flex: 1;
  margin-right: 16px;
  cursor: pointer;
}

.setting-item input[type="checkbox"] {
  width: 20px;
  height: 20px;
  cursor: pointer;
  accent-color: #007acc;
}

.setting-item input[type="number"] {
  width: 100px;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  transition: border-color 0.2s ease;
}

.setting-item input[type="number"]:focus {
  outline: none;
  border-color: #007acc;
  box-shadow: 0 0 0 2px rgba(0, 122, 204, 0.2);
}

.setting-item input[type="number"]:invalid {
  border-color: #e74c3c;
  box-shadow: 0 0 0 2px rgba(231, 76, 60, 0.2);
}

/* Dark theme support */
@media (prefers-color-scheme: dark) {
  .settings-section {
    background: #2d2d2d;
    border-color: #404040;
  }

  .settings-section h3 {
    color: #ffffff;
    border-bottom-color: #4fc3f7;
  }

  .setting-item {
    border-bottom-color: #404040;
  }

  .setting-item label {
    color: #e0e0e0;
  }

  .setting-item input[type="number"] {
    background: #404040;
    border-color: #555;
    color: #ffffff;
  }

  .setting-item input[type="number"]:focus {
    border-color: #4fc3f7;
    box-shadow: 0 0 0 2px rgba(79, 195, 247, 0.2);
  }
}

/* Mobile responsive */
@media (max-width: 768px) {
  .settings-section {
    padding: 16px;
    margin-bottom: 20px;
  }

  .setting-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .setting-item label {
    margin-right: 0;
    margin-bottom: 4px;
  }

  .setting-item input[type="number"] {
    width: 100%;
  }
}
</style>