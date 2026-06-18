<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTranscriberApi, type Project } from '@/composables/transcriber/useTranscriberApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ProjectsView')

const router = useRouter()
const api = useTranscriberApi()

const projects = ref<Project[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

// Create-project form state.
const showCreate = ref(false)
const newName = ref('')
const newDescription = ref('')
const creating = ref(false)
const createError = ref<string | null>(null)

const canCreate = computed(() => newName.value.trim().length > 0 && !creating.value)

async function load() {
  loading.value = true
  error.value = null
  try {
    projects.value = await api.listProjects()
  } catch (err) {
    logger.error('Failed to load projects', err)
    error.value = 'Failed to load projects.'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  showCreate.value = true
  createError.value = null
}

function cancelCreate() {
  showCreate.value = false
  newName.value = ''
  newDescription.value = ''
  createError.value = null
}

async function submitCreate() {
  if (!canCreate.value) return
  creating.value = true
  createError.value = null
  try {
    const project = await api.createProject(newName.value.trim(), newDescription.value.trim())
    projects.value = [project, ...projects.value]
    cancelCreate()
  } catch (err) {
    logger.error('Failed to create project', err)
    createError.value = 'Failed to create project.'
  } finally {
    creating.value = false
  }
}

async function removeProject(project: Project) {
  if (!window.confirm(`Delete project "${project.name}"? This cannot be undone.`)) return
  try {
    await api.deleteProject(project.id)
    projects.value = projects.value.filter((p) => p.id !== project.id)
  } catch (err) {
    logger.error('Failed to delete project', err)
    error.value = 'Failed to delete project.'
  }
}

function openProject(project: Project) {
  router.push({ name: 'transcriber-project-detail', params: { projectId: project.id } })
}

function formatDate(value: string): string {
  if (!value) return ''
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString()
}

onMounted(load)
</script>

<template>
  <div class="projects-view">
    <header class="projects-header">
      <h1 class="projects-title">Transcription Projects</h1>
      <button v-if="!showCreate" class="btn-primary" type="button" @click="openCreate">
        New project
      </button>
    </header>

    <form v-if="showCreate" class="create-form" @submit.prevent="submitCreate">
      <div class="create-fields">
        <input
          v-model="newName"
          class="create-input"
          type="text"
          placeholder="Project name"
          aria-label="Project name"
        />
        <input
          v-model="newDescription"
          class="create-input"
          type="text"
          placeholder="Description (optional)"
          aria-label="Project description"
        />
      </div>
      <div class="create-actions">
        <button class="btn-primary" type="submit" :disabled="!canCreate">
          {{ creating ? 'Creating…' : 'Create' }}
        </button>
        <button class="btn-secondary" type="button" @click="cancelCreate">Cancel</button>
      </div>
      <p v-if="createError" class="projects-error">{{ createError }}</p>
    </form>

    <div v-if="loading" class="projects-state">Loading projects…</div>

    <div v-else-if="error" class="projects-state projects-error">{{ error }}</div>

    <div v-else-if="!projects.length" class="projects-state">
      No projects yet — create one to start transcribing.
    </div>

    <ul v-else class="projects-list">
      <li v-for="project in projects" :key="project.id" class="project-card">
        <button class="project-open" type="button" @click="openProject(project)">
          <span class="project-name">{{ project.name }}</span>
          <span v-if="project.description" class="project-description">{{ project.description }}</span>
          <span class="project-meta">Created {{ formatDate(project.created_at) }}</span>
        </button>
        <button
          class="btn-danger"
          type="button"
          :aria-label="`Delete ${project.name}`"
          @click="removeProject(project)"
        >
          Delete
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.projects-view {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1rem;
}

.projects-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.projects-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-text, #111827);
}

.create-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem;
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 0.5rem;
  background: var(--color-surface, #f9fafb);
}

.create-fields {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.create-input {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.375rem;
  background: var(--color-bg, #fff);
  color: var(--color-text, #111827);
}

.create-actions {
  display: flex;
  gap: 0.5rem;
}

.projects-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.project-card {
  display: flex;
  align-items: stretch;
  gap: 0.5rem;
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 0.5rem;
  background: var(--color-bg, #fff);
}

.project-open {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.75rem 1rem;
  text-align: left;
  background: transparent;
  border: none;
  cursor: pointer;
  color: inherit;
}

.project-open:hover {
  background: var(--color-surface, #f3f4f6);
}

.project-name {
  font-weight: 600;
  color: var(--color-text, #111827);
}

.project-description {
  font-size: 0.875rem;
  color: var(--color-text-secondary, #6b7280);
}

.project-meta {
  font-size: 0.75rem;
  color: var(--color-text-secondary, #9ca3af);
}

.projects-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 2rem;
  color: var(--color-text-secondary, #6b7280);
  text-align: center;
}

.projects-error {
  color: var(--color-danger-600, #dc2626);
}

.btn-primary,
.btn-secondary,
.btn-danger {
  padding: 0.5rem 0.875rem;
  border-radius: 0.375rem;
  border: 1px solid transparent;
  font-size: 0.875rem;
  cursor: pointer;
}

.btn-primary {
  background: var(--color-primary-600, #2563eb);
  color: #fff;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: transparent;
  border-color: var(--color-border, #d1d5db);
  color: var(--color-text, #111827);
}

.btn-danger {
  margin: 0.75rem;
  align-self: center;
  background: transparent;
  border-color: var(--color-danger-600, #dc2626);
  color: var(--color-danger-600, #dc2626);
}
</style>
