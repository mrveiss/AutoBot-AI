<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTranscriberApi, type Project } from '@/composables/transcriber/useTranscriberApi'
import { useTranscriberStore } from '@/stores/transcriber/useTranscriberStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('TranscriberProjectsView')

const router = useRouter()
const api = useTranscriberApi()
const store = useTranscriberStore()

const projects = ref<Project[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

// New-project form state.
const creating = ref(false)
const newName = ref('')
const newDescription = ref('')
const saving = ref(false)
const formError = ref<string | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    const list = await api.listProjects()
    projects.value = list
    store.setProjects(list)
  } catch (err) {
    logger.error('Failed to load projects', err)
    error.value = 'Failed to load projects.'
  } finally {
    loading.value = false
  }
}

async function createProject() {
  const name = newName.value.trim()
  if (!name) {
    formError.value = 'Project name is required.'
    return
  }
  saving.value = true
  formError.value = null
  try {
    const project = await api.createProject(name, newDescription.value.trim())
    newName.value = ''
    newDescription.value = ''
    creating.value = false
    await load()
    openProject(project.id)
  } catch (err) {
    logger.error('Failed to create project', err)
    formError.value = 'Failed to create project.'
  } finally {
    saving.value = false
  }
}

async function deleteProject(project: Project) {
  if (!window.confirm(`Delete project "${project.name}" and all its recordings?`)) return
  try {
    await api.deleteProject(project.id)
    await load()
  } catch (err) {
    logger.error('Failed to delete project', err)
    error.value = 'Failed to delete project.'
  }
}

function openProject(projectId: number) {
  router.push({ name: 'transcriber-project-detail', params: { projectId: String(projectId) } })
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString()
}

onMounted(load)
</script>

<template>
  <div class="projects-view">
    <header class="projects-header">
      <h1 class="projects-title">Transcriber projects</h1>
      <button type="button" class="btn btn-primary" @click="creating = !creating">
        {{ creating ? 'Cancel' : 'New project' }}
      </button>
    </header>

    <form v-if="creating" class="project-form" @submit.prevent="createProject">
      <label class="project-form-field">
        <span>Name</span>
        <input
          v-model="newName"
          type="text"
          maxlength="120"
          placeholder="e.g. Q3 customer interviews"
        />
      </label>
      <label class="project-form-field">
        <span>Description <em>(optional)</em></span>
        <input
          v-model="newDescription"
          type="text"
          maxlength="500"
          placeholder="Short description"
        />
      </label>
      <p v-if="formError" class="project-form-error">{{ formError }}</p>
      <div class="project-form-actions">
        <button type="submit" class="btn btn-primary" :disabled="saving">
          {{ saving ? 'Creating…' : 'Create project' }}
        </button>
      </div>
    </form>

    <div v-if="loading" class="projects-state">Loading projects…</div>

    <div v-else-if="error" class="projects-state projects-error">
      <p>{{ error }}</p>
      <button type="button" class="btn btn-sm" @click="load">Retry</button>
    </div>

    <div v-else-if="!projects.length" class="projects-state">
      <p>No projects yet.</p>
      <p>Create a project to upload audio or video and get a diarized transcript.</p>
    </div>

    <ul v-else class="projects-list">
      <li v-for="project in projects" :key="project.id" class="project-card">
        <button type="button" class="project-card-main" @click="openProject(project.id)">
          <span class="project-card-name">{{ project.name }}</span>
          <span v-if="project.description" class="project-card-desc">{{ project.description }}</span>
          <span class="project-card-meta">Created {{ formatDate(project.created_at) }}</span>
        </button>
        <button
          type="button"
          class="btn-icon project-card-delete"
          :aria-label="`Delete project ${project.name}`"
          @click="deleteProject(project)"
        >
          ✕
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
  margin: 0;
  font-size: var(--text-2xl, 1.5rem);
  font-weight: var(--font-medium, 600);
  color: var(--text-primary);
}

.project-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 0.5rem;
  background: var(--bg-secondary, #f9fafb);
}

.project-form-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: var(--text-sm, 0.875rem);
  color: var(--text-secondary, #6b7280);
}

.project-form-field input {
  padding: 0.5rem;
  border: 1px solid var(--border-color, #d1d5db);
  border-radius: 0.375rem;
  background: var(--bg-primary, #fff);
  color: var(--text-primary);
}

.project-form-error {
  margin: 0;
  color: var(--color-danger-600, #dc2626);
  font-size: var(--text-sm, 0.875rem);
}

.project-form-actions {
  display: flex;
  justify-content: flex-end;
}

.projects-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 2rem;
  color: var(--text-secondary, #6b7280);
  text-align: center;
}

.projects-error {
  color: var(--color-danger-600, #dc2626);
}

.projects-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.project-card {
  display: flex;
  align-items: stretch;
  gap: 0.5rem;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 0.5rem;
  background: var(--bg-primary, #fff);
}

.project-card-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  padding: 0.75rem 1rem;
  background: transparent;
  border: none;
  text-align: left;
  cursor: pointer;
  color: inherit;
}

.project-card-main:hover {
  background: var(--bg-hover, #f3f4f6);
}

.project-card-name {
  font-weight: var(--font-medium, 600);
  color: var(--text-primary);
}

.project-card-desc {
  font-size: var(--text-sm, 0.875rem);
  color: var(--text-secondary, #6b7280);
}

.project-card-meta {
  font-size: var(--text-xs, 0.75rem);
  color: var(--text-tertiary, #9ca3af);
}

.project-card-delete {
  align-self: center;
  margin-right: 0.5rem;
}
</style>
