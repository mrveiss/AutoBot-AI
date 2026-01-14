<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  Batch Scheduler Component - Schedule management
  Issue #584 - Batch Processing Manager
-->
<template>
  <div class="batch-scheduler">
    <div class="scheduler-header">
      <h3 class="scheduler-title">
        <i class="fas fa-calendar-alt"></i>
        Scheduled Jobs
      </h3>
      <button
        class="add-schedule-btn"
        @click="showForm = true"
        :disabled="templates.length === 0"
        :title="templates.length === 0 ? 'Create a template first' : 'New Schedule'"
      >
        <i class="fas fa-plus"></i>
        New Schedule
      </button>
    </div>

    <!-- Loading state -->
    <div class="loading-state" v-if="loading">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Loading schedules...</span>
    </div>

    <!-- Empty state -->
    <div class="empty-state" v-if="!loading && schedules.length === 0">
      <i class="fas fa-calendar-alt empty-icon"></i>
      <p class="empty-text">
        {{ templates.length === 0
          ? 'Create a template first to set up scheduled jobs.'
          : 'No schedules yet. Create a schedule to run jobs automatically.'
        }}
      </p>
    </div>

    <!-- Schedules list -->
    <div class="schedules-list" v-if="!loading && schedules.length > 0">
      <div
        v-for="schedule in schedules"
        :key="schedule.schedule_id"
        class="schedule-card"
        :class="{ 'schedule-disabled': !schedule.enabled }"
      >
        <div class="schedule-info">
          <div class="schedule-header">
            <span class="schedule-name">{{ schedule.name }}</span>
            <span class="schedule-status" :class="schedule.enabled ? 'status-active' : 'status-inactive'">
              {{ schedule.enabled ? 'Active' : 'Inactive' }}
            </span>
          </div>
          <div class="schedule-details">
            <span class="schedule-cron" title="Cron expression">
              <i class="fas fa-clock"></i>
              {{ schedule.cron_expression }}
            </span>
            <span class="schedule-template">
              <i class="fas fa-file-code"></i>
              {{ getTemplateName(schedule.template_id) }}
            </span>
          </div>
          <div class="schedule-timing">
            <span v-if="schedule.last_run" class="timing-item">
              Last: {{ formatRelativeTime(schedule.last_run) }}
            </span>
            <span v-if="schedule.next_run" class="timing-item">
              Next: {{ formatRelativeTime(schedule.next_run) }}
            </span>
          </div>
        </div>
        <div class="schedule-actions">
          <label class="toggle-switch" :title="schedule.enabled ? 'Disable' : 'Enable'">
            <input
              type="checkbox"
              :checked="schedule.enabled"
              @change="handleToggle(schedule.schedule_id, !schedule.enabled)"
            />
            <span class="toggle-slider"></span>
          </label>
          <button
            class="action-btn delete-btn"
            @click="handleDelete(schedule.schedule_id)"
            title="Delete schedule"
          >
            <i class="fas fa-trash"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Create schedule form modal -->
    <div class="form-overlay" v-if="showForm" @click.self="showForm = false">
      <div class="schedule-form">
        <div class="form-header">
          <h4 class="form-title">Create Schedule</h4>
          <button class="close-btn" @click="showForm = false">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <form @submit.prevent="handleSubmit">
          <div class="form-group">
            <label class="form-label" for="schedule-name">Name *</label>
            <input
              id="schedule-name"
              v-model="formData.name"
              type="text"
              class="form-input"
              placeholder="Schedule name"
              required
            />
          </div>

          <div class="form-group">
            <label class="form-label" for="schedule-template">Template *</label>
            <select
              id="schedule-template"
              v-model="formData.template_id"
              class="form-select"
              required
            >
              <option value="" disabled>Select template</option>
              <option
                v-for="template in templates"
                :key="template.template_id"
                :value="template.template_id"
              >
                {{ template.name }} ({{ BATCH_TYPE_LABELS[template.job_type] }})
              </option>
            </select>
          </div>

          <div class="form-group">
            <label class="form-label" for="schedule-cron">Cron Expression *</label>
            <input
              id="schedule-cron"
              v-model="formData.cron_expression"
              type="text"
              class="form-input code"
              placeholder="0 * * * *"
              required
            />
            <span class="form-hint">
              Format: minute hour day month weekday (e.g., "0 */6 * * *" = every 6 hours)
            </span>
          </div>

          <div class="form-group">
            <label class="toggle-label">
              <input type="checkbox" v-model="formData.enabled" />
              <span>Enable immediately</span>
            </label>
          </div>

          <!-- Common cron presets -->
          <div class="cron-presets">
            <span class="presets-label">Quick presets:</span>
            <button type="button" class="preset-btn" @click="setCron('0 * * * *')">Hourly</button>
            <button type="button" class="preset-btn" @click="setCron('0 */6 * * *')">Every 6h</button>
            <button type="button" class="preset-btn" @click="setCron('0 0 * * *')">Daily</button>
            <button type="button" class="preset-btn" @click="setCron('0 0 * * 0')">Weekly</button>
          </div>

          <div class="form-actions">
            <button type="button" class="btn btn-secondary" @click="showForm = false">
              Cancel
            </button>
            <button type="submit" class="btn btn-primary" :disabled="!isValid || submitting">
              <i class="fas fa-spinner fa-spin" v-if="submitting"></i>
              Create Schedule
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { BatchSchedule, BatchTemplate, CreateBatchScheduleRequest } from '@/types/batch-processing'
import { BATCH_TYPE_LABELS, formatRelativeTime } from '@/types/batch-processing'

interface Props {
  schedules: BatchSchedule[]
  templates: BatchTemplate[]
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false
})

const emit = defineEmits<{
  create: [request: CreateBatchScheduleRequest]
  toggle: [scheduleId: string, enabled: boolean]
  delete: [scheduleId: string]
}>()

const showForm = ref(false)
const submitting = ref(false)

const formData = ref<{
  name: string
  template_id: string
  cron_expression: string
  enabled: boolean
}>({
  name: '',
  template_id: '',
  cron_expression: '',
  enabled: true
})

const isValid = computed(() => {
  return (
    formData.value.name.trim() !== '' &&
    formData.value.template_id !== '' &&
    formData.value.cron_expression.trim() !== ''
  )
})

function getTemplateName(templateId: string): string {
  const template = props.templates.find((t) => t.template_id === templateId)
  return template?.name || 'Unknown'
}

function setCron(expression: string) {
  formData.value.cron_expression = expression
}

function resetForm() {
  formData.value = {
    name: '',
    template_id: '',
    cron_expression: '',
    enabled: true
  }
}

async function handleSubmit() {
  if (!isValid.value) return

  submitting.value = true

  try {
    const request: CreateBatchScheduleRequest = {
      name: formData.value.name.trim(),
      template_id: formData.value.template_id,
      cron_expression: formData.value.cron_expression.trim(),
      enabled: formData.value.enabled
    }

    emit('create', request)
    showForm.value = false
    resetForm()
  } finally {
    submitting.value = false
  }
}

function handleToggle(scheduleId: string, enabled: boolean) {
  emit('toggle', scheduleId, enabled)
}

function handleDelete(scheduleId: string) {
  if (confirm('Are you sure you want to delete this schedule?')) {
    emit('delete', scheduleId)
  }
}
</script>

<style scoped>
.batch-scheduler {
  background-color: white;
  border: 1px solid var(--blue-gray-200);
  border-radius: 0.5rem;
  padding: 1.25rem;
}

.scheduler-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.scheduler-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1rem;
  font-weight: 600;
  color: var(--blue-gray-800);
  margin: 0;
}

.scheduler-title i {
  color: #2563eb;
}

.add-schedule-btn {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 0.875rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: #2563eb;
  background-color: #dbeafe;
  border: none;
  border-radius: 0.375rem;
  cursor: pointer;
  transition: background-color 0.15s;
}

.add-schedule-btn:hover:not(:disabled) {
  background-color: #bfdbfe;
}

.add-schedule-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 1.5rem;
  color: var(--blue-gray-500);
  font-size: 0.875rem;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 1.5rem;
  text-align: center;
}

.empty-icon {
  font-size: 2rem;
  color: var(--blue-gray-300);
  margin-bottom: 0.5rem;
}

.empty-text {
  font-size: 0.875rem;
  color: var(--blue-gray-500);
  margin: 0;
}

.schedules-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.schedule-card {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 0.875rem;
  background-color: var(--blue-gray-50);
  border-radius: 0.375rem;
  border: 1px solid var(--blue-gray-100);
}

.schedule-disabled {
  opacity: 0.6;
}

.schedule-info {
  flex: 1;
}

.schedule-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.375rem;
}

.schedule-name {
  font-weight: 500;
  color: var(--blue-gray-800);
}

.schedule-status {
  font-size: 0.625rem;
  font-weight: 600;
  text-transform: uppercase;
  padding: 0.125rem 0.375rem;
  border-radius: 9999px;
}

.status-active {
  background-color: #dcfce7;
  color: #16a34a;
}

.status-inactive {
  background-color: var(--blue-gray-200);
  color: var(--blue-gray-600);
}

.schedule-details {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  font-size: 0.75rem;
  color: var(--blue-gray-600);
  margin-bottom: 0.25rem;
}

.schedule-cron,
.schedule-template {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.schedule-cron {
  font-family: monospace;
}

.schedule-timing {
  display: flex;
  gap: 0.75rem;
  font-size: 0.75rem;
}

.timing-item {
  color: var(--blue-gray-400);
}

.schedule-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

/* Toggle switch */
.toggle-switch {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
  cursor: pointer;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: var(--blue-gray-300);
  border-radius: 20px;
  transition: 0.3s;
}

.toggle-slider:before {
  position: absolute;
  content: "";
  height: 14px;
  width: 14px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  border-radius: 50%;
  transition: 0.3s;
}

.toggle-switch input:checked + .toggle-slider {
  background-color: #2563eb;
}

.toggle-switch input:checked + .toggle-slider:before {
  transform: translateX(16px);
}

.action-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 0.25rem;
  cursor: pointer;
  transition: opacity 0.15s;
}

.delete-btn {
  background-color: #fee2e2;
  color: #dc2626;
}

.delete-btn:hover {
  opacity: 0.8;
}

/* Form modal */
.form-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
}

.schedule-form {
  background-color: white;
  border-radius: 0.5rem;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
  width: 100%;
  max-width: 450px;
}

.form-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--blue-gray-200);
}

.form-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--blue-gray-800);
  margin: 0;
}

.close-btn {
  padding: 0.375rem;
  background: none;
  border: none;
  color: var(--blue-gray-400);
  cursor: pointer;
  border-radius: 0.25rem;
}

.close-btn:hover {
  background-color: var(--blue-gray-100);
}

form {
  padding: 1.25rem;
}

.form-group {
  margin-bottom: 1rem;
}

.form-label {
  display: block;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--blue-gray-700);
  margin-bottom: 0.25rem;
}

.form-input,
.form-select {
  width: 100%;
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  border: 1px solid var(--blue-gray-300);
  border-radius: 0.375rem;
  background-color: white;
  color: var(--blue-gray-700);
}

.form-input.code {
  font-family: monospace;
}

.form-input:focus,
.form-select:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.1);
}

.form-select {
  appearance: none;
  background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e");
  background-position: right 0.5rem center;
  background-repeat: no-repeat;
  background-size: 1.25em 1.25em;
  padding-right: 2rem;
}

.form-hint {
  display: block;
  font-size: 0.75rem;
  color: var(--blue-gray-500);
  margin-top: 0.25rem;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: var(--blue-gray-700);
  cursor: pointer;
}

.toggle-label input {
  width: 16px;
  height: 16px;
}

.cron-presets {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.presets-label {
  font-size: 0.75rem;
  color: var(--blue-gray-500);
}

.preset-btn {
  padding: 0.25rem 0.5rem;
  font-size: 0.75rem;
  background-color: var(--blue-gray-100);
  color: var(--blue-gray-600);
  border: none;
  border-radius: 0.25rem;
  cursor: pointer;
}

.preset-btn:hover {
  background-color: var(--blue-gray-200);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 1.25rem;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  font-weight: 500;
  border-radius: 0.375rem;
  cursor: pointer;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background-color: white;
  color: var(--blue-gray-700);
  border: 1px solid var(--blue-gray-300);
}

.btn-primary {
  background-color: #2563eb;
  color: white;
  border: 1px solid #2563eb;
}

.btn-primary:hover:not(:disabled) {
  background-color: #1d4ed8;
}
</style>
