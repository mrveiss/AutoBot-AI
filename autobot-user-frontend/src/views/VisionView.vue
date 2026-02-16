<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  Vision & Multimodal AI View

  Container view for vision analysis, image processing, and automation features.
  Issue #777: Frontend for Vision & Multimodal AI Features.
-->
<template>
  <div class="vision-view">
    <!-- Sidebar Navigation - Issue #901: Technical Precision Design -->
    <aside class="vision-sidebar">
      <div class="sidebar-header">
        <h3>
          <svg class="header-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
          </svg>
          Vision & AI
        </h3>
      </div>

      <nav class="sidebar-nav">
        <router-link
          to="/vision/analyze"
          class="nav-item"
          :class="{ active: $route.path === '/vision/analyze' }"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path>
          </svg>
          <span>Screen Analysis</span>
        </router-link>

        <router-link
          to="/vision/image"
          class="nav-item"
          :class="{ active: $route.path === '/vision/image' }"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path>
          </svg>
          <span>Image Processing</span>
        </router-link>

        <router-link
          to="/vision/automation"
          class="nav-item"
          :class="{ active: $route.path === '/vision/automation' }"
        >
          <svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"></path>
          </svg>
          <span>Automation</span>
        </router-link>
      </nav>

      <!-- Service Status -->
      <div class="sidebar-footer">
        <div class="status-indicator" :class="statusClass">
          <div class="status-dot"></div>
          <span>{{ statusText }}</span>
        </div>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="vision-content">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { createLogger } from '@/utils/debugUtils';
import { visionMultimodalApiClient } from '@/utils/VisionMultimodalApiClient';

const logger = createLogger('VisionView');

const serviceStatus = ref<'healthy' | 'degraded' | 'offline'>('offline');

const statusClass = computed(() => ({
  healthy: serviceStatus.value === 'healthy',
  degraded: serviceStatus.value === 'degraded',
  offline: serviceStatus.value === 'offline',
}));

const statusText = computed(() => {
  if (serviceStatus.value === 'healthy') return 'Vision service online';
  if (serviceStatus.value === 'degraded') return 'Service degraded';
  return 'Service offline';
});

const checkServiceHealth = async () => {
  try {
    const res = await visionMultimodalApiClient.getVisionHealth();
    if (res.success && res.data?.status === 'healthy') {
      serviceStatus.value = 'healthy';
    } else {
      serviceStatus.value = 'degraded';
    }
  } catch {
    serviceStatus.value = 'offline';
    logger.warn('Vision service health check failed');
  }
};

onMounted(() => {
  checkServiceHealth();
});
</script>

<style scoped>
/* Issue #901: Technical Precision Vision View Design */

.vision-view {
  display: flex;
  height: 100%;
  overflow: hidden;
}

/* Sidebar */
.vision-sidebar {
  width: 260px;
  min-width: 260px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  padding: 20px;
  border-bottom: 1px solid var(--border-default);
}

.sidebar-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-sans);
  display: flex;
  align-items: center;
  gap: 10px;
  line-height: 1.5;
}

.header-icon {
  width: 18px;
  height: 18px;
  color: var(--color-info);
  flex-shrink: 0;
}

.sidebar-nav {
  flex: 1;
  padding: 12px 0;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px;
  border-left: 2px solid transparent;
  font-size: 14px;
  font-weight: 500;
  font-family: var(--font-sans);
  color: var(--text-secondary);
  text-decoration: none;
  transition: all 150ms cubic-bezier(0.4, 0, 0.2, 1);
}

.nav-item:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.nav-item.active {
  background: var(--color-info-bg);
  color: var(--color-info);
  border-left-color: var(--color-info);
}

.item-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

/* Footer status */
.sidebar-footer {
  padding: 16px 20px;
  border-top: 1px solid var(--border-default);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-family: var(--font-sans);
  color: var(--text-tertiary);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--border-default);
  flex-shrink: 0;
}

.status-indicator.healthy .status-dot {
  background: var(--color-success);
}

.status-indicator.healthy {
  color: var(--color-success-dark);
}

.status-indicator.degraded .status-dot {
  background: var(--color-warning);
}

.status-indicator.degraded {
  color: var(--color-warning-dark);
}

.status-indicator.offline .status-dot {
  background: var(--color-error);
}

.status-indicator.offline {
  color: var(--color-error);
}

/* Main content */
.vision-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px;
  background: var(--bg-primary);
}

/* Responsive */
@media (max-width: 768px) {
  .vision-sidebar {
    width: 64px;
    min-width: 64px;
  }

  .sidebar-header {
    padding: 16px 12px;
  }

  .sidebar-header h3 {
    font-size: 0;
    justify-content: center;
  }

  .header-icon {
    width: 20px;
    height: 20px;
  }

  .nav-item {
    justify-content: center;
    padding: 10px;
    gap: 0;
  }

  .nav-item span {
    display: none;
  }

  .item-icon {
    width: 20px;
    height: 20px;
  }

  .sidebar-footer {
    padding: 12px;
  }

  .status-indicator {
    justify-content: center;
  }

  .status-indicator span {
    display: none;
  }

  .vision-content {
    padding: 16px;
  }
}
</style>
