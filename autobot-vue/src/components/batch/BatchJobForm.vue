<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  Batch Job Form Component - Create new job modal/form
  Issue #584 - Batch Processing Manager
-->
<template>
  <div class="batch-job-form-overlay" @click.self="emit('close')">
    <div class="batch-job-form">
      <div class="form-header">
        <h3 class="form-title">
          <i class="fas fa-plus-circle"></i>
          Create Batch Job
        </h3>
        <button class="close-btn" @click="emit('close')" title="Close">
          <i class="fas fa-times"></i>
        </button>
      </div>

      <form @submit.prevent="handleSubmit">
        <!-- Job name -->
        <div class="form-group">
          <label class="form-label" for="job-name">Job Name *</label>
          <input
            id="job-name"
            v-model="formData.name"
            type="text"
            class="form-input"
            placeholder="Enter job name"
            required
          />
        </div>

        <!-- Job type -->
        <div class="form-group">
          <label class="form-label" for="job-type">Job Type *</label>
          <select
            id="job-type"
            v-model="formData.job_type"
            class="form-select"
            required
          >
            <option value="" disabled>Select job type</option>
            <option
              v-for="(label, type) in BATCH_TYPE_LABELS"
              :key="type"
              :value="type"
            >
              {{ label }}
            </option>
          </select>
        </div>

        <!-- Template selection (optional) -->
        <div class="form-group" v-if="templates.length > 0">
          <label class="form-label" for="template">Use Template (optional)</label>
          <select
            id="template"
            v-model="selectedTemplateId"
            class="form-select"
            @change="applyTemplate"
          >
            <option value="">No template</option>
            <option
              v-for="template in templates"
              :key="template.template_id"
              :value="template.template_id"
            >
              {{ template.name }}
            </option>
          </select>
        </div>

        <!-- Parameters (JSON editor) -->
        <div class="form-group">
          <label class="form-label" for="parameters">Parameters (JSON)</label>
          <textarea
            id="parameters"
            v-model="parametersJson"
            class="form-textarea"
            placeholder='{"key": "value"}'
            rows="5"
          ></textarea>
          <span class="form-hint" v-if="!jsonError">
            Enter parameters as valid JSON object
          </span>
          <span class="form-error" v-if="jsonError">
            {{ jsonError }}
          </span>
        </div>

        <!-- Form actions -->
        <div class="form-actions">
          <button
            type="button"
            class="btn btn-secondary"
            @click="emit('close')"
          >
            Cancel
          </button>
          <button
            type="submit"
            class="btn btn-primary"
            :disabled="!isValid || submitting"
          >
            <i class="fas fa-spinner fa-spin" v-if="submitting"></i>
            <i class="fas fa-play" v-else></i>
            Create Job
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { BatchTemplate, BatchJobType, CreateBatchJobRequest } from '@/types/batch-processing'
import { BATCH_TYPE_LABELS } from '@/types/batch-processing'

interface Props {
  templates?: BatchTemplate[]
}

const props = withDefaults(defineProps<Props>(), {
  templates: () => []
})

const emit = defineEmits<{
  close: []
  submit: [request: CreateBatchJobRequest]
}>()

const formData = ref<{
  name: string
  job_type: BatchJobType | ''
}>({
  name: '',
  job_type: ''
})

const selectedTemplateId = ref('')
const parametersJson = ref('{}')
const jsonError = ref('')
const submitting = ref(false)

// Validate JSON
watch(parametersJson, (value) => {
  try {
    JSON.parse(value)
    jsonError.value = ''
  } catch (e) {
    jsonError.value = 'Invalid JSON format'
  }
})

const isValid = computed(() => {
  return (
    formData.value.name.trim() !== '' &&
    formData.value.job_type !== '' &&
    jsonError.value === ''
  )
})

function applyTemplate() {
  if (!selectedTemplateId.value) {
    return
  }

  const template = props.templates.find(
    (t) => t.template_id === selectedTemplateId.value
  )

  if (template) {
    formData.value.job_type = template.job_type
    if (template.default_parameters) {
      parametersJson.value = JSON.stringify(template.default_parameters, null, 2)
    }
  }
}

async function handleSubmit() {
  if (!isValid.value) return

  submitting.value = true

  try {
    let parameters: Record<string, unknown> = {}
    try {
      parameters = JSON.parse(parametersJson.value)
    } catch {
      // Already validated, this shouldn't happen
    }

    const request: CreateBatchJobRequest = {
      name: formData.value.name.trim(),
      job_type: formData.value.job_type as BatchJobType,
      parameters,
      template_id: selectedTemplateId.value || undefined
    }

    emit('submit', request)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.batch-job-form-overlay {
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

.batch-job-form {
  background-color: white;
  border-radius: 0.5rem;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
  width: 100%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
}

.form-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid var(--blue-gray-200);
}

.form-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--blue-gray-800);
  margin: 0;
}

.form-title i {
  color: #2563eb;
}

.close-btn {
  padding: 0.5rem;
  background: none;
  border: none;
  color: var(--blue-gray-400);
  cursor: pointer;
  border-radius: 0.25rem;
}

.close-btn:hover {
  background-color: var(--blue-gray-100);
  color: var(--blue-gray-600);
}

form {
  padding: 1.5rem;
}

.form-group {
  margin-bottom: 1.25rem;
}

.form-label {
  display: block;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--blue-gray-700);
  margin-bottom: 0.375rem;
}

.form-input,
.form-select,
.form-textarea {
  width: 100%;
  padding: 0.625rem 0.875rem;
  font-size: 0.875rem;
  border: 1px solid var(--blue-gray-300);
  border-radius: 0.375rem;
  background-color: white;
  color: var(--blue-gray-700);
  transition: border-color 0.15s, box-shadow 0.15s;
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.form-select {
  appearance: none;
  background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e");
  background-position: right 0.5rem center;
  background-repeat: no-repeat;
  background-size: 1.5em 1.5em;
  padding-right: 2.5rem;
}

.form-textarea {
  font-family: monospace;
  resize: vertical;
  min-height: 100px;
}

.form-hint {
  display: block;
  font-size: 0.75rem;
  color: var(--blue-gray-500);
  margin-top: 0.375rem;
}

.form-error {
  display: block;
  font-size: 0.75rem;
  color: #dc2626;
  margin-top: 0.375rem;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding-top: 1rem;
  border-top: 1px solid var(--blue-gray-200);
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.625rem 1.25rem;
  font-size: 0.875rem;
  font-weight: 500;
  border-radius: 0.375rem;
  cursor: pointer;
  transition: all 0.15s;
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

.btn-secondary:hover:not(:disabled) {
  background-color: var(--blue-gray-50);
}

.btn-primary {
  background-color: #2563eb;
  color: white;
  border: 1px solid #2563eb;
}

.btn-primary:hover:not(:disabled) {
  background-color: #1d4ed8;
}

/* Responsive */
@media (max-width: 640px) {
  .batch-job-form {
    margin: 0.5rem;
  }

  .form-actions {
    flex-direction: column-reverse;
  }

  .btn {
    width: 100%;
    justify-content: center;
  }
}
</style>
