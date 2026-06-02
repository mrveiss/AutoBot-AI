<template>
  <div class="mcp-resource-browser">
    <div class="browser-header">
      <h2>MCP Resources</h2>
      <p class="description">Browse resources from connected MCP servers</p>
    </div>

    <div v-if="loading" class="loading-state">
      <Icon name="spinner" spin />
      <span>Loading resources...</span>
    </div>

    <div v-else-if="error" class="error-state">
      <Icon name="exclamation-triangle" />
      <p>{{ error }}</p>
      <BaseButton @click="loadResources" variant="primary" size="sm">
        Retry
      </BaseButton>
    </div>

    <div v-else class="resources-container">
      <!-- Bridge Tabs -->
      <div class="bridge-tabs">
        <button
          v-for="bridge in bridges"
          :key="bridge"
          class="bridge-tab"
          :class="{ active: activeBridge === bridge }"
          @click="activeBridge = bridge"
        >
          <Icon :name="getBridgeIcon(bridge)" />
          {{ bridge }}
        </button>
      </div>

      <!-- Resources List -->
      <div v-if="currentResources.length === 0" class="empty-state">
        <Icon name="folder-open" />
        <p>No resources available from {{ activeBridge }} bridge</p>
      </div>

      <div v-else class="resources-list">
        <div
          v-for="resource in currentResources"
          :key="resource.uri"
          class="resource-item"
          @click="viewResource(resource)"
        >
          <div class="resource-icon">
            <Icon :name="getMimeTypeIcon(resource.mimeType)" />
          </div>
          <div class="resource-info">
            <div class="resource-name">{{ resource.name }}</div>
            <div class="resource-uri">{{ resource.uri }}</div>
            <div v-if="resource.description" class="resource-description">
              {{ resource.description }}
            </div>
          </div>
          <div class="resource-meta">
            <span class="mime-badge">{{ resource.mimeType || 'unknown' }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Resource Viewer Modal -->
    <BaseModal
      v-if="viewingResource"
      :show="!!viewingResource"
      @close="viewingResource = null"
      size="xl"
    >
      <template #header>
        <h3>{{ viewingResource.name }}</h3>
      </template>

      <div v-if="resourceContent.loading" class="loading-content">
        <Icon name="spinner" spin />
        <span>Loading content...</span>
      </div>

      <div v-else-if="resourceContent.error" class="error-content">
        <Icon name="exclamation-triangle" />
        <p>{{ resourceContent.error }}</p>
      </div>

      <div v-else class="resource-content">
        <div class="content-meta">
          <span><strong>URI:</strong> {{ viewingResource.uri }}</span>
          <span><strong>Type:</strong> {{ viewingResource.mimeType }}</span>
        </div>
        <pre class="content-text">{{ resourceContent.text }}</pre>
      </div>

      <template #footer>
        <BaseButton @click="viewingResource = null" variant="ghost">
          Close
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useApi } from '@/composables/useApi'
import BaseButton from '@/components/common/BaseButton.vue'
import BaseModal from '@/components/common/BaseModal.vue'
import Icon from '@/components/common/Icon.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('McpResourceBrowser')
const api = useApi()

interface McpResource {
  uri: string
  name: string
  description?: string
  mimeType?: string
}

interface ResourceContent {
  uri: string
  mimeType?: string
  text?: string
}

const bridges = ['filesystem', 'git', 'knowledge'] as const
type Bridge = typeof bridges[number]

const activeBridge = ref<Bridge>('git')
const loading = ref(false)
const error = ref<string | null>(null)
const resourcesByBridge = ref<Record<Bridge, McpResource[]>>({
  filesystem: [],
  git: [],
  knowledge: []
})

const viewingResource = ref<McpResource | null>(null)
const resourceContent = ref<{
  loading: boolean
  error: string | null
  text: string | null
}>({
  loading: false,
  error: null,
  text: null
})

const currentResources = computed(() => resourcesByBridge.value[activeBridge.value])

async function loadResources() {
  loading.value = true
  error.value = null

  try {
    await Promise.all(
      bridges.map(async (bridge) => {
        try {
          const response = await api.get<{ resources: McpResource[] }>(
            `/api/${bridge}/mcp/resources`
          )
          resourcesByBridge.value[bridge] = response.resources || []
        } catch (err) {
          logger.error(`Failed to load ${bridge} resources:`, err)
          resourcesByBridge.value[bridge] = []
        }
      })
    )
  } catch (err) {
    logger.error('Failed to load resources:', err)
    error.value = 'Failed to load MCP resources. Please try again.'
  } finally {
    loading.value = false
  }
}

async function viewResource(resource: McpResource) {
  viewingResource.value = resource
  resourceContent.value = { loading: true, error: null, text: null }

  try {
    const bridge = getBridgeFromUri(resource.uri)
    const response = await api.post<{ contents: ResourceContent[] }>(
      `/api/${bridge}/mcp/resources/read`,
      { uri: resource.uri }
    )

    if (response.contents && response.contents.length > 0) {
      resourceContent.value.text = response.contents[0].text || 'No content available'
    } else {
      resourceContent.value.text = 'No content available'
    }
  } catch (err) {
    logger.error('Failed to load resource content:', err)
    resourceContent.value.error = 'Failed to load resource content'
  } finally {
    resourceContent.value.loading = false
  }
}

function getBridgeFromUri(uri: string): Bridge {
  if (uri.startsWith('git://')) return 'git'
  if (uri.startsWith('kb://')) return 'knowledge'
  if (uri.startsWith('file://')) return 'filesystem'
  return 'filesystem'
}

function getBridgeIcon(bridge: Bridge): string {
  const icons: Record<Bridge, string> = {
    git: 'code-branch',
    filesystem: 'folder',
    knowledge: 'brain'
  }
  return icons[bridge]
}

function getMimeTypeIcon(mimeType?: string): string {
  if (!mimeType) return 'file'
  if (mimeType.startsWith('text/')) return 'file-alt'
  if (mimeType.includes('json')) return 'brackets-curly'
  if (mimeType.includes('image')) return 'image'
  return 'file'
}

onMounted(() => {
  loadResources()
})
</script>

<style scoped>
.mcp-resource-browser {
  padding: 1.5rem;
  height: 100%;
  overflow-y: auto;
}

.browser-header {
  margin-bottom: 2rem;
}

.browser-header h2 {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--autobot-text-primary);
  margin-bottom: 0.5rem;
}

.description {
  color: var(--autobot-text-secondary);
  font-size: 0.875rem;
}

.loading-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem;
  gap: 1rem;
}

.loading-state span,
.error-state p {
  color: var(--autobot-text-secondary);
}

.bridge-tabs {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
  border-bottom: 2px solid var(--autobot-border-color);
}

.bridge-tab {
  padding: 0.75rem 1.5rem;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--autobot-text-secondary);
  cursor: pointer;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  transition: all 0.2s;
  margin-bottom: -2px;
}

.bridge-tab:hover {
  color: var(--autobot-text-primary);
}

.bridge-tab.active {
  color: var(--autobot-primary);
  border-bottom-color: var(--autobot-primary);
}

.resources-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.resource-item {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 1rem;
  background: var(--autobot-bg-secondary);
  border: 1px solid var(--autobot-border-color);
  border-radius: 0.5rem;
  cursor: pointer;
  transition: all 0.2s;
}

.resource-item:hover {
  border-color: var(--autobot-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.resource-icon {
  flex-shrink: 0;
  width: 2.5rem;
  height: 2.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--autobot-bg-primary);
  border-radius: 0.375rem;
  color: var(--autobot-primary);
}

.resource-info {
  flex: 1;
  min-width: 0;
}

.resource-name {
  font-weight: 600;
  color: var(--autobot-text-primary);
  margin-bottom: 0.25rem;
}

.resource-uri {
  font-size: 0.75rem;
  color: var(--autobot-text-secondary);
  font-family: 'Monaco', 'Courier New', monospace;
  word-break: break-all;
}

.resource-description {
  margin-top: 0.5rem;
  font-size: 0.875rem;
  color: var(--autobot-text-secondary);
}

.resource-meta {
  flex-shrink: 0;
}

.mime-badge {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  background: var(--autobot-bg-tertiary);
  border-radius: 0.25rem;
  font-size: 0.75rem;
  color: var(--autobot-text-secondary);
  font-family: 'Monaco', 'Courier New', monospace;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem;
  gap: 1rem;
  color: var(--autobot-text-secondary);
}

.loading-content,
.error-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  gap: 1rem;
}

.resource-content {
  max-height: 60vh;
  overflow: auto;
}

.content-meta {
  padding: 1rem;
  background: var(--autobot-bg-secondary);
  border-radius: 0.375rem;
  margin-bottom: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.content-text {
  padding: 1rem;
  background: var(--autobot-bg-tertiary);
  border-radius: 0.375rem;
  font-family: 'Monaco', 'Courier New', monospace;
  font-size: 0.875rem;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--autobot-text-primary);
}
</style>
