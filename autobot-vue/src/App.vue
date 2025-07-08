<template>
  <div id="app" class="app-container">
    <header class="app-header">
      <h1>AutoBot</h1>
      <nav class="app-nav">
        <button @click="activeTab = 'chat'" :class="{ active: activeTab === 'chat' }">Chat</button>
        <button @click="activeTab = 'settings'" :class="{ active: activeTab === 'settings' }">Settings</button>
        <button @click="activeTab = 'files'" :class="{ active: activeTab === 'files' }">Files</button>
        <button @click="activeTab = 'history'" :class="{ active: activeTab === 'history' }">History</button>
      </nav>
    </header>
    <main class="app-content">
    <section v-if="activeTab === 'chat'" class="chat-section">
      <div class="chat-window">
        <ChatInterface v-if="activeChatId" :key="activeChatId" />
      </div>
    </section>
      <section v-else-if="activeTab === 'settings'" class="settings-section">
        <SettingsPanel />
      </section>
      <section v-else-if="activeTab === 'files'" class="files-section">
        <FileBrowser />
      </section>
    <section v-else-if="activeTab === 'history'" class="history-section">
      <div class="chat-window">
        <HistoryView />
      </div>
    </section>
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
import ChatInterface from './components/ChatInterface.vue';
import SettingsPanel from './components/SettingsPanel.vue';
import FileBrowser from './components/FileBrowser.vue';
import HistoryView from './components/HistoryView.vue';

export default {
  name: 'App',
  components: {
    ChatInterface,
    SettingsPanel,
    FileBrowser,
    HistoryView,
  },
  setup() {
    const activeTab = ref('chat');
    const isAgentPaused = ref(false);
    const chatSessions = ref([]);
    const activeChatId = ref(null);

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
            const response = await fetch('/api/restart', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({ action: 'restart_all' })
            });
            if (response.ok) {
              console.log('Restart request sent successfully.');
              alert('All processes are restarting. Please wait for the application to reload.');
              // Optionally reload the page after a short delay
              setTimeout(() => {
                window.location.reload();
              }, 2000);
            } else {
              console.error('Failed to send restart request:', response.statusText);
              alert('Failed to restart processes. Please restart manually.');
            }
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
    
    const getCurrentLLM = () => {
      try {
        if (settings.value && settings.value.backend && settings.value.backend.llm) {
          const llm = settings.value.backend.llm;
          if (llm.provider_type === 'local') {
            return `${llm.local.provider.charAt(0).toUpperCase() + llm.local.provider.slice(1)} - ${llm.local.providers[llm.local.provider].selected_model || 'Not selected'}`;
          } else {
            return `${llm.cloud.provider.charAt(0).toUpperCase() + llm.cloud.provider.slice(1)} - ${llm.cloud.providers[llm.cloud.provider].selected_model || 'Not selected'}`;
          }
        }
      } catch (error) {
        console.error('Error accessing LLM settings:', error);
      }
      return 'Not selected';
    };
    
    onMounted(() => {
      loadSettings();
      // Set up an interval to check for settings updates
      setInterval(() => {
        loadSettings();
      }, 5000); // Check every 5 seconds
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
      getCurrentLLM
    };
  },
};
</script>

<style scoped>
.app-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw; /* Ensure full viewport width */
  font-family: 'Arial', sans-serif;
  background-color: #f0f2f5;
  color: #333;
  overflow-x: hidden; /* Prevent horizontal scrolling */
  box-sizing: border-box; /* Include padding and borders in width calculation */
  -ms-overflow-style: none; /* Hide scrollbar for Edge */
  scrollbar-width: none; /* Hide scrollbar for Firefox */
}

.app-container::-webkit-scrollbar {
  display: none; /* Hide scrollbar for Chrome, Safari, and Opera */
}

.app-header {
  background-color: #007bff;
  color: white;
  padding: 10px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
  position: sticky;
  top: 0;
  z-index: 1000; /* Ensure header stays on top */
}

.app-header h1 {
  margin: 0;
  font-size: clamp(18px, 2.5vw, 24px); /* Responsive font size */
}

.app-nav {
  display: flex;
  gap: clamp(5px, 1vw, 10px); /* Responsive gap */
}

.app-nav button {
  background: none;
  border: none;
  color: white;
  font-size: clamp(14px, 1.8vw, 16px); /* Responsive font size */
  cursor: pointer;
  padding: clamp(3px, 0.5vw, 5px) clamp(5px, 1vw, 10px);
  transition: background-color 0.3s;
}

.app-nav button.active {
  background-color: rgba(255, 255, 255, 0.2);
  border-radius: 4px;
}

.app-content {
  flex: 1;
  padding: clamp(10px, 2vw, 20px);
  display: flex;
  flex-direction: column;
  overflow-y: hidden; /* Prevent scrolling on the main content area */
  overflow-x: hidden; /* Explicitly prevent horizontal scrolling */
  width: 100%; /* Ensure content stays within container width */
  box-sizing: border-box;
}

.chat-section {
  display: flex;
  height: 100%;
  width: 100%; /* Ensure it fits within parent container */
  background-color: white;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
  box-sizing: border-box;
}



.chat-window {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.app-footer {
  background-color: #e9ecef;
  padding: clamp(5px, 1vw, 10px) clamp(10px, 2vw, 20px);
  border-top: 1px solid #dee2e6;
  display: flex;
  flex-direction: column;
  align-items: center;
  position: sticky;
  bottom: 0;
  z-index: 1000; /* Ensure footer stays on bottom */
  flex-wrap: wrap;
  transition: height 0.3s ease;
}

.app-footer.collapsed {
  padding: clamp(2px, 0.5vw, 5px) clamp(10px, 2vw, 20px);
}

.footer-toggle {
  cursor: pointer;
  margin-bottom: clamp(5px, 0.5vw, 10px);
  font-size: clamp(12px, 1.5vw, 14px);
  color: #007bff;
  display: flex;
  justify-content: center;
  width: 100%;
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
  max-width: 600px;
}

.performance-stats h4 {
  margin: 0 0 clamp(5px, 0.5vw, 10px) 0;
  font-size: clamp(12px, 1.5vw, 14px);
  color: #007bff;
}

#performanceGraph {
  background-color: #fff;
  border: 1px solid #e9ecef;
  border-radius: 4px;
}

.load-stats {
  display: flex;
  justify-content: space-around;
  width: 100%;
  margin-top: clamp(5px, 0.5vw, 10px);
  font-size: clamp(10px, 1.2vw, 12px);
}

button, .control-button, .action-buttons button {
  background-color: #007bff;
  color: white;
  border: none;
  padding: clamp(5px, 0.8vw, 8px) clamp(8px, 1.2vw, 12px);
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s;
  font-size: clamp(12px, 1.5vw, 14px);
  min-width: fit-content; /* Ensure buttons don't shrink too much */
}

button:hover, .control-button:hover, .action-buttons button:hover {
  background-color: #0056b3;
}

button:disabled, .control-button:disabled, .action-buttons button:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
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
