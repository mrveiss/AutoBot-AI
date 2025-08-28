<template>
  <div class="novnc-viewer h-full flex flex-col bg-black">
    <!-- Header -->
    <div class="flex justify-between items-center bg-gray-800 text-white px-4 py-2 text-sm flex-shrink-0">
      <div class="flex items-center gap-2">
        <i class="fas fa-desktop"></i>
        <span>Remote Desktop (noVNC)</span>
      </div>
      <div class="flex items-center gap-2">
        <a 
          :href="novncUrl" 
          target="_blank" 
          class="text-indigo-300 hover:text-indigo-100 underline flex items-center gap-1"
          title="Open noVNC in new window"
        >
          <i class="fas fa-external-link-alt"></i>
          Open in New Window
        </a>
        <button 
          @click="refreshViewer"
          class="text-gray-300 hover:text-white px-2 py-1 rounded hover:bg-gray-700 transition-colors"
          title="Refresh connection"
        >
          <i class="fas fa-sync-alt" :class="{ 'animate-spin': isRefreshing }"></i>
        </button>
      </div>
    </div>

    <!-- Connection Status -->
    <div v-if="connectionError" class="bg-red-600 text-white px-4 py-2 text-sm flex items-center gap-2">
      <i class="fas fa-exclamation-triangle"></i>
      <span>Connection failed. Make sure the noVNC server is running on {{ novncUrl }}</span>
      <button 
        @click="retryConnection" 
        class="ml-auto px-3 py-1 bg-red-700 hover:bg-red-800 rounded text-sm transition-colors"
      >
        Retry
      </button>
    </div>

    <!-- noVNC Iframe -->
    <div class="flex-1 relative">
      <iframe 
        :key="iframeKey"
        :src="novncUrl"
        class="w-full h-full border-0"
        title="noVNC Remote Desktop"
        allowfullscreen
        @load="onIframeLoad"
        @error="onIframeError"
      ></iframe>
      
      <!-- Loading overlay -->
      <div v-if="isLoading" class="absolute inset-0 bg-gray-900 bg-opacity-75 flex items-center justify-center">
        <div class="text-center text-white">
          <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-white mx-auto mb-2"></div>
          <p>Connecting to remote desktop...</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { API_CONFIG } from '@/config/environment.js'

// Component state
const novncUrl = ref(API_CONFIG.PLAYWRIGHT_VNC_URL)
const isLoading = ref(true)
const isRefreshing = ref(false)
const connectionError = ref(false)
const iframeKey = ref(0) // For forcing iframe refresh

// Methods
const onIframeLoad = () => {
  isLoading.value = false
  connectionError.value = false
}

const onIframeError = () => {
  isLoading.value = false
  connectionError.value = true
}

const refreshViewer = () => {
  isRefreshing.value = true
  isLoading.value = true
  connectionError.value = false
  iframeKey.value += 1 // Force iframe refresh
  
  setTimeout(() => {
    isRefreshing.value = false
  }, 1000)
}

const retryConnection = () => {
  refreshViewer()
}

// Lifecycle
onMounted(() => {
  // Set loading timeout
  setTimeout(() => {
    if (isLoading.value) {
      connectionError.value = true
      isLoading.value = false
    }
  }, 10000) // 10 second timeout
})
</script>

<style scoped>
.novnc-viewer {
  height: calc(100vh - 120px);
}
</style>