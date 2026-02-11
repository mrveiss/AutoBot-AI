// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * FileBrowserTool - File Browser Interface
 *
 * Browse and manage files on the backend server.
 * Migrated from main AutoBot frontend - Issue #729.
 */

import { ref, computed, onMounted } from 'vue'
import { useAutobotApi } from '@/composables/useAutobotApi'

const api = useAutobotApi()

// State
const loading = ref(false)
const error = ref<string | null>(null)
const currentPath = ref('/home/autobot')
const pathInput = ref('/home/autobot')

interface FileEntry {
  name: string
  type: 'file' | 'directory'
  size: number
  modified: string
  permissions: string
}

const files = ref<FileEntry[]>([])
const selectedFile = ref<FileEntry | null>(null)
const fileContent = ref<string>('')
const showEditor = ref(false)

// Breadcrumb navigation
const breadcrumbs = computed(() => {
  const parts = currentPath.value.split('/').filter(Boolean)
  const crumbs = [{ name: 'root', path: '/' }]
  let path = ''
  for (const part of parts) {
    path += '/' + part
    crumbs.push({ name: part, path })
  }
  return crumbs
})

// Format file size
function formatSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// Format date
function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleString()
}

// Get file icon
function getFileIcon(entry: FileEntry): string {
  if (entry.type === 'directory') {
    return 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z'
  }
  const ext = entry.name.split('.').pop()?.toLowerCase()
  if (['py', 'js', 'ts', 'vue', 'html', 'css'].includes(ext || '')) {
    return 'M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4'
  }
  if (['json', 'yaml', 'yml', 'toml', 'ini', 'conf'].includes(ext || '')) {
    return 'M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253'
  }
  if (['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp'].includes(ext || '')) {
    return 'M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z'
  }
  return 'M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z'
}

async function loadDirectory(path: string): Promise<void> {
  loading.value = true
  error.value = null

  try {
    const filesList = await api.listFiles(path)
    files.value = (filesList || []) as FileEntry[]
    currentPath.value = path
    pathInput.value = path
    selectedFile.value = null
    showEditor.value = false
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load directory'
  } finally {
    loading.value = false
  }
}

async function openEntry(entry: FileEntry): Promise<void> {
  if (entry.type === 'directory') {
    const newPath = currentPath.value === '/'
      ? `/${entry.name}`
      : `${currentPath.value}/${entry.name}`
    await loadDirectory(newPath)
  } else {
    // Open file
    selectedFile.value = entry
    await loadFileContent(entry)
  }
}

async function loadFileContent(entry: FileEntry): Promise<void> {
  loading.value = true
  try {
    const filePath = currentPath.value === '/'
      ? `/${entry.name}`
      : `${currentPath.value}/${entry.name}`
    const content = await api.readFile(filePath)
    fileContent.value = content || ''
    showEditor.value = true
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load file'
  } finally {
    loading.value = false
  }
}

function goUp(): void {
  if (currentPath.value === '/') return
  const parts = currentPath.value.split('/').filter(Boolean)
  parts.pop()
  const newPath = '/' + parts.join('/')
  loadDirectory(newPath || '/')
}

function navigateTo(path: string): void {
  loadDirectory(path)
}

function goToPath(): void {
  if (pathInput.value) {
    loadDirectory(pathInput.value)
  }
}

async function downloadFile(entry: FileEntry): Promise<void> {
  try {
    const filePath = currentPath.value === '/'
      ? `/${entry.name}`
      : `${currentPath.value}/${entry.name}`
    const content = await api.readFile(filePath)

    // Create download link
    const blob = new Blob([content], { type: 'application/octet-stream' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = entry.name
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to download file'
  }
}

function closeEditor(): void {
  showEditor.value = false
  selectedFile.value = null
  fileContent.value = ''
}

onMounted(() => {
  loadDirectory(currentPath.value)
})
</script>

<template>
  <div class="p-6 h-full flex flex-col">
    <div class="flex gap-6 flex-1 overflow-hidden">
      <!-- File Browser Panel -->
      <div class="flex-1 bg-white rounded-lg shadow-sm border border-gray-200 flex flex-col overflow-hidden">
        <!-- Toolbar -->
        <div class="bg-gray-50 border-b border-gray-200 px-4 py-3 flex items-center gap-4">
          <!-- Navigation buttons -->
          <button
            @click="goUp"
            :disabled="currentPath === '/'"
            class="p-2 text-gray-600 hover:text-gray-800 hover:bg-gray-200 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title="Go Up"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18" />
            </svg>
          </button>

          <!-- Path Input -->
          <div class="flex-1 flex items-center gap-2">
            <input
              v-model="pathInput"
              @keydown.enter="goToPath"
              type="text"
              class="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm font-mono"
              placeholder="/path/to/directory"
            />
            <button
              @click="goToPath"
              class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm"
            >
              Go
            </button>
          </div>

          <!-- Refresh -->
          <button
            @click="loadDirectory(currentPath)"
            :disabled="loading"
            class="p-2 text-gray-600 hover:text-gray-800 hover:bg-gray-200 rounded-lg transition-colors"
            title="Refresh"
          >
            <svg class="w-5 h-5" :class="{ 'animate-spin': loading }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>

        <!-- Breadcrumbs -->
        <div class="bg-gray-50 border-b border-gray-200 px-4 py-2 flex items-center gap-1 text-sm overflow-x-auto">
          <button
            v-for="(crumb, index) in breadcrumbs"
            :key="crumb.path"
            @click="navigateTo(crumb.path)"
            class="flex items-center gap-1 hover:text-primary-600 transition-colors"
          >
            <span v-if="index > 0" class="text-gray-400">/</span>
            <span :class="index === breadcrumbs.length - 1 ? 'font-medium text-primary-600' : 'text-gray-600'">
              {{ crumb.name }}
            </span>
          </button>
        </div>

        <!-- Error Message -->
        <div v-if="error" class="m-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {{ error }}
        </div>

        <!-- Loading -->
        <div v-if="loading && !files.length" class="flex-1 flex items-center justify-center">
          <svg class="animate-spin w-8 h-8 text-primary-500" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        </div>

        <!-- File List -->
        <div v-else class="flex-1 overflow-auto">
          <table class="w-full">
            <thead class="bg-gray-50 sticky top-0">
              <tr>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Size</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Modified</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Permissions</th>
                <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-200">
              <tr
                v-for="entry in files"
                :key="entry.name"
                @dblclick="openEntry(entry)"
                :class="[
                  'hover:bg-gray-50 cursor-pointer transition-colors',
                  selectedFile?.name === entry.name ? 'bg-primary-50' : ''
                ]"
              >
                <td class="px-4 py-3 whitespace-nowrap">
                  <div class="flex items-center gap-3">
                    <svg class="w-5 h-5" :class="entry.type === 'directory' ? 'text-yellow-500' : 'text-gray-400'" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="getFileIcon(entry)" />
                    </svg>
                    <span class="text-sm font-medium text-gray-900">{{ entry.name }}</span>
                  </div>
                </td>
                <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                  {{ entry.type === 'directory' ? '-' : formatSize(entry.size) }}
                </td>
                <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                  {{ formatDate(entry.modified) }}
                </td>
                <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-500 font-mono">
                  {{ entry.permissions }}
                </td>
                <td class="px-4 py-3 whitespace-nowrap text-right">
                  <div class="flex items-center justify-end gap-2">
                    <button
                      v-if="entry.type === 'file'"
                      @click.stop="downloadFile(entry)"
                      class="p-1.5 text-gray-400 hover:text-gray-600 transition-colors"
                      title="Download"
                    >
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                    </button>
                    <button
                      @click.stop="openEntry(entry)"
                      class="p-1.5 text-gray-400 hover:text-gray-600 transition-colors"
                      :title="entry.type === 'directory' ? 'Open' : 'View'"
                    >
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                      </svg>
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>

          <div v-if="files.length === 0 && !loading" class="p-8 text-center text-gray-500">
            <svg class="w-12 h-12 mx-auto text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
            <p class="mt-4">Empty directory</p>
          </div>
        </div>
      </div>

      <!-- File Viewer/Editor Panel -->
      <div v-if="showEditor" class="w-1/2 bg-white rounded-lg shadow-sm border border-gray-200 flex flex-col overflow-hidden">
        <!-- Header -->
        <div class="bg-gray-50 border-b border-gray-200 px-4 py-3 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <svg class="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
            </svg>
            <span class="font-medium text-gray-900">{{ selectedFile?.name }}</span>
          </div>
          <button
            @click="closeEditor"
            class="p-1.5 text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <!-- Content -->
        <div class="flex-1 overflow-auto">
          <pre class="p-4 text-sm font-mono text-gray-800 whitespace-pre-wrap">{{ fileContent }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>
