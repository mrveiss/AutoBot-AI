<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  ThemeManagerView.vue - Admin theme package management (#10472)

  Upload a theme package (.zip) to install it, list installed themes, and
  uninstall. Thin client of the backend theme API (admin-gated server-side).
  Reachable under the /slm route group.
-->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import apiClient from '@/utils/ApiClient'
import { fetchInstalledThemes, type InstalledTheme } from '@/composables/useThemeRegistry'
import { createLogger } from '@/utils/debugUtils'

const log = createLogger('ThemeManager')
const themes = ref<InstalledTheme[]>([])
const busy = ref(false)
const error = ref('')

async function refresh(): Promise<void> {
  themes.value = await fetchInstalledThemes()
}

async function onUpload(e: Event): Promise<void> {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  busy.value = true
  error.value = ''
  try {
    const form = new FormData()
    form.append('file', file)
    await apiClient.post('/api/themes', form)
    await refresh()
  } catch (err) {
    error.value = (err as Error).message
    log.error('Theme upload failed', err)
  } finally {
    busy.value = false
  }
}

async function remove(id: string): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    await apiClient.delete(`/api/themes/${id}`)
    await refresh()
  } catch (err) {
    error.value = (err as Error).message
    log.error('Theme uninstall failed', err)
  } finally {
    busy.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <section class="theme-manager">
    <h1 class="text-2xl font-semibold mb-2">Themes</h1>
    <p class="text-autobot-text-secondary mb-4">
      Upload a theme package (.zip) to make it available to all users.
    </p>
    <input type="file" accept=".zip" :disabled="busy" @change="onUpload" />
    <p v-if="error" class="error text-red-500 mt-2">{{ error }}</p>
    <ul class="mt-4 space-y-2">
      <li v-for="t in themes" :key="t.id" class="flex items-center gap-3">
        <strong>{{ t.name }}</strong>
        <small class="text-autobot-text-secondary">v{{ t.version }} — {{ t.author }}</small>
        <button
          type="button"
          class="px-3 py-1 rounded-md bg-autobot-bg-tertiary hover:bg-autobot-bg-hover"
          :disabled="busy"
          @click="remove(t.id)"
        >
          Uninstall
        </button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.theme-manager {
  padding: 1.5rem;
}
</style>
