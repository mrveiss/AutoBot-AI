<template>
  <div id="app" class="app-container">
    <!-- Animated background layers -->
    <div class="bg-gradient-layer"></div>
    <div class="bg-mesh-layer"></div>

    <header class="app-header">
      <div class="header-left">
        <div class="brand-container">
          <div class="brand-icon">
            <div class="logo-dot"></div>
            <div class="logo-pulse"></div>
          </div>
          <h1 class="brand-title">AutoBot <span class="brand-version">Pro</span></h1>
        </div>
        <div class="connection-status">
          <div class="status-indicator glass-card" :class="backendStatus.class" :title="backendStatus.message">
            <div class="status-icon-wrapper">
              <div class="status-dot" :class="backendStatus.class"></div>
              <span class="status-label">Backend</span>
            </div>
            <span class="status-text">{{ backendStatus.text }}</span>
          </div>
          <div class="status-indicator glass-card" :class="llmStatus.class" :title="llmStatus.message">
            <div class="status-icon-wrapper">
              <div class="status-dot" :class="llmStatus.class"></div>
              <span class="status-label">LLM</span>
            </div>
            <span class="status-text">{{ llmStatus.text }}</span>
          </div>
          <div class="status-indicator glass-card" :class="redisStatus.class" :title="redisStatus.message">
            <div class="status-icon-wrapper">
              <div class="status-dot" :class="redisStatus.class"></div>
              <span class="status-label">Redis</span>
            </div>
            <span class="status-text">{{ redisStatus.text }}</span>
          </div>
        </div>
      </div>
      <nav class="app-nav">
        <button class="nav-btn" @click="activeTab = 'chat'" :class="{ active: activeTab === 'chat' }">
          <div class="nav-icon">💬</div>
          <span>Chat</span>
          <div class="nav-indicator"></div>
        </button>
        <button class="nav-btn" @click="activeTab = 'voice'" :class="{ active: activeTab === 'voice' }">
          <div class="nav-icon">🎤</div>
          <span>Voice</span>
          <div class="nav-indicator"></div>
        </button>
        <button class="nav-btn" @click="activeTab = 'knowledge'" :class="{ active: activeTab === 'knowledge' }">
          <div class="nav-icon">🧠</div>
          <span>Knowledge</span>
          <div class="nav-indicator"></div>
        </button>
        <button class="nav-btn" @click="activeTab = 'terminal'" :class="{ active: activeTab === 'terminal' }">
          <div class="nav-icon">⚡</div>
          <span>Terminal</span>
          <div class="nav-indicator"></div>
        </button>
        <button class="nav-btn" @click="activeTab = 'settings'" :class="{ active: activeTab === 'settings' }">
          <div class="nav-icon">⚙️</div>
          <span>Settings</span>
          <div class="nav-indicator"></div>
        </button>
        <button class="nav-btn" @click="activeTab = 'files'" :class="{ active: activeTab === 'files' }">
          <div class="nav-icon">📁</div>
          <span>Files</span>
          <div class="nav-indicator"></div>
        </button>
        <button class="nav-btn" @click="activeTab = 'monitor'" :class="{ active: activeTab === 'monitor' }">
          <div class="nav-icon">📊</div>
          <span>Monitor</span>
          <div class="nav-indicator"></div>
        </button>
      </nav>
    </header>
    <main class="app-content">
      <div class="content-wrapper glass-panel">
        <Transition name="fade-slide" mode="out-in">
          <section v-if="activeTab === 'chat'" key="chat" class="section chat-section">
            <div class="section-header">
              <h2 class="section-title">AI Assistant</h2>
              <div class="section-actions">
                <button class="action-btn" @click="newChat">
                  <span class="btn-icon">+</span>
                  New Chat
                </button>
              </div>
            </div>
            <div class="section-content">
              <ChatInterface v-if="activeChatId" :key="activeChatId" />
            </div>
          </section>

          <section v-else-if="activeTab === 'voice'" key="voice" class="section voice-section">
            <div class="section-header">
              <h2 class="section-title">Voice Interface</h2>
              <div class="voice-status">
                <div class="voice-indicator"></div>
                Click to speak
              </div>
            </div>
            <div class="section-content">
              <VoiceInterface />
            </div>
          </section>

          <section v-else-if="activeTab === 'knowledge'" key="knowledge" class="section knowledge-section">
            <div class="section-header">
              <h2 class="section-title">Knowledge Base</h2>
              <div class="section-stats">
                <span class="stat-item">Knowledge Management</span>
              </div>
            </div>
            <div class="section-content">
              <KnowledgeManager />
            </div>
          </section>

          <section v-else-if="activeTab === 'terminal'" key="terminal" class="section terminal-section">
            <div class="section-header">
              <h2 class="section-title">Terminal Control</h2>
              <div class="terminal-status">
                <span class="status-dot connected"></span>
                Terminal Interface
              </div>
            </div>
            <div class="section-content">
              <TerminalWindow />
            </div>
          </section>

          <section v-else-if="activeTab === 'settings'" key="settings" class="section settings-section">
            <div class="section-header">
              <h2 class="section-title">System Configuration</h2>
            </div>
            <div class="section-content">
              <SettingsPanel />
            </div>
          </section>

          <section v-else-if="activeTab === 'files'" key="files" class="section files-section">
            <div class="section-header">
              <h2 class="section-title">File Manager</h2>
              <div class="section-actions">
                <button class="action-btn" @click="uploadFile">
                  <span class="btn-icon">📤</span>
                  Upload
                </button>
              </div>
            </div>
            <div class="section-content">
              <FileBrowser />
            </div>
          </section>

          <section v-else-if="activeTab === 'monitor'" key="monitor" class="section monitor-section">
            <div class="section-header">
              <h2 class="section-title">System Monitor</h2>
              <div class="refresh-btn" @click="refreshStats">
                <div class="refresh-icon">🔄</div>
              </div>
            </div>
            <div class="section-content">
              <SystemMonitor />
            </div>
          </section>
        </Transition>
      </div>
    </main>
    <footer class="app-footer" :class="{ 'collapsed': isFooterCollapsed }">
      <div class="footer-toggle" @click="toggleFooter">
        <span>{{ isFooterCollapsed ? 'Expand' : 'Collapse' }} System Info</span>
      </div>
      <div class="performance-stats" v-if="!isFooterCollapsed">
        <h4>System Performance</h4>
        <canvas id="performanceGraph" width="400" height="100"></canvas>
      </div>
      <div class="load-stats">
        <span>Current LLM: {{ getCurrentLLM() }}</span>
        <span>CPU Load: {{ performanceData.cpuLoad }}%</span>
        <span>Memory Usage: {{ performanceData.memoryUsage }}%</span>
        <span>GPU Usage: {{ performanceData.gpuUsage }}%</span>
      </div>
    </footer>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue';
import apiClient from './utils/ApiClient.js';
import ChatInterface from './components/ChatInterface.vue';
import SettingsPanel from './components/SettingsPanel.vue';
import FileBrowser from './components/FileBrowser.vue';
import HistoryView from './components/HistoryView.vue';
import KnowledgeManager from './components/KnowledgeManager.vue';
import VoiceInterface from './components/VoiceInterface.vue';
import SystemMonitor from './components/SystemMonitor.vue';
import TerminalWindow from './components/TerminalWindow.vue';

export default {
  name: 'App',
  components: {
    ChatInterface,
    SettingsPanel,
    FileBrowser,
    HistoryView,
    KnowledgeManager,
    VoiceInterface,
    SystemMonitor,
    TerminalWindow,
  },
  setup() {
    const activeTab = ref('chat');
    const isAgentPaused = ref(false);
    const chatSessions = ref([]);
    const activeChatId = ref(null);
    const isListening = ref(false);
    const refreshing = ref(false);
    const activeSessions = ref(0);
    const knowledgeStats = ref({ entries: 0, size: 0 });

    const handleNewChat = () => {
      // Create a new chat session and add it to the list
      const newChatId = Date.now().toString();
      chatSessions.value.push({
        id: newChatId,
        name: `Chat ${chatSessions.value.length + 1}`,
        messages: []
      });
      activeChatId.value = newChatId;
      console.log('New Chat created:', newChatId);
    };

    const handleSaveChat = () => {
      // Placeholder for save chat functionality
      console.log('Save Chat button clicked');
      if (activeChatId.value) {
        const activeChat = chatSessions.value.find(chat => chat.id === activeChatId.value);
        if (activeChat) {
          console.log('Saving chat:', activeChat.name);
          alert(`Chat "${activeChat.name}" saved. Full backend integration pending.`);
        }
      } else {
        alert('No active chat to save.');
      }
    };

    const handleLoadChat = () => {
      // Placeholder for load chat functionality
      console.log('Load Chat button clicked');
      if (chatSessions.value.length > 0) {
        // For demonstration, switch to the first chat in the list if available
        activeChatId.value = chatSessions.value[0].id;
        alert(`Loaded chat "${chatSessions.value[0].name}". Full backend integration pending.`);
      } else {
        alert('No chats available to load.');
      }
    };

    const handleResetChat = async () => {
      // Clear messages in the current active chat and ensure they are not reloaded
      if (activeChatId.value) {
        const activeChat = chatSessions.value.find(chat => chat.id === activeChatId.value);
        if (activeChat) {
          activeChat.messages = [];
          // Clear any persisted data for this chat
          localStorage.removeItem(`chat_${activeChat.id}_messages`);
          console.log('Current chat reset:', activeChat.name);
          alert(`Chat "${activeChat.name}" reset. Restarting all processes...`);

          try {
            // Send a request to restart backend and frontend processes
            await apiClient.restartBackend();
            console.log('Restart request sent successfully.');
            alert('All processes are restarting. Please wait for the application to reload.');
            // Optionally reload the page after a short delay
            setTimeout(() => {
              window.location.reload();
            }, 2000);
          } catch (error) {
            console.error('Error sending restart request:', error);
            alert('Error occurred while restarting. Please restart manually.');
          }
        }
      } else {
        alert('No active chat to reset.');
      }
    };

    const handlePauseAgent = () => {
      // Placeholder for pause agent functionality
      console.log('Pause Agent button clicked');
      isAgentPaused.value = true;
      alert('Pause Agent functionality is a placeholder. Full implementation pending.');
    };

    const handleResumeAgent = () => {
      // Placeholder for resume agent functionality
      console.log('Resume Agent button clicked');
      isAgentPaused.value = false;
      alert('Resume Agent functionality is a placeholder. Full implementation pending.');
    };

    const handleToggleAgent = () => {
      if (isAgentPaused.value) {
        handleResumeAgent();
      } else {
        handlePauseAgent();
      }
    };

    // Initialize with a default chat session
    handleNewChat();

    const performanceData = ref({
      cpuLoad: 0,
      memoryUsage: 0,
      gpuUsage: 0
    });

    // Connection status tracking
    const backendStatus = ref({
      connected: false,
      class: 'disconnected',
      text: 'Disconnected',
      message: 'Backend server is not responding'
    });

    const llmStatus = ref({
      connected: false,
      class: 'disconnected',
      text: 'Disconnected',
      message: 'LLM service is not available'
    });

    const redisStatus = ref({
      connected: false,
      class: 'disconnected',
      text: 'Disconnected',
      message: 'Redis service is not available or RediSearch module is missing'
    });

    const checkRedisConnection = async () => {
      if (!backendStatus.value.connected) {
        redisStatus.value = {
          connected: false,
          class: 'disconnected',
          text: 'Disconnected',
          message: 'Redis status unknown because backend is disconnected'
        };
        return false;
      }
      try {
        const data = await apiClient.checkHealth();
        if (data.redis_status === 'connected') {
          redisStatus.value = {
            connected: true,
            class: 'connected',
            text: 'Connected',
            message: data.redis_search_module_loaded ?
              'Redis with RediSearch available' :
              'Redis connected but RediSearch not loaded'
          };
          return true;
        } else if (data.redis_status === 'not_configured') {
          redisStatus.value = {
            connected: false,
            class: 'warning',
            text: 'Not Configured',
            message: 'Redis is not configured in the backend'
          };
          return false;
        }
        throw new Error('Redis status check failed');
      } catch (error) {
        redisStatus.value = {
          connected: false,
          class: 'disconnected',
          text: 'Disconnected',
          message: `Redis connection failed: ${error.message}`
        };
        return false;
      }
    };

    // Connection status checking functions
    const checkBackendConnection = async () => {
      try {
        await apiClient.checkHealth();
        backendStatus.value = {
          connected: true,
          class: 'connected',
          text: 'Connected',
          message: 'Backend server is responding'
        };
        return true;
      } catch (error) {
        backendStatus.value = {
          connected: false,
          class: 'disconnected',
          text: 'Disconnected',
          message: `Backend connection failed: ${error.message}`
        };
        return false;
      }
    };

    const checkLLMConnection = async () => {
      if (!backendStatus.value.connected) {
        llmStatus.value = {
          connected: false,
          class: 'disconnected',
          text: 'Disconnected',
          message: 'LLM status unknown because backend is disconnected'
        };
        return false;
      }
      try {
        const data = await apiClient.checkHealth();
        if (data.ollama === 'connected') {
          llmStatus.value = {
            connected: true,
            class: 'connected',
            text: 'Connected',
            message: 'Ollama LLM service is available'
          };
          return true;
        } else {
          llmStatus.value = {
            connected: false,
            class: 'disconnected',
            text: 'Disconnected',
            message: 'Ollama service not available'
          };
          return false;
        }
      } catch (error) {
        llmStatus.value = {
          connected: false,
          class: 'disconnected',
          text: 'Disconnected',
          message: `LLM connection failed: ${error.message}`
        };
        return false;
      }
    };

    const checkConnections = async () => {
      await checkBackendConnection();
      await checkLLMConnection();
      await checkRedisConnection();
      await fetchCurrentLLM(); // Fetch current LLM info
    };

    // Function to update performance data (placeholder for real data)
    const updatePerformanceData = () => {
      // Simulate fetching performance data
      performanceData.value.cpuLoad = Math.floor(Math.random() * 100);
      performanceData.value.memoryUsage = Math.floor(Math.random() * 100);
      performanceData.value.gpuUsage = Math.floor(Math.random() * 100);
      drawPerformanceGraph();
    };

    // Function to draw performance graph
    const drawPerformanceGraph = () => {
      const canvas = document.getElementById('performanceGraph');
      if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Draw grid lines
        ctx.strokeStyle = '#e9ecef';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 100; i += 20) {
          ctx.beginPath();
          ctx.moveTo(50 + (i * 3), 20);
          ctx.lineTo(50 + (i * 3), 80);
          ctx.stroke();
        }

        // CPU Load - Blue
        ctx.fillStyle = '#007bff';
        ctx.fillRect(50, 25, performanceData.value.cpuLoad * 3, 15);

        // Memory Usage - Green
        ctx.fillStyle = '#28a745';
        ctx.fillRect(50, 45, performanceData.value.memoryUsage * 3, 15);

        // GPU Usage - Red
        ctx.fillStyle = '#dc3545';
        ctx.fillRect(50, 65, performanceData.value.gpuUsage * 3, 15);

        // Labels
        ctx.fillStyle = '#000';
        ctx.font = '12px Arial';
        ctx.textAlign = 'right';
        ctx.fillText('CPU', 40, 35);
        ctx.fillText('Memory', 40, 55);
        ctx.fillText('GPU', 40, 75);

        // Percentage labels on bars
        ctx.textAlign = 'left';
        ctx.fillStyle = '#fff';
        if (performanceData.value.cpuLoad > 10) {
          ctx.fillText(`${performanceData.value.cpuLoad}%`, 55, 35);
        } else {
          ctx.fillStyle = '#000';
          ctx.fillText(`${performanceData.value.cpuLoad}%`, 55 + (performanceData.value.cpuLoad * 3), 35);
        }
        if (performanceData.value.memoryUsage > 10) {
          ctx.fillStyle = '#fff';
          ctx.fillText(`${performanceData.value.memoryUsage}%`, 55, 55);
        } else {
          ctx.fillStyle = '#000';
          ctx.fillText(`${performanceData.value.memoryUsage}%`, 55 + (performanceData.value.memoryUsage * 3), 55);
        }
        if (performanceData.value.gpuUsage > 10) {
          ctx.fillStyle = '#fff';
          ctx.fillText(`${performanceData.value.gpuUsage}%`, 55, 75);
        } else {
          ctx.fillStyle = '#000';
          ctx.fillText(`${performanceData.value.gpuUsage}%`, 55 + (performanceData.value.gpuUsage * 3), 75);
        }
      }
    };

    // Update performance data initially and periodically
    // Use a timeout as a workaround if onMounted causes issues
    setTimeout(() => {
      updatePerformanceData();
      setInterval(updatePerformanceData, 5000);
    }, 100);

    // Load settings from local storage or use a default structure
    const settings = ref({});

    const loadSettings = () => {
      const savedSettings = localStorage.getItem('chat_settings');
      if (savedSettings) {
        try {
          settings.value = JSON.parse(savedSettings);
        } catch (e) {
          console.error('Error parsing saved settings:', e);
          settings.value = { backend: { llm: { provider_type: 'local', local: { provider: 'ollama', providers: { ollama: { selected_model: 'Not selected' } } }, cloud: { provider: 'openai', providers: { openai: { selected_model: 'Not selected' } } } } } };
        }
      } else {
        settings.value = { backend: { llm: { provider_type: 'local', local: { provider: 'ollama', providers: { ollama: { selected_model: 'Not selected' } } }, cloud: { provider: 'openai', providers: { openai: { selected_model: 'Not selected' } } } } } };
      }
    };

    const currentLLM = ref('Loading...');

    const getCurrentLLM = () => {
      // If LLM is disconnected, show that instead of model name
      if (!llmStatus.value.connected) {
        return 'Disconnected';
      }
      return currentLLM.value;
    };

    const newChat = () => {
      // Create a new chat session
      const newChatId = Date.now().toString();
      chatSessions.value.push({
        id: newChatId,
        name: `Chat ${chatSessions.value.length + 1}`,
        messages: []
      });
      activeChatId.value = newChatId;
      console.log('New Chat created:', newChatId);
    };

    const uploadFile = () => {
      // File upload functionality
      const input = document.createElement('input');
      input.type = 'file';
      input.multiple = true;
      input.onchange = (e) => {
        const files = Array.from(e.target.files);
        console.log('Files selected for upload:', files);
        // TODO: Implement file upload to backend
      };
      input.click();
    };

    const refreshStats = async () => {
      refreshing.value = true;
      try {
        // Fetch system stats
        await checkConnections();
        await updatePerformanceData();
        // TODO: Fetch knowledge base stats
        // TODO: Fetch active terminal sessions
      } finally {
        setTimeout(() => {
          refreshing.value = false;
        }, 1000);
      }
    };

    const fetchCurrentLLM = async () => {
      if (!backendStatus.value.connected) {
        currentLLM.value = 'Backend Disconnected';
        return;
      }

      try {
        const response = await apiClient.get('/api/system/status');
        const data = await response.json();
        if (data.current_llm) {
          currentLLM.value = data.current_llm;
        } else {
          currentLLM.value = 'Not configured';
        }
      } catch (error) {
        console.error('Error fetching current LLM:', error);
        currentLLM.value = 'Connection Error';
      }
    };

    onMounted(async () => {
      loadSettings();
      // Set up an interval to check for settings updates
      setInterval(() => {
        loadSettings();
      }, 5000); // Check every 5 seconds

      // Initial connection check
      await checkConnections();

      // Set up periodic connection checking
      setInterval(checkConnections, 10000); // Check every 10 seconds
    });

    const isFooterCollapsed = ref(false);

    const toggleFooter = () => {
      isFooterCollapsed.value = !isFooterCollapsed.value;
    };

    return {
      activeTab,
      isAgentPaused,
      chatSessions,
      activeChatId,
      handleNewChat,
      handleSaveChat,
      handleLoadChat,
      handleResetChat,
      handlePauseAgent,
      handleResumeAgent,
      handleToggleAgent,
      performanceData,
      settings,
      isFooterCollapsed,
      toggleFooter,
      getCurrentLLM,
      currentLLM,
      fetchCurrentLLM,
      backendStatus,
      llmStatus,
      redisStatus,
      checkConnections,
      newChat,
      uploadFile,
      refreshStats,
      isListening,
      refreshing,
      activeSessions,
      knowledgeStats
    };
  },
};
</script>

<style scoped>
/* Executive Design System CSS Variables */
:root {
  /* Executive Color Palette */
  --executive-navy: #1a2332;
  --executive-dark-navy: #0f1419;
  --executive-charcoal: #2d3748;
  --executive-slate: #4a5568;
  --executive-platinum: #f7fafc;
  --executive-silver: #e2e8f0;
  --executive-accent: #3182ce;
  --executive-gold: #d69e2e;
  --executive-success: #38a169;
  --executive-warning: #ed8936;
  --executive-danger: #e53e3e;

  /* Typography */
  --font-primary: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;

  /* Executive Shadows */
  --shadow-soft: 0 2px 4px rgba(26, 35, 50, 0.08);
  --shadow-medium: 0 4px 12px rgba(26, 35, 50, 0.12);
  --shadow-strong: 0 8px 24px rgba(26, 35, 50, 0.16);
  --shadow-executive: 0 12px 36px rgba(26, 35, 50, 0.2);
}

.app-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  font-family: var(--font-primary);
  background: linear-gradient(145deg, var(--executive-navy) 0%, var(--executive-dark-navy) 100%);
  color: var(--executive-platinum);
  overflow-x: hidden;
  box-sizing: border-box;
  position: relative;
  -ms-overflow-style: none;
  scrollbar-width: none;
  font-weight: 400;
  line-height: 1.6;
}

/* Executive Background Layers */
.bg-gradient-layer {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(-45deg,
    rgba(49, 130, 206, 0.05),
    rgba(26, 35, 50, 0.05),
    rgba(45, 55, 72, 0.05),
    rgba(74, 85, 104, 0.05)
  );
  background-size: 400% 400%;
  animation: subtleGradientShift 30s ease infinite;
  z-index: -2;
}

.bg-mesh-layer {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-image:
    radial-gradient(circle at 20% 80%, rgba(49, 130, 206, 0.03) 0%, transparent 50%),
    radial-gradient(circle at 80% 20%, rgba(214, 158, 46, 0.02) 0%, transparent 50%),
    radial-gradient(circle at 40% 40%, rgba(255, 255, 255, 0.01) 0%, transparent 50%),
    linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.005) 50%, transparent 100%);
  animation: subtleMeshFloat 45s ease-in-out infinite;
  z-index: -1;
}

@keyframes subtleGradientShift {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}

@keyframes subtleMeshFloat {
  0%, 100% { transform: translateY(0) rotate(0deg); }
  33% { transform: translateY(-3px) rotate(0.2deg); }
  66% { transform: translateY(2px) rotate(-0.2deg); }
}

/* Glass morphism utility class */
.glass-card {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
}

.glass-panel {
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 20px;
  box-shadow: var(--shadow-executive);
}

.app-container::-webkit-scrollbar {
  display: none; /* Hide scrollbar for Chrome, Safari, and Opera */
}

.app-header {
  background: rgba(47, 58, 78, 0.95);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  color: var(--executive-platinum);
  padding: 16px 32px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: var(--shadow-strong);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  position: sticky;
  top: 0;
  z-index: 1000;
  transition: all 0.3s cubic-bezier(0.25, 0.1, 0.25, 1);
  min-height: 72px;
}

.brand-container {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-icon {
  position: relative;
  width: 40px;
  height: 40px;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--executive-accent), var(--executive-gold));
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-medium);
  transition: all 0.3s ease;
}

.brand-icon:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-strong);
}

.logo-dot {
  width: 12px;
  height: 12px;
  background: white;
  border-radius: 50%;
  position: relative;
  z-index: 2;
  box-shadow: 0 0 8px rgba(255, 255, 255, 0.4);
}

.logo-pulse {
  position: absolute;
  width: 32px;
  height: 32px;
  border: 2px solid rgba(79, 172, 254, 0.3);
  border-radius: 50%;
  animation: executivePulse 3s ease-in-out infinite;
}

@keyframes executivePulse {
  0% { transform: scale(1); opacity: 0.4; }
  50% { transform: scale(1.2); opacity: 0.2; }
  100% { transform: scale(1.4); opacity: 0; }
}

.brand-title {
  font-size: 22px;
  font-weight: 600;
  color: var(--executive-platinum);
  margin: 0;
  letter-spacing: -0.025em;
  font-family: var(--font-primary);
}

.brand-version {
  font-size: 10px;
  background: linear-gradient(90deg, #4facfe, #00f2fe);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.app-header h1 {
  margin: 0;
  font-size: clamp(18px, 2.5vw, 24px); /* Responsive font size */
}

.header-left {
  display: flex;
  align-items: center;
  gap: 20px;
}

.connection-status {
  display: flex;
  gap: 8px;
}

.status-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 6px 10px;
  border-radius: 10px;
  font-size: 9px;
  font-weight: 500;
  cursor: help;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  min-width: 60px;
  position: relative;
  overflow: hidden;
}

.status-indicator:hover {
  transform: translateY(-2px) scale(1.02);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15);
}

.status-icon-wrapper {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  transition: all 0.3s ease;
  position: relative;
}

.status-dot::before {
  content: '';
  position: absolute;
  width: 100%;
  height: 100%;
  border-radius: 50%;
  animation: statusPulse 2s infinite;
}

.status-dot.connected {
  background: linear-gradient(45deg, #10b981, #34d399);
  box-shadow: 0 0 12px rgba(16, 185, 129, 0.4);
}

.status-dot.connected::before {
  background: rgba(16, 185, 129, 0.3);
}

.status-dot.disconnected {
  background: linear-gradient(45deg, #ef4444, #f87171);
  box-shadow: 0 0 12px rgba(239, 68, 68, 0.4);
}

.status-dot.disconnected::before {
  background: rgba(239, 68, 68, 0.3);
}

.status-dot.warning {
  background: linear-gradient(45deg, #f59e0b, #fbbf24);
  box-shadow: 0 0 12px rgba(245, 158, 11, 0.4);
}

.status-dot.warning::before {
  background: rgba(245, 158, 11, 0.3);
}

@keyframes statusPulse {
  0% { transform: scale(1); opacity: 1; }
  100% { transform: scale(2); opacity: 0; }
}

.status-label {
  color: rgba(255, 255, 255, 0.9);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  font-size: 8px;
}

.status-text {
  color: rgba(255, 255, 255, 0.7);
  font-size: 8px;
  text-align: center;
}

.status-indicator.connected {
  background-color: #d4edda;
  color: #155724;
  border-color: #c3e6cb;
}

.status-indicator.disconnected {
  background-color: #f8d7da;
  color: #721c24;
  border-color: #f5c6cb;
}

.status-indicator.warning {
  background-color: #fff3cd;
  color: #856404;
  border-color: #ffeaa7;
}

.status-icon {
  font-size: 12px;
  min-width: 14px;
}

.status-text {
  font-size: 10px;
  font-weight: 600;
  white-space: nowrap;
}

.status-indicator:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.app-nav {
  display: flex;
  gap: 3px;
  background: rgba(255, 255, 255, 0.05);
  padding: 6px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.nav-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.75);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  padding: 12px 16px;
  border-radius: 12px;
  transition: all 0.3s cubic-bezier(0.25, 0.1, 0.25, 1);
  position: relative;
  overflow: hidden;
  min-width: 64px;
  backdrop-filter: blur(8px);
}

.nav-btn:hover {
  color: white;
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.15);
  transform: translateY(-2px);
  box-shadow: var(--shadow-medium);
}

.nav-btn.active {
  color: white;
  background: var(--executive-accent);
  border-color: var(--executive-accent);
  box-shadow: var(--shadow-strong);
}

.nav-icon {
  font-size: 16px;
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.2));
  transition: transform 0.3s ease;
}

.nav-btn:hover .nav-icon {
  transform: scale(1.1);
}

.nav-indicator {
  position: absolute;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%) scaleX(0);
  width: 70%;
  height: 2px;
  background: linear-gradient(90deg, #4facfe, #00f2fe);
  border-radius: 1px;
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.nav-btn.active .nav-indicator {
  transform: translateX(-50%) scaleX(1);
}

.app-nav button.active {
  background-color: rgba(255, 255, 255, 0.2);
  border-radius: 4px;
}

.app-content {
  flex: 1;
  padding: 24px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

.content-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  margin: 0;
  padding: 0;
}

.section {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px 32px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.02);
}

.section-title {
  font-size: 24px;
  font-weight: 600;
  margin: 0;
  color: var(--executive-platinum);
  letter-spacing: -0.02em;
  font-family: var(--font-primary);
}

.section-actions {
  display: flex;
  gap: 12px;
}

.section-content {
  flex: 1;
  padding: 32px;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0; /* Critical: Allow flex children to shrink and create scrollable areas */
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: white;
  padding: 12px 20px;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.action-btn:hover {
  background: rgba(255, 255, 255, 0.15);
  transform: translateY(-1px);
  box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);
}

.btn-icon {
  font-size: 16px;
}

/* Section-specific styles */
.voice-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.8);
}

.voice-indicator {
  width: 8px;
  height: 8px;
  background: #ef4444;
  border-radius: 50%;
  transition: all 0.3s ease;
}

.voice-status.listening .voice-indicator {
  background: #10b981;
  animation: voicePulse 1s ease-in-out infinite;
}

@keyframes voicePulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.3); }
}

.section-stats {
  display: flex;
  gap: 16px;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.7);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.terminal-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.8);
}

.refresh-btn {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.refresh-btn:hover {
  background: rgba(255, 255, 255, 0.15);
  transform: translateY(-1px);
}

.refresh-icon {
  font-size: 18px;
  transition: transform 0.3s ease;
}

.refresh-icon.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Transition animations */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(20px) scale(0.95);
}

.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-20px) scale(0.95);
}

.chat-section, .knowledge-section, .settings-section, .files-section, .history-section {
  display: flex;
  height: 100%;
  width: 100%; /* Ensure it fits within parent container */
  background-color: white;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
  box-sizing: border-box;
}

.knowledge-section, .settings-section, .files-section, .history-section {
  overflow-y: auto; /* Allow scrolling for content */
  padding: 20px;
}



.chat-window {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.app-footer {
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  padding: 16px 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  flex-direction: column;
  align-items: center;
  position: sticky;
  bottom: 0;
  z-index: 1000;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.app-footer.collapsed {
  padding: clamp(2px, 0.5vw, 5px) clamp(10px, 2vw, 20px);
}

.footer-toggle {
  cursor: pointer;
  margin-bottom: 16px;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.8);
  display: flex;
  justify-content: center;
  width: 100%;
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  transition: all 0.3s ease;
}

.footer-toggle:hover {
  color: white;
  background: rgba(255, 255, 255, 0.1);
}

.footer-toggle:hover {
  text-decoration: underline;
}

.action-buttons {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: clamp(5px, 1vw, 10px);
  max-width: 600px; /* Limit width on large screens */
}

.performance-stats {
  display: flex;
  flex-direction: column;
  align-items: center;
  max-width: 800px;
  width: 100%;
}

.performance-stats h4 {
  margin: 0 0 16px 0;
  font-size: 16px;
  color: rgba(255, 255, 255, 0.9);
  font-weight: 600;
}

#performanceGraph {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 12px;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.load-stats {
  display: flex;
  justify-content: space-around;
  width: 100%;
  margin-top: 16px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.8);
  gap: 24px;
}

button:not(.nav-btn):not(.action-btn):not(.refresh-btn), .control-button, .action-buttons button {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  font-size: 14px;
  font-weight: 500;
  position: relative;
  overflow: hidden;
}

button:not(.nav-btn):not(.action-btn):not(.refresh-btn)::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
  transition: left 0.5s ease;
}

button:not(.nav-btn):not(.action-btn):not(.refresh-btn):hover::before {
  left: 100%;
}

button:not(.nav-btn):not(.action-btn):not(.refresh-btn):hover, .control-button:hover, .action-buttons button:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 40px rgba(102, 126, 234, 0.4);
}

button:not(.nav-btn):not(.action-btn):not(.refresh-btn):disabled, .control-button:disabled, .action-buttons button:disabled {
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.5);
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}


@media (max-width: 768px) {
  .action-buttons {
    flex-wrap: wrap;
    justify-content: space-around;
  }

  .action-buttons button {
    margin-bottom: 5px; /* Add spacing for wrapped buttons */
  }
}

@media (min-width: 1200px) {
  .app-container {
    max-width: 100vw; /* Prevent horizontal scrolling on large screens */
    margin: 0 auto;
    overflow-x: hidden; /* Reinforce no horizontal scrolling */
  }
}

/* Target elements with specific data attribute for overflow handling */
[data-v-1d553c0c] {
  max-width: 100%; /* Ensure it doesn't exceed container width */
  width: 100%; /* Fit within visible screen */
  box-sizing: border-box; /* Include padding in width calculation */
  overflow: hidden; /* Prevent scrollbars on the element itself */
}

/* Allow inner elements to have scrollbars if needed */
[data-v-1d553c0c] * {
  overflow-x: auto; /* Inner elements can have scrollbars */
  box-sizing: border-box;
}
</style>
