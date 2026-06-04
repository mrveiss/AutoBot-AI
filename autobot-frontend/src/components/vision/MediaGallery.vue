<template>
  <div class="media-gallery">
    <!-- Header -->
    <div class="gallery-header">
      <div class="header-info">
        <h3>{{ t('vision.mediaGallery.title') }}</h3>
        <p>{{ t('vision.mediaGallery.subtitle') }}</p>
      </div>
      <div class="header-actions">
        <div class="filter-group">
          <select v-model="filterType">
            <option value="">{{ t('vision.mediaGallery.allTypes') }}</option>
            <option value="image">{{ t('vision.mediaGallery.images') }}</option>
            <option value="video">{{ t('vision.mediaGallery.videos') }}</option>
            <option value="screen">{{ t('vision.mediaGallery.screenCaptures') }}</option>
          </select>
        </div>
        <button @click="clearAll" class="btn-clear-all" :disabled="items.length === 0">
          <Icon name="trash" />
          {{ t('vision.mediaGallery.clearAll') }}
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
            loading="lazy"
            @error="handleThumbnailError"
          />
          <div v-else class="thumbnail-placeholder">
            <Icon :name="getTypeIcon(item.type)" />
          </div>
          <div class="item-type-badge">
            <Icon :name="getTypeIcon(item.type)" />
          </div>
        </div>
        <div class="item-info">
          <span class="item-name" :title="item.filename">{{ truncateFilename(item.filename) }}</span>
          <span class="item-date">{{ formatDate(item.timestamp) }}</span>
        </div>
        <div class="item-actions">
          <button @click.stop="$emit('re-analyze', item)" class="btn-action" :title="t('vision.mediaGallery.reAnalyze')">
            <Icon name="redo" />
          </button>
          <button @click.stop="downloadItem(item)" class="btn-action" :title="t('vision.mediaGallery.download')">
            <Icon name="download" />
          </button>
          <button @click.stop="deleteItem(item.id)" class="btn-action btn-delete" :title="t('vision.mediaGallery.deleteItem')">
            <Icon name="trash" />
          </button>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else class="empty-state">
      <div class="empty-icon">
        <Icon name="image" />
      </div>
      <h4>{{ t('vision.mediaGallery.noMediaItems') }}</h4>
      <p v-if="filterType">{{ t('vision.mediaGallery.noFilterResults', { type: filterType }) }}</p>
      <p v-else>{{ t('vision.mediaGallery.noMediaHint') }}</p>
    </div>

    <!-- Detail Modal -->
    <div v-if="selectedItem" class="detail-overlay" @click.self="selectedItem = null">
      <div class="detail-modal">
        <div class="modal-header">
          <h4>{{ selectedItem.filename }}</h4>
          <button @click="selectedItem = null" class="btn-close">
            <Icon name="times" />
          </button>
        </div>
        <div class="modal-content">
          <div class="preview-section">
            <img
              v-if="selectedItem.thumbnail"
              :src="selectedItem.thumbnail"
              :alt="selectedItem.filename"
              class="preview-image"
              loading="lazy"
            />
            <div v-else class="preview-placeholder">
              <Icon :name="getTypeIcon(selectedItem.type)" />
            </div>
          </div>

          <div class="details-section">
            <div class="detail-row">
              <span class="label">{{ t('vision.mediaGallery.type') }}</span>
              <span class="value">{{ selectedItem.type }}</span>
            </div>
            <div class="detail-row">
              <span class="label">{{ t('vision.mediaGallery.filename') }}</span>
              <span class="value">{{ selectedItem.filename }}</span>
            </div>
            <div class="detail-row">
              <span class="label">{{ t('vision.mediaGallery.date') }}</span>
              <span class="value">{{ formatFullDate(selectedItem.timestamp) }}</span>
            </div>

            <div v-if="selectedItem.analysisResult" class="analysis-section">
              <h5>{{ t('vision.mediaGallery.analysisResults') }}</h5>
              <div class="analysis-data">
                <div class="data-row" v-if="selectedItem.analysisResult.confidence">
                  <span class="label">{{ t('vision.mediaGallery.confidenceLabel') }}</span>
                  <span class="value">
                    {{ ((selectedItem.analysisResult.confidence as number) * 100).toFixed(1) }}%
                  </span>
                </div>
                <div class="data-row" v-if="selectedItem.analysisResult.processing_time">
                  <span class="label">{{ t('vision.mediaGallery.processingTime') }}</span>
                  <span class="value">
                    {{ (selectedItem.analysisResult.processing_time as number).toFixed(2) }}s
                  </span>
                </div>
                <div class="data-row" v-if="selectedItem.analysisResult.device_used">
                  <span class="label">{{ t('vision.mediaGallery.device') }}</span>
                  <span class="value">{{ selectedItem.analysisResult.device_used }}</span>
                </div>
              </div>

              <button @click="showRawJson = !showRawJson" class="btn-toggle">
                <Icon :name="showRawJson ? 'chevron-up' : 'chevron-down'" />
                {{ showRawJson ? t('vision.mediaGallery.hideFullResults') : t('vision.mediaGallery.showFullResults') }}
              </button>
              <pre v-if="showRawJson" class="json-display">{{ JSON.stringify(selectedItem.analysisResult, null, 2) }}</pre>
            </div>
          </div>
        </div>
        <div class="modal-actions">
          <button @click="$emit('re-analyze', selectedItem); selectedItem = null" class="btn-primary">
            <Icon name="redo" />
            {{ t('vision.mediaGallery.reAnalyze') }}
          </button>
          <button @click="downloadItem(selectedItem)" class="btn-secondary">
            <Icon name="download" />
            {{ t('vision.mediaGallery.download') }}
          </button>
          <button @click="deleteItem(selectedItem.id); selectedItem = null" class="btn-danger">
            <Icon name="trash" />
            {{ t('vision.mediaGallery.deleteItem') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Clear All Confirmation Modal -->
    <div v-if="showClearConfirm" class="confirm-overlay" @click.self="cancelClearAll">
      <div class="confirm-modal">
        <div class="confirm-icon">
          <Icon name="exclamation-triangle" />
        </div>
        <h4>{{ t('vision.mediaGallery.clearAllConfirmTitle') }}</h4>
        <p>{{ t('vision.mediaGallery.clearAllConfirmMsg', { count: items.length }) }}</p>
        <div class="confirm-actions">
          <button @click="cancelClearAll" class="btn-cancel">{{ t('vision.mediaGallery.cancelBtn') }}</button>
          <button @click="confirmClearAll" class="btn-confirm">{{ t('vision.mediaGallery.clearAllConfirm') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onUnmounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useNotificationBus } from '@/composables/useNotificationBus';
import { useThumbnailWorker } from '@/composables/useThumbnailWorker';
import type { GalleryItem } from '@/utils/VisionMultimodalApiClient';

const { t } = useI18n();
const { showToast } = useNotificationBus();
const { revokeBlobUrl } = useThumbnailWorker();

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
    image: 'image',
    video: 'video',
    screen: 'desktop',
  };
  return icons[type] || 'file';
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
    showToast(t('vision.mediaGallery.toastNoAnalysisData'), 'warning');
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
  showToast(t('vision.mediaGallery.toastGalleryCleared'), 'success');
};

const cancelClearAll = () => {
  showClearConfirm.value = false;
};

const handleThumbnailError = (event: Event) => {
  const img = event.target as HTMLImageElement;
  img.style.display = 'none';
};

const deleteItem = (itemId: string) => {
  const item = props.items.find(i => i.id === itemId);
  if (item?.thumbnail && item.thumbnail.startsWith('blob:')) {
    revokeBlobUrl(item.thumbnail);
  }
  emit('delete', itemId);
};

// Cleanup blob URLs when component unmounts
onUnmounted(() => {
  props.items.forEach(item => {
    if (item.thumbnail && item.thumbnail.startsWith('blob:')) {
      revokeBlobUrl(item.thumbnail);
    }
  });
});
</script>

<style scoped>
.media-gallery {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5);
}

/* Header */
.gallery-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-5);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  flex-wrap: wrap;
  gap: var(--spacing-4);
}

.header-info h3 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-1);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.header-info p {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.header-actions {
  display: flex;
  gap: var(--spacing-3);
  align-items: center;
}

.filter-group select {
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.btn-clear-all {
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--color-error-bg);
  color: var(--color-error);
  border: 1px solid var(--color-error);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  transition: all var(--duration-200);
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
  gap: var(--spacing-4);
}

.gallery-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  overflow: hidden;
  cursor: pointer;
  transition: all var(--duration-200);
}

.gallery-item:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-md);
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
  font-size: var(--text-5xl);
  color: var(--text-muted);
}

.item-type-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 28px;
  height: 28px;
  background: rgba(0, 0, 0, 0.6);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: var(--text-xs);
}

.item-info {
  padding: var(--spacing-3);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.item-name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-date {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.item-actions {
  display: flex;
  gap: var(--spacing-1);
  padding: var(--spacing-0) var(--spacing-3) var(--spacing-3);
}

.btn-action {
  flex: 1;
  padding: var(--spacing-2);
  background: var(--bg-tertiary);
  border: none;
  border-radius: var(--radius-md);
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all var(--duration-150);
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
  gap: var(--spacing-4);
  padding: var(--spacing-20) var(--spacing-5);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
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
  margin: var(--spacing-0);
  font-size: var(--text-base);
  color: var(--text-primary);
}

.empty-state p {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
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
  z-index: var(--z-modal);
  padding: var(--spacing-5);
}

.detail-modal {
  background: var(--bg-secondary);
  border-radius: var(--radius-xl);
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
  padding: var(--spacing-4) var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
}

.modal-header h4 {
  margin: var(--spacing-0);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.btn-close {
  padding: var(--spacing-2);
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
  padding: var(--spacing-5);
}

.preview-section {
  margin-bottom: var(--spacing-5);
}

.preview-image {
  width: 100%;
  max-height: 300px;
  object-fit: contain;
  border-radius: var(--radius-lg);
  background: var(--bg-tertiary);
}

.preview-placeholder {
  width: 100%;
  height: 200px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 64px;
  color: var(--text-muted);
}

.details-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.detail-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.detail-row .label {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.detail-row .value {
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.analysis-section {
  margin-top: var(--spacing-5);
  padding-top: var(--spacing-5);
  border-top: 1px solid var(--border-default);
}

.analysis-section h5 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-3);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.analysis-data {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-3);
}

.data-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
}

.data-row .label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.data-row .value {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--text-primary);
}

.btn-toggle {
  padding: var(--spacing-2) var(--spacing-3);
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: var(--text-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.btn-toggle:hover {
  color: var(--text-secondary);
}

.json-display {
  margin-top: var(--spacing-3);
  padding: var(--spacing-3);
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  overflow-x: auto;
  max-height: 200px;
}

.modal-actions {
  display: flex;
  gap: var(--spacing-3);
  padding: var(--spacing-4) var(--spacing-5);
  border-top: 1px solid var(--border-default);
}

.btn-primary {
  flex: 1;
  padding: var(--spacing-2-5) var(--spacing-4);
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-secondary {
  padding: var(--spacing-2-5) var(--spacing-4);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

.btn-danger {
  padding: var(--spacing-2-5) var(--spacing-4);
  background: var(--color-error-bg);
  color: var(--color-error);
  border: 1px solid var(--color-error);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
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
  z-index: var(--z-popover);
  padding: var(--spacing-5);
}

.confirm-modal {
  background: var(--bg-secondary);
  border-radius: var(--radius-xl);
  padding: var(--spacing-6);
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
  font-size: var(--text-xl);
}

.confirm-modal h4 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.confirm-modal p {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-5);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.confirm-actions {
  display: flex;
  gap: var(--spacing-3);
}

.btn-cancel {
  flex: 1;
  padding: var(--spacing-2-5) var(--spacing-4);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
}

.btn-cancel:hover {
  background: var(--bg-hover);
}

.btn-confirm {
  flex: 1;
  padding: var(--spacing-2-5) var(--spacing-4);
  background: var(--color-error);
  color: white;
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
}

.btn-confirm:hover {
  background: var(--color-error-dark, #c0392b);
}
</style>
