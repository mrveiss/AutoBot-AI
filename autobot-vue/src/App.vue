<script setup lang="ts">
import { ref } from 'vue'

const isDarkMode = ref(localStorage.getItem('darkMode') !== 'false')
const messages = ref<{ sender: string, text: string }[]>([])
const messageInput = ref<string>('')
const isPreferencesExpanded = ref(true)
const isAutoscrollEnabled = ref(true)
const ws = ref<WebSocket | null>(null)
const isConnected = ref(false)

function toggleDarkMode(value: boolean) {
  localStorage.setItem('darkMode', value.toString())
  document.documentElement.classList.toggle('dark-mode', value)
  if (!value) {
    document.documentElement.classList.remove('dark-mode')
  }
}

function handleButtonClick(action: string) {
  console.log(`${action} button clicked`);
  if (action === 'Send Message') {
    sendMessage();
  } else if (action === 'Reset Chat') {
    resetChat();
  } else if (action === 'New Chat') {
    newChat();
  } else if (action === 'Settings') {
    fetchSettings();
  } else {
    alert(`${action} functionality is a placeholder. Full implementation will be added with backend integration.`);
  }
}

async function fetchSettings() {
  try {
    const response = await fetch('http://localhost:8001/api/settings');
    if (response.ok) {
      const settings = await response.json();
      messages.value.push({ sender: 'AutoBot', text: `Settings fetched: ${JSON.stringify(settings, null, 2)}` });
      if (isAutoscrollEnabled.value) {
        scrollToBottom();
      }
    } else {
      console.error('Failed to fetch settings:', response.status, response.statusText);
      messages.value.push({ sender: 'Error', text: `Failed to fetch settings: ${response.status} ${response.statusText}` });
      if (isAutoscrollEnabled.value) {
        scrollToBottom();
      }
    }
  } catch (error) {
    console.error('Error fetching settings:', error);
    messages.value.push({ sender: 'Error', text: `Error fetching settings: ${String(error)}. Please ensure the backend server is running on port 8001.` });
    if (isAutoscrollEnabled.value) {
      scrollToBottom();
    }
  }
}
function connectWebSocket() {
  if (ws.value) {
    ws.value.close();
  }
  const url = `ws://localhost:8001/ws`;
  ws.value = new WebSocket(url);
  ws.value.onopen = () => {
    isConnected.value = true;
    console.log('WebSocket connected');
    fetchChatHistory();
  };
  ws.value.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleWebSocketMessage(data);
    } catch (error) {
      console.error('Error parsing WebSocket message:', error);
    }
  };
  ws.value.onclose = () => {
    isConnected.value = false;
    console.log('WebSocket closed');
    setTimeout(connectWebSocket, 5000); // Attempt to reconnect after 5 seconds
  };
  ws.value.onerror = (error) => {
    console.error('WebSocket error:', error);
    isConnected.value = false;
  };
}
function handleWebSocketMessage(data: any) {
  const eventType = data.type;
  const payload = data.payload || {};
  let sender = 'AutoBot';
  let text = '';
  if (eventType === 'goal_received') {
    text = `Goal received: "${payload.goal || 'N/A'}"`;
  } else if (eventType === 'plan_ready') {
    text = `Here is the plan:\n${payload.llm_response || 'No plan text available.'}`;
  } else if (eventType === 'goal_completed') {
    text = `Goal completed. Result: ${JSON.stringify(payload.results || {}, null, 2)}`;
  } else if (eventType === 'command_execution_start') {
    text = `Executing command: ${payload.command || 'N/A'}`;
  } else if (eventType === 'command_execution_end') {
    const status = payload.status || 'N/A';
    const output = payload.output || '';
    const error = payload.error || '';
    text = `Command finished (${status}). Output: ${output || error}`;
  } else if (eventType === 'error') {
    text = `Error: ${payload.message || 'Unknown error'}`;
    sender = 'Error';
  } else if (eventType === 'progress') {
    text = `Progress: ${payload.message || 'N/A'}`;
  } else if (eventType === 'llm_response') {
    text = payload.response || 'N/A';
  } else if (eventType === 'user_message') {
    text = payload.message || 'N/A';
    sender = 'User';
  } else if (eventType === 'thought') {
    text = JSON.stringify(payload.thought || {}, null, 2);
    sender = 'Thought';
  } else if (eventType === 'tool_code') {
    text = payload.code || 'N/A';
    sender = 'Tool-Code';
  } else if (eventType === 'tool_output') {
    text = payload.output || 'N/A';
    sender = 'Tool-Output';
  } else if (eventType === 'settings_updated') {
    text = 'Settings updated successfully.';
  } else if (eventType === 'file_uploaded') {
    text = `File uploaded: ${payload.filename || 'N/A'}`;
  } else if (eventType === 'knowledge_base_update') {
    text = `Knowledge Base updated: ${payload.type || 'N/A'}`;
  } else if (eventType === 'llm_status') {
    const status = payload.status || 'N/A';
    const model = payload.model || 'N/A';
    const message = payload.message || '';
    text = `LLM (${model}) connection ${status}. ${message}`;
    if (status === 'disconnected') {
      sender = 'Error';
    }
  } else if (eventType === 'diagnostics_report') {
    text = `Diagnostics Report: ${JSON.stringify(payload, null, 2)}`;
  } else if (eventType === 'user_permission_request') {
    text = `User Permission Request: ${JSON.stringify(payload, null, 2)}`;
  }
  if (text) {
    messages.value.push({ sender, text });
    if (isAutoscrollEnabled.value) {
      scrollToBottom();
    }
  }
}
async function fetchChatHistory() {
  try {
    const response = await fetch('http://localhost:8001/api/chat/history');
    if (response.ok) {
      const data = await response.json();
      messages.value = data.history.map((msg: any) => ({
        sender: msg.sender || 'Unknown',
        text: msg.text || 'No content'
      }));
      if (isAutoscrollEnabled.value) {
        scrollToBottom();
      }
    } else {
      console.error('Failed to fetch chat history:', response.status);
    }
  } catch (error) {
    console.error('Error fetching chat history:', error);
  }
}
async function sendMessageToBackend(goal: string) {
  try {
    const response = await fetch('http://localhost:8001/api/goal', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        goal: goal,
        use_phi2: false,
        user_role: 'user'
      }),
    });
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();
    console.log('Goal submitted successfully:', data);
  } catch (error: unknown) {
    console.error('Error submitting goal:', error);
    messages.value.push({ sender: 'Error', text: `Failed to send message: ${String(error)}` });
    if (isAutoscrollEnabled.value) {
      scrollToBottom();
    }
  }
}

function sendMessage() {
  if (messageInput.value.trim()) {
    const userMessage = messageInput.value;
    messages.value.push({ sender: 'User', text: userMessage });
    messageInput.value = '';
    sendMessageToBackend(userMessage);
    if (isAutoscrollEnabled.value) {
      scrollToBottom();
    }
  }
}

function scrollToBottom() {
  const chatHistory = document.getElementById('chat-history');
  if (chatHistory) {
    chatHistory.scrollTop = chatHistory.scrollHeight;
  }
}

function resetChat() {
  messages.value = [];
}

function newChat() {
  messages.value = [];
  messages.value.push({ sender: 'AutoBot', text: 'Welcome to a new chat! How can I assist you?' });
}

if (isDarkMode.value) {
  document.documentElement.classList.add('dark-mode')
}
// Connect to WebSocket on component mount
connectWebSocket();
</script>

<template>
  <div class="container">
    <div id="sidebar-overlay" class="sidebar-overlay hidden"></div>
    <div class="icons-section" id="hide-button">
      <button id="toggle-sidebar" class="toggle-sidebar-button" aria-label="Toggle Sidebar" aria-expanded="false">
        <span aria-hidden="true">
          <svg id="sidebar-hamburger-svg" xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="CurrentColor">
            <path d="M3 13h18v-2H3v2zm0 4h18v-2H3v2zm0-8h18V7H3v2z"></path>
          </svg>
        </span>
      </button>
      <div id="logo-container">
        <a href="https://github.com/frdel/agent-zero" target="_blank" rel="noopener noreferrer">
          <img src="./assets/logo.svg" alt="a0" width="22" height="22" />
        </a>
      </div>
    </div>

    <div id="left-panel" class="panel">
      <div class="left-panel-top">
        <div class="config-section">
          <button class="config-button" @click="handleButtonClick('Reset Chat')">Reset Chat</button>
          <button class="config-button" @click="handleButtonClick('New Chat')">New Chat</button>
          <button class="config-button" @click="handleButtonClick('Load Chat')">Load Chat</button>
          <button class="config-button" @click="handleButtonClick('Save Chat')">Save Chat</button>
          <button class="config-button" @click="handleButtonClick('Restart')">Restart</button>
          <button class="config-button" @click="handleButtonClick('Settings')">Settings</button>
        </div>

        <div class="tabs-container">
          <div class="tabs">
            <div class="tab active" id="chats-tab">Chats</div>
            <div class="tab" id="tasks-tab">Tasks</div>
          </div>
        </div>

        <div class="config-section" id="chats-section">
          <div class="chats-list-container">
            <ul class="config-list">
              <li>
                <div class="chat-list-button">
                  <span class="chat-name">Chat #1</span>
                </div>
                <button class="edit-button">X</button>
              </li>
            </ul>
            <div class="empty-list-message">
              <p><i>No chats to list.</i></p>
            </div>
          </div>
        </div>

        <div class="config-section" id="tasks-section" style="display: none;">
          <div class="tasks-list-container">
            <ul class="config-list">
              <li>
                <div class="chat-list-button has-task-container">
                  <div class="task-container task-container-vertical">
                    <span class="task-name">Task #1 (Chat #1)</span>
                    <div class="task-info-line">
                      <span class="scheduler-status-badge scheduler-status-badge-small scheduler-status-idle">idle</span>
                      <button class="edit-button" title="View task details">View</button>
                      <button class="edit-button" title="Clear task chat">Clear</button>
                      <button class="edit-button" title="Delete task">X</button>
                    </div>
                  </div>
                </div>
              </li>
            </ul>
            <div class="empty-list-message">
              <p><i>No tasks to list.</i></p>
            </div>
          </div>
        </div>
      </div>

      <div class="left-panel-bottom">
        <div class="pref-section">
          <span>
            <h3 class="pref-header" @click="isPreferencesExpanded = !isPreferencesExpanded">
              Preferences
              <svg class="arrow-icon" :class="{ 'expanded': isPreferencesExpanded }" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                <path d="M8 4l8 8-8 8" />
              </svg>
            </h3>
            <ul class="config-list" id="pref-list" v-if="isPreferencesExpanded">
              <li>
                <span>Autoscroll</span>
                <label class="switch">
                  <input id="auto-scroll-switch" type="checkbox" v-model="isAutoscrollEnabled" />
                  <span class="slider"></span>
                </label>
              </li>
              <li>
                <span class="switch-label">Dark mode</span>
                <label class="switch">
                  <input type="checkbox" v-model="isDarkMode" @change="toggleDarkMode(isDarkMode)" />
                  <span class="slider"></span>
                </label>
              </li>
              <li>
                <span class="switch-label">Speech</span>
                <label class="switch">
                  <input type="checkbox" />
                  <span class="slider"></span>
                </label>
              </li>
              <li>
                <span>Show thoughts</span>
                <label class="switch">
                  <input type="checkbox" checked />
                  <span class="slider"></span>
                </label>
              </li>
              <li>
                <span>Show JSON</span>
                <label class="switch">
                  <input type="checkbox" />
                  <span class="slider"></span>
                </label>
              </li>
              <li>
                <span>Show utility messages</span>
                <label class="switch">
                  <input type="checkbox" />
                  <span class="slider"></span>
                </label>
              </li>
            </ul>
          </span>
        </div>
        <div class="version-info">
          <span id="a0version">Version 1.0</span>
        </div>
      </div>
    </div>

    <div id="right-panel" class="panel">
      <div id="time-date-container">
        <div id="time-date"></div>
        <div class="status-icon">
          <svg viewBox="0 0 30 30">
            <circle class="connected-circle" cx="15" cy="15" r="8" fill="#00c340" opacity="1" v-if="isConnected" />
            <circle class="disconnected-circle" cx="15" cy="15" r="12" fill="none" stroke="#e40138" stroke-width="3" opacity="1" v-if="!isConnected" />
          </svg>
        </div>
      </div>
      <div id="chat-history">
        <div v-for="(msg, index) in messages" :key="index" class="chat-message" :class="{ 'user-message': msg.sender === 'User', 'agent-message': msg.sender === 'AutoBot' }">
          <strong>{{ msg.sender }}:</strong> {{ msg.text }}
        </div>
      </div>
      <div id="toast" class="toast">
        <div class="toast__content">
          <div class="toast__title"></div>
          <div class="toast__separator"></div>
          <div class="toast__message"></div>
        </div>
        <button class="toast__copy" style="display: none;">Copy</button>
        <button class="toast__close" style="display: none;">Close</button>
      </div>
      <div id="progress-bar-box" style="display: none;">
        <h4 id="progress-bar-h">
          <span id="progress-bar-i">|></span><span id="progress-bar"></span>
        </h4>
        <h4 id="progress-bar-stop-speech" style="display: none;">
          <span id="stop-speech" style="cursor: pointer">Stop Speech</span>
        </h4>
      </div>
      <div id="input-section">
        <div class="preview-section" style="display: none;"></div>
        <div class="input-row">
          <div class="attachment-wrapper">
            <label for="file-input" class="attachment-icon">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                <path d="M16.5 6v11.5c0 2.21-1.79 4-4 4s-4-1.79-4-4V5c0-1.38 1.12-2.5 2.5-2.5s2.5 1.12 2.5 2.5v10.5c0 .55-.45 1-1 1s-1-.45-1-1V6H10v9.5c0 1.38 1.12 2.5 2.5 2.5s2.5-1.12 2.5-2.5V5c0-2.21-1.79-4-4-4S7 2.79 7 5v12.5c0 3.04 2.46 5.5 5.5 5.5s5.5-2.46 5.5-5.5V6h-1.5z" />
              </svg>
            </label>
            <input type="file" id="file-input" accept="*" multiple style="display: none" />
            <div class="tooltip" style="display: none;">
              Add attachments to the message
            </div>
          </div>
          <div id="chat-input-container" style="position: relative;">
            <textarea id="chat-input" placeholder="Type your message here..." rows="1" v-model="messageInput" @keyup.enter="sendMessage"></textarea>
            <button id="expand-button" aria-label="Expand input">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
                <path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/>
              </svg>
            </button>
          </div>
          <div id="chat-buttons-wrapper">
            <button class="chat-button" id="send-button" aria-label="Send message" @click="handleButtonClick('Send Message')">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
                <path d="M25 20 L75 50 L25 80" fill="none" stroke="currentColor" stroke-width="15"></path>
              </svg>
            </button>
            <button class="chat-button mic-inactive" id="microphone-button" aria-label="Start/Stop recording" @click="handleButtonClick('Microphone')">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 18" fill="currentColor">
                <path d="m8,12c1.66,0,3-1.34,3-3V3c0-1.66-1.34-3-3-3s-3,1.34-3,3v6c0,1.66,1.34,3,3,3Zm-1,1.9c-2.7-.4-4.8-2.6-5-5.4H0c.2,3.8,3.1,6.9,7,7.5v2h2v-2c3.9-.6,6.8-3.7,7-7.5h-2c-.2,2.8-2.3,5-5,5.4h-2Z" />
              </svg>
            </button>
          </div>
        </div>
        <div class="text-buttons-row">
          <button class="text-button" @click="handleButtonClick('Pause Agent')">
            <svg xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" width="14" height="14">
              <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"></path>
            </svg>
            <span>Pause Agent</span>
          </button>
          <button class="text-button" @click="handleButtonClick('Import Knowledge')">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5"></path>
            </svg>
            <p>Import knowledge</p>
          </button>
          <button class="text-button" id="work_dir_browser" @click="handleButtonClick('Files')">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 123.37 92.59">
              <path d="m5.72,11.5l-3.93,8.73h119.77s-3.96-8.73-3.96-8.73h-60.03c-1.59,0-2.88-1.29-2.88-2.88V1.75H13.72v6.87c0,1.59-1.29,2.88-2.88,2.88h-5.12Z" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="7"></path>
              <path d="m6.38,20.23H1.75l7.03,67.03c.11,1.07.55,2.02,1.2,2.69.55.55,1.28.89,2.11.89h97.1c.82,0,1.51-.33,2.05-.87.68-.68,1.13-1.67,1.28-2.79l9.1-66.94H6.38Z" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="8"></path>
            </svg>
            <p>Files</p>
          </button>
          <button class="text-button" id="history_inspect" @click="handleButtonClick('History')">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="5 10 85 85">
              <path fill="currentColor" d="m59.572,57.949c-.41,0-.826-.105-1.207-.325l-9.574-5.528c-.749-.432-1.21-1.231-1.21-2.095v-14.923c0-1.336,1.083-2.419,2.419-2.419s2.419,1.083,2.419,2.419v13.526l8.364,4.829c1.157.668,1.554,2.148.886,3.305-.448.776-1.261,1.21-2.097,1.21Zm30.427-7.947c0,10.684-4.161,20.728-11.716,28.283-6.593,6.59-15.325,10.69-24.59,11.544-1.223.113-2.448.169-3.669.169-7.492,0-14.878-2.102-21.22-6.068l-15.356,5.733c-.888.331-1.887.114-2.557-.556s-.887-1.669-.556-2.557l5.733-15.351c-4.613-7.377-6.704-16.165-5.899-24.891.854-9.266,4.954-17.998,11.544-24.588,7.555-7.555,17.6-11.716,28.285-11.716s20.73,4.161,28.285,11.716c7.555,7.555,11.716,17.599,11.716,28.283Zm-15.137-24.861c-13.71-13.71-36.018-13.71-49.728,0-11.846,11.846-13.682,30.526-4.365,44.417.434.647.53,1.464.257,2.194l-4.303,11.523,11.528-4.304c.274-.102.561-.153.846-.153.474,0,.944.139,1.348.41,13.888,9.315,32.568,7.479,44.417-4.365,13.707-13.708,13.706-36.014,0-49.723Zm-24.861-4.13c-15.989,0-28.996,13.006-28.996,28.992s13.008,28.992,28.996,28.992c1.336,0,2.419-1.083,2.419-2.419s-1.083-2.419-2.419-2.419c-13.32,0-24.157-10.835-24.157-24.153s10.837-24.153,24.157-24.153,24.153,10.835,24.153,24.153c0,1.336,1.083,2.419,2.419,2.419s2.419-1.083,2.419-2.419c0-15.986-13.006-28.992-28.992-28.992Zm25.041,33.531c-1.294.347-2.057,1.673-1.71,2.963.343,1.289,1.669,2.057,2.963,1.71,1.289-.343,2.053-1.669,1.71-2.963-.347-1.289-1.673-2.057-2.963-1.71Zm-2.03,6.328c-1.335,0-2.419,1.084-2.419,2.419s1.084,2.419,2.419,2.419,2.419-1.084,2.419-2.419-1.084-2.419-2.419-2.419Zm-3.598,5.587c-1.289-.347-2.615.416-2.963,1.71-.343,1.289.421,2.615,1.71,2.963,1.294.347,2.62-.421,2.963-1.71.347-1.294-.416-2.62-1.71-2.963Zm-4.919,4.462c-1.157-.667-2.638-.27-3.306.887-.667,1.157-.27,2.638.887,3.305,1.157.668,2.638.27,3.306-.887.667-1.157.27-2.638-.887-3.306Zm-9.327,3.04c-.946.946-.946,2.478,0,3.42.942.946,2.473.946,3.42,0,.946-.942.946-2.473,0-3.42-.946-.946-2.478-.946-3.42,0Z"></path>
            </svg>
            <p>History</p>
          </button>
          <button class="text-button" id="ctx_window" @click="handleButtonClick('Context')">
            <svg xmlns="http://www.w3.org/2000/svg" version="1.1" viewBox="17 15 70 70" fill="currentColor">
              <path d="m63 25c1.1016 0 2-0.89844 2-2s-0.89844-2-2-2h-26c-1.1016 0-2 0.89844-2 2s0.89844 2 2 2z"></path>
              <path d="m63 79c1.1016 0 2-0.89844 2-2s-0.89844-2-2-2h-26c-1.1016 0-2 0.89844-2 2s0.89844 2 2 2z"></path>
              <path d="m68 39h-36c-6.0703 0-11 4.9297-11 11s4.9297 11 11 11h36c6.0703 0 11-4.9297 11-11s-4.9297-11-11-11zm0 18h-36c-3.8594 0-7-3.1406-7-7s3.1406-7 7-7h36c3.8594 0 7 3.1406 7 7s-3.1406 7-7 7z"></path>
            </svg>
            <p>Context</p>
          </button>
          <button class="text-button" id="nudges_window" @click="handleButtonClick('Nudge')">
            <svg id="Layer_1" data-name="Layer 1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 49 58" fill="currentColor">
              <path d="m11.97,16.32c-.46,0-.91-.25-1.15-.68-.9-1.63-1.36-3.34-1.36-5.1C9.45,4.73,14.18,0,20,0s10.55,4.73,10.55,10.55c0,.87-.13,1.75-.41,2.76-.19.7-.9,1.13-1.62.93-.7-.19-1.12-.92-.93-1.62.21-.79.31-1.44.31-2.07,0-4.36-3.55-7.91-7.91-7.91s-7.91,3.55-7.91,7.91c0,1.3.35,2.59,1.03,3.82.36.64.13,1.44-.51,1.79-.21.11-.42.17-.64.17Z" stroke-width="0.5" stroke="currentColor" />
              <path d="m34.5,58h-6.18c-3.17,0-6.15-1.23-8.39-3.47L1.16,35.75c-1.54-1.54-1.54-4.05,0-5.59,2.4-2.4,6.27-2.68,8.99-.64l4.58,3.44V10.55c0-2.91,2.36-5.27,5.27-5.27s5.27,2.36,5.27,5.27v8.62c.78-.45,1.68-.71,2.64-.71,2.3,0,4.26,1.48,4.98,3.53.84-.56,1.85-.89,2.93-.89,2.3,0,4.26,1.48,4.98,3.53.84-.56,1.85-.89,2.93-.89,2.91,0,5.27,2.36,5.27,5.27v14.5c0,8-6.51,14.5-14.5,14.5ZM6.03,30.79c-1.1,0-2.19.42-3.01,1.23-.51.51-.51,1.35,0,1.86l18.77,18.78c1.74,1.74,4.06,2.7,6.53,2.7h6.18c6.54,0,11.86-5.32,11.86-11.86v-14.5c0-1.45-1.18-2.64-2.64-2.64s-2.64,1.18-2.64,2.64v1.32c0,.73-.59,1.32-1.32,1.32s-1.32-.59-1.32-1.32v-3.95c0-1.45-1.18-2.64-2.64-2.64s-2.64,1.18-2.64,2.64v3.95c0,.73-.59,1.32-1.32,1.32s-1.32-.59-1.32-1.32v-6.59c0-1.45-1.18-2.64-2.64-2.64s-2.64,1.18-2.64,2.64v6.59c0,.73-.59,1.32-1.32,1.32s-1.32-.59-1.32-1.32V10.55c0-1.45-1.18-2.64-2.64-2.64s-2.64,1.18-2.64,2.64v25.05c0,.5-.28.95-.73,1.18s-.98.18-1.38-.12l-6.69-5.02c-.75-.56-1.65-.84-2.54-.84Z" stroke-width="0.5" stroke="currentColor" />
            </svg>
            <p>Nudge</p>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.container {
  display: grid;
  grid-template-columns: 300px 1fr;
  height: 100vh;
  width: 100vw;
  margin: 0;
  padding: 0;
}

.hidden {
  display: none;
}

.icons-section {
  grid-column: 1;
  padding: 10px;
  display: flex;
  align-items: center;
  width: 100%;
  box-sizing: border-box;
}

.toggle-sidebar-button {
  background: none;
  border: none;
  cursor: pointer;
  margin-right: 10px;
}

#logo-container {
  display: flex;
  align-items: center;
}

.panel {
  height: 100vh;
  padding: 10px;
  box-sizing: border-box;
}

#left-panel {
  grid-column: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.left-panel-top {
  flex: 1;
  overflow-y: visible;
}

.left-panel-bottom {
  padding-top: 10px;
}

.config-section {
  margin-bottom: 10px;
}

.config-button {
  display: block;
  width: 100%;
  padding: 8px;
  margin-bottom: 5px;
  border: 1px solid #ccc;
  background-color: #f0f0f0;
  color: #333;
  cursor: pointer;
  text-align: left;
  transition: background-color 0.2s;
}

.config-button:hover {
  background-color: #e0e0e0;
}

.tabs-container {
  margin-bottom: 10px;
}

.tabs {
  display: flex;
  border-bottom: 1px solid #ccc;
}

.tab {
  padding: 8px 16px;
  cursor: pointer;
}

.chats-list-container, .tasks-list-container {
  max-height: none;
  overflow-y: visible;
}

.config-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.config-list li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 5px 0;
  border-bottom: 1px solid #ccc;
}

.chat-list-button {
  flex: 1;
  padding: 5px;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-name, .task-name {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
}

.edit-button {
  background: none;
  border: none;
  cursor: pointer;
}

.empty-list-message {
  text-align: center;
  padding: 10px;
}

.pref-section {
  margin-bottom: 10px;
}

.pref-header {
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 5px;
}

.arrow-icon {
  transition: transform 0.3s ease;
}

.arrow-icon.expanded {
  transform: rotate(90deg);
}

.version-info {
  text-align: center;
  font-size: 0.8em;
}

#right-panel {
  grid-column: 2;
  display: flex;
  flex-direction: column;
}

#time-date-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 5px 10px;
  border-bottom: 1px solid #ccc;
}

.status-icon {
  display: flex;
  align-items: center;
}

#chat-history {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
}

.chat-message {
  margin-bottom: 10px;
  padding: 8px;
  border-radius: 5px;
}

.user-message {
  background-color: #e3f2fd;
  margin-left: 20%;
  margin-right: 5px;
  text-align: right;
}

.agent-message {
  background-color: #f5f5f5;
  margin-right: 20%;
  margin-left: 5px;
}

#progress-bar-box {
  padding: 5px 10px;
  border-top: 1px solid #ccc;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

#progress-bar-h {
  margin: 0;
  font-size: 1em;
}

#input-section {
  padding: 10px;
  border-top: 1px solid #ccc;
}

.input-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.attachment-wrapper {
  position: relative;
}

.attachment-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

#chat-input-container {
  flex: 1;
  position: relative;
}

#chat-input {
  width: 100%;
  padding: 8px;
  border: 1px solid #ccc;
  resize: none;
  min-height: 40px;
  max-height: 100px;
}

#expand-button {
  position: absolute;
  bottom: 5px;
  right: 5px;
  background: none;
  border: none;
  cursor: pointer;
}

#chat-buttons-wrapper {
  display: flex;
  gap: 5px;
}

.chat-button {
  border: 1px solid #ccc;
  background-color: #f0f0f0;
  color: #333;
  padding: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  transition: background-color 0.2s;
}

.chat-button:hover {
  background-color: #e0e0e0;
}

.text-buttons-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
  justify-content: center;
}

.text-button {
  display: flex;
  align-items: center;
  background-color: #f0f0f0;
  border: none;
  color: #333;
  cursor: pointer;
  gap: 5px;
  padding: 5px 10px;
  transition: background-color 0.2s;
}

.text-button:hover {
  background-color: #e0e0e0;
}

/* Dark Mode Styles */
.dark-mode {
  background-color: #121212;
  color: #e0e0e0;
}

.dark-mode .container {
  background-color: #121212;
}

.dark-mode .panel {
  background-color: #1e1e1e;
}

.dark-mode .config-button {
  background-color: #2d2d2d;
  border: 1px solid #404040;
  color: #e0e0e0;
}

.dark-mode .config-button:hover {
  background-color: #3d3d3d;
}

.dark-mode .tab {
  color: #e0e0e0;
  border-bottom-color: #404040;
}

.dark-mode .tab.active {
  background-color: #2d2d2d;
}

.dark-mode .config-list li {
  border-bottom: 1px solid #404040;
}

.dark-mode .chat-list-button {
  color: #e0e0e0;
}

.dark-mode .edit-button {
  color: #e0e0e0;
}

.dark-mode .empty-list-message {
  color: #a0a0a0;
}

.dark-mode .pref-header {
  color: #e0e0e0;
}

.dark-mode .arrow-icon {
  stroke: #e0e0e0;
}

.dark-mode .version-info {
  color: #a0a0a0;
}

.dark-mode #time-date-container {
  border-bottom: 1px solid #404040;
  color: #e0e0e0;
}

.dark-mode #chat-history {
  background-color: #1e1e1e;
}

.dark-mode .user-message {
  background-color: #1e3a5f;
  color: #e0e0e0;
}

.dark-mode .agent-message {
  background-color: #2d2d2d;
  color: #e0e0e0;
}

.dark-mode #progress-bar-box {
  border-top: 1px solid #404040;
  color: #e0e0e0;
}

.dark-mode #input-section {
  border-top: 1px solid #404040;
}

.dark-mode #chat-input {
  background-color: #2d2d2d;
  border: 1px solid #404040;
  color: #e0e0e0;
}

.dark-mode .chat-button {
  background-color: #2d2d2d;
  border: 1px solid #404040;
  color: #e0e0e0;
}

.dark-mode .chat-button:hover {
  background-color: #3d3d3d;
}

.dark-mode .text-button {
  background-color: #2d2d2d;
  color: #e0e0e0;
}

.dark-mode .text-button:hover {
  background-color: #3d3d3d;
}
</style>
