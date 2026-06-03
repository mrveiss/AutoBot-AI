<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import { useTranscriberStore } from '@/stores/transcriber/useTranscriberStore'
import type { Project } from '@/composables/transcriber/useTranscriberApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ProjectsView')
const api = useTranscriberApi()
const store = useTranscriberStore()
const router = useRouter()

const showCreate = ref(false)
const newName = ref('')
const newDesc = ref('')
const creating = ref(false)

onMounted(async () => {
  try {
    store.setProjects(await api.listProjects())
  } catch (err) {
    logger.error('Failed to load projects', err)
  }
})

async function createProject() {
  if (!newName.value.trim()) return
  creating.value = true
  try {
    const p = await api.createProject(newName.value.trim(), newDesc.value.trim())
    store.setProjects([p, ...store.projects])
    showCreate.value = false
    newName.value = ''
    newDesc.value = ''
    router.push({ name: 'transcriber-project-detail', params: { projectId: p.id } })
  } catch (err) {
    logger.error('Failed to create project', err)
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div class="projects-view">
    <div class="projects-header">
      <h1>Projects</h1>
      <button class="btn btn-primary" @click="showCreate = true">New Project</button>
    </div>

    <div v-if="showCreate" class="create-project-form card">
      <input v-model="newName" placeholder="Project name" class="input" />
      <input v-model="newDesc" placeholder="Description (optional)" class="input" />
      <div class="form-actions">
        <button class="btn btn-primary" @click="createProject" :disabled="creating || !newName.trim()">
          Create
        </button>
        <button class="btn btn-ghost" @click="showCreate = false">Cancel</button>
      </div>
    </div>

    <div class="projects-grid">
      <RouterLink
        v-for="project in store.projects"
        :key="project.id"
        :to="{ name: 'transcriber-project-detail', params: { projectId: project.id } }"
        class="project-card card"
      >
        <h3>{{ project.name }}</h3>
        <p v-if="project.description" class="text-muted">{{ project.description }}</p>
        <time class="text-xs text-muted">{{ new Date(project.created_at).toLocaleDateString() }}</time>
      </RouterLink>
    </div>

    <p v-if="store.projects.length === 0" class="empty-state">
      No projects yet. Create your first project to get started.
    </p>
  </div>
</template>
