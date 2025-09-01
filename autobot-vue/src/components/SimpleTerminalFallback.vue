<template>
  <div class="simple-terminal-fallback">
    <div class="terminal-header">
      <h3>Terminal (Fallback Mode)</h3>
      <div class="status">Status: {{ connectionStatus }}</div>
    </div>
    
    <div class="terminal-output" ref="output">
      <div v-for="(line, index) in outputLines" :key="index" class="output-line">
        {{ line }}
      </div>
    </div>
    
    <div class="terminal-input">
      <span class="prompt">$ </span>
      <input 
        v-model="currentInput" 
        @keyup.enter="sendCommand"
        :disabled="!isConnected"
        class="input-field"
        placeholder="Enter command..."
      />
      <button @click="sendCommand" :disabled="!isConnected">Send</button>
    </div>
    
    <div class="debug-info">
      <small>Fallback terminal - XTerm.js failed to load</small>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useTerminalService } from '@/services/TerminalService.js'

const props = defineProps({
  sessionId: String,
  chatContext: Boolean,
  title: String
})

const {
  sendInput,
  connect: connectToService,
  disconnect,
  createSession,
  isConnected
} = useTerminalService()

const sessionId = ref(props.sessionId)
const outputLines = ref(['🔧 Fallback terminal loaded'])
const currentInput = ref('')
const connectionStatus = ref('disconnected')

const initializeSession = async () => {
  if (props.chatContext && props.sessionId) {
    sessionId.value = props.sessionId
  } else {
    try {
      const newSessionId = await createSession()
      sessionId.value = newSessionId
    } catch (error) {
      sessionId.value = `terminal_${Date.now()}`
    }
  }
}

const connect = async () => {
  if (!sessionId.value) await initializeSession()
  
  try {
    connectionStatus.value = 'connecting'
    await connectToService(sessionId.value, {
      onOutput: (data) => {
        outputLines.value.push(data.content || data)
      },
      onStatusChange: (status) => {
        connectionStatus.value = status
      },
      onError: (error) => {
        outputLines.value.push(`Error: ${error}`)
      }
    })
  } catch (error) {
    outputLines.value.push(`Connection failed: ${error.message}`)
  }
}

const sendCommand = () => {
  if (!currentInput.value.trim() || !isConnected(sessionId.value)) return
  
  const command = currentInput.value.trim()
  outputLines.value.push(`$ ${command}`)
  
  sendInput(sessionId.value, command + '\n')
  currentInput.value = ''
}

onMounted(async () => {
  await connect()
})

onUnmounted(() => {
  if (sessionId.value && isConnected(sessionId.value)) {
    disconnect(sessionId.value)
  }
})
</script>

<style scoped>
.simple-terminal-fallback {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #1a1a1a;
  color: #fff;
  font-family: monospace;
}

.terminal-header {
  display: flex;
  justify-content: space-between;
  padding: 1rem;
  background: #2d2d2d;
  border-bottom: 1px solid #444;
}

.terminal-output {
  flex: 1;
  padding: 1rem;
  overflow-y: auto;
  font-size: 14px;
}

.output-line {
  white-space: pre-wrap;
  margin-bottom: 2px;
}

.terminal-input {
  display: flex;
  padding: 0.5rem;
  background: #2d2d2d;
  border-top: 1px solid #444;
}

.prompt {
  color: #4ade80;
  margin-right: 0.5rem;
}

.input-field {
  flex: 1;
  background: none;
  border: none;
  color: #fff;
  font-family: monospace;
  outline: none;
}

button {
  margin-left: 0.5rem;
  padding: 0.25rem 0.5rem;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.debug-info {
  padding: 0.5rem;
  background: #f59e0b;
  color: #000;
  text-align: center;
}
</style>