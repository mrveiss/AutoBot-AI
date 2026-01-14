<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  Batch Templates Component - Template management section
  Issue #584 - Batch Processing Manager
-->
<template>
  <div class="batch-templates">
    <div class="templates-header">
      <h3 class="templates-title">
        <i class="fas fa-file-code"></i>
        Job Templates
      </h3>
      <button class="add-template-btn" @click="showForm = true">
        <i class="fas fa-plus"></i>
        New Template
      </button>
    </div>

    <!-- Loading state -->
    <div class="loading-state" v-if="loading">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Loading templates...</span>
    </div>

    <!-- Empty state -->
    <div class="empty-state" v-if="!loading && templates.length === 0">
      <i class="fas fa-file-code empty-icon"></i>
      <p class="empty-text">No templates yet. Create a template to save job configurations.</p>
    </div>

    <!-- Templates list -->
    <div class="templates-list" v-if="!loading && templates.length > 0">
      <div
        v-for="template in templates"
        :key="template.template_id"
        class="template-card"
      >
        <div class="template-info">
          <div class="template-header">
            <i :class="BATCH_TYPE_ICONS[template.job_type]" class="template-type-icon"></i>
            <span class="template-name">{{ template.name }}</span>
          </div>
          <p class="template-description" v-if="template.description">
            {{ template.description }}
          </p>
          <div class="template-meta">
            <span class="template-type">{{ BATCH_TYPE_LABELS[template.job_type] }}</span>
            <span class="template-date">{{ formatRelativeTime(template.created_at) }}</span>
          </div>
        </div>
        <div class="template-actions">
          <button
            class="action-btn delete-btn"
            @click="handleDelete(template.template_id)"
            title="Delete template"
          >
            <i class="fas fa-trash"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Create template form modal -->
    <div class="form-overlay" v-if="showForm" @click.self="showForm = false">
      <div class="template-form">
        <div class="form-header">
          <h4 class="form-title">Create Template</h4>
          <button class="close-btn" @click="showForm = false">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <form @submit.prevent="handleSubmit">
          <div class="form-group">
            <label class="form-label" for="template-name">Name *</label>
            <input
              id="template-name"
              v-model="formData.name"
              type="text"
              class="form-input"
              placeholder="Template name"
              required
            />
          </div>

          <div class="form-group">
            <label class="form-label" for="template-description">Description</label>
            <textarea
              id="template-description"
              v-model="formData.description"
              class="form-textarea"
              placeholder="Optional description"
              rows="2"
            ></textarea>
          </div>

          <div class="form-group">
            <label class="form-label" for="template-type">Job Type *</label>
            <select
              id="template-type"
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

          <div class="form-group">
            <label class="form-label" for="template-params">Default Parameters</label>
            <textarea
              id="template-params"
              v-model="paramsJson"
              class="form-textarea code"
              placeholder='{"key": "value"}'
              rows="4"
            ></textarea>
          </div>

          <div class="form-actions">
            <button type="button" class="btn btn-secondary" @click="showForm = false">
              Cancel
            </button>
            <button type="submit" class="btn btn-primary" :disabled="!isValid || submitting">
              <i class="fas fa-spinner fa-spin" v-if="submitting"></i>
              Create Template
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { BatchTemplate, BatchJobType, CreateBatchTemplateRequest } from '@/types/batch-processing'
import { BATCH_TYPE_LABELS, BATCH_TYPE_ICONS, formatRelativeTime } from '@/types/batch-processing'

interface Props {
  templates: BatchTemplate[]
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false
})

const emit = defineEmits<{
  create: [request: CreateBatchTemplateRequest]
  delete: [templateId: string]
}>()

const showForm = ref(false)
const submitting = ref(false)

const formData = ref<{
  name: string
  description: string
  job_type: BatchJobType | ''
}>({
  name: '',
  description: '',
  job_type: ''
})

const paramsJson = ref('{}')
const jsonError = ref('')

watch(paramsJson, (value) => {
  try {
    JSON.parse(value)
    jsonError.value = ''
  } catch {
    jsonError.value = 'Invalid JSON'
  }
})

const isValid = computed(() => {
  return (
    formData.value.name.trim() !== '' &&
    formData.value.job_type !== '' &&
    jsonError.value === ''
  )
})

function resetForm() {
  formData.value = { name: '', description: '', job_type: '' }
  paramsJson.value = '{}'
}

async function handleSubmit() {
  if (!isValid.value) return

  submitting.value = true

  try {
    let defaultParameters: Record<string, unknown> = {}
    try {
      defaultParameters = JSON.parse(paramsJson.value)
    } catch {
      // Already validated
    }

    const request: CreateBatchTemplateRequest = {
      name: formData.value.name.trim(),
      description: formData.value.description.trim() || undefined,
      job_type: formData.value.job_type as BatchJobType,
      default_parameters: defaultParameters
    }

    emit('create', request)
    showForm.value = false
    resetForm()
  } finally {
    submitting.value = false
  }
}

function handleDelete(templateId: string) {
  if (confirm('Are you sure you want to delete this template?')) {
    emit('delete', templateId)
  }
}
</script>

<style scoped>
.batch-templates {
  background-color: white;
  border: 1px solid var(--blue-gray-200);
  border-radius: 0.5rem;
  padding: 1.25rem;
}

.templates-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.templates-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1rem;
  font-weight: 600;
  color: var(--blue-gray-800);
  margin: 0;
}

.templates-title i {
  color: #2563eb;
}

.add-template-btn {
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

.add-template-btn:hover {
  background-color: #bfdbfe;
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

.templates-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.template-card {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 0.875rem;
  background-color: var(--blue-gray-50);
  border-radius: 0.375rem;
  border: 1px solid var(--blue-gray-100);
}

.template-info {
  flex: 1;
}

.template-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
}

.template-type-icon {
  font-size: 0.875rem;
  color: var(--blue-gray-500);
}

.template-name {
  font-weight: 500;
  color: var(--blue-gray-800);
}

.template-description {
  font-size: 0.75rem;
  color: var(--blue-gray-500);
  margin: 0 0 0.5rem 0;
}

.template-meta {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.75rem;
}

.template-type {
  color: #2563eb;
}

.template-date {
  color: var(--blue-gray-400);
}

.template-actions {
  display: flex;
  gap: 0.25rem;
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

.template-form {
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
.form-select,
.form-textarea {
  width: 100%;
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  border: 1px solid var(--blue-gray-300);
  border-radius: 0.375rem;
  background-color: white;
  color: var(--blue-gray-700);
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
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

.form-textarea.code {
  font-family: monospace;
  font-size: 0.75rem;
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
