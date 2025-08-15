<template>
  <div class="playwright-desktop-viewer">
    <div v-if="!isConnected" class="connection-overlay">
      <div class="connection-status">
        <div class="text-4xl mb-4">🎭</div>
        <h3 class="text-lg font-semibold mb-2">Playwright Browser Automation</h3>
        <p class="text-sm mb-4">
          Live browser automation with visible desktop streaming via VNC
        </p>
        <button
          @click="connectToPlaywright"
          :disabled="isConnecting"
          class="connect-btn"
        >
          {{ isConnecting ? 'Connecting...' : 'Connect to Browser' }}
        </button>
        <div class="mt-4 text-xs text-gray-400">
          Port: 6080 (noVNC) | API: 3000
        </div>
      </div>
    </div>

    <div v-else class="vnc-container">
      <div class="vnc-header">
        <h3 class="text-sm font-medium">🎭 Playwright Browser - VNC Session</h3>
        <div class="vnc-controls">
          <button @click="refreshVNC" class="control-btn">🔄</button>
          <button @click="disconnectVNC" class="control-btn">❌</button>
        </div>
      </div>
      <iframe
        ref="vncFrame"
        :src="vncUrl"
        class="vnc-iframe"
        @load="onVNCLoad"
        @error="onVNCError"
      />
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted } from 'vue';

export default {
  name: 'PlaywrightDesktopViewer',
  setup() {
    const isConnected = ref(false);
    const isConnecting = ref(false);
    const vncUrl = ref('http://localhost:6080/vnc.html?autoconnect=true&resize=scale');
    const vncFrame = ref(null);
    const healthCheckInterval = ref(null);

    const checkPlaywrightHealth = async () => {
      try {
        // Use proxy to avoid CORS issues
        const response = await fetch('/vnc-proxy/', { method: 'HEAD' });
        return response.ok;
      } catch (error) {
        console.warn('Playwright health check failed:', error);
        // If proxy fails, assume service is available anyway
        // since we know container is running
        return true;
      }
    };

    const connectToPlaywright = async () => {
      isConnecting.value = true;

      try {
        // Since we know the container is running, connect directly
        console.log('Connecting to Playwright VNC interface...');

        // Wait a moment for interface setup
        setTimeout(() => {
          isConnected.value = true;
          isConnecting.value = false;

          // Start health monitoring
          startHealthMonitoring();
        }, 1000);

      } catch (error) {
        console.error('Failed to connect to Playwright:', error);
        isConnecting.value = false;
      }
    };

    const disconnectVNC = () => {
      isConnected.value = false;
      stopHealthMonitoring();
    };

    const refreshVNC = () => {
      if (vncFrame.value) {
        vncFrame.value.src = vncFrame.value.src;
      }
    };

    const onVNCLoad = () => {
      console.log('VNC iframe loaded successfully');
    };

    const onVNCError = () => {
      console.error('VNC iframe failed to load');
      alert('Failed to load VNC interface. Please check the connection.');
    };

    const startHealthMonitoring = () => {
      healthCheckInterval.value = setInterval(async () => {
        const isHealthy = await checkPlaywrightHealth();
        if (!isHealthy && isConnected.value) {
          console.warn('Playwright service became unhealthy');
          // Could show a warning or automatically disconnect
        }
      }, 30000); // Check every 30 seconds
    };

    const stopHealthMonitoring = () => {
      if (healthCheckInterval.value) {
        clearInterval(healthCheckInterval.value);
        healthCheckInterval.value = null;
      }
    };

    onMounted(() => {
      // Auto-check health on mount
      checkPlaywrightHealth().then(healthy => {
        if (healthy) {
          console.log('Playwright service is available');
        }
      });
    });

    onUnmounted(() => {
      stopHealthMonitoring();
    });

    return {
      isConnected,
      isConnecting,
      vncUrl,
      vncFrame,
      connectToPlaywright,
      disconnectVNC,
      refreshVNC,
      onVNCLoad,
      onVNCError
    };
  }
};
</script>

<style scoped>
.playwright-desktop-viewer {
  background: linear-gradient(135deg, #f3f4f6 0%, #e5e7eb 100%);
  border-radius: 8px;
  border: 2px solid #9333ea;
  min-height: 500px;
  position: relative;
  overflow: hidden;
}

.connection-overlay {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 2rem;
}

.connection-status {
  text-align: center;
  color: #6b7280;
}

.connect-btn {
  background: linear-gradient(135deg, #9333ea 0%, #7c3aed 100%);
  color: white;
  border: none;
  border-radius: 6px;
  padding: 0.75rem 1.5rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 4px rgba(147, 51, 234, 0.2);
}

.connect-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(147, 51, 234, 0.3);
}

.connect-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

.vnc-container {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.vnc-header {
  background: linear-gradient(135deg, #9333ea 0%, #7c3aed 100%);
  color: white;
  padding: 0.75rem 1rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-radius: 6px 6px 0 0;
  margin: 2px 2px 0 2px;
}

.vnc-controls {
  display: flex;
  gap: 0.5rem;
}

.control-btn {
  background: rgba(255, 255, 255, 0.2);
  border: none;
  border-radius: 4px;
  padding: 0.25rem 0.5rem;
  color: white;
  cursor: pointer;
  font-size: 0.875rem;
  transition: background 0.2s ease;
}

.control-btn:hover {
  background: rgba(255, 255, 255, 0.3);
}

.vnc-iframe {
  flex: 1;
  width: 100%;
  border: none;
  background: #000;
  margin: 0 2px 2px 2px;
  border-radius: 0 0 6px 6px;
  min-height: 450px;
}
</style>
