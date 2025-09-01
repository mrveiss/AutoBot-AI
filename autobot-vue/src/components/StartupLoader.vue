<template>
  <div v-if="showLoader" class="startup-overlay">
    <div class="startup-container">
      <!-- AutoBot Logo/Icon -->
      <div class="startup-header">
        <div class="startup-icon">🤖</div>
        <h1 class="startup-title">AutoBot</h1>
        <p class="startup-subtitle">Intelligent Automation System</p>
      </div>

      <!-- Progress Bar -->
      <div class="progress-container">
        <div class="progress-bar">
          <div 
            class="progress-fill" 
            :style="{ width: progress + '%' }"
            :class="{ 'progress-pulse': isLoading }"
          ></div>
        </div>
        <div class="progress-text">{{ progress }}%</div>
      </div>

      <!-- Current Status -->
      <div class="status-container">
        <div class="current-status">
          <span class="status-icon">{{ currentMessage.icon || '🚀' }}</span>
          <span class="status-message">{{ currentMessage.message || 'Starting AutoBot...' }}</span>
        </div>
        
        <div v-if="currentMessage.details" class="status-details">
          {{ currentMessage.details }}
        </div>
      </div>

      <!-- Recent Messages Log -->
      <div class="messages-log">
        <div class="messages-title">
          <span>📋 Startup Log</span>
          <span class="elapsed-time">{{ formattedElapsedTime }}</span>
        </div>
        <div class="messages-container">
          <div 
            v-for="message in recentMessages" 
            :key="message.timestamp"
            class="message-item"
            :class="{ 'message-current': isCurrentMessage(message) }"
          >
            <span class="message-icon">{{ message.icon }}</span>
            <span class="message-text">{{ message.message }}</span>
            <span class="message-time">{{ formatTime(message.timestamp) }}</span>
          </div>
        </div>
      </div>

      <!-- Skip/Continue Options (after 10 seconds) -->
      <div v-if="showSkipOption" class="skip-container">
        <button @click="skipLoader" class="skip-button">
          Continue to AutoBot →
        </button>
        <p class="skip-text">Services are starting in background</p>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted, computed } from 'vue'

export default {
  name: 'StartupLoader',
  props: {
    autoHide: {
      type: Boolean,
      default: true
    },
    minDisplayTime: {
      type: Number,
      default: 2000 // Minimum 2 seconds
    }
  },
  emits: ['ready', 'skip'],
  setup(props, { emit }) {
    const showLoader = ref(true)
    const progress = ref(0)
    const currentMessage = ref({})
    const messages = ref([])
    const elapsedTime = ref(0)
    const startTime = ref(Date.now())
    const showSkipOption = ref(false)
    const isLoading = ref(true)

    let websocket = null
    let statusInterval = null
    let skipTimer = null

    const recentMessages = computed(() => {
      return messages.value.slice(-8) // Show last 8 messages
    })

    const formattedElapsedTime = computed(() => {
      const seconds = Math.floor(elapsedTime.value / 1000)
      const minutes = Math.floor(seconds / 60)
      if (minutes > 0) {
        return `${minutes}:${(seconds % 60).toString().padStart(2, '0')}`
      }
      return `${seconds}s`
    })

    const isCurrentMessage = (message) => {
      return message.timestamp === currentMessage.value.timestamp
    }

    const formatTime = (timestamp) => {
      if (!timestamp) return ''
      try {
        return new Date(timestamp).toLocaleTimeString([], { 
          hour: '2-digit', 
          minute: '2-digit',
          second: '2-digit'
        })
      } catch {
        return ''
      }
    }

    const connectWebSocket = () => {
      // Use proxy in development, direct URL in production
      let wsUrl
      if (window.location.port === '5173') {
        // Development mode - use Vite proxy
        wsUrl = `ws://${window.location.host}/api/startup/ws`
      } else {
        // Production mode - direct to backend
        wsUrl = `ws://${window.location.hostname}:8001/api/startup/ws`
      }
      
      console.log('Connecting to startup WebSocket:', wsUrl)
      
      try {
        websocket = new WebSocket(wsUrl)
        
        websocket.onopen = () => {
          console.log('Startup WebSocket connected')
        }

        websocket.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            
            if (data.type === 'status') {
              // Update overall status
              progress.value = data.data.progress || progress.value
              elapsedTime.value = data.data.elapsed_time * 1000
              
              // If backend reports ready or 100% progress, complete startup
              if (data.data.is_ready || data.data.progress >= 100) {
                handleStartupComplete()
              }
            } else if (data.type === 'message') {
              // New startup message
              const message = data.data
              messages.value.push(message)
              currentMessage.value = message
              progress.value = message.progress || progress.value
              
              // Check if ready
              if (message.phase === 'ready' || message.progress >= 100) {
                handleStartupComplete()
              }
            }
          } catch (e) {
            console.error('Error parsing startup message:', e)
          }
        }

        websocket.onclose = () => {
          console.log('Startup WebSocket closed')
          // Try to reconnect if not ready
          if (isLoading.value && showLoader.value) {
            setTimeout(connectWebSocket, 2000)
          }
        }

        websocket.onerror = (error) => {
          console.error('Startup WebSocket error:', error)
        }

      } catch (error) {
        console.error('Failed to connect startup WebSocket:', error)
        // Fallback to polling
        startPolling()
      }
    }

    const startPolling = async () => {
      let pollAttempts = 0
      const maxPollAttempts = 30 // 30 seconds max
      
      statusInterval = setInterval(async () => {
        pollAttempts++
        
        try {
          // Use relative URL to go through Vite proxy in development
          const response = await fetch('/api/startup/status')
          const data = await response.json()
          
          progress.value = data.progress || 0
          elapsedTime.value = data.elapsed_time * 1000
          
          if (data.messages && data.messages.length > 0) {
            messages.value = data.messages
            currentMessage.value = data.messages[data.messages.length - 1]
          } else if (messages.value.length === 0) {
            // No messages from backend, show fallback
            const fallbackMessage = {
              icon: '🤖',
              message: 'Starting AutoBot systems...',
              timestamp: new Date().toISOString(),
              progress: Math.min(pollAttempts * 3, 90) // Gradual progress
            }
            messages.value = [fallbackMessage]
            currentMessage.value = fallbackMessage
            progress.value = fallbackMessage.progress
          }
          
          if (data.is_ready || data.progress >= 100) {
            handleStartupComplete()
          } else if (pollAttempts >= maxPollAttempts) {
            // Timeout - assume ready
            console.log('Startup polling timeout - assuming system ready')
            handleStartupComplete()
          }
        } catch (error) {
          console.error('Error polling startup status:', error)
          
          // Show fallback message on error
          if (messages.value.length === 0 || pollAttempts <= 3) {
            const fallbackMessage = {
              icon: '⏳',
              message: 'Connecting to AutoBot backend...',
              timestamp: new Date().toISOString(),
              progress: Math.min(pollAttempts * 5, 50)
            }
            messages.value = [fallbackMessage]
            currentMessage.value = fallbackMessage
            progress.value = fallbackMessage.progress
          }
          
          // If we can't connect after several attempts, assume system is ready
          if (pollAttempts >= maxPollAttempts) {
            console.log('Cannot connect to startup status - assuming system ready')
            handleStartupComplete()
          }
        }
      }, 1000)
    }

    const handleStartupComplete = async () => {
      isLoading.value = false
      progress.value = 100
      currentMessage.value = {
        icon: '🎉',
        message: 'AutoBot is ready!',
        details: 'All systems operational'
      }

      // Wait for minimum display time
      const elapsed = Date.now() - startTime.value
      const remainingTime = Math.max(0, props.minDisplayTime - elapsed)
      
      setTimeout(() => {
        if (props.autoHide) {
          hideLoader()
        }
        emit('ready')
      }, remainingTime)
    }

    const hideLoader = () => {
      showLoader.value = false
    }

    const skipLoader = () => {
      hideLoader()
      emit('skip')
    }

    onMounted(() => {
      // Initialize with default startup message
      const initialMessage = {
        icon: '🤖',
        message: 'Initializing AutoBot...',
        timestamp: new Date().toISOString(),
        progress: 0
      }
      messages.value = [initialMessage]
      currentMessage.value = initialMessage
      
      // Show skip option after 10 seconds
      skipTimer = setTimeout(() => {
        showSkipOption.value = true
      }, 10000)

      // Try WebSocket first, fallback to polling
      connectWebSocket()
    })

    onUnmounted(() => {
      if (websocket) {
        websocket.close()
      }
      if (statusInterval) {
        clearInterval(statusInterval)
      }
      if (skipTimer) {
        clearTimeout(skipTimer)
      }
    })

    return {
      showLoader,
      progress,
      currentMessage,
      recentMessages,
      elapsedTime,
      formattedElapsedTime,
      showSkipOption,
      isLoading,
      isCurrentMessage,
      formatTime,
      skipLoader
    }
  }
}
</script>

<style scoped>
.startup-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  color: white;
}

.startup-container {
  text-align: center;
  max-width: 500px;
  padding: 2rem;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 20px;
  backdrop-filter: blur(10px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.startup-header {
  margin-bottom: 2rem;
}

.startup-icon {
  font-size: 4rem;
  margin-bottom: 1rem;
  animation: bounce 2s infinite;
}

.startup-title {
  font-size: 2.5rem;
  font-weight: bold;
  margin: 0 0 0.5rem 0;
  background: linear-gradient(45deg, #fff, #e0e7ff);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.startup-subtitle {
  font-size: 1rem;
  opacity: 0.8;
  margin: 0;
}

.progress-container {
  margin: 2rem 0;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 0.5rem;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #4ade80, #22d3ee);
  border-radius: 4px;
  transition: width 0.5s ease;
}

.progress-pulse {
  animation: pulse 1.5s ease-in-out infinite;
}

.progress-text {
  font-size: 0.9rem;
  opacity: 0.9;
}

.status-container {
  margin: 1.5rem 0;
  text-align: left;
}

.current-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1.1rem;
  font-weight: 500;
}

.status-icon {
  font-size: 1.2rem;
}

.status-details {
  font-size: 0.9rem;
  opacity: 0.7;
  margin-top: 0.25rem;
  margin-left: 1.7rem;
}

.messages-log {
  margin-top: 2rem;
  text-align: left;
}

.messages-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.9rem;
  font-weight: 500;
  margin-bottom: 1rem;
  opacity: 0.9;
}

.elapsed-time {
  font-family: monospace;
  opacity: 0.7;
}

.messages-container {
  max-height: 200px;
  overflow-y: auto;
  padding: 1rem;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.message-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0;
  font-size: 0.85rem;
  opacity: 0.7;
  transition: opacity 0.3s ease;
}

.message-current {
  opacity: 1;
  font-weight: 500;
}

.message-icon {
  font-size: 1rem;
  flex-shrink: 0;
}

.message-text {
  flex: 1;
}

.message-time {
  font-family: monospace;
  font-size: 0.75rem;
  opacity: 0.6;
  flex-shrink: 0;
}

.skip-container {
  margin-top: 2rem;
  padding-top: 1.5rem;
  border-top: 1px solid rgba(255, 255, 255, 0.2);
}

.skip-button {
  background: rgba(255, 255, 255, 0.2);
  color: white;
  border: 1px solid rgba(255, 255, 255, 0.3);
  padding: 0.75rem 1.5rem;
  border-radius: 25px;
  cursor: pointer;
  transition: all 0.3s ease;
  font-size: 0.9rem;
  font-weight: 500;
}

.skip-button:hover {
  background: rgba(255, 255, 255, 0.3);
  transform: translateY(-1px);
}

.skip-text {
  font-size: 0.8rem;
  opacity: 0.7;
  margin: 0.5rem 0 0 0;
}

@keyframes bounce {
  0%, 20%, 50%, 80%, 100% {
    transform: translateY(0);
  }
  40% {
    transform: translateY(-10px);
  }
  60% {
    transform: translateY(-5px);
  }
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.6;
  }
}

/* Scrollbar styling */
.messages-container::-webkit-scrollbar {
  width: 4px;
}

.messages-container::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
}

.messages-container::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.3);
  border-radius: 2px;
}

.messages-container::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.5);
}
</style>