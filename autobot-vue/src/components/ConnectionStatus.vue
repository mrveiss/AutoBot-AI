<template>
  <div class="connection-status">
    <!-- Connection Status Indicator -->
    <div 
      class="fixed top-20 right-4 z-40 bg-white rounded-lg shadow-lg border p-3 min-w-64"
      :class="statusClasses"
    >
      <div class="flex items-center justify-between">
        <div class="flex items-center">
          <div 
            class="w-3 h-3 rounded-full mr-2"
            :class="indicatorClasses"
          ></div>
          <span class="font-medium text-sm">{{ statusText }}</span>
        </div>
        <BaseButton
          @click="toggleDetails"
          variant="ghost"
          size="sm"
          :aria-expanded="showDetails"
          aria-label="Toggle connection details"
          class="ml-2 text-gray-400 hover:text-gray-600"
        >
          <svg
            class="w-4 h-4 transition-transform"
            :class="{ 'rotate-180': showDetails }"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
          </svg>
        </BaseButton>
      </div>
      
      <!-- Detailed Status -->
      <transition name="slide-down">
        <div v-if="showDetails" class="mt-3 pt-3 border-t border-gray-200 text-xs space-y-2">
          <!-- Backend Connection -->
          <div class="flex justify-between items-center">
            <span class="text-gray-600">Backend:</span>
            <div class="flex items-center">
              <div 
                class="w-2 h-2 rounded-full mr-1"
                :class="connection.status === 'connected' ? 'bg-green-500' : 
                        connection.mockMode ? 'bg-yellow-500' : 'bg-red-500'"
              ></div>
              <span class="font-mono text-xs">
                {{ connection.backend || (connection.mockMode ? 'Mock Mode' : 'Disconnected') }}
              </span>
            </div>
          </div>
          
          <!-- Performance Metrics -->
          <div class="space-y-1">
            <div class="flex justify-between">
              <span class="text-gray-600">Requests:</span>
              <span class="font-mono">{{ performance.requests }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-gray-600">Avg Response:</span>
              <span class="font-mono">{{ formatTime(performance.averageResponseTime) }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-gray-600">Error Rate:</span>
              <span 
                class="font-mono"
                :class="performance.errorRate > 0.1 ? 'text-red-600' : 'text-green-600'"
              >
                {{ formatPercentage(performance.errorRate) }}
              </span>
            </div>
          </div>
          
          <!-- Actions -->
          <div class="flex justify-between pt-2">
            <BaseButton
              @click="forceReconnect"
              variant="link"
              size="xs"
              :loading="reconnecting"
              :disabled="reconnecting"
              class="text-blue-600 hover:text-blue-800"
            >
              {{ reconnecting ? 'Reconnecting...' : 'Force Reconnect' }}
            </BaseButton>
            <BaseButton
              @click="runHealthCheck"
              variant="link"
              size="xs"
              :loading="healthChecking"
              :disabled="healthChecking"
              class="text-green-600 hover:text-green-800"
            >
              {{ healthChecking ? 'Checking...' : 'Health Check' }}
            </BaseButton>
          </div>
          
          <!-- Health Check Results -->
          <div v-if="healthStatus" class="pt-2 border-t border-gray-100">
            <div class="flex justify-between items-center">
              <span class="text-gray-600">Health:</span>
              <div class="flex items-center">
                <div 
                  class="w-2 h-2 rounded-full mr-1"
                  :class="healthStatus.healthy ? 'bg-green-500' : 'bg-red-500'"
                ></div>
                <span class="font-mono text-xs">
                  {{ healthStatus.healthy ? 'OK' : 'Failed' }}
                  ({{ formatTime(healthStatus.responseTime) }})
                </span>
              </div>
            </div>
            <div v-if="healthStatus.mock" class="text-yellow-600 text-xs mt-1">
              Running in development mock mode
            </div>
          </div>
        </div>
      </transition>
    </div>
    
    <!-- Toast Notifications -->
    <transition-group name="toast" tag="div" class="fixed top-24 right-4 z-50 space-y-2">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        class="bg-white rounded-lg shadow-lg border p-3 max-w-sm"
        :class="toast.type === 'error' ? 'border-red-300 bg-red-50' : 
                toast.type === 'warning' ? 'border-yellow-300 bg-yellow-50' :
                toast.type === 'success' ? 'border-green-300 bg-green-50' :
                'border-blue-300 bg-blue-50'"
      >
        <div class="flex items-start justify-between">
          <div class="flex items-start">
            <div 
              class="w-5 h-5 mr-2 flex-shrink-0 mt-0.5"
              :class="toast.type === 'error' ? 'text-red-500' : 
                      toast.type === 'warning' ? 'text-yellow-500' :
                      toast.type === 'success' ? 'text-green-500' :
                      'text-blue-500'"
            >
              <!-- Icon based on type -->
              <svg v-if="toast.type === 'error'" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
              </svg>
              <svg v-else-if="toast.type === 'warning'" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
              </svg>
              <svg v-else-if="toast.type === 'success'" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
              </svg>
              <svg v-else fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path>
              </svg>
            </div>
            <div>
              <p class="text-sm font-medium text-gray-900">{{ toast.title }}</p>
              <p v-if="toast.message" class="text-xs text-gray-600 mt-1">{{ toast.message }}</p>
            </div>
          </div>
          <BaseButton
            @click="removeToast(toast.id)"
            variant="ghost"
            size="sm"
            class="ml-2 text-gray-400 hover:text-gray-600"
            aria-label="Close notification"
          >
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
            </svg>
          </BaseButton>
        </div>
      </div>
    </transition-group>
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import serviceIntegration from '@/config/OptimizedServiceIntegration.js';
import BaseButton from '@/components/base/BaseButton.vue';

export default {
  name: 'ConnectionStatus',
  components: {
    BaseButton
  },
  setup() {
    const showDetails = ref(false);
    const connection = ref({
      status: 'checking',
      backend: null,
      mockMode: false
    });
    const performance = ref({
      requests: 0,
      averageResponseTime: 0,
      errorRate: 0,
      slowRequestRate: 0
    });
    const healthStatus = ref(null);
    const reconnecting = ref(false);
    const healthChecking = ref(false);
    const toasts = ref([]);
    
    let statusUpdateInterval = null;
    
    // Computed properties
    const statusText = computed(() => {
      if (connection.value.mockMode) {
        return 'Development Mode';
      } else if (connection.value.status === 'connected') {
        return 'Connected';
      } else if (connection.value.status === 'checking') {
        return 'Connecting...';
      } else {
        return 'Disconnected';
      }
    });
    
    const statusClasses = computed(() => ({
      'border-green-300': connection.value.status === 'connected' && !connection.value.mockMode,
      'border-yellow-300': connection.value.mockMode,
      'border-red-300': connection.value.status === 'disconnected',
      'border-blue-300': connection.value.status === 'checking'
    }));
    
    const indicatorClasses = computed(() => ({
      'bg-green-500 animate-pulse': connection.value.status === 'connected' && !connection.value.mockMode,
      'bg-yellow-500': connection.value.mockMode,
      'bg-red-500': connection.value.status === 'disconnected',
      'bg-blue-500 animate-pulse': connection.value.status === 'checking'
    }));
    
    // Methods
    const toggleDetails = () => {
      showDetails.value = !showDetails.value;
    };
    
    const updateStatus = () => {
      connection.value = serviceIntegration.getConnectionStatus();
      performance.value = serviceIntegration.getPerformanceStats();
    };
    
    const forceReconnect = async () => {
      reconnecting.value = true;
      try {
        await serviceIntegration.forceReconnect();
        addToast('success', 'Reconnection Initiated', 'Attempting to reconnect to backend...');
      } catch (error) {
        addToast('error', 'Reconnection Failed', error.message);
      } finally {
        reconnecting.value = false;
      }
    };
    
    const runHealthCheck = async () => {
      healthChecking.value = true;
      try {
        healthStatus.value = await serviceIntegration.healthCheck();
        const status = healthStatus.value.healthy ? 'success' : 'error';
        const title = healthStatus.value.healthy ? 'Health Check Passed' : 'Health Check Failed';
        const message = healthStatus.value.mock ? 'Mock mode active' : 
                       `Response time: ${formatTime(healthStatus.value.responseTime)}`;
        addToast(status, title, message);
      } catch (error) {
        addToast('error', 'Health Check Error', error.message);
        healthStatus.value = { healthy: false, error: error.message };
      } finally {
        healthChecking.value = false;
      }
    };
    
    const addToast = (type, title, message = '') => {
      const toast = {
        id: Date.now() + Math.random(),
        type,
        title,
        message
      };
      toasts.value.push(toast);
      
      // Auto-remove after 5 seconds
      setTimeout(() => {
        removeToast(toast.id);
      }, 5000);
    };
    
    const removeToast = (id) => {
      const index = toasts.value.findIndex(toast => toast.id === id);
      if (index > -1) {
        toasts.value.splice(index, 1);
      }
    };
    
    const formatTime = (ms) => {
      if (ms < 1000) {
        return `${Math.round(ms)}ms`;
      } else {
        return `${(ms / 1000).toFixed(1)}s`;
      }
    };
    
    const formatPercentage = (rate) => {
      return `${(rate * 100).toFixed(1)}%`;
    };
    
    const handleConnectionStatusChange = (status) => {
      const prevStatus = connection.value.status;
      connection.value = { ...connection.value, ...status };
      
      // Show toast notifications for status changes
      if (prevStatus !== status.status) {
        if (status.status === 'connected' && !status.mockMode) {
          addToast('success', 'Backend Connected', status.backendUrl);
        } else if (status.mockMode) {
          addToast('warning', 'Mock Mode Active', 'Backend unavailable - using development data');
        } else if (status.status === 'disconnected') {
          addToast('error', 'Backend Disconnected', 'Connection to backend lost');
        }
      }
    };
    
    // Lifecycle
    onMounted(() => {
      // Initial status update
      updateStatus();
      
      // Set up status listener
      serviceIntegration.addStatusListener(handleConnectionStatusChange);
      
      // Set up periodic updates
      statusUpdateInterval = setInterval(updateStatus, 5000);
      
      // Run initial health check
      setTimeout(() => {
        runHealthCheck();
      }, 1000);
    });
    
    onUnmounted(() => {
      if (statusUpdateInterval) {
        clearInterval(statusUpdateInterval);
      }
      serviceIntegration.removeStatusListener(handleConnectionStatusChange);
    });
    
    return {
      showDetails,
      connection,
      performance,
      healthStatus,
      reconnecting,
      healthChecking,
      toasts,
      statusText,
      statusClasses,
      indicatorClasses,
      toggleDetails,
      forceReconnect,
      runHealthCheck,
      removeToast,
      formatTime,
      formatPercentage
    };
  }
};
</script>

<style scoped>
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.3s ease;
  max-height: 200px;
  overflow: hidden;
}

.slide-down-enter-from,
.slide-down-leave-to {
  max-height: 0;
  opacity: 0;
}

.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(100%);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(100%);
}

.toast-move {
  transition: transform 0.3s ease;
}

.connection-status {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
</style>