<template>
  <div class="p-4 border border-yellow-300 bg-yellow-50 rounded-lg">
    <h3 class="text-lg font-semibold text-yellow-800 mb-4">Chat Persistence Debug Panel</h3>

    <div class="grid grid-cols-2 gap-4 mb-4">
      <!-- Current Store State -->
      <div class="bg-white p-3 rounded border">
        <h4 class="font-semibold text-gray-700 mb-2">Current Store State</h4>
        <p class="text-sm">Sessions: {{ store.sessions.length }}</p>
        <p class="text-sm">Current ID: {{ store.currentSessionId || 'None' }}</p>
        <div class="mt-2 max-h-32 overflow-y-auto">
          <div v-for="session in store.sessions" :key="session.id"
               class="text-xs p-1 bg-gray-100 mb-1 rounded">
            {{ session.title }} ({{ session.id.slice(-8) }})
          </div>
        </div>
      </div>

      <!-- Persisted State -->
      <div class="bg-white p-3 rounded border">
        <h4 class="font-semibold text-gray-700 mb-2">Persisted State</h4>
        <p class="text-sm">Sessions: {{ persistedState.sessions?.length || 0 }}</p>
        <p class="text-sm">Current ID: {{ persistedState.currentSessionId || 'None' }}</p>
        <div class="mt-2 max-h-32 overflow-y-auto">
          <div v-for="session in persistedState.sessions || []" :key="session.id"
               class="text-xs p-1 bg-gray-100 mb-1 rounded">
            {{ session.title }} ({{ session.id.slice(-8) }})
          </div>
        </div>
      </div>
    </div>

    <!-- Actions -->
    <div class="flex flex-wrap gap-2 mb-4">
      <button @click="refreshPersistenceState"
              class="px-3 py-1 bg-blue-500 text-white rounded text-sm hover:bg-blue-600">
        Refresh State
      </button>

      <button @click="createTestSession"
              class="px-3 py-1 bg-green-500 text-white rounded text-sm hover:bg-green-600">
        Create Test Session
      </button>

      <button @click="deleteLastSession"
              class="px-3 py-1 bg-red-500 text-white rounded text-sm hover:bg-red-600">
        Delete Last Session
      </button>

      <button @click="debugPersistence"
              class="px-3 py-1 bg-purple-500 text-white rounded text-sm hover:bg-purple-600">
        Debug Console
      </button>

      <button @click="clearLocalStorage"
              class="px-3 py-1 bg-gray-500 text-white rounded text-sm hover:bg-gray-600">
        Clear localStorage
      </button>
    </div>

    <!-- Status Messages -->
    <div v-if="statusMessage"
         class="p-2 rounded text-sm"
         :class="statusMessage.type === 'success' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'">
      {{ statusMessage.text }}
    </div>

    <!-- Test Results -->
    <div v-if="testResults.length > 0" class="mt-4">
      <h4 class="font-semibold text-gray-700 mb-2">Test Results</h4>
      <div class="max-h-40 overflow-y-auto">
        <div v-for="(result, index) in testResults" :key="index"
             class="text-xs p-2 mb-1 rounded"
             :class="result.success ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'">
          <strong>{{ result.action }}:</strong> {{ result.message }}
          <span class="text-gray-600">({{ result.timestamp }})</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useChatStore } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'

const store = useChatStore()
const controller = useChatController()

const persistedState = ref<any>({})
const statusMessage = ref<{ type: 'success' | 'error', text: string } | null>(null)
const testResults = ref<Array<{ action: string, message: string, success: boolean, timestamp: string }>>([])

const refreshPersistenceState = () => {
  try {
    const persistedData = localStorage.getItem('autobot-chat-store')
    if (persistedData) {
      persistedState.value = JSON.parse(persistedData)
      setStatus('success', 'Persistence state refreshed')
    } else {
      persistedState.value = {}
      setStatus('error', 'No persisted data found')
    }
  } catch (error) {
    setStatus('error', `Failed to read persistence: ${error}`)
  }
}

const createTestSession = async () => {
  try {
    const sessionId = await controller.createNewSession(`Test Session ${Date.now()}`)
    addTestResult('Create Session', `Created session ${sessionId.slice(-8)}`, true)
    setStatus('success', 'Test session created')

    // Wait a moment then refresh to check persistence
    setTimeout(() => {
      refreshPersistenceState()
    }, 200)
  } catch (error) {
    addTestResult('Create Session', `Failed: ${error}`, false)
    setStatus('error', 'Failed to create test session')
  }
}

const deleteLastSession = async () => {
  if (store.sessions.length === 0) {
    setStatus('error', 'No sessions to delete')
    return
  }

  const lastSession = store.sessions[store.sessions.length - 1]
  const sessionTitle = lastSession.title
  const sessionId = lastSession.id

  try {
    // Store state before deletion
    const beforeCount = store.sessions.length

    await controller.deleteChatSession(sessionId)

    // Store state after deletion
    const afterCount = store.sessions.length

    addTestResult('Delete Session',
      `Deleted "${sessionTitle}" (${beforeCount} → ${afterCount})`,
      afterCount < beforeCount)

    setStatus('success', `Deleted session: ${sessionTitle}`)

    // Wait a moment then refresh to check persistence
    setTimeout(() => {
      refreshPersistenceState()
    }, 200)

  } catch (error) {
    addTestResult('Delete Session', `Failed: ${error}`, false)
    setStatus('error', `Failed to delete session: ${error}`)
  }
}

const debugPersistence = () => {
  store.debugPersistenceState()
  setStatus('success', 'Check console for debug output')
}

const clearLocalStorage = () => {
  localStorage.removeItem('autobot-chat-store')
  store.clearAllSessions()
  refreshPersistenceState()
  setStatus('success', 'localStorage cleared')
  addTestResult('Clear Storage', 'localStorage and store cleared', true)
}

const setStatus = (type: 'success' | 'error', text: string) => {
  statusMessage.value = { type, text }
  setTimeout(() => {
    statusMessage.value = null
  }, 3000)
}

const addTestResult = (action: string, message: string, success: boolean) => {
  testResults.value.unshift({
    action,
    message,
    success,
    timestamp: new Date().toLocaleTimeString()
  })

  // Keep only last 10 results
  if (testResults.value.length > 10) {
    testResults.value = testResults.value.slice(0, 10)
  }
}

onMounted(() => {
  refreshPersistenceState()
})
</script>