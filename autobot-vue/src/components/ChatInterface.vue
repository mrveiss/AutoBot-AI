<template>
  <div class="chat-interface">
       <h2>Chat with AutoBot</h2>
    <div class="chat-container">
      <div class="chat-sidebar" :class="{ 'collapsed': sidebarCollapsed }">
        <button class="toggle-sidebar" @click="sidebarCollapsed = !sidebarCollapsed">
          {{ sidebarCollapsed ? '▶' : '◀' }}
        </button>
        <div class="sidebar-content" v-if="!sidebarCollapsed">
          <h3>Chat History</h3>
          <div class="conversation-list">
            <div v-for="chat in chatList" :key="chat.chatId" class="conversation-item" :class="{ 'active': currentChatId === chat.chatId }" @click="switchChat(chat.chatId)">
              <span>{{ chat.name || getChatPreview(chat.chatId) || `Chat ${chat.chatId.slice(0, 8)}...` }}</span>
              <div class="conversation-actions">
                <button class="action-icon" @click.stop="editChatName(chat.chatId)" title="Edit Name">✎</button>
                <button class="action-icon delete" @click.stop="deleteSpecificChat(chat.chatId)" title="Delete">🗑️</button>
              </div>
            </div>
            <div class="chat-control-buttons">
              <button class="control-button small" @click="newChat">New Chat</button>
              <button class="control-button small" @click="resetChat" :disabled="!currentChatId">Reset Chat</button>
              <button class="control-button small" @click="deleteSpecificChat" :disabled="!currentChatId">Delete Chat</button>
              <button class="control-button small" @click="refreshChatList">Refresh</button>
            </div>
          </div>
          <h3>Message Display</h3>
          <div class="preference-toggle">
            <label>
              <input type="checkbox" v-model="settings.message_display.show_thoughts" />
              Show Thoughts
            </label>
            <label>
              <input type="checkbox" v-model="settings.message_display.show_json" />
              Show JSON Output
            </label>
            <label>
              <input type="checkbox" v-model="settings.message_display.show_utility" />
              Show Utility Messages
            </label>
            <label>
              <input type="checkbox" v-model="settings.message_display.show_planning" />
              Show Planning Messages
            </label>
            <label>
              <input type="checkbox" v-model="settings.message_display.show_debug" />
              Show Debug Messages
            </label>
            <label>
              <input type="checkbox" v-model="settings.chat.auto_scroll" />
              Autoscroll
            </label>
          </div>
          <h3>Backend Control</h3>
          <div class="preference-toggle">
            <button class="control-button" @click="startBackendServer" :disabled="backendStarting">
              {{ backendStarting ? 'Starting...' : 'Start Backend Server' }}
            </button>
          </div>
        </div>
      </div>
      <div class="chat-messages" ref="chatMessages" role="log">
        <div v-for="(message, index) in filteredMessages" :key="index" :class="['message', message.sender, message.type]">
          <div class="message-content" v-html="formatMessage(message.text, message.type)"></div>
          <div class="message-timestamp">{{ message.timestamp }}</div>
        </div>
      </div>
    </div>
    <!-- Chat controls moved to sidebar -->
    <div class="chat-input">
      <textarea id="chat-input" v-model="inputMessage" placeholder="Type your message or goal for AutoBot..." @keyup.enter="sendMessage"></textarea>
      <button @click="sendMessage">Send</button>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, nextTick, computed, watch } from 'vue';

export default {
  name: 'ChatInterface',
  setup() {
    const messages = ref([]);
    const inputMessage = ref('');
    const chatMessages = ref(null);
    // Settings structure to match a comprehensive config file
    const settings = ref({
      message_display: {
        show_thoughts: true,
        show_json: false, // Default to off as per user feedback
        show_utility: false, // Default to off as per user feedback
        show_planning: true,
        show_debug: false // Default to off to reduce noise
      },
      chat: {
        auto_scroll: true,
        max_messages: 100
      },
      backend: {
        use_phi2: false,
        api_endpoint: 'http://localhost:8001',
        ollama_endpoint: 'http://localhost:11434',
        ollama_model: 'tinyllama:latest',
        streaming: false
      },
      ui: {
        theme: 'light', // Options: 'light', 'dark'
        font_size: 'medium' // Options: 'small', 'medium', 'large'
      }
    });
    const sidebarCollapsed = ref(false);
    const backendStarting = ref(false);
    const chatList = ref([]);
    const currentChatId = ref(null);
    const isAgentPaused = ref(false);
    const prompts = ref([]);
    const defaults = ref({});
    let eventSource = null;

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

    // Connection status checking functions
    const checkBackendConnection = async () => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/health`, {
          method: 'GET',
          timeout: 5000
        });
        if (response.ok) {
          backendStatus.value = {
            connected: true,
            class: 'connected',
            text: 'Connected',
            message: 'Backend server is responding'
          };
          return true;
        } else {
          throw new Error(`Backend returned ${response.status}`);
        }
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
      try {
        // Check if we can reach the LLM endpoint
        const llmEndpoint = settings.value.backend.ollama_endpoint || 'http://localhost:11434';
        const response = await fetch(`${llmEndpoint}/api/tags`, {
          method: 'GET',
          timeout: 5000
        });
        if (response.ok) {
          llmStatus.value = {
            connected: true,
            class: 'connected',
            text: 'Connected',
            message: 'LLM service is available'
          };
          return true;
        } else {
          throw new Error(`LLM service returned ${response.status}`);
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
    };

    onMounted(async () => {
      // Check if there are persisted messages for this chat session
      const chatId = window.location.hash.split('chatId=')[1] || 'default';
      const persistedMessages = localStorage.getItem(`chat_${chatId}_messages`);
      if (persistedMessages) {
        messages.value = JSON.parse(persistedMessages);
      } else {
        // No default welcome message
        messages.value = [];
      }
      
      // Load settings from local storage if available
      const savedSettings = localStorage.getItem('chat_settings');
      if (savedSettings) {
        settings.value = JSON.parse(savedSettings);
      }
      
      // Check connections first
      await checkConnections();
      
      // Fetch backend settings to override with latest configuration
      await fetchBackendSettings();
      // Load system prompts on initialization
      await loadPrompts();
      
      // Set up periodic connection checking
      setInterval(checkConnections, 10000); // Check every 10 seconds
    });
    
    // Function to save settings to local storage and backend
    const saveSettings = async () => {
      localStorage.setItem('chat_settings', JSON.stringify(settings.value));
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/settings`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ settings: settings.value })
        });
        if (!response.ok) {
          console.error('Failed to save settings to backend:', response.statusText);
        }
      } catch (error) {
        console.error('Error saving settings to backend:', error);
      }
    };

    // Function to save backend-specific settings
    const saveBackendSettings = async () => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/settings/backend`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ settings: { backend: settings.value.backend } })
        });
        if (!response.ok) {
          console.error('Failed to save backend settings:', response.statusText);
        } else {
          console.log('Backend settings saved successfully.');
        }
      } catch (error) {
        console.error('Error saving backend settings:', error);
      }
    };

    // Function to fetch backend settings
    const fetchBackendSettings = async () => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/settings/backend`);
        if (response.ok) {
          const backendSettings = await response.json();
          settings.value.backend = { ...settings.value.backend, ...backendSettings };
          console.log('Backend settings loaded successfully.');
        } else {
          console.error('Failed to load backend settings:', response.statusText);
        }
      } catch (error) {
        console.error('Error loading backend settings:', error);
      }
    };

    // Function to load system prompts from backend
    const loadPrompts = async () => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/prompts`);
        if (response.ok) {
          const data = await response.json();
          prompts.value = data.prompts || [];
          defaults.value = data.defaults || {};
          console.log(`Loaded ${prompts.value.length} system prompts from backend.`);
        } else {
          console.error('Failed to load system prompts:', response.statusText);
        }
      } catch (error) {
        console.error('Error loading system prompts:', error);
      }
    };

    // Computed property to group prompts by type
    const groupedPrompts = computed(() => {
      const grouped = {};
      prompts.value.forEach(prompt => {
        const type = prompt.type || 'custom';
        if (!grouped[type]) {
          grouped[type] = { type, prompts: [] };
        }
        grouped[type].prompts.push(prompt);
      });
      return Object.values(grouped).sort((a, b) => {
        if (a.type === 'default') return -1;
        if (b.type === 'default') return 1;
        return a.type.localeCompare(b.type);
      });
    });

    // Function to edit a system prompt
    const editPrompt = async (promptId) => {
      const prompt = prompts.value.find(p => p.id === promptId);
      if (!prompt) {
        console.warn(`Prompt ${promptId} not found for editing.`);
        return;
      }
      const newContent = prompt(`Edit prompt: ${prompt.name}`, prompt.content);
      if (newContent !== null) {
        try {
          const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/prompts/${promptId}`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ content: newContent })
          });
          if (response.ok) {
            const updatedPrompt = await response.json();
            const index = prompts.value.findIndex(p => p.id === promptId);
            if (index !== -1) {
              prompts.value[index] = updatedPrompt;
            }
            console.log(`Updated prompt ${prompt.name} successfully.`);
          } else {
            console.error('Failed to update prompt:', response.statusText);
          }
        } catch (error) {
          console.error('Error updating prompt:', error);
        }
      }
    };

    // Function to revert a system prompt to default
    const revertPrompt = async (promptId) => {
      const prompt = prompts.value.find(p => p.id === promptId);
      if (!prompt) {
        console.warn(`Prompt ${promptId} not found for reverting.`);
        return;
      }
      if (confirm(`Are you sure you want to revert ${prompt.name} to its default content?`)) {
        try {
          const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/prompts/${promptId}/revert`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            }
          });
          if (response.ok) {
            const updatedPrompt = await response.json();
            const index = prompts.value.findIndex(p => p.id === promptId);
            if (index !== -1) {
              prompts.value[index] = updatedPrompt;
            }
            console.log(`Reverted prompt ${prompt.name} to default successfully.`);
          } else {
            console.error('Failed to revert prompt:', response.statusText);
          }
        } catch (error) {
          console.error('Error reverting prompt:', error);
        }
      }
    };

    // Watch for changes in settings and save them to local storage
    watch(settings, () => {
      saveSettings();
      if (settings.value.backend) {
        saveBackendSettings();
      }
    }, { deep: true });

    const filteredMessages = computed(() => {
      return messages.value.filter(message => {
        if (message.sender === 'user') return true;
        if (message.type === 'response') return true; // Always show main responses
        if (message.type === 'thought' && settings.value.message_display.show_thoughts) return true;
        if (message.type === 'json' && settings.value.message_display.show_json) return true;
        if (message.type === 'utility' && settings.value.message_display.show_utility) return true;
        if (message.type === 'planning' && settings.value.message_display.show_planning) return true;
        if (message.type === 'debug' && settings.value.message_display.show_debug) return true;
        if (message.type === 'tool_output') return true; // Always show tool output
        return false;
      });
    });

    const formatMessage = (text, type) => {
      // Custom formatting for different message types to clearly distinguish them
      if (type === 'thought') {
        // Format thoughts as internal monologue about understanding user intent
        let cleanedThought = text.replace(/\\n/g, ' ').replace(/\\"/g, '"').replace(/\\\\/g, '');
        try {
          const jsonObj = JSON.parse(cleanedThought);
          if (jsonObj.thoughts && jsonObj.thoughts.length > 0) {
            cleanedThought = jsonObj.thoughts.join(' ');
          }
        } catch (e) {
          cleanedThought = cleanedThought.replace(/\{.*?\}/g, '');
        }
        return `<div class="thought-message"><strong>Thinking:</strong> <i>${cleanedThought}</i></div>`;
      } else if (type === 'planning') {
        // Format planning messages to show the approach to solving the task
        let cleanedPlan = text.replace(/\\n/g, ' ').replace(/\\"/g, '"').replace(/\\\\/g, '');
        try {
          const jsonStart = cleanedPlan.indexOf('{');
          const jsonEnd = cleanedPlan.lastIndexOf('}');
          if (jsonStart !== -1 && jsonEnd !== -1) {
            const jsonStr = cleanedPlan.slice(jsonStart, jsonEnd + 1);
            const jsonObj = JSON.parse(jsonStr);
            let humanizedText = cleanedPlan.slice(0, jsonStart).trim();
            if (!humanizedText) humanizedText = "Planning how to approach this:";
            return `<div class="planning-message"><strong>Planning:</strong> <b>${humanizedText}</b></div>`;
          }
        } catch (e) {
          cleanedPlan = cleanedPlan.replace(/\{.*?\}/g, '').replace(/\[.*?\]/g, '').replace(/"/g, '').trim();
          return `<div class="planning-message"><strong>Planning:</strong> <b>${cleanedPlan}</b></div>`;
        }
        return `<div class="planning-message"><strong>Planning:</strong> <b>${cleanedPlan}</b></div>`;
      } else if (type === 'json') {
        // Display full JSON content when show_json toggle is on
        if (settings.value.message_display.show_json) {
          try {
            const jsonObj = JSON.parse(text);
            const formattedJson = JSON.stringify(jsonObj, null, 2);
            return `<div class="json-message"><strong>JSON Output:</strong> <pre>${formattedJson}</pre></div>`;
          } catch (e) {
            // If parsing fails, show raw text
            return `<div class="json-message"><strong>JSON Output (Parse Error):</strong> <pre>${text}</pre></div>`;
          }
        } else {
          return ''; // Hide if toggle is off
        }
      } else if (type === 'debug') {
        // Display full debug content when show_debug toggle is on
        if (settings.value.message_display.show_debug) {
          try {
            const jsonObj = JSON.parse(text);
            const formattedJson = JSON.stringify(jsonObj, null, 2);
            return `<div class="debug-message"><strong>Debug:</strong> <pre>${formattedJson}</pre></div>`;
          } catch (e) {
            return `<div class="debug-message"><strong>Debug:</strong> ${text}</div>`;
          }
        } else {
          return ''; // Hide if toggle is off
        }
      } else if (type === 'utility') {
        return `<div class="utility-message"><strong>Utility:</strong> <span style="color: #6c757d;">${text.replace(/\{.*?\}/g, '').replace(/\[.*?\]/g, '').replace(/"/g, '').trim()}</span></div>`;
      } else if (type === 'tool_output') {
        // Format tool output messages
        return `<div class="tool-output-message"><strong>Tool Output:</strong> <pre>${text}</pre></div>`;
      } else if (type === 'response') {
        // For response type, display the text directly
        return `<div class="response-message"><strong>Response:</strong> ${text}</div>`;
      }
      return text;
    };

    const sendMessage = async () => {
      if (inputMessage.value && inputMessage.value.trim()) {
        const messageText = inputMessage.value;
        // Clear input immediately to prevent multiple sends
        inputMessage.value = '';
        
        // Check if there is no active chat, create a new one if needed
        let chatId = window.location.hash.split('chatId=')[1];
        if (!chatId || !currentChatId.value) {
          await newChat();
          chatId = window.location.hash.split('chatId=')[1];
        }
        
        // Add user message
        messages.value.push({
          sender: 'user',
          text: messageText,
          timestamp: new Date().toLocaleTimeString(),
          type: 'user'
        });

        try {
          const requestBody = JSON.stringify({ message: messageText });
          if (settings.value.message_display.show_json) {
            messages.value.push({
              sender: 'bot',
              text: `Request to backend: ${requestBody}`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'json'
            });
          }

          // Always use the backend API endpoint for goal requests
          let apiEndpoint = settings.value.backend.api_endpoint;
          let goalEndpoint = '/api/chat';
          console.log('Using API endpoint for goal request:', apiEndpoint, 'with endpoint:', goalEndpoint);
          
          const response = await fetch(`${apiEndpoint}${goalEndpoint}`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: requestBody
          });
          if (response.ok) {
            const contentType = response.headers.get('content-type');
            if (settings.value.message_display.show_utility) {
              messages.value.push({
                sender: 'debug',
                text: `Response content type: ${contentType}`,
                timestamp: new Date().toLocaleTimeString(),
                type: 'utility'
              });
            }
            if (contentType && contentType.includes('text/event-stream')) {
              if (settings.value.message_display.show_utility) {
                messages.value.push({
                  sender: 'debug',
                  text: `Detected streaming response. Initiating streaming handler.`,
                  timestamp: new Date().toLocaleTimeString(),
                  type: 'utility'
                });
              }
              // Handle streaming response using ReadableStream directly from the initial response
              handleStreamingResponseFromResponse(response);
            } else {
              if (settings.value.message_display.show_utility) {
                messages.value.push({
                  sender: 'bot',
                  text: `Non-streaming response detected. Waiting for JSON data.`,
                  timestamp: new Date().toLocaleTimeString(),
                  type: 'utility'
                });
              }
              const botResponse = await response.json();
              console.log('Raw bot response:', botResponse);
              let responseText = botResponse.text || JSON.stringify(botResponse);
              let responseType = botResponse.type || 'response';
              
              // Handle OpenAI-compatible response format for non-streaming
              if (botResponse.object === 'chat.completion' && botResponse.choices && botResponse.choices.length > 0) {
                const choice = botResponse.choices[0];
                if (choice.message && choice.message.content) {
                  responseText = choice.message.content;
                  responseType = 'response';
                }
              }
              
              if (settings.value.message_display.show_json) {
                messages.value.push({
                  sender: 'bot',
                  text: `Response from backend: ${JSON.stringify(botResponse, null, 2)}`,
                  timestamp: new Date().toLocaleTimeString(),
                  type: 'json'
                });
              }

              // Extract detailed LLM request and response if available
              if (botResponse.llm_request && settings.value.message_display.show_utility) {
                messages.value.push({
                  sender: 'bot',
                  text: `LLM Request: ${JSON.stringify(botResponse.llm_request, null, 2)}`,
                  timestamp: new Date().toLocaleTimeString(),
                  type: 'utility'
                });
              }
              if (botResponse.llm_response && settings.value.message_display.show_utility) {
                messages.value.push({
                  sender: 'bot',
                  text: `LLM Response: ${JSON.stringify(botResponse.llm_response, null, 2)}`,
                  timestamp: new Date().toLocaleTimeString(),
                  type: 'utility'
                });
              }

              messages.value.push({
                sender: 'bot',
                text: responseText,
                timestamp: new Date().toLocaleTimeString(),
                type: responseType
              });
            }
          } else {
            console.error('Failed to get bot response:', response.statusText);
            if (settings.value.message_display.show_utility) {
              messages.value.push({
                sender: 'bot',
                text: `Error from backend: Status ${response.status} - ${response.statusText}`,
                timestamp: new Date().toLocaleTimeString(),
                type: 'utility'
              });
            }
            messages.value.push({
              sender: 'bot',
              text: `Error: Unable to connect to the backend. Please ensure the server is running.`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'response'
            });
          }
        } catch (error) {
          console.error('Error sending message:', error);
          if (settings.value.message_display.show_utility) {
            messages.value.push({
              sender: 'bot',
              text: `Error sending request to backend: ${error.message}`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'utility'
            });
          }
          messages.value.push({
            sender: 'bot',
            text: `Error: Unable to connect to the backend. Please ensure the server is running.`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'response'
          });
        }

        // Save messages after each update
        saveMessagesToStorage();

        // Scroll to the latest message if autoscroll is enabled
        nextTick(() => {
          if (chatMessages.value && settings.value.chat.auto_scroll) {
            chatMessages.value.scrollTop = chatMessages.value.scrollHeight;
          }
        });
      }
    };

    const handleStreamingResponseFromResponse = (response) => {
      if (eventSource) {
        eventSource.close();
      }
      let fullResponseText = '';
      let fullThoughtText = '';
      let fullJsonText = '';
      let fullUtilityText = '';
      let fullPlanningText = '';
      let currentToolCall = null;
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      
      function readStream() {
        reader.read().then(({ done, value }) => {
          if (done) {
            if (settings.value.message_display.show_utility) {
              messages.value.push({
                sender: 'bot',
                text: 'Streaming response completed.',
                timestamp: new Date().toLocaleTimeString(),
                type: 'utility'
              });
            }
            const lastBotMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'response' && !msg.final);
            if (lastBotMessageIndex >= 0) {
              messages.value[lastBotMessageIndex].final = true;
            }
            const lastThoughtMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'thought' && !msg.final);
            if (lastThoughtMessageIndex >= 0) {
              messages.value[lastThoughtMessageIndex].final = true;
            }
            const lastJsonMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'json' && !msg.final);
            if (lastJsonMessageIndex >= 0) {
              messages.value[lastJsonMessageIndex].final = true;
            }
            const lastUtilityMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'utility' && !msg.final);
            if (lastUtilityMessageIndex >= 0) {
              messages.value[lastUtilityMessageIndex].final = true;
            }
            const lastPlanningMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'planning' && !msg.final);
            if (lastPlanningMessageIndex >= 0) {
              messages.value[lastPlanningMessageIndex].final = true;
            }
            saveMessagesToStorage();
            return;
          }
          
          const chunk = decoder.decode(value, { stream: true });
          if (settings.value.message_display.show_debug) {
            messages.value.push({
              sender: 'debug',
              text: `Raw chunk received: ${chunk}`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'debug'
            });
          }
          
          try { // Outer try block for chunk parsing
            const dataMatches = chunk.split('\n').filter(line => line.startsWith('data: '));
            if (dataMatches.length > 0) {
              for (const dataLine of dataMatches) {
                const dataStr = dataLine.replace('data: ', '').trim();
                if (!dataStr) continue;
                
                try { // Inner try block for JSON parsing
                  const data = JSON.parse(dataStr);

                  if (settings.value.message_display.show_json) {
                    messages.value.push({
                      sender: 'bot',
                      text: JSON.stringify(data, null, 2),
                      timestamp: new Date().toLocaleTimeString(),
                      type: 'json',
                      final: false
                    });
                  }
                  
                  if (data.object === 'chat.completion.chunk' && data.choices && data.choices.length > 0) {
                    const choice = data.choices[0];
                    if (choice.delta) {
                      if (choice.delta.content) {
                        fullResponseText += choice.delta.content;
                        const lastBotMessageIndex = messages.value.findLastIndex(msg => msg.sender === 'bot' && msg.type === 'response' && !msg.final);
                        if (lastBotMessageIndex >= 0) {
                          messages.value[lastBotMessageIndex].text = fullResponseText;
                        } else {
                          messages.value.push({
                            sender: 'bot',
                            text: fullResponseText,
                            timestamp: new Date().toLocaleTimeString(),
                            type: 'response',
                            final: false
                          });
                        }
                        nextTick(() => {
                          if (chatMessages.value && settings.value.chat.auto_scroll) {
                            chatMessages.value.scrollTop = chatMessages.value.scrollHeight;
                          }
                        });
                      }
                      if (choice.delta.tool_calls) {
                          const toolCallDelta = choice.delta.tool_calls[0];
                          if (toolCallDelta.function) {
                              if (toolCallDelta.function.name) {
                                  if (!currentToolCall || currentToolCall.id !== toolCallDelta.id) {
                                      currentToolCall = {
                                          id: toolCallDelta.id,
                                          name: toolCallDelta.function.name,
                                          arguments: ''
                                      };
                                  }
                              }
                              if (toolCallDelta.function.arguments) {
                                  if (currentToolCall) {
                                      currentToolCall.arguments += toolCallDelta.function.arguments;
                                  }
                              }
                          }
                      }
                    }
                    if (choice.finish_reason) {
                      if (choice.finish_reason === 'tool_calls' && data.choices[0].message && data.choices[0].message.tool_calls) {
                        if (settings.value.message_display.show_utility) {
                          messages.value.push({
                            sender: 'bot',
                            text: `Tool call requested: ${JSON.stringify(data.choices[0].message.tool_calls, null, 2)}`,
                            timestamp: new Date().toLocaleTimeString(),
                            type: 'utility'
                          });
                        }
                        reader.cancel();
                        
                        const toolCall = currentToolCall;
                        if (toolCall && (toolCall.name === 'fetch_wikipedia_content' || toolCall.name === 'get_wikipedia_content')) {
                          try {
                            const args = JSON.parse(toolCall.arguments || '{}');
                            const searchQuery = args.search_query || 'unknown query';
                            messages.value.push({
                              sender: 'bot',
                              text: `Fetching Wikipedia content for "${searchQuery}"...`,
                              timestamp: new Date().toLocaleTimeString(),
                              type: 'utility'
                            });
                            messages.value.push({
                              sender: 'bot',
                              text: `Wikipedia content for "${searchQuery}": [Simulated response] This is a placeholder for the actual Wikipedia content that would be fetched.`,
                              timestamp: new Date().toLocaleTimeString(),
                              type: 'response',
                              final: true
                            });
                            saveMessagesToStorage();
                          } catch (error) {
                            if (settings.value.message_display.show_utility) {
                              messages.value.push({
                                sender: 'bot',
                                text: `Error processing tool call arguments: ${error.message}`,
                                timestamp: new Date().toLocaleTimeString(),
                                type: 'utility'
                              });
                            }
                          }
                        }
                        const lastBotMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'response' && !msg.final);
                        if (lastBotMessageIndex >= 0) {
                          messages.value[lastBotMessageIndex].final = true;
                        }
                        saveMessagesToStorage();
                        currentToolCall = null;
                        return;
                      }
                      const lastBotMessageIndex = messages.value.findLastIndex(msg => msg.sender === 'bot' && msg.type === 'response' && !msg.final);
                      if (lastBotMessageIndex >= 0) {
                        messages.value[lastBotMessageIndex].final = true;
                      }
                      saveMessagesToStorage();
                      reader.cancel();
                      return;
                    }
                  } else if (data.text) {
                      if (data.type === 'thought') {
                        fullThoughtText += data.text;
                        const lastThoughtMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'thought' && !msg.final);
                        if (lastThoughtMessageIndex >= 0) {
                          messages.value[lastThoughtMessageIndex].text = data.full_text || fullThoughtText;
                        } else if (settings.value.message_display.show_thoughts) {
                          messages.value.push({
                            sender: 'bot',
                            text: data.full_text || fullThoughtText,
                            timestamp: new Date().toLocaleTimeString(),
                            type: 'thought',
                            final: false
                          });
                        }
                      } else if (data.type === 'json') {
                        fullJsonText += data.text;
                        const lastJsonMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'json' && !msg.final);
                        if (lastJsonMessageIndex >= 0) {
                          messages.value[lastJsonMessageIndex].text = data.full_text || fullJsonText;
                        } else if (settings.value.message_display.show_json) {
                          messages.value.push({
                            sender: 'bot',
                            text: data.full_text || fullJsonText,
                            timestamp: new Date().toLocaleTimeString(),
                            type: 'json',
                            final: false
                          });
                        }
                      } else if (data.type === 'utility') {
                        fullUtilityText += data.text;
                        const lastUtilityMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'utility' && !msg.final);
                        if (lastUtilityMessageIndex >= 0) {
                          messages.value[lastUtilityMessageIndex].text = data.full_text || fullUtilityText;
                        } else if (settings.value.message_display.show_utility) {
                          messages.value.push({
                            sender: 'bot',
                            text: data.full_text || fullUtilityText,
                            timestamp: new Date().toLocaleTimeString(),
                            type: 'utility',
                            final: false
                          });
                        }
                      } else if (data.type === 'planning') {
                        fullPlanningText += data.text;
                        const lastPlanningMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'planning' && !msg.final);
                        if (lastPlanningMessageIndex >= 0) {
                          messages.value[lastPlanningMessageIndex].text = data.full_text || fullPlanningText;
                        } else if (settings.value.message_display.show_planning) {
                          messages.value.push({
                            sender: 'bot',
                            text: data.full_text || fullPlanningText,
                            timestamp: new Date().toLocaleTimeString(),
                            type: 'planning',
                            final: false
                          });
                        }
                      } else {
                        const currentMessageText = data.full_text || (fullResponseText + data.text);
                        fullResponseText = currentMessageText;
                        const lastBotMessageIndex = messages.value.findLastIndex(msg => msg.sender === 'bot' && msg.type === 'response' && !msg.final);
                        if (lastBotMessageIndex >= 0) {
                          messages.value[lastBotMessageIndex].text = currentMessageText;
                        } else {
                          messages.value.push({
                            sender: 'bot',
                            text: currentMessageText,
                            timestamp: new Date().toLocaleTimeString(),
                            type: 'response',
                            final: false
                          });
                        }
                      }
                      nextTick(() => {
                        if (chatMessages.value && settings.value.chat.auto_scroll) {
                          chatMessages.value.scrollTop = chatMessages.value.scrollHeight;
                        }
                      });
                    }
                    if (data.done) {
                      const lastBotMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'response' && !msg.final);
                      if (lastBotMessageIndex >= 0) {
                        messages.value[lastBotMessageIndex].text = data.full_text || messages.value[lastBotMessageIndex].text;
                        messages.value[lastBotMessageIndex].final = true;
                      }
                      const lastThoughtMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'thought' && !msg.final);
                      if (lastThoughtMessageIndex >= 0) {
                        messages.value[lastThoughtMessageIndex].text = data.full_text || messages.value[lastThoughtMessageIndex].text;
                        messages.value[lastThoughtMessageIndex].final = true;
                      }
                      const lastJsonMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'json' && !msg.final);
                      if (lastJsonMessageIndex >= 0) {
                        messages.value[lastJsonMessageIndex].text = data.full_text || messages.value[lastJsonMessageIndex].text;
                        messages.value[lastJsonMessageIndex].final = true;
                      }
                      const lastUtilityMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'utility' && !msg.final);
                      if (lastUtilityMessageIndex >= 0) {
                        messages.value[lastUtilityMessageIndex].text = data.full_text || messages.value[lastUtilityMessageIndex].text;
                        messages.value[lastUtilityMessageIndex].final = true;
                      }
                      const lastPlanningMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'planning' && !msg.final);
                      if (lastPlanningMessageIndex >= 0) {
                        messages.value[lastPlanningMessageIndex].text = data.full_text || messages.value[lastPlanningMessageIndex].text;
                        messages.value[lastPlanningMessageIndex].final = true;
                      }
                      saveMessagesToStorage();
                      reader.cancel();
                      return;
                    }
                } catch (error) { // Catch for inner try block
                  console.error('Error parsing JSON data:', error, 'from data:', dataStr);
                  if (settings.value.message_display.show_debug) {
                    messages.value.push({
                      sender: 'debug',
                      text: `Error parsing JSON data: ${error.message} from data: ${dataStr}`,
                      timestamp: new Date().toLocaleTimeString(),
                      type: 'debug'
                    });
                  }
                }
              }
            } else { // Else for dataMatches.length > 0
              if (settings.value.message_display.show_debug) {
                messages.value.push({
                  sender: 'debug',
                  text: `No data match found in chunk: ${chunk}`,
                  timestamp: new Date().toLocaleTimeString(),
                  type: 'debug'
                });
              }
            }
          } catch (error) { // Catch for outer try block
            console.error('Error parsing streaming data:', error, 'from chunk:', chunk);
            if (settings.value.message_display.show_debug) {
              messages.value.push({
                sender: 'debug',
                text: `Error parsing streaming data: ${error.message} from chunk: ${chunk}`,
                timestamp: new Date().toLocaleTimeString(),
                type: 'debug'
              });
            }
            messages.value.push({
              sender: 'bot',
              text: `Error: Streaming connection failed. Please try again.`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'response',
              final: true
            });
            saveMessagesToStorage();
          }
          readStream(); // Recursive call to continue reading the stream
        }).catch(error => { // Catch for the promise returned by reader.read().then()
          console.error('Error reading stream:', error);
          if (settings.value.message_display.show_debug) {
            messages.value.push({
              sender: 'debug',
              text: `Error reading stream: ${error.message}`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'debug'
            });
          }
          messages.value.push({
            sender: 'bot',
            text: `Error: Streaming connection failed. Please try again.`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'response',
            final: true
          });
          saveMessagesToStorage();
        });
      }
      readStream(); // Initial call to start reading the stream
    };

    const newChat = async () => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/chats/new`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        if (response.ok) {
          const newChatData = await response.json();
          messages.value = [];
          window.location.hash = `chatId=${newChatData.chatId}`;
          currentChatId.value = newChatData.chatId;
          console.log('New Chat created:', newChatData.chatId);
          // Don't add an automatic welcome message - let the chat start clean
          // Update chat list
          chatList.value.push({ chatId: newChatData.chatId, name: newChatData.name || '' });
        } else {
          console.error('Failed to create new chat:', response.statusText);
          messages.value.push({
            sender: 'bot',
            text: 'Failed to create new chat. Please check backend.',
            timestamp: new Date().toLocaleTimeString(),
            type: 'response'
          });
        }
      } catch (error) {
        console.error('Error creating new chat:', error);
        messages.value.push({
          sender: 'bot',
          text: 'Error creating new chat. Please check backend.',
          timestamp: new Date().toLocaleTimeString(),
          type: 'response'
        });
      }
    };

    const resetChat = async () => {
      try {
        const chatId = window.location.hash.split('chatId=')[1];
        if (!chatId) {
          messages.value.push({
            sender: 'bot',
            text: 'No active chat to reset.',
            timestamp: new Date().toLocaleTimeString(),
            type: 'response'
          });
          return;
        }
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/chats/${chatId}/reset`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        if (response.ok) {
      messages.value = [];
      messages.value.push({
        sender: 'bot',
        text: 'Chat reset successfully.',
        timestamp: new Date().toLocaleTimeString(),
        type: 'response'
      });
        } else {
          console.error('Failed to reset chat:', response.statusText);
          messages.value.push({
            sender: 'bot',
            text: 'Failed to reset chat. Please check backend.',
            timestamp: new Date().toLocaleTimeString(),
            type: 'response'
          });
        }
      } catch (error) {
        console.error('Error resetting chat:', error);
        messages.value.push({
          sender: 'bot',
          text: 'Error resetting chat. Please check backend.',
          timestamp: new Date().toLocaleTimeString(),
          type: 'response'
        });
      }
    };

    const deleteChat = async () => {
      const chatId = window.location.hash.split('chatId=')[1];
      if (!chatId) {
        messages.value.push({
          sender: 'bot',
          text: 'No active chat to delete.',
          timestamp: new Date().toLocaleTimeString(),
          type: 'response'
        });
        return;
      }
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/chats/${chatId}`, {
          method: 'DELETE',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        if (response.ok) {
          // Remove from local storage
          localStorage.removeItem(`chat_${chatId}_messages`);
          // Remove from chat list
          chatList.value = chatList.value.filter(chat => chat.chatId !== chatId);
          // If the deleted chat was active, clear messages
          if (!specificChatId || chatId === currentChatId.value) {
            messages.value = [];
            // Update current chat ID to null since no chat is active
            currentChatId.value = null;
            window.location.hash = '';
            messages.value.push({
              sender: 'bot',
              text: 'Chat deleted successfully. Click "New Chat" to start a new conversation.',
              timestamp: new Date().toLocaleTimeString(),
              type: 'response'
            });
          } else {
            console.log(`Chat ${chatId} deleted successfully.`);
          }
        } else {
          console.error('Failed to delete chat:', response.statusText);
          messages.value.push({
            sender: 'bot',
            text: 'Failed to delete chat. Please check backend.',
            timestamp: new Date().toLocaleTimeString(),
            type: 'response'
          });
        }
      } catch (error) {
        console.error('Error deleting chat:', error);
        messages.value.push({
          sender: 'bot',
          text: 'Error deleting chat. Please check backend.',
          timestamp: new Date().toLocaleTimeString(),
          type: 'response'
        });
      }
    };

    const loadChatMessages = async (chatId) => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/chats/${chatId}`);
        if (response.ok) {
          const data = await response.json();
          messages.value = data;
            console.log(`Loaded chat messages from backend for chat ${chatId}.`);
        } else {
          console.error('Failed to load chat messages:', response.statusText);
          // Fallback to local storage if backend fails
          const persistedMessages = localStorage.getItem(`chat_${chatId}_messages`);
          if (persistedMessages) {
            messages.value = JSON.parse(persistedMessages);
            console.log(`Loaded chat messages from local storage for chat ${chatId}.`);
          } else {
            messages.value = [];
            messages.value.push({
              sender: 'bot',
              text: 'No chat history found. How can I assist you?',
              timestamp: new Date().toLocaleTimeString(),
              type: 'response'
            });
          }
        }
      } catch (error) {
        console.error('Error loading chat messages:', error);
        // Fallback to local storage if backend fails
        const persistedMessages = localStorage.getItem(`chat_${chatId}_messages`);
        if (persistedMessages) {
          messages.value = JSON.parse(persistedMessages);
            console.log(`Loaded chat messages from local storage for chat ${chatId}.`);
        } else {
          messages.value = [];
        }
      }
    };

    const saveMessagesToStorage = async () => {
      const chatId = window.location.hash.split('chatId=')[1];
      if (!chatId) {
        console.warn('No chat ID found to save messages.');
        return;
      }
      // Save to local storage
      localStorage.setItem(`chat_${chatId}_messages`, JSON.stringify(messages.value));
      // Also save to backend
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/chats/${chatId}/save`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ messages: messages.value })
        });
        if (!response.ok) {
          console.error('Failed to save chat messages to backend:', response.statusText);
        } else {
          console.log('Chat messages saved to backend successfully.');
        }
      } catch (error) {
        console.error('Error saving chat messages to backend:', error);
      }
    };

    // Function to start the backend server
    const startBackendServer = async () => {
      backendStarting.value = true;
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/restart`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        if (response.ok) {
          const result = await response.json();
          console.log(`Backend server restart initiated: ${result.message}`);
        } else {
          console.error('Failed to restart backend server:', response.statusText);
        }
      } catch (error) {
        console.error('Error restarting backend server:', error);
      } finally {
        backendStarting.value = false;
      }
    };

    // Function to load chat list from backend or local storage
    const loadChatList = async () => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/chats`);
        if (response.ok) {
          const data = await response.json();
          chatList.value = data.chats || [];
          console.log(`Loaded chat list from backend with ${chatList.value.length} chats.`);
        } else {
          console.error('Failed to load chat list from backend:', response.statusText);
          // Fallback to local storage
          loadChatListFromLocalStorage();
        }
      } catch (error) {
        console.error('Error loading chat list from backend:', error);
        // Fallback to local storage
        loadChatListFromLocalStorage();
      }
    };

    // Function to build chat list from local storage
    const loadChatListFromLocalStorage = () => {
      const localChats = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key.startsWith('chat_') && key.endsWith('_messages')) {
          const chatId = key.split('_')[1];
          localChats.push({ chatId, name: '' });
        }
      }
      chatList.value = localChats;
      console.log(`Loaded chat list from local storage with ${localChats.length} chats.`);
    };

    // Function to switch to a different chat
    const switchChat = async (chatId) => {
      if (chatId === currentChatId.value) return;
      window.location.hash = `chatId=${chatId}`;
      currentChatId.value = chatId;
      messages.value = [];
      // Always try to load from backend first
      await loadChatMessages(chatId);
    };

    // Function to get a preview of the chat for display in the history list
    const getChatPreview = (chatId) => {
      const persistedMessages = localStorage.getItem(`chat_${chatId}_messages`);
      if (persistedMessages) {
        try {
          const chatMessages = JSON.parse(persistedMessages);
          if (chatMessages.length > 0) {
            const userMessage = chatMessages.find(msg => msg.sender === 'user');
            if (userMessage && userMessage.text) {
              return userMessage.text.substring(0, 20) + (userMessage.text.length > 20 ? '...' : '');
            }
          }
        } catch (e) {
          console.error('Error parsing chat messages for preview:', e);
        }
      }
      return '';
    };

    // Function to edit chat name
    const editChatName = (chatId) => {
      const newName = prompt('Enter a name for this chat:', chatList.value.find(chat => chat.chatId === chatId)?.name || '');
      if (newName) {
        const chatIndex = chatList.value.findIndex(chat => chat.chatId === chatId);
        if (chatIndex !== -1) {
          chatList.value[chatIndex].name = newName;
          // Save updated chat list to local storage
          localStorage.setItem('chat_list', JSON.stringify(chatList.value));
          console.log(`Updated name for chat ${chatId} to "${newName}".`);
        }
      }
    };

    // Function to refresh chat list
    const refreshChatList = async () => {
      await loadChatList();
      console.log(`Chat history list refreshed from backend.`);
    };

    // Function to handle specific chat deletion
    const deleteSpecificChat = async (specificChatId = null) => {
      const chatId = specificChatId || window.location.hash.split('chatId=')[1];
      if (!chatId) {
        messages.value.push({
          sender: 'bot',
          text: 'No active chat to delete.',
          timestamp: new Date().toLocaleTimeString(),
          type: 'response'
        });
        return;
      }
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/backend/api/chats/${chatId}`, {
          method: 'DELETE',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        if (response.ok) {
          // Remove from local storage
          localStorage.removeItem(`chat_${chatId}_messages`);
          // Remove from chat list
          chatList.value = chatList.value.filter(chat => chat.chatId !== chatId);
          // If the deleted chat was active, clear messages
          if (!specificChatId || chatId === currentChatId.value) {
            messages.value = [];
            // Update current chat ID to null since no chat is active
            currentChatId.value = null;
            window.location.hash = '';
            messages.value.push({
              sender: 'bot',
              text: 'Chat deleted successfully. Click "New Chat" to start a new conversation.',
              timestamp: new Date().toLocaleTimeString(),
              type: 'response'
            });
          } else {
            console.log(`Chat ${chatId} deleted successfully.`);
          }
        } else {
          console.error('Failed to delete chat:', response.statusText);
          messages.value.push({
            sender: 'bot',
            text: 'Failed to delete chat. Please check backend.',
            timestamp: new Date().toLocaleTimeString(),
            type: 'response'
          });
        }
      } catch (error) {
        console.error('Error deleting chat:', error);
        messages.value.push({
          sender: 'bot',
          text: 'Error deleting chat. Please check backend.',
          timestamp: new Date().toLocaleTimeString(),
          type: 'response'
        });
      }
    };

    // Initial load of chat messages based on URL hash
    onMounted(async () => {
      // Load chat list for sidebar
      await loadChatList();
      
      // Load custom chat list names if available
      const savedChatList = localStorage.getItem('chat_list');
      if (savedChatList) {
        try {
          const customList = JSON.parse(savedChatList);
          // Update names in the chat list based on custom names
          chatList.value.forEach(chat => {
            const customChat = customList.find(c => c.chatId === chat.chatId);
            if (customChat && customChat.name) {
              chat.name = customChat.name;
            }
          });
        } catch (e) {
          console.error('Error loading custom chat list names:', e);
        }
      }
      
      let chatId = window.location.hash.split('chatId=')[1];
      if (!chatId && chatList.value.length > 0) {
        // If no chat ID in URL but we have chats, select the first one
        chatId = chatList.value[0].chatId;
        window.location.hash = `chatId=${chatId}`;
      } else if (!chatId) {
        // If no chat ID in URL and no existing chats, create a new chat
        await newChat();
        chatId = window.location.hash.split('chatId=')[1];
      }
      
      if (chatId) {
        currentChatId.value = chatId;
        // Always load from backend first to ensure sync
        await loadChatMessages(chatId);
      }
      
      // Load settings from local storage if available
      const savedSettings = localStorage.getItem('chat_settings');
      if (savedSettings) {
        settings.value = JSON.parse(savedSettings);
      }
    });

    return {
      messages,
      filteredMessages,
      inputMessage,
      chatMessages,
      sendMessage,
      newChat,
      resetChat,
      deleteChat,
      formatMessage,
      saveMessagesToStorage,
      sidebarCollapsed,
      settings,
      backendStarting,
      startBackendServer,
      prompts,
      defaults,
      loadPrompts,
      editPrompt,
      revertPrompt,
      chatList,
      currentChatId,
      switchChat,
      getChatPreview,
      editChatName,
      refreshChatList,
      deleteSpecificChat,
      groupedPrompts,
      isAgentPaused,
      backendStatus,
      llmStatus,
      checkConnections
    };
  }
};
</script>

<style scoped>
.chat-interface {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
  padding: clamp(10px, 1.5vw, 15px);
  overflow: hidden; /* Prevent overall scrolling */
}

.chat-container {
  display: flex;
  flex: 1;
  min-height: 0; /* Ensure it shrinks properly */
}

.chat-sidebar {
  width: clamp(200px, 20vw, 250px);
  background-color: #f8f9fa;
  border-right: 1px solid #e9ecef;
  transition: width 0.3s ease;
  position: relative;
  display: flex;
  flex-direction: column;
}

.chat-sidebar.collapsed {
  width: 40px;
}

.toggle-sidebar {
  position: absolute;
  top: 10px;
  right: -20px;
  width: 20px;
  height: 30px;
  background-color: #6c757d;
  color: white;
  border: none;
  border-radius: 0 4px 4px 0;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 5;
}

.toggle-sidebar:hover {
  background-color: #5a6268;
}

.sidebar-content {
  padding: 10px;
  overflow-y: auto;
}

.sidebar-content h3 {
  margin: 0 0 10px 0;
  font-size: clamp(14px, 1.8vw, 16px);
  color: #007bff;
}

.settings-section {
  margin-bottom: 15px;
}

.settings-section h4 {
  margin: 0 0 8px 0;
  font-size: clamp(12px, 1.6vw, 14px);
  color: #343a40;
  border-bottom: 1px solid #e9ecef;
  padding-bottom: 5px;
}

.preference-toggle label {
  display: block;
  margin-bottom: 5px;
  font-size: clamp(11px, 1.4vw, 13px);
}

.preference-toggle input[type="checkbox"],
.preference-toggle input[type="radio"] {
  margin-right: 5px;
}

.preference-toggle input[type="text"],
.preference-toggle input[type="number"],
.preference-toggle select {
  margin-left: 5px;
  border: 1px solid #ced4da;
  border-radius: 3px;
  padding: 2px 5px;
  font-size: clamp(11px, 1.4vw, 13px);
}

.preference-toggle input[type="text"]:focus,
.preference-toggle input[type="number"]:focus,
.preference-toggle select:focus {
  outline: none;
  border-color: #007bff;
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.25);
}

.chat-interface h2 {
  margin: 0 0 clamp(10px, 1.5vw, 15px) 0;
  font-size: clamp(16px, 2vw, 20px);
  color: #007bff;
}

.chat-messages {
  flex: 1;
  overflow-y: auto; /* Only the messages area scrolls */
  padding: clamp(5px, 1vw, 10px);
  border: 1px solid #e9ecef;
  border-radius: 4px;
  margin-bottom: clamp(10px, 1.5vw, 15px);
  min-height: 0; /* Ensure it shrinks properly */
  margin-left: clamp(10px, 1.5vw, 15px);
}

.message {
  margin-bottom: clamp(5px, 1vw, 10px);
  padding: clamp(5px, 0.8vw, 8px) clamp(8px, 1.2vw, 12px);
  border-radius: 4px;
  max-width: 80%;
  font-size: clamp(12px, 1.5vw, 14px);
}

.message.user {
  background-color: #007bff;
  color: white;
  margin-left: auto;
}

.message.bot {
  background-color: #e9ecef;
  color: #333;
  margin-right: auto;
}

.message.thought {
  background-color: #f8f9fa;
  border-left: 4px solid #6c757d;
  font-style: italic;
}

.message.json, .message.debug {
  background-color: #fff3cd;
  border-left: 4px solid #ffc107;
  font-size: clamp(10px, 1.2vw, 12px);
}

.message.utility {
  background-color: #d4edda;
  border-left: 4px solid #28a745;
}

.message.planning {
  background-color: #cce5ff;
  border-left: 4px solid #007bff;
  font-weight: bold;
}

.message.tool-output {
  background-color: #e2f0cb; /* Light green */
  border-left: 4px solid #7cb342; /* Darker green */
  font-family: 'Courier New', Courier, monospace;
  font-size: clamp(10px, 1.2vw, 12px);
}

.thought-message, .planning-message, .response-message, .debug-message, .utility-message, .tool-output-message {
  display: flex;
  flex-direction: column;
}

.thought-message strong, .planning-message strong, .response-message strong, .debug-message strong, .utility-message strong {
  color: #495057;
  margin-bottom: 3px;
}

.message-content {
  word-wrap: break-word;
}

.message-content pre {
  background-color: rgba(0, 0, 0, 0.05);
  padding: 5px;
  border-radius: 3px;
  overflow-x: auto;
  font-size: clamp(10px, 1.2vw, 12px);
}

.message-timestamp {
  font-size: clamp(9px, 1vw, 11px);
  margin-top: 5px;
  opacity: 0.7;
}

.chat-control-buttons {
  display: flex;
  flex-direction: column;
  gap: clamp(3px, 0.5vw, 5px);
  margin-top: 10px;
}

.chat-input {
  display: flex;
  gap: clamp(5px, 1vw, 10px);
  position: sticky;
  bottom: 0; /* Keep input area at the bottom */
  background-color: white; /* Ensure background to avoid transparency */
  padding: clamp(5px, 1vw, 10px) 0;
  z-index: 10; /* Ensure it stays above other content if needed */
  margin-left: clamp(10px, 1.5vw, 15px);
  width: calc(100% - clamp(10px, 1.5vw, 15px));
}

.chat-input textarea {
  flex: 1;
  padding: clamp(5px, 1vw, 10px);
  border: 1px solid #ced4da;
  border-radius: 4px;
  resize: none;
  min-height: clamp(40px, 6vw, 60px);
  font-family: 'Arial', sans-serif;
  font-size: clamp(12px, 1.5vw, 14px);
  /* Removed text-size-adjust due to lack of support in Firefox and Safari */
}

.chat-input button {
  align-self: flex-end;
  background-color: #007bff;
  color: white;
  border: none;
  padding: clamp(5px, 1vw, 10px) clamp(10px, 2vw, 20px);
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s;
  font-size: clamp(12px, 1.5vw, 14px);
}


.chat-input button:hover {
  background-color: #0056b3;
}

@media (max-width: 768px) {
  .chat-input {
    flex-direction: row; /* Keep input and button on the same line */
    align-items: flex-end;
  }
  
  .chat-input textarea {
    min-height: 40px; /* Smaller height on mobile */
  }
}

.control-button {
  background-color: #007bff;
  color: white;
  border: none;
  padding: clamp(5px, 1vw, 10px) clamp(10px, 2vw, 20px);
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s;
  font-size: clamp(12px, 1.5vw, 14px);
}

.control-button.small {
  padding: clamp(3px, 0.5vw, 5px) clamp(5px, 1vw, 10px);
  font-size: clamp(10px, 1.2vw, 12px);
}

.control-button:hover {
  background-color: #0056b3;
}

.control-button:disabled {
  background-color: #6c757d;
  cursor: not-allowed;
}

.conversation-list {
  margin-bottom: 15px;
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid #e9ecef;
  border-radius: 4px;
  padding: 5px;
}

.conversation-item {
  padding: 8px;
  cursor: pointer;
  border-radius: 3px;
  margin-bottom: 2px;
  transition: background-color 0.2s;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.conversation-actions {
  display: none;
  gap: 5px;
}

.conversation-item:hover .conversation-actions {
  display: flex;
}

.action-icon {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 12px;
  padding: 2px 4px;
  border-radius: 3px;
  transition: background-color 0.2s;
}

.action-icon:hover {
  background-color: rgba(0, 0, 0, 0.1);
}

.action-icon.delete {
  color: #dc3545;
}

.action-icon.delete:hover {
  background-color: rgba(220, 53, 69, 0.2);
}

.conversation-item:hover {
  background-color: #e9ecef;
}

.conversation-item.active {
  background-color: #007bff;
  color: white;
}

.conversation-item span {
  font-size: clamp(11px, 1.4vw, 13px);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: block;
}
</style>
