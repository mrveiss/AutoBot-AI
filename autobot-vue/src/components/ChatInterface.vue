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
            <button @click="handleToggleAgent" class="control-button">{{ isAgentPaused ? 'Resume Agent' : 'Pause Agent' }}</button>
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
        show_debug: true // Default to on for debug messages to troubleshoot
      },
      chat: {
        auto_scroll: true,
        max_messages: 100
      },
      backend: {
        use_phi2: false,
        api_endpoint: '',
        ollama_endpoint: '',
        ollama_model: '',
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
      
      // Fetch backend settings to override with latest configuration
      await fetchBackendSettings();
      // Load system prompts on initialization
      await loadPrompts();
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
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/settings/backend`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ settings: { backend: settings.value.backend } })
        });
        if (!response.ok) {
          console.error('Failed to save backend settings:', response.statusText);
          messages.value.push({
            sender: 'debug',
            text: `Failed to save backend settings: ${response.statusText}`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'debug'
          });
        } else {
          messages.value.push({
            sender: 'debug',
            text: `Backend settings saved successfully.`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'debug'
          });
        }
      } catch (error) {
        console.error('Error saving backend settings:', error);
        messages.value.push({
          sender: 'debug',
          text: `Error saving backend settings: ${error.message}`,
          timestamp: new Date().toLocaleTimeString(),
          type: 'debug'
        });
      }
    };

    // Function to fetch backend settings
    const fetchBackendSettings = async () => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/settings/backend`);
        if (response.ok) {
          const backendSettings = await response.json();
          settings.value.backend = { ...settings.value.backend, ...backendSettings };
          messages.value.push({
            sender: 'debug',
            text: `Backend settings loaded successfully.`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'debug'
          });
        } else {
          console.error('Failed to load backend settings:', response.statusText);
          messages.value.push({
            sender: 'debug',
            text: `Failed to load backend settings: ${response.statusText}`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'debug'
          });
        }
      } catch (error) {
        console.error('Error loading backend settings:', error);
        messages.value.push({
          sender: 'debug',
          text: `Error loading backend settings: ${error.message}`,
          timestamp: new Date().toLocaleTimeString(),
          type: 'debug'
        });
      }
    };

    // Function to load system prompts from backend
    const loadPrompts = async () => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/prompts`);
        if (response.ok) {
          const data = await response.json();
          prompts.value = data.prompts || [];
          defaults.value = data.defaults || {};
          messages.value.push({
            sender: 'debug',
            text: `Loaded ${prompts.value.length} system prompts from backend.`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'debug'
          });
        } else {
          console.error('Failed to load system prompts:', response.statusText);
          messages.value.push({
            sender: 'debug',
            text: `Failed to load system prompts: ${response.statusText}`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'debug'
          });
        }
      } catch (error) {
        console.error('Error loading system prompts:', error);
        messages.value.push({
          sender: 'debug',
          text: `Error loading system prompts: ${error.message}`,
          timestamp: new Date().toLocaleTimeString(),
          type: 'debug'
        });
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
        messages.value.push({
          sender: 'debug',
          text: `Prompt ${promptId} not found for editing.`,
          timestamp: new Date().toLocaleTimeString(),
          type: 'debug'
        });
        return;
      }
      const newContent = prompt(`Edit prompt: ${prompt.name}`, prompt.content);
      if (newContent !== null) {
        try {
          const response = await fetch(`${settings.value.backend.api_endpoint}/api/prompts/${promptId}`, {
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
            messages.value.push({
              sender: 'debug',
              text: `Updated prompt ${prompt.name} successfully.`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'debug'
            });
          } else {
            console.error('Failed to update prompt:', response.statusText);
            messages.value.push({
              sender: 'debug',
              text: `Failed to update prompt ${prompt.name}: ${response.statusText}`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'debug'
            });
          }
        } catch (error) {
          console.error('Error updating prompt:', error);
          messages.value.push({
            sender: 'debug',
            text: `Error updating prompt ${prompt.name}: ${error.message}`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'debug'
          });
        }
      }
    };

    // Function to revert a system prompt to default
    const revertPrompt = async (promptId) => {
      const prompt = prompts.value.find(p => p.id === promptId);
      if (!prompt) {
        messages.value.push({
          sender: 'debug',
          text: `Prompt ${promptId} not found for reverting.`,
          timestamp: new Date().toLocaleTimeString(),
          type: 'debug'
        });
        return;
      }
      if (confirm(`Are you sure you want to revert ${prompt.name} to its default content?`)) {
        try {
          const response = await fetch(`${settings.value.backend.api_endpoint}/api/prompts/${promptId}/revert`, {
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
            messages.value.push({
              sender: 'debug',
              text: `Reverted prompt ${prompt.name} to default successfully.`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'debug'
            });
          } else {
            console.error('Failed to revert prompt:', response.statusText);
            messages.value.push({
              sender: 'debug',
              text: `Failed to revert prompt ${prompt.name}: ${response.statusText}`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'debug'
            });
          }
        } catch (error) {
          console.error('Error reverting prompt:', error);
          messages.value.push({
            sender: 'debug',
            text: `Error reverting prompt ${prompt.name}: ${error.message}`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'debug'
          });
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
      } else if (type === 'json' || type === 'debug') {
        // Display full JSON content when toggle is on
        if (settings.value.message_display.show_json || settings.value.message_display.show_debug) {
          try {
            // Attempt to parse and pretty print JSON
            const jsonObj = JSON.parse(text);
            const formattedJson = JSON.stringify(jsonObj, null, 2);
            return `<div class="debug-message"><strong>Debug/JSON:</strong> <pre>${formattedJson}</pre></div>`;
          } catch (e) {
            // If parsing fails, show raw text with some formatting for JSON-like structures
            const cleanedText = text.replace(/\\n/g, '').replace(/\\"/g, '"').replace(/\{.*?\}/g, match => `<pre>${match}</pre>`);
            return `<div class="debug-message"><strong>Debug/JSON:</strong> ${cleanedText}</div>`;
          }
        } else {
          // If toggle is off, show a summarized version
          try {
            const jsonObj = JSON.parse(text);
            let humanizedText = '';
            if (jsonObj.tool_name) {
              if (jsonObj.tool_name === 'respond_conversationally') {
                humanizedText += 'I will respond conversationally.<br>';
              } else {
                humanizedText += `I will use the tool: ${jsonObj.tool_name}.<br>`;
              }
            }
            if (jsonObj.tool_args && jsonObj.tool_args.response_text) {
              try {
                const responseJson = JSON.parse(jsonObj.tool_args.response_text);
                if (responseJson.sequel) {
                  humanizedText += `Response: ${responseJson.sequel}`;
                } else if (responseJson.sequence) {
                  humanizedText += `Response: ${responseJson.sequence[0][1]}`;
                } else {
                  humanizedText += `Response data: ${jsonObj.tool_args.response_text}`;
                }
              } catch (e) {
                humanizedText += `Response data: ${jsonObj.tool_args.response_text}`;
              }
            }
            return `<div class="debug-message"><strong>Debug/JSON:</strong> <pre>${humanizedText}</pre></div>`;
          } catch (e) {
            const cleanedText = text.replace(/\\n/g, '').replace(/\\"/g, '"').replace(/\{.*?\}/g, match => `<pre>${match}</pre>`);
            return `<div class="debug-message"><strong>Debug/JSON:</strong> ${cleanedText}</div>`;
          }
        }
      } else if (type === 'utility') {
        return `<div class="utility-message"><strong>Utility:</strong> <span style="color: #6c757d;">${text.replace(/\{.*?\}/g, '').replace(/\[.*?\]/g, '').replace(/"/g, '').trim()}</span></div>`;
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
          const requestBody = JSON.stringify({ message: messageText, chatId: chatId });
          if (settings.value.message_display.show_json) {
            messages.value.push({
              sender: 'debug',
              text: `Request to backend: ${requestBody}`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'json'
            });
          }

          // Ensure the correct endpoint based on the selected LLM provider and model
          let apiEndpoint = settings.value.backend.api_endpoint;
          let chatEndpoint = '/api/chat';
          let requestFormat = 'default';
          if (settings.value.backend.llm && settings.value.backend.llm.provider_type) {
            if (settings.value.backend.llm.provider_type === 'local') {
              const provider = settings.value.backend.llm.local.provider;
              if (provider && settings.value.backend.llm.local.providers[provider]) {
                apiEndpoint = settings.value.backend.llm.local.providers[provider].endpoint || apiEndpoint;
                if (provider === 'lmstudio') {
                  chatEndpoint = '/v1/chat/completions';
                  requestFormat = 'openai';
                }
              }
            } else if (settings.value.backend.llm.provider_type === 'cloud') {
              const provider = settings.value.backend.llm.cloud.provider;
              if (provider && settings.value.backend.llm.cloud.providers[provider]) {
                apiEndpoint = settings.value.backend.llm.cloud.providers[provider].endpoint || apiEndpoint;
                chatEndpoint = '/v1/chat/completions';
                requestFormat = 'openai';
              }
            }
          }
          console.log('Using API endpoint for chat request:', apiEndpoint, 'with endpoint:', chatEndpoint);
          
          // Format the request body based on the provider
          let formattedBody = requestBody;
          if (requestFormat === 'openai') {
            const originalData = JSON.parse(requestBody);
            const model = settings.value.backend.llm.provider_type === 'local' 
              ? settings.value.backend.llm.local.providers[settings.value.backend.llm.local.provider].selected_model
              : settings.value.backend.llm.cloud.providers[settings.value.backend.llm.cloud.provider].selected_model;
            formattedBody = JSON.stringify({
              model: model || 'default-model',
              messages: [
                { role: 'user', content: originalData.message }
              ],
              stream: settings.value.backend.streaming || false,
              tools: [
                {
                  type: "function",
                  function: {
                    name: "fetch_wikipedia_content",
                    description: "Search Wikipedia and fetch the introduction of the most relevant article. Use this if the user is asking for something that is likely on Wikipedia.",
                    parameters: {
                      type: "object",
                      properties: {
                        search_query: {
                          type: "string",
                          description: "Search query for finding the Wikipedia article"
                        }
                      },
                      required: ["search_query"]
                    }
                  }
                }
              ]
            });
          }
          
          const response = await fetch(`${apiEndpoint}${chatEndpoint}`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: formattedBody
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
              messages.value.push({
                sender: 'debug',
                text: `Non-streaming response detected. Waiting for JSON data.`,
                timestamp: new Date().toLocaleTimeString(),
                type: 'debug'
              });
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
                  sender: 'debug',
                  text: `Response from backend: ${JSON.stringify(botResponse, null, 2)}`,
                  timestamp: new Date().toLocaleTimeString(),
                  type: 'json'
                });
              }

              // Extract detailed LLM request and response if available
              if (botResponse.llm_request) {
                messages.value.push({
                  sender: 'debug',
                  text: `LLM Request: ${JSON.stringify(botResponse.llm_request, null, 2)}`,
                  timestamp: new Date().toLocaleTimeString(),
                  type: 'debug'
                });
              }
              if (botResponse.llm_response) {
                messages.value.push({
                  sender: 'debug',
                  text: `LLM Response: ${JSON.stringify(botResponse.llm_response, null, 2)}`,
                  timestamp: new Date().toLocaleTimeString(),
                  type: 'debug'
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
            messages.value.push({
              sender: 'debug',
              text: `Error from backend: Status ${response.status} - ${response.statusText}`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'debug'
            });
            messages.value.push({
              sender: 'bot',
              text: `Error: Unable to connect to the backend. Please ensure the server is running.`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'response'
            });
          }
        } catch (error) {
          console.error('Error sending message:', error);
          messages.value.push({
            sender: 'debug',
            text: `Error sending request to backend: ${error.message}`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'debug'
          });
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
      // Do not create a new EventSource directly; it's handled by the fetch response
      let fullResponseText = '';
      let fullThoughtText = '';
      let fullJsonText = '';
      let fullUtilityText = '';
      let fullPlanningText = '';
      let currentToolCall = null; // To accumulate tool call data across chunks
      
      console.log('Streaming response started:', response);
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      
      function readStream() {
        reader.read().then(({ done, value }) => {
          if (done) {
            messages.value.push({
              sender: 'debug',
              text: 'Streaming response completed.',
              timestamp: new Date().toLocaleTimeString(),
              type: 'debug'
            });
            console.log('Streaming completed.');
            // Mark the last bot message as final for each type
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
            // Save messages after streaming completes
            saveMessagesToStorage();
            return;
          }
          
          const chunk = decoder.decode(value, { stream: true });
          // Only add debug message for raw chunk if it's not already logged
          if (settings.value.message_display.show_debug && !messages.value.some(msg => msg.type === 'debug' && msg.text.includes('Raw chunk received') && msg.text.includes(chunk))) {
            messages.value.push({
              sender: 'debug',
              text: `Raw chunk received: ${chunk}`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'debug'
            });
          }
          console.log('Received chunk:', chunk);
          
          // Parse the chunk to extract JSON data
          try {
            // Handle multiple data events in a single chunk
            const dataMatches = chunk.split('\n').filter(line => line.startsWith('data: '));
            if (dataMatches.length > 0) {
              for (const dataLine of dataMatches) {
                const dataStr = dataLine.replace('data: ', '').trim();
                if (!dataStr) continue; // Skip empty data lines
                
                if (settings.value.message_display.show_debug && !messages.value.some(msg => msg.type === 'debug' && msg.text.includes('Attempting to parse JSON') && msg.text.includes(dataStr))) {
                  messages.value.push({
                    sender: 'debug',
                    text: `Attempting to parse JSON: ${dataStr}`,
                    timestamp: new Date().toLocaleTimeString(),
                    type: 'debug'
                  });
                }
                console.log('Attempting to parse JSON:', dataStr);
                
                try {
                  const data = JSON.parse(dataStr);
                  console.log('Parsed data:', data);
                  
                  // Check if this is an OpenAI-compatible response chunk
                  if (data.object === 'chat.completion.chunk' && data.choices && data.choices.length > 0) {
                    const choice = data.choices[0];
                    if (choice.delta) {
                      if (choice.delta.content) {
                        fullResponseText += choice.delta.content;
                        const lastBotMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'response' && !msg.final);
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
                        // Scroll to the latest message if autoscroll is enabled
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
                                  // Initialize currentToolCall if it's a new tool call
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
                        console.log('Tool call requested:', data.choices[0].message.tool_calls);
                        messages.value.push({
                          sender: 'debug',
                          text: `Tool call requested: ${JSON.stringify(data.choices[0].message.tool_calls, null, 2)}`,
                          timestamp: new Date().toLocaleTimeString(),
                          type: 'debug'
                        });
                        // Stop streaming when a tool call is requested
                        reader.cancel();
                        
                        // Simulate tool execution for demonstration
                        const toolCall = currentToolCall; // Use the accumulated tool call
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
                            // Simulated response (since actual execution would require backend support)
                            messages.value.push({
                              sender: 'bot',
                              text: `Wikipedia content for "${searchQuery}": [Simulated response] This is a placeholder for the actual Wikipedia content that would be fetched.`,
                              timestamp: new Date().toLocaleTimeString(),
                              type: 'response',
                              final: true
                            });
                            saveMessagesToStorage();
                          } catch (error) {
                            messages.value.push({
                              sender: 'debug',
                              text: `Error processing tool call arguments: ${error.message}`,
                              timestamp: new Date().toLocaleTimeString(),
                              type: 'debug'
                            });
                          }
                        }
                        // Mark the last bot message as final if it exists
                        const lastBotMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'response' && !msg.final);
                        if (lastBotMessageIndex >= 0) {
                          messages.value[lastBotMessageIndex].final = true;
                        }
                        saveMessagesToStorage();
                        currentToolCall = null; // Reset for next tool call
                        return; // Stop further processing of this stream
                      }
                      console.log('Streaming done signal received from OpenAI API.');
                      // Mark the last bot message as final
                      const lastBotMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'response' && !msg.final);
                      if (lastBotMessageIndex >= 0) {
                        messages.value[lastBotMessageIndex].final = true;
                      }
                      // Save messages after streaming completes
                      saveMessagesToStorage();
                      reader.cancel(); // Stop reading further
                      return;
                    }
                  } else if (data.text) {
                    // Handle custom format if present
                    // Determine message type and update the appropriate text accumulator
                    if (data.type === 'thought') {
                      fullThoughtText += data.text;
                      const lastThoughtMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'thought' && !msg.final);
                      if (lastThoughtMessageIndex >= 0) {
                        messages.value[lastThoughtMessageIndex].text = fullThoughtText;
                      } else if (settings.value.message_display.show_thoughts) {
                        messages.value.push({
                          sender: 'bot',
                          text: fullThoughtText,
                          timestamp: new Date().toLocaleTimeString(),
                          type: 'thought',
                          final: false
                        });
                      }
                    } else if (data.type === 'json') {
                      fullJsonText += data.text;
                      const lastJsonMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'json' && !msg.final);
                      if (lastJsonMessageIndex >= 0) {
                        messages.value[lastJsonMessageIndex].text = fullJsonText;
                      } else if (settings.value.message_display.show_json) {
                        messages.value.push({
                          sender: 'bot',
                          text: fullJsonText,
                          timestamp: new Date().toLocaleTimeString(),
                          type: 'json',
                          final: false
                        });
                      }
                    } else if (data.type === 'utility') {
                      fullUtilityText += data.text;
                      const lastUtilityMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'utility' && !msg.final);
                      if (lastUtilityMessageIndex >= 0) {
                        messages.value[lastUtilityMessageIndex].text = fullUtilityText;
                      } else if (settings.value.message_display.show_utility) {
                        messages.value.push({
                          sender: 'bot',
                          text: fullUtilityText,
                          timestamp: new Date().toLocaleTimeString(),
                          type: 'utility',
                          final: false
                        });
                      }
                    } else if (data.type === 'planning') {
                      fullPlanningText += data.text;
                      const lastPlanningMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'planning' && !msg.final);
                      if (lastPlanningMessageIndex >= 0) {
                        messages.value[lastPlanningMessageIndex].text = fullPlanningText;
                      } else if (settings.value.message_display.show_planning) {
                        messages.value.push({
                          sender: 'bot',
                          text: fullPlanningText,
                          timestamp: new Date().toLocaleTimeString(),
                          type: 'planning',
                          final: false
                        });
                      }
                    } else {
                      fullResponseText += data.text;
                      const lastBotMessageIndex = messages.value.findIndex(msg => msg.sender === 'bot' && msg.type === 'response' && !msg.final);
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
                    }
                    // Scroll to the latest message if autoscroll is enabled
                    nextTick(() => {
                      if (chatMessages.value && settings.value.chat.auto_scroll) {
                        chatMessages.value.scrollTop = chatMessages.value.scrollHeight;
                      }
                    });
                  }
                  if (data.done) {
                    console.log('Streaming done signal received.');
                    // Mark the last bot message as final for each type
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
                    // Save messages after streaming completes
                    saveMessagesToStorage();
                    reader.cancel(); // Stop reading further
                    return;
                  }
                } catch (error) {
                  console.error('Error parsing JSON data:', error, 'from data:', dataStr);
                  messages.value.push({
                    sender: 'debug',
                    text: `Error parsing JSON data: ${error.message} from data: ${dataStr}`,
                    timestamp: new Date().toLocaleTimeString(),
                    type: 'debug'
                  });
                }
              }
            } else {
              messages.value.push({
                sender: 'debug',
                text: `No data match found in chunk: ${chunk}`,
                timestamp: new Date().toLocaleTimeString(),
                type: 'debug'
              });
              console.log('No data match found in chunk:', chunk);
            }
          } catch (error) {
            console.error('Error parsing streaming data:', error, 'from chunk:', chunk);
            messages.value.push({
              sender: 'debug',
              text: `Error parsing streaming data: ${error.message} from chunk: ${chunk}`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'debug'
            });
          }
          readStream(); // Continue reading the next chunk
        }).catch(error => {
          console.error('Error reading stream:', error);
          messages.value.push({
            sender: 'debug',
            text: `Error reading stream: ${error.message}`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'debug'
          });
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
      readStream();
    };

    const newChat = async () => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/chats/new`, {
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
          messages.value.push({
            sender: 'bot',
            text: 'New chat created successfully. How can I assist you?',
            timestamp: new Date().toLocaleTimeString(),
            type: 'response'
          });
          // Save the initial message to storage
          localStorage.setItem(`chat_${newChatData.chatId}_messages`, JSON.stringify(messages.value));
          // Also save to backend
          await saveMessagesToStorage();
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
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/chats/${chatId}/reset`, {
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
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/chats/${chatId}`, {
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
          // Clear messages for the deleted chat
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
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/chats/${chatId}`);
        if (response.ok) {
          const data = await response.json();
          messages.value = data;
          if (settings.value.message_display.show_utility) {
            messages.value.push({
              sender: 'debug',
              text: `Loaded chat messages from backend for chat ${chatId}.`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'utility'
            });
          }
        } else {
          console.error('Failed to load chat messages:', response.statusText);
          if (settings.value.message_display.show_debug) {
            messages.value.push({
              sender: 'debug',
              text: `Failed to load chat messages from backend: ${response.statusText}`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'debug'
            });
          }
          // Fallback to local storage if backend fails
          const persistedMessages = localStorage.getItem(`chat_${chatId}_messages`);
          if (persistedMessages) {
            messages.value = JSON.parse(persistedMessages);
            if (settings.value.message_display.show_debug) {
              messages.value.push({
                sender: 'debug',
                text: `Loaded chat messages from local storage for chat ${chatId}.`,
                timestamp: new Date().toLocaleTimeString(),
                type: 'debug'
              });
            }
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
        if (settings.value.message_display.show_debug) {
          messages.value.push({
            sender: 'debug',
            text: `Error loading chat messages from backend: ${error.message}`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'debug'
          });
        }
        // Fallback to local storage if backend fails
        const persistedMessages = localStorage.getItem(`chat_${chatId}_messages`);
        if (persistedMessages) {
          messages.value = JSON.parse(persistedMessages);
          if (settings.value.message_display.show_debug) {
            if (settings.value.message_display.show_utility) {
              messages.value.push({
                sender: 'debug',
                text: `Loaded chat messages from local storage for chat ${chatId}.`,
                timestamp: new Date().toLocaleTimeString(),
                type: 'utility'
              });
            }
          }
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
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/chats/${chatId}/save`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ messages: messages.value })
        });
        if (!response.ok) {
          console.error('Failed to save chat messages to backend:', response.statusText);
          if (settings.value.message_display.show_debug) {
            messages.value.push({
              sender: 'debug',
              text: `Failed to save chat messages to backend: ${response.statusText}`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'debug'
            });
          }
        } else {
          if (settings.value.message_display.show_debug) {
            messages.value.push({
              sender: 'debug',
              text: `Chat messages saved to backend successfully.`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'debug'
            });
          }
        }
      } catch (error) {
        console.error('Error saving chat messages to backend:', error);
        if (settings.value.message_display.show_debug) {
          messages.value.push({
            sender: 'debug',
            text: `Error saving chat messages to backend: ${error.message}`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'debug'
          });
        }
      }
    };

    // Function to start the backend server
    const startBackendServer = async () => {
      backendStarting.value = true;
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/restart`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        if (response.ok) {
          const result = await response.json();
          messages.value.push({
            sender: 'debug',
            text: `Backend server restart initiated: ${result.message}`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'debug'
          });
        } else {
          console.error('Failed to restart backend server:', response.statusText);
          messages.value.push({
            sender: 'debug',
            text: `Failed to restart backend server: ${response.statusText}`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'debug'
          });
        }
      } catch (error) {
        console.error('Error restarting backend server:', error);
        messages.value.push({
          sender: 'debug',
          text: `Error restarting backend server: ${error.message}`,
          timestamp: new Date().toLocaleTimeString(),
          type: 'debug'
        });
      } finally {
        backendStarting.value = false;
      }
    };

    // Function to load chat list from backend or local storage
    const loadChatList = async () => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/chats`);
        if (response.ok) {
          const data = await response.json();
          chatList.value = data.chats || [];
          if (settings.value.message_display.show_debug) {
            messages.value.push({
              sender: 'debug',
              text: `Loaded chat list from backend with ${chatList.value.length} chats.`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'debug'
            });
          }
        } else {
          console.error('Failed to load chat list from backend:', response.statusText);
          if (settings.value.message_display.show_debug) {
            messages.value.push({
              sender: 'debug',
              text: `Failed to load chat list from backend: ${response.statusText}`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'debug'
            });
          }
          // Fallback to local storage
          loadChatListFromLocalStorage();
        }
      } catch (error) {
        console.error('Error loading chat list from backend:', error);
        if (settings.value.message_display.show_debug) {
          messages.value.push({
            sender: 'debug',
            text: `Error loading chat list from backend: ${error.message}`,
            timestamp: new Date().toLocaleTimeString(),
            type: 'debug'
          });
        }
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
      if (settings.value.message_display.show_debug) {
        messages.value.push({
          sender: 'debug',
          text: `Loaded chat list from local storage with ${chatList.value.length} chats.`,
          timestamp: new Date().toLocaleTimeString(),
          type: 'debug'
        });
      }
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
          if (settings.value.message_display.show_debug) {
            messages.value.push({
              sender: 'debug',
              text: `Updated name for chat ${chatId} to "${newName}".`,
              timestamp: new Date().toLocaleTimeString(),
              type: 'debug'
            });
          }
        }
      }
    };

    // Function to refresh chat list
    const refreshChatList = async () => {
      await loadChatList();
      if (settings.value.message_display.show_debug) {
        messages.value.push({
          sender: 'debug',
          text: `Chat history list refreshed from backend.`,
          timestamp: new Date().toLocaleTimeString(),
          type: 'debug'
        });
      }
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
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/chats/${chatId}`, {
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
            if (settings.value.message_display.show_debug) {
              messages.value.push({
                sender: 'debug',
                text: `Chat ${chatId} deleted successfully.`,
                timestamp: new Date().toLocaleTimeString(),
                type: 'debug'
              });
            }
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
      isAgentPaused
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

.thought-message, .planning-message, .response-message, .debug-message, .utility-message {
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
