<template>
  <div class="media-gallery">
    <!-- Header -->
    <div class="gallery-header">
      <div class="header-info">
        <h3>Media Gallery</h3>
        <p>History of processed images, videos, and screen captures</p>
      </div>
      <div class="header-actions">
        <div class="filter-group">
          <select v-model="filterType">
            <option value="">All Types</option>
            <option value="image">Images</option>
            <option value="video">Videos</option>
            <option value="screen">Screen Captures</option>
          </select>
        </div>
        <button @click="clearAll" class="btn-clear-all" :disabled="items.length === 0">
          <i class="fas fa-trash"></i>
          Clear All
        </button>
      </div>
    </div>

    <!-- Gallery Grid -->
    <div v-if="filteredItems.length > 0" class="gallery-grid">
      <div
        v-for="item in filteredItems"
        :key="item.id"
        class="gallery-item"
        @click="selectItem(item)"
      >
        <div class="item-thumbnail">
          <img
            v-if="item.thumbnail"
            :src="item.thumbnail"
            :alt="item.filename"
            @error="handleThumbnailError"
          />
          <div v-else class="thumbnail-placeholder">
            <i :class="getTypeIcon(item.type)"></i>
          </div>
          <div class="item-type-badge">
            <i :class="getTypeIcon(item.type)"></i>
          </div>
        </div>
        <div class="item-info">
          <span class="item-name" :title="item.filename">{{ truncateFilename(item.filename) }}</span>
          <span class="item-date">{{ formatDate(item.timestamp) }}</span>
        </div>
        <div class="item-actions">
          <button @click.stop="$emit('re-analyze', item)" class="btn-action" title="Re-analyze">
            <i class="fas fa-redo"></i>
          </button>
          <button @click.stop="downloadItem(item)" class="btn-action" title="Download">
            <i class="fas fa-download"></i>
          </button>
          <button @click.stop="$emit('delete', item.id)" class="btn-action btn-delete" title="Delete">
            <i class="fas fa-trash"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else class="empty-state">
      <div class="empty-icon">
        <i class="fas fa-images"></i>
      </div>
      <h4>No Media Items</h4>
      <p v-if="filterType">No {{ filterType }}s found. Try changing the filter.</p>
      <p v-else>Process some images or capture screens to see them here</p>
    </div>

    <!-- Detail Modal -->
    <div v-if="selectedItem" class="detail-overlay" @click.self="selectedItem = null">
      <div class="detail-modal">
        <div class="modal-header">
          <h4>{{ selectedItem.filename }}</h4>
          <button @click="selectedItem = null" class="btn-close">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-content">
          <div class="preview-section">
            <img
              v-if="selectedItem.thumbnail"
              :src="selectedItem.thumbnail"
              :alt="selectedItem.filename"
              class="preview-image"
            />
            <div v-else class="preview-placeholder">
              <i :class="getTypeIcon(selectedItem.type)"></i>
            </div>
          </div>

          <div class="details-section">
            <div class="detail-row">
              <span class="label">Type</span>
              <span class="value">{{ selectedItem.type }}</span>
            </div>
            <div class="detail-row">
              <span class="label">Filename</span>
              <span class="value">{{ selectedItem.filename }}</span>
            </div>
            <div class="detail-row">
              <span class="label">Date</span>
              <span class="value">{{ formatFullDate(selectedItem.timestamp) }}</span>
            </div>

            <div v-if="selectedItem.analysisResult" class="analysis-section">
              <h5>Analysis Results</h5>
              <div class="analysis-data">
                <div class="data-row" v-if="selectedItem.analysisResult.confidence">
                  <span class="label">Confidence</span>
                  <span class="value">
                    {{ ((selectedItem.analysisResult.confidence as number) * 100).toFixed(1) }}%
                  </span>
                </div>
                <div class="data-row" v-if="selectedItem.analysisResult.processing_time">
                  <span class="label">Processing Time</span>
                  <span class="value">
                    {{ (selectedItem.analysisResult.processing_time as number).toFixed(2) }}s
                  </span>
                </div>
                <div class="data-row" v-if="selectedItem.analysisResult.device_used">
                  <span class="label">Device</span>
                  <span class="value">{{ selectedItem.analysisResult.device_used }}</span>
                </div>
              </div>

              <button @click="showRawJson = !showRawJson" class="btn-toggle">
                <i :class="showRawJson ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"></i>
                {{ showRawJson ? 'Hide' : 'Show' }} Full Results
              </button>
              <pre v-if="showRawJson" class="json-display">{{ JSON.stringify(selectedItem.analysisResult, null, 2) }}</pre>
            </div>
          </div>
        </div>
        <div class="modal-actions">
          <button @click="$emit('re-analyze', selectedItem); selectedItem = null" class="btn-primary">
            <i class="fas fa-redo"></i>
            Re-analyze
          </button>
          <button @click="downloadItem(selectedItem)" class="btn-secondary">
            <i class="fas fa-download"></i>
            Download
          </button>
          <button @click="$emit('delete', selectedItem.id); selectedItem = null" class="btn-danger">
            <i class="fas fa-trash"></i>
            Delete
          </button>
        </div>
      </div>
    </div>

    <!-- Clear All Confirmation Modal -->
    <div v-if="showClearConfirm" class="confirm-overlay" @click.self="cancelClearAll">
      <div class="confirm-modal">
        <div class="confirm-icon">
          <i class="fas fa-exclamation-triangle"></i>
        </div>
        <h4>Clear All Items?</h4>
        <p>Are you sure you want to clear all {{ items.length }} gallery items? This action cannot be undone.</p>
        <div class="confirm-actions">
          <button @click="cancelClearAll" class="btn-cancel">Cancel</button>
          <button @click="confirmClearAll" class="btn-confirm">Clear All</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useToast } from '@/composables/useToast';
import type { GalleryItem } from '@/utils/VisionMultimodalApiClient';

const { showToast } = useToast();

// Props
const props = defineProps<{
  items: GalleryItem[];
}>();

// Emits
const emit = defineEmits<{
  (e: 're-analyze', item: GalleryItem): void;
  (e: 'delete', itemId: string): void;
  (e: 'clear-all'): void;
}>();

// State
const filterType = ref<string>('');
const selectedItem = ref<GalleryItem | null>(null);
const showRawJson = ref(false);
const showClearConfirm = ref(false);

// Computed
const filteredItems = computed(() => {
  if (!filterType.value) return props.items;
  return props.items.filter(item => item.type === filterType.value);
});

// Methods
const selectItem = (item: GalleryItem) => {
  selectedItem.value = item;
  showRawJson.value = false;
};

const getTypeIcon = (type: string): string => {
  const icons: Record<string, string> = {
    image: 'fas fa-image',
    video: 'fas fa-video',
    screen: 'fas fa-desktop',
  };
  return icons[type] || 'fas fa-file';
};

const truncateFilename = (filename: string, maxLength: number = 20): string => {
  if (filename.length <= maxLength) return filename;
  const ext = filename.split('.').pop() || '';
  const name = filename.slice(0, filename.length - ext.length - 1);
  const truncatedName = name.slice(0, maxLength - ext.length - 4) + '...';
  return `${truncatedName}.${ext}`;
};

const formatDate = (timestamp: number): string => {
  const date = new Date(timestamp);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const formatFullDate = (timestamp: number): string => {
  return new Date(timestamp).toLocaleString();
};

const downloadItem = (item: GalleryItem) => {
  if (!item.analysisResult) {
    showToast('No analysis data to download', 'warning');
    return;
  }

  const dataStr = JSON.stringify(item.analysisResult, null, 2);
  const blob = new Blob([dataStr], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${item.filename.split('.')[0]}_analysis.json`;
  a.click();
  URL.revokeObjectURL(url);
};

const clearAll = () => {
  showClearConfirm.value = true;
};

const confirmClearAll = () => {
  emit('clear-all');
  showClearConfirm.value = false;
  showToast('Gallery cleared', 'success');
};

const cancelClearAll = () => {
  showClearConfirm.value = false;
};

const handleThumbnailError = (event: Event) => {
  const img = event.target as HTMLImageElement;
  img.style.display = 'none';
};
</script>

<style scoped>
.media-gallery {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* Header */
.gallery-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  flex-wrap: wrap;
  gap: 16px;
}

.header-info h3 {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-info p {
  margin: 0;
  font-size: 13px;
  color: var(--text-tertiary);
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.filter-group select {
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text-primary);
}

.btn-clear-all {
  padding: 8px 16px;
  background: var(--color-error-bg);
  color: var(--color-error);
  border: 1px solid var(--color-error);
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-clear-all:hover:not(:disabled) {
  background: var(--color-error);
  color: white;
}

.btn-clear-all:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Gallery Grid */
.gallery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}

.gallery-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s;
}

.gallery-item:hover {
  border-color: var(--color-primary);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.item-thumbnail {
  position: relative;
  height: 140px;
  background: var(--bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
}

.item-thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumbnail-placeholder {
  font-size: 48px;
  color: var(--text-muted);
}

.item-type-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 28px;
  height: 28px;
  background: rgba(0, 0, 0, 0.6);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 12px;
}

.item-info {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.item-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-date {
  font-size: 11px;
  color: var(--text-tertiary);
}

.item-actions {
  display: flex;
  gap: 4px;
  padding: 0 12px 12px;
}

.btn-action {
  flex: 1;
  padding: 8px;
  background: var(--bg-tertiary);
  border: none;
  border-radius: 6px;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.15s;
}

.btn-action:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.btn-action.btn-delete:hover {
  background: var(--color-error-bg);
  color: var(--color-error);
}

/* Empty State */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 80px 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
}

.empty-icon {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  color: var(--text-muted);
}

.empty-state h4 {
  margin: 0;
  font-size: 16px;
  color: var(--text-primary);
}

.empty-state p {
  margin: 0;
  font-size: 13px;
  color: var(--text-tertiary);
  text-align: center;
}

/* Detail Modal */
.detail-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.detail-modal {
  background: var(--bg-secondary);
  border-radius: 12px;
  width: 100%;
  max-width: 600px;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
}

.modal-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.btn-close {
  padding: 8px;
  background: none;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
}

.btn-close:hover {
  color: var(--text-primary);
}

.modal-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.preview-section {
  margin-bottom: 20px;
}

.preview-image {
  width: 100%;
  max-height: 300px;
  object-fit: contain;
  border-radius: 8px;
  background: var(--bg-tertiary);
}

.preview-placeholder {
  width: 100%;
  height: 200px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 64px;
  color: var(--text-muted);
}

.details-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.detail-row .label {
  font-size: 13px;
  color: var(--text-tertiary);
}

.detail-row .value {
  font-size: 13px;
  color: var(--text-primary);
}

.analysis-section {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--border-default);
}

.analysis-section h5 {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.analysis-data {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.data-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border-radius: 6px;
}

.data-row .label {
  font-size: 12px;
  color: var(--text-tertiary);
}

.data-row .value {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
}

.btn-toggle {
  padding: 8px 12px;
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-toggle:hover {
  color: var(--text-secondary);
}

.json-display {
  margin-top: 12px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  font-size: 11px;
  color: var(--text-secondary);
  overflow-x: auto;
  max-height: 200px;
}

.modal-actions {
  display: flex;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid var(--border-default);
}

.btn-primary {
  flex: 1;
  padding: 10px 16px;
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-secondary {
  padding: 10px 16px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

.btn-danger {
  padding: 10px 16px;
  background: var(--color-error-bg);
  color: var(--color-error);
  border: 1px solid var(--color-error);
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-danger:hover {
  background: var(--color-error);
  color: white;
}

/* Confirmation Modal */
.confirm-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1100;
  padding: 20px;
}

.confirm-modal {
  background: var(--bg-secondary);
  border-radius: 12px;
  padding: 24px;
  width: 100%;
  max-width: 360px;
  text-align: center;
}

.confirm-icon {
  width: 48px;
  height: 48px;
  margin: 0 auto 16px;
  background: var(--color-warning-bg);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-warning);
  font-size: 20px;
}

.confirm-modal h4 {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.confirm-modal p {
  margin: 0 0 20px;
  font-size: 13px;
  color: var(--text-secondary);
}

.confirm-actions {
  display: flex;
  gap: 12px;
}

.btn-cancel {
  flex: 1;
  padding: 10px 16px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}

.btn-cancel:hover {
  background: var(--bg-hover);
}

.btn-confirm {
  flex: 1;
  padding: 10px 16px;
  background: var(--color-error);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}

.btn-confirm:hover {
  background: var(--color-error-dark, #c0392b);
}
</style>
