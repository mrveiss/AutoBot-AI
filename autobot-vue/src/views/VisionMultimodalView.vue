<template>
  <div class="vision-multimodal-view">
    <!-- Sidebar Navigation -->
    <aside class="vision-sidebar">
      <div class="sidebar-header">
        <h3><i class="fas fa-eye"></i> Vision & Multimodal</h3>
      </div>

      <!-- Category Navigation -->
      <nav class="category-nav">
        <div
          class="category-item"
          :class="{ active: activeSection === 'overview' }"
          @click="activeSection = 'overview'"
        >
          <i class="fas fa-tachometer-alt"></i>
          <span>Overview</span>
        </div>

        <div class="category-divider">
          <span>Analysis</span>
        </div>

        <div
          class="category-item"
          :class="{ active: activeSection === 'image-analysis' }"
          @click="activeSection = 'image-analysis'"
        >
          <i class="fas fa-image"></i>
          <span>Image Analysis</span>
        </div>

        <div
          class="category-item"
          :class="{ active: activeSection === 'screen-capture' }"
          @click="activeSection = 'screen-capture'"
        >
          <i class="fas fa-desktop"></i>
          <span>Screen Capture</span>
        </div>

        <div
          class="category-item"
          :class="{ active: activeSection === 'video-processing' }"
          @click="activeSection = 'video-processing'"
        >
          <i class="fas fa-video"></i>
          <span>Video Processing</span>
        </div>

        <div class="category-divider">
          <span>Automation</span>
        </div>

        <div
          class="category-item"
          :class="{ active: activeSection === 'automation' }"
          @click="activeSection = 'automation'"
        >
          <i class="fas fa-robot"></i>
          <span>GUI Automation</span>
          <span class="count" v-if="automationOpportunitiesCount > 0">
            {{ automationOpportunitiesCount }}
          </span>
        </div>

        <div class="category-divider">
          <span>History</span>
        </div>

        <div
          class="category-item"
          :class="{ active: activeSection === 'gallery' }"
          @click="activeSection = 'gallery'"
        >
          <i class="fas fa-images"></i>
          <span>Media Gallery</span>
          <span class="count" v-if="galleryCount > 0">{{ galleryCount }}</span>
        </div>

        <div
          class="category-item"
          :class="{ active: activeSection === 'performance' }"
          @click="activeSection = 'performance'"
        >
          <i class="fas fa-chart-line"></i>
          <span>Performance</span>
        </div>
      </nav>

      <!-- Quick Actions -->
      <div class="sidebar-actions">
        <button @click="loadAllData" class="btn-refresh" :disabled="loading">
          <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
          Refresh
        </button>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="vision-content">
      <!-- Header -->
      <header class="content-header">
        <div class="header-left">
          <h2>{{ sectionTitle }}</h2>
          <span class="subtitle">{{ sectionDescription }}</span>
        </div>
        <div class="header-actions">
          <div class="status-badge" :class="systemStatus">
            <i :class="statusIcon"></i>
            <span>{{ statusLabel }}</span>
          </div>
        </div>
      </header>

      <!-- Loading State -->
      <div v-if="loading && !hasData" class="loading-container">
        <LoadingSpinner size="lg" />
        <p>Loading vision services...</p>
      </div>

      <!-- Error State -->
      <div v-else-if="error" class="error-container">
        <div class="error-icon">
          <i class="fas fa-exclamation-triangle"></i>
        </div>
        <h3>Failed to Load Data</h3>
        <p>{{ error }}</p>
        <button @click="loadAllData" class="btn-primary">
          <i class="fas fa-redo"></i> Retry
        </button>
      </div>

      <!-- Content Sections -->
      <div v-else class="content-body">
        <!-- Overview Section -->
        <section v-if="activeSection === 'overview'" class="section-overview">
          <div class="stats-grid">
            <div class="stat-card" :class="{ active: visionHealthy }">
              <div class="stat-icon" :class="visionHealthy ? 'healthy' : 'unhealthy'">
                <i class="fas fa-eye"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ visionHealthy ? 'Ready' : 'Offline' }}</span>
                <span class="stat-label">Vision Service</span>
              </div>
            </div>

            <div class="stat-card" :class="{ active: multimodalHealthy }">
              <div class="stat-icon" :class="multimodalHealthy ? 'healthy' : 'unhealthy'">
                <i class="fas fa-brain"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ multimodalHealthy ? 'Ready' : 'Offline' }}</span>
                <span class="stat-label">Multimodal Service</span>
              </div>
            </div>

            <div class="stat-card" :class="{ active: gpuAvailable }">
              <div class="stat-icon" :class="gpuAvailable ? 'healthy' : 'warning'">
                <i class="fas fa-microchip"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ gpuAvailable ? 'GPU' : 'CPU' }}</span>
                <span class="stat-label">Processing Device</span>
              </div>
            </div>

            <div class="stat-card">
              <div class="stat-icon">
                <i class="fas fa-cube"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ supportedElementTypes }}</span>
                <span class="stat-label">Element Types</span>
              </div>
            </div>
          </div>

          <div class="overview-sections">
            <!-- Capabilities Card -->
            <div class="overview-card">
              <h4><i class="fas fa-list-check"></i> Capabilities</h4>
              <div class="capabilities-grid">
                <div
                  v-for="capability in capabilities"
                  :key="capability.name"
                  class="capability-item"
                  :class="{ enabled: capability.enabled }"
                >
                  <i :class="capability.icon"></i>
                  <span>{{ capability.name }}</span>
                  <i :class="capability.enabled ? 'fas fa-check-circle' : 'fas fa-times-circle'"></i>
                </div>
              </div>
            </div>

            <!-- Quick Actions Card -->
            <div class="overview-card">
              <h4><i class="fas fa-bolt"></i> Quick Actions</h4>
              <div class="quick-actions-grid">
                <button class="quick-action" @click="activeSection = 'image-analysis'">
                  <i class="fas fa-upload"></i>
                  <span>Upload Image</span>
                </button>
                <button class="quick-action" @click="activeSection = 'screen-capture'">
                  <i class="fas fa-camera"></i>
                  <span>Capture Screen</span>
                </button>
                <button class="quick-action" @click="activeSection = 'automation'">
                  <i class="fas fa-magic"></i>
                  <span>Find Actions</span>
                </button>
                <button class="quick-action" @click="activeSection = 'gallery'">
                  <i class="fas fa-history"></i>
                  <span>View History</span>
                </button>
              </div>
            </div>

            <!-- Model Availability Card -->
            <div class="overview-card" v-if="multimodalStats">
              <h4><i class="fas fa-cubes"></i> Model Availability</h4>
              <div class="models-grid">
                <div class="model-item" :class="{ available: visionModelsAvailable }">
                  <i class="fas fa-eye"></i>
                  <span>Vision Models</span>
                  <span class="status">{{ visionModelsAvailable ? 'Available' : 'Unavailable' }}</span>
                </div>
                <div class="model-item" :class="{ available: audioModelsAvailable }">
                  <i class="fas fa-microphone"></i>
                  <span>Audio Models</span>
                  <span class="status">{{ audioModelsAvailable ? 'Available' : 'Unavailable' }}</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- Image Analysis Section -->
        <section v-if="activeSection === 'image-analysis'" class="section-image-analysis">
          <ImageAnalyzer
            @analysis-complete="handleAnalysisComplete"
            @add-to-gallery="addToGallery"
          />
        </section>

        <!-- Screen Capture Section -->
        <section v-if="activeSection === 'screen-capture'" class="section-screen-capture">
          <ScreenCaptureViewer
            @analysis-complete="handleAnalysisComplete"
            @add-to-gallery="addToGallery"
          />
        </section>

        <!-- Video Processing Section -->
        <section v-if="activeSection === 'video-processing'" class="section-video-processing">
          <VideoProcessor
            @analysis-complete="handleAnalysisComplete"
            @add-to-gallery="addToGallery"
          />
        </section>

        <!-- GUI Automation Section -->
        <section v-if="activeSection === 'automation'" class="section-automation">
          <GUIAutomationControls
            :opportunities="automationOpportunities"
            :loading="automationLoading"
            @refresh="loadAutomationOpportunities"
          />
        </section>

        <!-- Media Gallery Section -->
        <section v-if="activeSection === 'gallery'" class="section-gallery">
          <MediaGallery
            :items="galleryItems"
            @re-analyze="handleReAnalyze"
            @delete="handleDeleteFromGallery"
            @clear-all="handleClearGallery"
          />
        </section>

        <!-- Performance Section -->
        <section v-if="activeSection === 'performance'" class="section-performance">
          <div class="performance-content">
            <div class="performance-header">
              <h3>Performance Metrics</h3>
              <button @click="loadPerformanceStats" class="btn-refresh-sm" :disabled="performanceLoading">
                <i class="fas fa-sync-alt" :class="{ 'fa-spin': performanceLoading }"></i>
              </button>
            </div>

            <div v-if="performanceLoading" class="loading-inline">
              <LoadingSpinner size="sm" />
              <span>Loading performance data...</span>
            </div>

            <div v-else-if="performanceStats" class="performance-grid">
              <div class="perf-card">
                <h4>GPU Status</h4>
                <div class="perf-details">
                  <div class="perf-item">
                    <span class="label">Available</span>
                    <span class="value" :class="gpuAvailable ? 'success' : 'warning'">
                      {{ gpuAvailable ? 'Yes' : 'No' }}
                    </span>
                  </div>
                  <div class="perf-item" v-if="gpuStats.gpu_device_name">
                    <span class="label">Device</span>
                    <span class="value">{{ gpuStats.gpu_device_name }}</span>
                  </div>
                  <div class="perf-item" v-if="gpuStats.gpu_memory_allocated_mb">
                    <span class="label">Memory Used</span>
                    <span class="value">{{ gpuStats.gpu_memory_allocated_mb.toFixed(1) }} MB</span>
                  </div>
                </div>
              </div>

              <div class="perf-card">
                <h4>Optimization</h4>
                <div class="perf-details">
                  <div class="perf-item">
                    <span class="label">Mixed Precision</span>
                    <span class="value" :class="mixedPrecisionEnabled ? 'success' : 'muted'">
                      {{ mixedPrecisionEnabled ? 'Enabled' : 'Disabled' }}
                    </span>
                  </div>
                  <div class="perf-item">
                    <span class="label">Auto Optimization</span>
                    <span class="value success">Enabled</span>
                  </div>
                </div>
              </div>

              <div class="perf-card full-width">
                <h4>Actions</h4>
                <div class="perf-actions">
                  <button @click="triggerOptimization" class="btn-secondary" :disabled="optimizing">
                    <i class="fas fa-bolt"></i>
                    {{ optimizing ? 'Optimizing...' : 'Optimize Performance' }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { createLogger } from '@/utils/debugUtils';
import { useToast } from '@/composables/useToast';
import {
  visionMultimodalApiClient,
  type VisionHealthResponse,
  type VisionStatusResponse,
  type MultimodalStats,
  type AutomationOpportunity,
  type PerformanceStats,
  type GPUStats,
  type GalleryItem,
  type MultiModalResponse,
  type ScreenAnalysisResponse,
} from '@/utils/VisionMultimodalApiClient';
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue';
import ImageAnalyzer from '@/components/vision/ImageAnalyzer.vue';
import ScreenCaptureViewer from '@/components/vision/ScreenCaptureViewer.vue';
import VideoProcessor from '@/components/vision/VideoProcessor.vue';
import GUIAutomationControls from '@/components/vision/GUIAutomationControls.vue';
import MediaGallery from '@/components/vision/MediaGallery.vue';

const logger = createLogger('VisionMultimodalView');
const { showToast } = useToast();

// Section Types
type SectionType =
  | 'overview'
  | 'image-analysis'
  | 'screen-capture'
  | 'video-processing'
  | 'automation'
  | 'gallery'
  | 'performance';

// State
const loading = ref(false);
const error = ref<string | null>(null);
const activeSection = ref<SectionType>('overview');

// Vision State
const visionHealth = ref<VisionHealthResponse | null>(null);
const visionStatus = ref<VisionStatusResponse | null>(null);

// Multimodal State
const multimodalStats = ref<MultimodalStats | null>(null);

// Automation State
const automationOpportunities = ref<AutomationOpportunity[]>([]);
const automationLoading = ref(false);

// Performance State
const performanceStats = ref<PerformanceStats | null>(null);
const performanceLoading = ref(false);
const optimizing = ref(false);

// Gallery State
const galleryItems = ref<GalleryItem[]>([]);

// Computed
const hasData = computed(() => visionHealth.value !== null || multimodalStats.value !== null);

const visionHealthy = computed(() => visionHealth.value?.status === 'healthy');

const multimodalHealthy = computed(
  () => multimodalStats.value?.system_status === 'healthy'
);

const gpuAvailable = computed(() => multimodalStats.value?.gpu_available ?? false);

const gpuStats = computed<GPUStats>(() => multimodalStats.value?.gpu_stats ?? {
  gpu_memory_allocated_mb: 0,
  gpu_memory_reserved_mb: 0,
  gpu_device_count: 0,
  gpu_device_name: null,
});

const mixedPrecisionEnabled = computed(
  () => performanceStats.value?.optimization_status?.mixed_precision_enabled ?? false
);

const visionModelsAvailable = computed(
  () => multimodalStats.value?.vision_models_available ?? false
);

const audioModelsAvailable = computed(
  () => multimodalStats.value?.audio_models_available ?? false
);

const supportedElementTypes = computed(
  () => visionStatus.value?.supported_element_types ?? 0
);

const automationOpportunitiesCount = computed(() => automationOpportunities.value.length);

const galleryCount = computed(() => galleryItems.value.length);

const systemStatus = computed(() => {
  if (visionHealthy.value && multimodalHealthy.value) return 'healthy';
  if (visionHealthy.value || multimodalHealthy.value) return 'degraded';
  return 'unhealthy';
});

const statusIcon = computed(() => {
  const icons: Record<string, string> = {
    healthy: 'fas fa-check-circle',
    degraded: 'fas fa-exclamation-triangle',
    unhealthy: 'fas fa-times-circle',
  };
  return icons[systemStatus.value] || 'fas fa-question';
});

const statusLabel = computed(() => {
  const labels: Record<string, string> = {
    healthy: 'All Systems Online',
    degraded: 'Partial Availability',
    unhealthy: 'Services Offline',
  };
  return labels[systemStatus.value] || 'Unknown';
});

const sectionTitle = computed(() => {
  const titles: Record<SectionType, string> = {
    overview: 'Vision & Multimodal Overview',
    'image-analysis': 'Image Analysis',
    'screen-capture': 'Screen Capture Analysis',
    'video-processing': 'Video Processing',
    automation: 'GUI Automation',
    gallery: 'Media Gallery',
    performance: 'Performance Metrics',
  };
  return titles[activeSection.value] || 'Vision & Multimodal';
});

const sectionDescription = computed(() => {
  const descriptions: Record<SectionType, string> = {
    overview: 'Monitor vision and multimodal processing services',
    'image-analysis': 'Upload and analyze images with AI vision models',
    'screen-capture': 'Capture and analyze screen content in real-time',
    'video-processing': 'Process video files and extract frame analysis',
    automation: 'Discover and execute GUI automation opportunities',
    gallery: 'View history of processed media and results',
    performance: 'Monitor processing performance and GPU utilization',
  };
  return descriptions[activeSection.value] || '';
});

const capabilities = computed(() => {
  const features = visionStatus.value?.features;
  return [
    {
      name: 'Screen Analysis',
      icon: 'fas fa-desktop',
      enabled: features?.screen_analysis ?? false,
    },
    {
      name: 'Element Detection',
      icon: 'fas fa-object-group',
      enabled: features?.element_detection ?? false,
    },
    {
      name: 'OCR Extraction',
      icon: 'fas fa-font',
      enabled: features?.ocr_extraction ?? false,
    },
    {
      name: 'Template Matching',
      icon: 'fas fa-clone',
      enabled: features?.template_matching ?? false,
    },
    {
      name: 'Multimodal Processing',
      icon: 'fas fa-layer-group',
      enabled: features?.multimodal_processing ?? false,
    },
  ];
});

// Methods
const loadAllData = async () => {
  loading.value = true;
  error.value = null;

  try {
    await Promise.all([
      loadVisionHealth(),
      loadVisionStatus(),
      loadMultimodalStats(),
    ]);
    logger.debug('All data loaded successfully');
  } catch (err) {
    logger.error('Failed to load data:', err);
    error.value = err instanceof Error ? err.message : 'Failed to load vision services data';
  } finally {
    loading.value = false;
  }
};

const loadVisionHealth = async () => {
  const response = await visionMultimodalApiClient.getVisionHealth();
  if (response.success && response.data) {
    visionHealth.value = response.data;
    logger.debug('Vision health loaded:', response.data);
  }
};

const loadVisionStatus = async () => {
  const response = await visionMultimodalApiClient.getVisionStatus();
  if (response.success && response.data) {
    visionStatus.value = response.data;
    logger.debug('Vision status loaded:', response.data);
  }
};

const loadMultimodalStats = async () => {
  const response = await visionMultimodalApiClient.getMultimodalStats();
  if (response.success && response.data) {
    multimodalStats.value = response.data;
    logger.debug('Multimodal stats loaded:', response.data);
  }
};

const loadAutomationOpportunities = async () => {
  automationLoading.value = true;
  try {
    const response = await visionMultimodalApiClient.getAutomationOpportunities();
    if (response.success && response.data) {
      automationOpportunities.value = response.data.opportunities;
      logger.debug('Automation opportunities loaded:', response.data);
    }
  } catch (err) {
    logger.error('Failed to load automation opportunities:', err);
    showToast('Failed to load automation opportunities', 'error');
  } finally {
    automationLoading.value = false;
  }
};

const loadPerformanceStats = async () => {
  performanceLoading.value = true;
  try {
    const response = await visionMultimodalApiClient.getPerformanceStats();
    if (response.success && response.data) {
      performanceStats.value = response.data;
      logger.debug('Performance stats loaded:', response.data);
    }
  } catch (err) {
    logger.error('Failed to load performance stats:', err);
    showToast('Failed to load performance stats', 'error');
  } finally {
    performanceLoading.value = false;
  }
};

const triggerOptimization = async () => {
  optimizing.value = true;
  try {
    const response = await visionMultimodalApiClient.optimizePerformance();
    if (response.success) {
      showToast('Performance optimization completed', 'success');
      await loadPerformanceStats();
    } else {
      showToast(response.error || 'Optimization failed', 'error');
    }
  } catch (err) {
    logger.error('Failed to trigger optimization:', err);
    showToast('Failed to trigger optimization', 'error');
  } finally {
    optimizing.value = false;
  }
};

const handleAnalysisComplete = (result: MultiModalResponse | ScreenAnalysisResponse | Record<string, unknown>) => {
  logger.debug('Analysis complete:', result);
  showToast('Analysis completed successfully', 'success');
};

const addToGallery = (item: GalleryItem) => {
  galleryItems.value.unshift(item);
  // Persist to localStorage
  saveGalleryToStorage();
  logger.debug('Added to gallery:', item);
};

const handleReAnalyze = (item: GalleryItem) => {
  logger.debug('Re-analyzing item:', item);
  // Navigate to appropriate section based on type
  if (item.type === 'image') {
    activeSection.value = 'image-analysis';
  } else if (item.type === 'screen') {
    activeSection.value = 'screen-capture';
  } else if (item.type === 'video') {
    activeSection.value = 'video-processing';
  }
};

const handleDeleteFromGallery = (itemId: string) => {
  galleryItems.value = galleryItems.value.filter(item => item.id !== itemId);
  saveGalleryToStorage();
  showToast('Item removed from gallery', 'success');
};

const handleClearGallery = () => {
  galleryItems.value = [];
  saveGalleryToStorage();
};

const saveGalleryToStorage = () => {
  try {
    localStorage.setItem('vision-gallery', JSON.stringify(galleryItems.value));
  } catch (err) {
    logger.error('Failed to save gallery to storage:', err);
  }
};

const loadGalleryFromStorage = () => {
  try {
    const stored = localStorage.getItem('vision-gallery');
    if (stored) {
      galleryItems.value = JSON.parse(stored);
    }
  } catch (err) {
    logger.error('Failed to load gallery from storage:', err);
  }
};

// Lifecycle
onMounted(() => {
  loadAllData();
  loadGalleryFromStorage();
});

onUnmounted(() => {
  // Cleanup if needed
});
</script>

<style scoped>
.vision-multimodal-view {
  display: flex;
  height: 100%;
  min-height: 0;
  background: var(--bg-primary);
}

/* Sidebar */
.vision-sidebar {
  width: 260px;
  min-width: 260px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  padding: 20px;
  border-bottom: 1px solid var(--border-default);
}

.sidebar-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.sidebar-header i {
  color: var(--color-primary);
}

.category-nav {
  flex: 1;
  overflow-y: auto;
  padding: 12px 0;
}

.category-divider {
  padding: 12px 20px 8px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
}

.category-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px;
  cursor: pointer;
  transition: all 0.15s;
  color: var(--text-secondary);
}

.category-item:hover {
  background: var(--bg-hover);
}

.category-item.active {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.category-item i {
  width: 20px;
  text-align: center;
  font-size: 14px;
}

.category-item span:first-of-type:not(.count) {
  flex: 1;
  font-size: 14px;
}

.category-item .count {
  font-size: 12px;
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: 10px;
  color: var(--text-tertiary);
}

.category-item.active .count {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.sidebar-actions {
  padding: 16px 20px;
  border-top: 1px solid var(--border-default);
}

.btn-refresh {
  width: 100%;
  padding: 10px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-refresh:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-refresh:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Main Content */
.vision-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.content-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.header-left h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-left .subtitle {
  font-size: 13px;
  color: var(--text-tertiary);
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
}

.status-badge.healthy {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.status-badge.degraded {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.status-badge.unhealthy {
  background: var(--color-error-bg);
  color: var(--color-error);
}

/* Loading & Error States */
.loading-container,
.error-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  color: var(--text-tertiary);
  padding: 40px;
}

.error-container .error-icon {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--color-error-bg);
  color: var(--color-error);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
}

.error-container h3 {
  margin: 0;
  color: var(--text-primary);
}

.error-container p {
  margin: 0;
  color: var(--text-secondary);
}

/* Content Body */
.content-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

/* Overview Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  transition: all 0.2s;
}

.stat-card.active {
  border-color: var(--color-success);
}

.stat-card .stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  background: var(--bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: var(--text-secondary);
}

.stat-card .stat-icon.healthy {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.stat-card .stat-icon.unhealthy {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.stat-card .stat-icon.warning {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.stat-label {
  font-size: 13px;
  color: var(--text-tertiary);
}

/* Overview Sections */
.overview-sections {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.overview-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
}

.overview-card h4 {
  margin: 0 0 16px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.overview-card h4 i {
  color: var(--color-primary);
}

/* Capabilities Grid */
.capabilities-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

.capability-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  color: var(--text-muted);
}

.capability-item.enabled {
  color: var(--text-secondary);
}

.capability-item i:first-child {
  width: 20px;
  text-align: center;
}

.capability-item span {
  flex: 1;
  font-size: 13px;
}

.capability-item i:last-child {
  color: var(--color-error);
}

.capability-item.enabled i:last-child {
  color: var(--color-success);
}

/* Quick Actions Grid */
.quick-actions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
}

.quick-action {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  color: var(--text-secondary);
}

.quick-action:hover {
  background: var(--bg-hover);
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.quick-action i {
  font-size: 20px;
}

.quick-action span {
  font-size: 13px;
  font-weight: 500;
}

/* Models Grid */
.models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.model-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  color: var(--text-muted);
}

.model-item.available {
  color: var(--text-secondary);
}

.model-item i {
  width: 24px;
  text-align: center;
  font-size: 16px;
}

.model-item span:first-of-type {
  flex: 1;
  font-size: 14px;
}

.model-item .status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--color-error-bg);
  color: var(--color-error);
}

.model-item.available .status {
  background: var(--color-success-bg);
  color: var(--color-success);
}

/* Performance Section */
.performance-content {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 24px;
}

.performance-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.performance-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.btn-refresh-sm {
  padding: 8px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-refresh-sm:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-refresh-sm:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.loading-inline {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px;
  color: var(--text-tertiary);
}

.performance-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
}

.perf-card {
  background: var(--bg-tertiary);
  border-radius: 8px;
  padding: 16px;
}

.perf-card.full-width {
  grid-column: 1 / -1;
}

.perf-card h4 {
  margin: 0 0 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.perf-details {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.perf-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.perf-item .label {
  font-size: 13px;
  color: var(--text-tertiary);
}

.perf-item .value {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.perf-item .value.success {
  color: var(--color-success);
}

.perf-item .value.warning {
  color: var(--color-warning);
}

.perf-item .value.muted {
  color: var(--text-muted);
}

.perf-actions {
  display: flex;
  gap: 12px;
}

/* Buttons */
.btn-primary {
  padding: 10px 20px;
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-secondary {
  padding: 10px 20px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Responsive */
@media (max-width: 768px) {
  .vision-multimodal-view {
    flex-direction: column;
  }

  .vision-sidebar {
    width: 100%;
    min-width: 100%;
    max-height: 50vh;
  }

  .stats-grid {
    grid-template-columns: 1fr 1fr;
  }

  .performance-grid {
    grid-template-columns: 1fr;
  }
}
</style>
