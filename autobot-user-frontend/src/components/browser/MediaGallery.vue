<template>
  <div class="media-gallery">
    <!-- Header -->
    <div class="gallery-header">
      <div class="flex items-center space-x-3">
        <i class="fas fa-images text-purple-600 text-xl"></i>
        <div>
          <h3 class="text-lg font-semibold text-gray-800">Media Gallery</h3>
          <p class="text-sm text-gray-500">Screenshots and recordings from automation</p>
        </div>
      </div>

      <div class="flex items-center space-x-2">
        <div class="view-toggle">
          <button
            @click="viewMode = 'grid'"
            :class="{ active: viewMode === 'grid' }"
            title="Grid View"
          >
            <i class="fas fa-th"></i>
          </button>
          <button
            @click="viewMode = 'list'"
            :class="{ active: viewMode === 'list' }"
            title="List View"
          >
            <i class="fas fa-list"></i>
          </button>
        </div>

        <BaseButton
          variant="outline"
          size="sm"
          @click="clearGallery"
          :disabled="mediaItems.length === 0"
        >
          <i class="fas fa-trash mr-1"></i>
          Clear All
        </BaseButton>
      </div>
    </div>

    <!-- Stats -->
    <div class="gallery-stats">
      <div class="stat-item">
        <i class="fas fa-camera text-blue-500"></i>
        <span class="stat-value">{{ screenshots.length }}</span>
        <span class="stat-label">Screenshots</span>
      </div>
      <div class="stat-item">
        <i class="fas fa-video text-red-500"></i>
        <span class="stat-value">{{ recordings.length }}</span>
        <span class="stat-label">Recordings</span>
      </div>
      <div class="stat-item">
        <i class="fas fa-hdd text-green-500"></i>
        <span class="stat-value">{{ totalSize }}</span>
        <span class="stat-label">Total Size</span>
      </div>
    </div>

    <!-- Filters -->
    <div class="gallery-filters">
      <div class="filter-group">
        <label class="filter-label">Type:</label>
        <select v-model="filterType" class="filter-select">
          <option value="all">All Media</option>
          <option value="screenshot">Screenshots</option>
          <option value="recording">Recordings</option>
        </select>
      </div>

      <div class="filter-group">
        <label class="filter-label">Sort:</label>
        <select v-model="sortBy" class="filter-select">
          <option value="newest">Newest First</option>
          <option value="oldest">Oldest First</option>
          <option value="size">By Size</option>
        </select>
      </div>

      <div class="search-box">
        <i class="fas fa-search"></i>
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search by filename or URL..."
          class="search-input"
        />
      </div>
    </div>

    <!-- Gallery Content -->
    <div class="gallery-content">
      <div v-if="filteredMedia.length === 0" class="empty-state">
        <EmptyState
          icon="fas fa-images"
          title="No Media Items"
          message="Capture screenshots or recordings from browser automation"
        />
      </div>

      <!-- Grid View -->
      <div v-else-if="viewMode === 'grid'" class="media-grid">
        <div
          v-for="item in filteredMedia"
          :key="item.id"
          class="media-card"
          @click="openPreview(item)"
        >
          <div class="media-thumbnail">
            <img
              v-if="item.type === 'screenshot'"
              :src="item.thumbnail || item.url"
              :alt="item.filename"
              class="thumbnail-image"
            />
            <div v-else class="video-placeholder">
              <i class="fas fa-video text-4xl text-gray-400"></i>
              <div v-if="item.duration" class="video-duration">
                {{ formatDuration(item.duration) }}
              </div>
            </div>

            <!-- Overlay Actions -->
            <div class="thumbnail-overlay">
              <button
                @click.stop="downloadMedia(item)"
                class="overlay-btn"
                title="Download"
              >
                <i class="fas fa-download"></i>
              </button>
              <button
                @click.stop="deleteMedia(item.id)"
                class="overlay-btn"
                title="Delete"
              >
                <i class="fas fa-trash"></i>
              </button>
            </div>

            <!-- Media Type Badge -->
            <div class="media-type-badge" :class="item.type">
              <i :class="item.type === 'screenshot' ? 'fas fa-camera' : 'fas fa-video'"></i>
            </div>
          </div>

          <div class="media-info">
            <h4 class="media-filename" :title="item.filename">{{ item.filename }}</h4>
            <div class="media-meta">
              <span v-if="item.width && item.height">{{ item.width }}x{{ item.height }}</span>
              <span>{{ formatSize(item.size) }}</span>
              <span>{{ formatDate(item.capturedAt) }}</span>
            </div>
            <p v-if="item.pageUrl" class="media-url" :title="item.pageUrl">
              {{ item.pageUrl }}
            </p>
          </div>
        </div>
      </div>

      <!-- List View -->
      <div v-else class="media-list">
        <div
          v-for="item in filteredMedia"
          :key="item.id"
          class="media-list-item"
          @click="openPreview(item)"
        >
          <div class="list-thumbnail">
            <img
              v-if="item.type === 'screenshot'"
              :src="item.thumbnail || item.url"
              :alt="item.filename"
            />
            <i v-else class="fas fa-video text-2xl text-gray-400"></i>
          </div>

          <div class="list-info">
            <h4 class="list-filename">{{ item.filename }}</h4>
            <p v-if="item.pageTitle" class="list-title">{{ item.pageTitle }}</p>
            <p v-if="item.pageUrl" class="list-url">{{ item.pageUrl }}</p>
          </div>

          <div class="list-meta">
            <span class="meta-badge">{{ item.type }}</span>
            <span>{{ formatSize(item.size) }}</span>
            <span v-if="item.width && item.height">{{ item.width }}x{{ item.height }}</span>
          </div>

          <div class="list-actions">
            <button
              @click.stop="downloadMedia(item)"
              class="action-btn"
              title="Download"
            >
              <i class="fas fa-download"></i>
            </button>
            <button
              @click.stop="deleteMedia(item.id)"
              class="action-btn text-red-600"
              title="Delete"
            >
              <i class="fas fa-trash"></i>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Preview Modal -->
    <div v-if="previewItem" class="preview-modal" @click.self="closePreview">
      <div class="preview-content">
        <div class="preview-header">
          <h3 class="preview-title">{{ previewItem.filename }}</h3>
          <div class="preview-actions">
            <button @click="downloadMedia(previewItem)" class="preview-btn" title="Download">
              <i class="fas fa-download"></i>
            </button>
            <button @click="closePreview" class="preview-btn" title="Close">
              <i class="fas fa-times"></i>
            </button>
          </div>
        </div>

        <div class="preview-body">
          <img
            v-if="previewItem.type === 'screenshot'"
            :src="previewItem.url"
            :alt="previewItem.filename"
            class="preview-image"
          />
          <video
            v-else
            :src="previewItem.url"
            controls
            class="preview-video"
          ></video>
        </div>

        <div class="preview-footer">
          <div class="preview-info">
            <div class="info-item">
              <span class="info-label">Type:</span>
              <span class="info-value">{{ previewItem.type }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">Size:</span>
              <span class="info-value">{{ formatSize(previewItem.size) }}</span>
            </div>
            <div v-if="previewItem.width && previewItem.height" class="info-item">
              <span class="info-label">Dimensions:</span>
              <span class="info-value">{{ previewItem.width }}x{{ previewItem.height }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">Captured:</span>
              <span class="info-value">{{ formatFullDate(previewItem.capturedAt) }}</span>
            </div>
          </div>
          <div v-if="previewItem.pageUrl" class="preview-url">
            <span class="info-label">Source URL:</span>
            <a :href="previewItem.pageUrl" target="_blank" class="url-link">
              {{ previewItem.pageUrl }}
              <i class="fas fa-external-link-alt ml-1"></i>
            </a>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { ref, computed } from 'vue'
import { useBrowserAutomation } from '@/composables/useBrowserAutomation'
import BaseButton from '@/components/base/BaseButton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import type { MediaItem } from '@/types/browser'

export default {
  name: 'MediaGallery',
  components: {
    BaseButton,
    EmptyState
  },
  setup() {
    const { mediaItems, deleteMediaItem, clearMediaGallery } = useBrowserAutomation()

    const viewMode = ref<'grid' | 'list'>('grid')
    const filterType = ref<'all' | 'screenshot' | 'recording'>('all')
    const sortBy = ref<'newest' | 'oldest' | 'size'>('newest')
    const searchQuery = ref('')
    const previewItem = ref<MediaItem | null>(null)

    // Computed
    const screenshots = computed(() =>
      mediaItems.value.filter(item => item.type === 'screenshot')
    )

    const recordings = computed(() =>
      mediaItems.value.filter(item => item.type === 'recording')
    )

    const totalSize = computed(() => {
      const bytes = mediaItems.value.reduce((sum, item) => sum + item.size, 0)
      return formatSize(bytes)
    })

    const filteredMedia = computed(() => {
      let items = mediaItems.value

      // Filter by type
      if (filterType.value !== 'all') {
        items = items.filter(item => item.type === filterType.value)
      }

      // Filter by search query
      if (searchQuery.value.trim()) {
        const query = searchQuery.value.toLowerCase()
        items = items.filter(
          item =>
            item.filename.toLowerCase().includes(query) ||
            item.pageUrl?.toLowerCase().includes(query) ||
            item.pageTitle?.toLowerCase().includes(query)
        )
      }

      // Sort
      items = [...items].sort((a, b) => {
        if (sortBy.value === 'newest') {
          return b.capturedAt.getTime() - a.capturedAt.getTime()
        } else if (sortBy.value === 'oldest') {
          return a.capturedAt.getTime() - b.capturedAt.getTime()
        } else {
          return b.size - a.size
        }
      })

      return items
    })

    // Methods
    const openPreview = (item: MediaItem) => {
      previewItem.value = item
    }

    const closePreview = () => {
      previewItem.value = null
    }

    const downloadMedia = (item: MediaItem) => {
      const link = document.createElement('a')
      link.href = item.url
      link.download = item.filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    }

    const deleteMedia = (mediaId: string) => {
      if (confirm('Are you sure you want to delete this media item?')) {
        deleteMediaItem(mediaId)
        if (previewItem.value?.id === mediaId) {
          closePreview()
        }
      }
    }

    const clearGallery = () => {
      if (confirm('Are you sure you want to clear all media items?')) {
        clearMediaGallery()
      }
    }

    const formatSize = (bytes: number): string => {
      if (bytes === 0) return '0 B'
      const k = 1024
      const sizes = ['B', 'KB', 'MB', 'GB']
      const i = Math.floor(Math.log(bytes) / Math.log(k))
      return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`
    }

    const formatDate = (date: Date): string => {
      return new Intl.DateTimeFormat('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      }).format(date)
    }

    const formatFullDate = (date: Date): string => {
      return new Intl.DateTimeFormat('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      }).format(date)
    }

    const formatDuration = (seconds: number): string => {
      const mins = Math.floor(seconds / 60)
      const secs = Math.floor(seconds % 60)
      return `${mins}:${secs.toString().padStart(2, '0')}`
    }

    return {
      mediaItems,
      viewMode,
      filterType,
      sortBy,
      searchQuery,
      previewItem,
      screenshots,
      recordings,
      totalSize,
      filteredMedia,
      openPreview,
      closePreview,
      downloadMedia,
      deleteMedia,
      clearGallery,
      formatSize,
      formatDate,
      formatFullDate,
      formatDuration
    }
  }
}
</script>

<style scoped>
.media-gallery {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-surface);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.gallery-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-5);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-light);
}

.view-toggle {
  display: flex;
  background: var(--bg-surface);
  border-radius: var(--radius-md);
  padding: 2px;
}

.view-toggle button {
  padding: var(--spacing-2) var(--spacing-3);
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--text-secondary);
  transition: all var(--duration-200);
}

.view-toggle button.active {
  background: var(--color-primary);
  color: white;
}

.gallery-stats {
  display: flex;
  justify-content: space-around;
  padding: var(--spacing-4);
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-light);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.gallery-filters {
  display: flex;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-light);
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.filter-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.filter-select {
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  color: var(--text-primary);
  font-size: 14px;
}

.search-box {
  display: flex;
  align-items: center;
  flex: 1;
  max-width: 300px;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 0 var(--spacing-3);
}

.search-box i {
  color: var(--text-secondary);
  margin-right: var(--spacing-2);
}

.search-input {
  flex: 1;
  border: none;
  background: transparent;
  padding: var(--spacing-2) 0;
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
}

.gallery-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-5);
}

.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
}

.media-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: var(--spacing-4);
}

.media-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
  cursor: pointer;
  transition: all var(--duration-200);
}

.media-card:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
}

.media-thumbnail {
  position: relative;
  width: 100%;
  padding-top: 66.67%;
  background: var(--bg-surface);
  overflow: hidden;
}

.thumbnail-image {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.video-placeholder {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.video-duration {
  position: absolute;
  bottom: 8px;
  right: 8px;
  background: rgba(0, 0, 0, 0.8);
  color: white;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-size: 12px;
}

.thumbnail-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  opacity: 0;
  transition: opacity var(--duration-200);
}

.media-card:hover .thumbnail-overlay {
  opacity: 1;
}

.overlay-btn {
  padding: var(--spacing-2-5);
  background: white;
  border: none;
  border-radius: var(--radius-md);
  color: var(--text-primary);
  cursor: pointer;
  transition: transform var(--duration-200);
}

.overlay-btn:hover {
  transform: scale(1.1);
}

.media-type-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  padding: 4px 8px;
  border-radius: var(--radius-md);
  font-size: 12px;
  color: white;
}

.media-type-badge.screenshot {
  background: #3b82f6;
}

.media-type-badge.recording {
  background: #ef4444;
}

.media-info {
  padding: var(--spacing-3);
}

.media-filename {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: var(--spacing-1);
}

.media-meta {
  display: flex;
  gap: var(--spacing-2);
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: var(--spacing-1);
}

.media-url {
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.media-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.media-list-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--duration-200);
}

.media-list-item:hover {
  box-shadow: var(--shadow-md);
}

.list-thumbnail {
  width: 80px;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-surface);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.list-thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.list-info {
  flex: 1;
}

.list-filename {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.list-title {
  font-size: 14px;
  color: var(--text-secondary);
}

.list-url {
  font-size: 12px;
  color: var(--text-tertiary);
}

.list-meta {
  display: flex;
  gap: var(--spacing-2);
  font-size: 12px;
  color: var(--text-secondary);
}

.meta-badge {
  padding: 2px 8px;
  background: var(--bg-surface);
  border-radius: var(--radius-sm);
  text-transform: uppercase;
  font-weight: 600;
}

.list-actions {
  display: flex;
  gap: var(--spacing-2);
}

.action-btn {
  padding: var(--spacing-2);
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--text-secondary);
  transition: color var(--duration-200);
}

.action-btn:hover {
  color: var(--text-primary);
}

/* Preview Modal */
.preview-modal {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.9);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: var(--spacing-5);
}

.preview-content {
  background: var(--bg-surface);
  border-radius: var(--radius-lg);
  width: 100%;
  max-width: 1200px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-2xl);
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-light);
}

.preview-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.preview-actions {
  display: flex;
  gap: var(--spacing-2);
}

.preview-btn {
  padding: var(--spacing-2) var(--spacing-3);
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--text-primary);
  transition: all var(--duration-200);
}

.preview-btn:hover {
  background: var(--bg-tertiary);
}

.preview-body {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-4);
  background: var(--bg-tertiary);
  overflow: auto;
}

.preview-image,
.preview-video {
  max-width: 100%;
  max-height: 100%;
  border-radius: var(--radius-md);
}

.preview-footer {
  padding: var(--spacing-4);
  border-top: 1px solid var(--border-light);
}

.preview-info {
  display: flex;
  gap: var(--spacing-5);
  margin-bottom: var(--spacing-3);
}

.info-item {
  display: flex;
  flex-direction: column;
}

.info-label {
  font-size: 12px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--spacing-1);
}

.info-value {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 500;
}

.preview-url {
  display: flex;
  flex-direction: column;
}

.url-link {
  color: var(--color-primary);
  text-decoration: none;
  font-size: 14px;
}

.url-link:hover {
  text-decoration: underline;
}
</style>
