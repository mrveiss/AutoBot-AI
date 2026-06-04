<template>
  <div class="mcp-resource-browser">
    <div class="browser-header">
      <h2 class="header-title">
        <Icon name="folder-open" />
        MCP Resources
      </h2>
      <p class="header-description">
        Browse and view resources exposed by MCP servers (filesystem, git, knowledge)
      </p>
      <button
        class="refresh-btn"
        :disabled="loading"
        @click="refreshResources"
      >
        <Icon :name="loading ? 'spinner' : 'sync-alt'" :class="{ 'animate-spin': loading }" />
        {{ loading ? 'Loading...' : 'Refresh' }}
      </button>
    </div>

    <!-- Error Display -->
    <div v-if="error" class="error-banner">
      <Icon name="exclamation-triangle" />
      <span>{{ error }}</span>
    </div>

    <!-- Loading State -->
    <div v-if="loading && resources.length === 0" class="loading-state">
      <Icon name="spinner" class="animate-spin" />
      <p>Loading MCP resources...</p>
    </div>

    <!-- Empty State -->
    <div v-else-if="!loading && resources.length === 0 && !error" class="empty-state">
      <Icon name="folder-open" />
      <h3>No Resources Available</h3>
      <p>No MCP resources are currently available from connected servers.</p>
    </div>

    <!-- Resources List -->
    <div v-else class="resources-list">
      <div class="resources-count">
        {{ resources.length }} {{ resources.length === 1 ? 'resource' : 'resources' }} available
      </div>

      <div
        v-for="resource in resources"
        :key="resource.uri"
        class="resource-item"
        :class="{ 'resource-item--selected': selectedResource?.uri === resource.uri }"
        @click="selectResource(resource)"
      >
        <div class="resource-icon">
          <Icon :name="getResourceIcon(resource)" />
        </div>
        <div class="resource-info">
          <div class="resource-name">{{ resource.name }}</div>
          <div class="resource-uri">{{ resource.uri }}</div>
          <div v-if="resource.description" class="resource-description">
            {{ resource.description }}
          </div>
          <div v-if="resource.mime_type" class="resource-meta">
            <span class="mime-type">{{ resource.mime_type }}</span>
          </div>
        </div>
        <div class="resource-actions">
          <button
            class="action-btn"
            :disabled="loadingContent"
            @click.stop="viewResource(resource)"
          >
            <Icon name="eye" />
            View
          </button>
        </div>
      </div>
    </div>

    <!-- Resource Content Modal -->
    <Teleport to="body">
      <div
        v-if="showContentModal"
        class="modal-overlay"
        @click="closeContentModal"
      >
        <div
          class="modal-content"
          @click.stop
        >
          <div class="modal-header">
            <h3>{{ selectedResource?.name }}</h3>
            <button class="close-btn" @click="closeContentModal">
              <Icon name="times" />
            </button>
          </div>
          <div class="modal-body">
            <div v-if="loadingContent" class="loading-content">
              <Icon name="spinner" class="animate-spin" />
              <p>Loading resource content...</p>
            </div>
            <div v-else-if="resourceContent" class="resource-content">
              <div class="content-meta">
                <span class="meta-item">
                  <Icon name="file" />
                  {{ resourceContent.mime_type || 'unknown' }}
                </span>
                <span class="meta-item">
                  <Icon name="weight" />
                  {{ formatBytes(resourceContent.size_bytes) }}
                </span>
              </div>
              <pre class="content-display">{{ resourceContent.content }}</pre>
            </div>
            <div v-else class="error-content">
              <Icon name="exclamation-triangle" />
              <p>Failed to load resource content</p>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn-secondary" @click="closeContentModal">
              Close
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import Icon from '@/components/common/Icon.vue'
import { useMCPResources, type MCPResource, type MCPResourceContent } from '@/composables/useMCPResources'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('MCPResourceBrowser')

const {
  resources,
  loading,
  error,
  listResources,
  readResource
} = useMCPResources()

const selectedResource = ref<MCPResource | null>(null)
const resourceContent = ref<MCPResourceContent | null>(null)
const loadingContent = ref(false)
const showContentModal = ref(false)

onMounted(async () => {
  await refreshResources()
})

async function refreshResources() {
  await listResources()
}

function selectResource(resource: MCPResource) {
  selectedResource.value = resource
}

async function viewResource(resource: MCPResource) {
  selectedResource.value = resource
  loadingContent.value = true
  showContentModal.value = true

  try {
    const content = await readResource(resource.uri)
    resourceContent.value = content
  } catch (err) {
    logger.error('Failed to load resource content:', err)
  } finally {
    loadingContent.value = false
  }
}

function closeContentModal() {
  showContentModal.value = false
  resourceContent.value = null
}

function getResourceIcon(resource: MCPResource): string {
  if (!resource.mime_type) return 'file'

  const mime = resource.mime_type.toLowerCase()
  if (mime.startsWith('text/')) return 'file-alt'
  if (mime.startsWith('image/')) return 'file-image'
  if (mime.startsWith('application/json')) return 'file-code'
  if (mime.includes('pdf')) return 'file-pdf'

  return 'file'
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 Bytes'

  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))

  return `${Math.round((bytes / Math.pow(k, i)) * 100) / 100} ${sizes[i]}`
}
</script>

<style scoped>
.mcp-resource-browser {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: var(--spacing-6);
  background: var(--bg-primary);
}

.browser-header {
  margin-bottom: var(--spacing-6);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.header-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.header-description {
  color: var(--text-secondary);
  margin: 0;
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-weight: 500;
  align-self: flex-start;
  transition: background var(--duration-150) var(--ease-in-out);
}

.refresh-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  background: var(--color-error-bg);
  color: var(--color-error);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-4);
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-4);
  padding: var(--spacing-8);
  color: var(--text-secondary);
}

.empty-state h3 {
  margin: 0;
  color: var(--text-primary);
}

.resources-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.resources-count {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.resource-item {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-150) var(--ease-in-out);
}

.resource-item:hover {
  background: var(--bg-tertiary);
  border-color: var(--color-primary);
}

.resource-item--selected {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.resource-icon {
  font-size: var(--text-2xl);
  color: var(--color-info);
  flex-shrink: 0;
}

.resource-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.resource-name {
  font-weight: 600;
  color: var(--text-primary);
}

.resource-uri {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  word-break: break-all;
}

.resource-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.resource-meta {
  display: flex;
  gap: var(--spacing-3);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.mime-type {
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
}

.resource-actions {
  flex-shrink: 0;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--color-info);
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--text-sm);
  transition: background var(--duration-150) var(--ease-in-out);
}

.action-btn:hover:not(:disabled) {
  background: var(--color-info-hover);
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Modal Styles */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: var(--spacing-4);
}

.modal-content {
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  max-width: 800px;
  width: 100%;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-6);
  border-bottom: 1px solid var(--border-default);
}

.modal-header h3 {
  margin: 0;
  font-size: var(--text-xl);
  color: var(--text-primary);
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: var(--text-xl);
  padding: var(--spacing-2);
  border-radius: var(--radius-sm);
  transition: color var(--duration-150) var(--ease-in-out);
}

.close-btn:hover {
  color: var(--text-primary);
  background: var(--bg-tertiary);
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-6);
}

.loading-content,
.error-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-3);
  padding: var(--spacing-8);
  color: var(--text-secondary);
}

.resource-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.content-meta {
  display: flex;
  gap: var(--spacing-4);
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.content-display {
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  line-height: 1.6;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-primary);
  max-height: 500px;
  overflow-y: auto;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-3);
  padding: var(--spacing-6);
  border-top: 1px solid var(--border-default);
}

.btn-secondary {
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-weight: 500;
  transition: all var(--duration-150) var(--ease-in-out);
}

.btn-secondary:hover {
  background: var(--bg-tertiary);
  border-color: var(--color-primary);
}

.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
