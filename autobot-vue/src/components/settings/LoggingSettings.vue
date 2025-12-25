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

.setting-item input,
.setting-item select {
  min-width: 150px;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  transition: border-color 0.2s ease;
}

.setting-item input[type="checkbox"] {
  min-width: auto;
  width: 20px;
  height: 20px;
  cursor: pointer;
  accent-color: #007acc;
}

.setting-item input:focus,
.setting-item select:focus {
  outline: none;
  border-color: #007acc;
  box-shadow: 0 0 0 2px rgba(0, 122, 204, 0.2);
}

.setting-item input:invalid {
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

  .setting-item input,
  .setting-item select {
    background: #404040;
    border-color: #555;
    color: #ffffff;
  }

  .setting-item input:focus,
  .setting-item select:focus {
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

  .setting-item input,
  .setting-item select {
    min-width: auto;
    width: 100%;
  }
}
</style>