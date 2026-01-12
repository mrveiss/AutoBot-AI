<template>
  <div v-if="loggingSettings && isSettingsLoaded" class="settings-section">
    <h3>Logging Settings</h3>
    <div class="setting-item">
      <label for="log-level">Log Level</label>
      <select
        id="log-level"
        :value="loggingSettings.level"
        @change="handleSelectChange('level', $event)"
      >
        <option
          v-for="level in loggingSettings.log_levels || []"
          :key="level"
          :value="level"
        >
          {{ level.toUpperCase() }}
        </option>
      </select>
    </div>
    <div class="setting-item">
      <label for="console-logging">Console Logging</label>
      <input
        id="console-logging"
        type="checkbox"
        :checked="loggingSettings.console"
        @change="handleCheckboxChange('console', $event)"
      />
    </div>
    <div class="setting-item">
      <label for="file-logging">File Logging</label>
      <input
        id="file-logging"
        type="checkbox"
        :checked="loggingSettings.file"
        @change="handleCheckboxChange('file', $event)"
      />
    </div>
    <div class="setting-item">
      <label for="max-file-size">Max Log File Size (MB)</label>
      <input
        id="max-file-size"
        type="number"
        :value="loggingSettings.max_file_size"
        min="1"
        max="100"
        @input="handleNumberInputChange('max_file_size', $event)"
      />
    </div>
    <div class="setting-item">
      <label for="log-requests">Enable Request Logging</label>
      <input
        id="log-requests"
        type="checkbox"
        :checked="loggingSettings.log_requests"
        @change="handleCheckboxChange('log_requests', $event)"
      />
    </div>
    <div class="setting-item">
      <label for="log-sql">Enable SQL Logging</label>
      <input
        id="log-sql"
        type="checkbox"
        :checked="loggingSettings.log_sql"
        @change="handleCheckboxChange('log_sql', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
interface LoggingSettings {
  level: string
  log_levels: string[]
  console: boolean
  file: boolean
  max_file_size: number
  log_requests: boolean
  log_sql: boolean
}

interface Props {
  loggingSettings: LoggingSettings | null
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

// Issue #594 Fix: Event handlers that work correctly with Vue template syntax
const handleSelectChange = (key: string, event: Event) => {
  const target = event.target as HTMLSelectElement
  updateSetting(key, target.value)
}

const handleCheckboxChange = (key: string, event: Event) => {
  const target = event.target as HTMLInputElement
  updateSetting(key, target.checked)
}

const handleNumberInputChange = (key: string, event: Event) => {
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

.setting-item input,
.setting-item select {
  min-width: 150px;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  transition: border-color var(--duration-200) var(--ease-in-out);
}

.setting-item input[type="checkbox"] {
  min-width: auto;
  width: 20px;
  height: 20px;
  cursor: pointer;
  accent-color: var(--color-primary);
}

.setting-item input:focus,
.setting-item select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--ring-primary);
}

.setting-item input:invalid {
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

  .setting-item input,
  .setting-item select {
    min-width: auto;
    width: 100%;
  }
}
</style>