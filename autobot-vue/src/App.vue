<template>
  <div id="app" class="min-h-screen bg-blueGray-50">
    <!-- Sidebar -->
    <nav class="md:left-0 md:block md:fixed md:top-0 md:bottom-0 md:overflow-y-auto md:flex-row md:flex-nowrap md:overflow-hidden shadow-xl bg-white flex flex-wrap items-center justify-between relative md:w-64 z-10 py-4 px-6">
      <div class="md:flex-col md:items-stretch md:min-h-full md:flex-nowrap px-0 flex flex-wrap items-center justify-between w-full mx-auto">
        <!-- Brand -->
        <div class="flex items-center">
          <div class="w-12 h-12 bg-gradient-to-br from-indigo-500 to-indigo-700 rounded-full flex items-center justify-center shadow-lg">
            <span class="text-white text-xl font-bold">A</span>
          </div>
          <span class="ml-3 text-xl font-semibold text-blueGray-700">AutoBot Pro</span>
        </div>

        <!-- Mobile menu button -->
        <button
          class="cursor-pointer text-black opacity-50 md:hidden px-3 py-1 text-xl leading-none bg-transparent rounded border border-solid border-transparent"
          type="button"
          @click="toggleNavbar"
        >
          <i class="fas fa-bars"></i>
        </button>

        <!-- Navigation -->
        <div
          class="md:flex md:flex-col md:items-stretch md:opacity-100 md:relative md:mt-4 md:shadow-none shadow absolute top-0 left-0 right-0 z-40 overflow-y-auto overflow-x-hidden h-auto items-center flex-1 rounded"
          :class="[navbarOpen ? 'bg-white m-2 mt-16 px-6 py-3' : 'hidden']"
        >
          <!-- Navigation links -->
          <ul class="md:flex-col md:min-w-full flex flex-col list-none mt-6">
            <li class="items-center">
              <a
                @click="activeTab = 'dashboard'"
                :class="[activeTab === 'dashboard' ? 'text-indigo-500 bg-indigo-50' : 'text-blueGray-700 hover:text-blueGray-500']"
                class="text-xs uppercase py-3 px-4 font-bold block rounded-lg cursor-pointer transition-all duration-150"
              >
                <i class="fas fa-tachometer-alt mr-2 text-sm"></i>
                Dashboard
              </a>
            </li>
            <li class="items-center">
              <a
                @click="activeTab = 'chat'"
                :class="[activeTab === 'chat' ? 'text-indigo-500 bg-indigo-50' : 'text-blueGray-700 hover:text-blueGray-500']"
                class="text-xs uppercase py-3 px-4 font-bold block rounded-lg cursor-pointer transition-all duration-150"
              >
                <i class="fas fa-comments mr-2 text-sm"></i>
                AI Assistant
              </a>
            </li>
            <li class="items-center">
              <a
                @click="activeTab = 'voice'"
                :class="[activeTab === 'voice' ? 'text-indigo-500 bg-indigo-50' : 'text-blueGray-700 hover:text-blueGray-500']"
                class="text-xs uppercase py-3 px-4 font-bold block rounded-lg cursor-pointer transition-all duration-150"
              >
                <i class="fas fa-microphone mr-2 text-sm"></i>
                Voice Interface
              </a>
            </li>
            <li class="items-center">
              <a
                @click="activeTab = 'knowledge'"
                :class="[activeTab === 'knowledge' ? 'text-indigo-500 bg-indigo-50' : 'text-blueGray-700 hover:text-blueGray-500']"
                class="text-xs uppercase py-3 px-4 font-bold block rounded-lg cursor-pointer transition-all duration-150"
              >
                <i class="fas fa-brain mr-2 text-sm"></i>
                Knowledge Base
              </a>
            </li>
            <li class="items-center">
              <a
                @click="activeTab = 'terminal'"
                :class="[activeTab === 'terminal' ? 'text-indigo-500 bg-indigo-50' : 'text-blueGray-700 hover:text-blueGray-500']"
                class="text-xs uppercase py-3 px-4 font-bold block rounded-lg cursor-pointer transition-all duration-150"
              >
                <i class="fas fa-terminal mr-2 text-sm"></i>
                Terminal
              </a>
            </li>
            <li class="items-center">
              <a
                @click="activeTab = 'files'"
                :class="[activeTab === 'files' ? 'text-indigo-500 bg-indigo-50' : 'text-blueGray-700 hover:text-blueGray-500']"
                class="text-xs uppercase py-3 px-4 font-bold block rounded-lg cursor-pointer transition-all duration-150"
              >
                <i class="fas fa-folder mr-2 text-sm"></i>
                File Manager
              </a>
            </li>
            <li class="items-center">
              <a
                @click="activeTab = 'monitor'"
                :class="[activeTab === 'monitor' ? 'text-indigo-500 bg-indigo-50' : 'text-blueGray-700 hover:text-blueGray-500']"
                class="text-xs uppercase py-3 px-4 font-bold block rounded-lg cursor-pointer transition-all duration-150"
              >
                <i class="fas fa-chart-line mr-2 text-sm"></i>
                System Monitor
              </a>
            </li>
            <li class="items-center">
              <a
                @click="activeTab = 'settings'"
                :class="[activeTab === 'settings' ? 'text-indigo-500 bg-indigo-50' : 'text-blueGray-700 hover:text-blueGray-500']"
                class="text-xs uppercase py-3 px-4 font-bold block rounded-lg cursor-pointer transition-all duration-150"
              >
                <i class="fas fa-cog mr-2 text-sm"></i>
                Settings
              </a>
            </li>
          </ul>

          <!-- Status section -->
          <div class="mt-auto pt-6 border-t border-blueGray-200">
            <h6 class="text-xs uppercase text-blueGray-400 font-bold tracking-wider mb-3">System Status</h6>
            <div class="space-y-2">
              <div class="flex items-center justify-between">
                <span class="text-xs text-blueGray-600">Backend</span>
                <span :class="['text-xs font-semibold', backendStatus.class === 'connected' ? 'text-emerald-500' : 'text-red-500']">
                  {{ backendStatus.text }}
                </span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-xs text-blueGray-600">LLM</span>
                <span :class="['text-xs font-semibold', llmStatus.class === 'connected' ? 'text-emerald-500' : 'text-red-500']">
                  {{ llmStatus.text }}
                </span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-xs text-blueGray-600">Redis</span>
                <span :class="['text-xs font-semibold', redisStatus.class === 'connected' ? 'text-emerald-500' : 'text-red-500']">
                  {{ redisStatus.text }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </nav>

    <!-- Main content -->
    <div class="relative md:ml-64 bg-blueGray-50 min-h-screen">
      <!-- Navbar -->
      <nav class="absolute top-0 left-0 w-full z-10 bg-transparent md:flex-row md:flex-nowrap md:justify-start flex items-center p-4">
        <div class="w-full mx-auto items-center flex justify-between md:flex-nowrap flex-wrap md:px-10 px-4">
          <!-- Page heading -->
          <h1 class="text-white text-2xl font-semibold">{{ pageTitle }}</h1>
          <!-- User menu -->
          <ul class="flex-col md:flex-row list-none items-center hidden md:flex">
            <a class="text-blueGray-200 hover:text-white px-3 py-2 flex items-center text-xs uppercase font-bold">
              <i class="fas fa-user-circle text-lg mr-2"></i>
              Admin User
            </a>
          </ul>
        </div>
      </nav>

      <!-- Header gradient -->
      <div class="relative bg-gradient-to-br from-indigo-600 to-indigo-800 md:pt-32 pb-32 pt-12">
        <div class="px-4 md:px-10 mx-auto w-full">
          <!-- Dashboard cards (only show on dashboard) -->
          <div v-if="activeTab === 'dashboard'" class="flex flex-wrap">
            <div class="w-full lg:w-6/12 xl:w-3/12 px-4">
              <div class="relative flex flex-col min-w-0 break-words bg-white rounded-lg mb-6 xl:mb-0 shadow-lg">
                <div class="flex-auto p-4">
                  <div class="flex flex-wrap">
                    <div class="relative w-full pr-4 max-w-full flex-grow flex-1">
                      <h5 class="text-blueGray-400 uppercase font-bold text-xs">Active Sessions</h5>
                      <span class="font-semibold text-xl text-blueGray-700">{{ activeSessions }}</span>
                    </div>
                    <div class="relative w-auto pl-4 flex-initial">
                      <div class="text-white p-3 text-center inline-flex items-center justify-center w-12 h-12 shadow-lg rounded-full bg-red-500">
                        <i class="fas fa-users"></i>
                      </div>
                    </div>
                  </div>
                  <p class="text-sm text-blueGray-400 mt-4">
                    <span class="text-emerald-500 mr-2">
                      <i class="fas fa-arrow-up"></i> 3.48%
                    </span>
                    <span class="whitespace-nowrap">Since last month</span>
                  </p>
                </div>
              </div>
            </div>
            <div class="w-full lg:w-6/12 xl:w-3/12 px-4">
              <div class="relative flex flex-col min-w-0 break-words bg-white rounded-lg mb-6 xl:mb-0 shadow-lg">
                <div class="flex-auto p-4">
                  <div class="flex flex-wrap">
                    <div class="relative w-full pr-4 max-w-full flex-grow flex-1">
                      <h5 class="text-blueGray-400 uppercase font-bold text-xs">Knowledge Items</h5>
                      <span class="font-semibold text-xl text-blueGray-700">{{ knowledgeItems }}</span>
                    </div>
                    <div class="relative w-auto pl-4 flex-initial">
                      <div class="text-white p-3 text-center inline-flex items-center justify-center w-12 h-12 shadow-lg rounded-full bg-orange-500">
                        <i class="fas fa-database"></i>
                      </div>
                    </div>
                  </div>
                  <p class="text-sm text-blueGray-400 mt-4">
                    <span class="text-emerald-500 mr-2">
                      <i class="fas fa-arrow-up"></i> 12%
                    </span>
                    <span class="whitespace-nowrap">Since last week</span>
                  </p>
                </div>
              </div>
            </div>
            <div class="w-full lg:w-6/12 xl:w-3/12 px-4">
              <div class="relative flex flex-col min-w-0 break-words bg-white rounded-lg mb-6 xl:mb-0 shadow-lg">
                <div class="flex-auto p-4">
                  <div class="flex flex-wrap">
                    <div class="relative w-full pr-4 max-w-full flex-grow flex-1">
                      <h5 class="text-blueGray-400 uppercase font-bold text-xs">Tasks Completed</h5>
                      <span class="font-semibold text-xl text-blueGray-700">{{ tasksCompleted }}</span>
                    </div>
                    <div class="relative w-auto pl-4 flex-initial">
                      <div class="text-white p-3 text-center inline-flex items-center justify-center w-12 h-12 shadow-lg rounded-full bg-emerald-500">
                        <i class="fas fa-check-circle"></i>
                      </div>
                    </div>
                  </div>
                  <p class="text-sm text-blueGray-400 mt-4">
                    <span class="text-orange-500 mr-2">
                      <i class="fas fa-arrow-down"></i> 1.10%
                    </span>
                    <span class="whitespace-nowrap">Since yesterday</span>
                  </p>
                </div>
              </div>
            </div>
            <div class="w-full lg:w-6/12 xl:w-3/12 px-4">
              <div class="relative flex flex-col min-w-0 break-words bg-white rounded-lg mb-6 xl:mb-0 shadow-lg">
                <div class="flex-auto p-4">
                  <div class="flex flex-wrap">
                    <div class="relative w-full pr-4 max-w-full flex-grow flex-1">
                      <h5 class="text-blueGray-400 uppercase font-bold text-xs">Performance</h5>
                      <span class="font-semibold text-xl text-blueGray-700">{{ performance }}%</span>
                    </div>
                    <div class="relative w-auto pl-4 flex-initial">
                      <div class="text-white p-3 text-center inline-flex items-center justify-center w-12 h-12 shadow-lg rounded-full bg-lightBlue-500">
                        <i class="fas fa-tachometer-alt"></i>
                      </div>
                    </div>
                  </div>
                  <p class="text-sm text-blueGray-400 mt-4">
                    <span class="text-emerald-500 mr-2">
                      <i class="fas fa-arrow-up"></i> 12%
                    </span>
                    <span class="whitespace-nowrap">Since last month</span>
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Content area -->
      <div class="px-4 md:px-10 mx-auto w-full -m-24">
        <div class="flex flex-wrap mt-4">
          <div class="w-full mb-12 px-4">
            <Transition name="fade-slide" mode="out-in">
              <!-- Dashboard View -->
              <div v-if="activeTab === 'dashboard'" key="dashboard" class="relative flex flex-col min-w-0 break-words w-full mb-6 shadow-lg rounded-lg bg-white">
                <div class="rounded-t mb-0 px-6 py-6">
                  <div class="text-center flex justify-between">
                    <h6 class="text-blueGray-700 text-xl font-bold">System Overview</h6>
                    <button class="bg-indigo-500 text-white active:bg-indigo-600 text-xs font-bold uppercase px-3 py-1 rounded outline-none focus:outline-none mr-1 mb-1 ease-linear transition-all duration-150" type="button">
                      <i class="fas fa-sync mr-1"></i> Refresh
                    </button>
                  </div>
                </div>
                <div class="flex-auto px-6 py-6">
                  <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div class="bg-blueGray-50 rounded-lg p-6">
                      <h3 class="text-lg font-semibold text-blueGray-700 mb-4">Recent Activity</h3>
                      <div class="space-y-3">
                        <div class="flex items-center">
                          <div class="w-2 h-2 bg-emerald-500 rounded-full mr-3"></div>
                          <span class="text-sm text-blueGray-600">New knowledge item added</span>
                          <span class="ml-auto text-xs text-blueGray-400">2 min ago</span>
                        </div>
                        <div class="flex items-center">
                          <div class="w-2 h-2 bg-lightBlue-500 rounded-full mr-3"></div>
                          <span class="text-sm text-blueGray-600">Voice command processed</span>
                          <span class="ml-auto text-xs text-blueGray-400">5 min ago</span>
                        </div>
                        <div class="flex items-center">
                          <div class="w-2 h-2 bg-orange-500 rounded-full mr-3"></div>
                          <span class="text-sm text-blueGray-600">File uploaded successfully</span>
                          <span class="ml-auto text-xs text-blueGray-400">12 min ago</span>
                        </div>
                      </div>
                    </div>
                    <div class="bg-blueGray-50 rounded-lg p-6">
                      <h3 class="text-lg font-semibold text-blueGray-700 mb-4">Quick Actions</h3>
                      <div class="grid grid-cols-2 gap-3">
                        <button @click="activeTab = 'chat'" class="btn btn-primary text-sm">
                          <i class="fas fa-comments mr-2"></i>
                          New Chat
                        </button>
                        <button @click="activeTab = 'knowledge'" class="btn btn-secondary text-sm">
                          <i class="fas fa-plus mr-2"></i>
                          Add Knowledge
                        </button>
                        <button @click="activeTab = 'files'" class="btn btn-success text-sm">
                          <i class="fas fa-upload mr-2"></i>
                          Upload File
                        </button>
                        <button @click="activeTab = 'terminal'" class="btn btn-outline text-sm">
                          <i class="fas fa-terminal mr-2"></i>
                          Terminal
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Chat View -->
              <section v-else-if="activeTab === 'chat'" key="chat" class="card">
                <div class="card-header bg-gradient-to-r from-indigo-500 to-indigo-600 text-white">
                  <div class="flex items-center justify-between">
                    <h2 class="text-xl font-bold">AI Assistant</h2>
                    <button @click="newChat" class="btn bg-white bg-opacity-20 hover:bg-opacity-30 text-white text-sm">
                      <i class="fas fa-plus mr-2"></i>
                      New Chat
                    </button>
                  </div>
                </div>
                <div class="card-body p-0">
                  <ChatInterface v-if="activeChatId" :key="activeChatId" />
                </div>
              </section>

              <!-- Voice View -->
              <section v-else-if="activeTab === 'voice'" key="voice" class="card">
                <div class="card-header">
                  <h2 class="text-xl font-bold text-blueGray-700">Voice Interface</h2>
                </div>
                <div class="card-body">
                  <VoiceInterface />
                </div>
              </section>

              <!-- Knowledge View -->
              <section v-else-if="activeTab === 'knowledge'" key="knowledge" class="card">
                <div class="card-header">
                  <h2 class="text-xl font-bold text-blueGray-700">Knowledge Base</h2>
                </div>
                <div class="card-body p-0">
                  <KnowledgeManager />
                </div>
              </section>

              <!-- Terminal View -->
              <section v-else-if="activeTab === 'terminal'" key="terminal" class="card bg-blueGray-900">
                <div class="card-header bg-blueGray-800">
                  <h2 class="text-xl font-bold text-white">Terminal</h2>
                </div>
                <div class="card-body p-0">
                  <TerminalWindow />
                </div>
              </section>

              <!-- Settings View -->
              <section v-else-if="activeTab === 'settings'" key="settings" class="card">
                <div class="card-header">
                  <h2 class="text-xl font-bold text-blueGray-700">System Settings</h2>
                </div>
                <div class="card-body">
                  <SettingsPanel />
                </div>
              </section>

              <!-- Files View -->
              <section v-else-if="activeTab === 'files'" key="files" class="card">
                <div class="card-header">
                  <div class="flex items-center justify-between">
                    <h2 class="text-xl font-bold text-blueGray-700">File Manager</h2>
                    <button @click="uploadFile" class="btn btn-primary text-sm">
                      <i class="fas fa-upload mr-2"></i>
                      Upload
                    </button>
                  </div>
                </div>
                <div class="card-body">
                  <FileBrowser />
                </div>
              </section>

              <!-- Monitor View -->
              <section v-else-if="activeTab === 'monitor'" key="monitor" class="card">
                <div class="card-header">
                  <div class="flex items-center justify-between">
                    <h2 class="text-xl font-bold text-blueGray-700">System Monitor</h2>
                    <button @click="refreshStats" class="btn btn-primary text-sm">
                      <i class="fas fa-sync mr-2"></i>
                      Refresh
                    </button>
                  </div>
                </div>
                <div class="card-body p-0">
                  <SystemMonitor />
                </div>
              </section>
            </Transition>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import ChatInterface from './components/ChatInterface.vue';
import VoiceInterface from './components/VoiceInterface.vue';
import KnowledgeManager from './components/KnowledgeManager.vue';
import TerminalWindow from './components/TerminalWindow.vue';
import SettingsPanel from './components/SettingsPanel.vue';
import FileBrowser from './components/FileBrowser.vue';
import SystemMonitor from './components/SystemMonitor.vue';

export default {
  name: 'App',
  components: {
    ChatInterface,
    VoiceInterface,
    KnowledgeManager,
    TerminalWindow,
    SettingsPanel,
    FileBrowser,
    SystemMonitor
  },
  setup() {
    const activeTab = ref('dashboard');
    const activeChatId = ref(`chat-${Date.now()}`);
    const navbarOpen = ref(false);

    // Dashboard stats
    const activeSessions = ref(3);
    const knowledgeItems = ref(1247);
    const tasksCompleted = ref(89);
    const performance = ref(92);

    // Connection statuses
    const backendStatus = ref({ text: 'Checking...', class: 'warning', message: 'Connecting to backend...' });
    const llmStatus = ref({ text: 'Checking...', class: 'warning', message: 'Connecting to LLM...' });
    const redisStatus = ref({ text: 'Checking...', class: 'warning', message: 'Connecting to Redis...' });

    const pageTitle = computed(() => {
      const titles = {
        dashboard: 'Dashboard',
        chat: 'AI Assistant',
        voice: 'Voice Interface',
        knowledge: 'Knowledge Base',
        terminal: 'Terminal',
        settings: 'Settings',
        files: 'File Manager',
        monitor: 'System Monitor'
      };
      return titles[activeTab.value] || 'AutoBot';
    });

    const toggleNavbar = () => {
      navbarOpen.value = !navbarOpen.value;
    };

    const newChat = () => {
      activeChatId.value = `chat-${Date.now()}`;
    };

    const uploadFile = () => {
      console.log('Upload file clicked');
    };

    const refreshStats = () => {
      console.log('Refresh stats clicked');
    };

    const checkConnectionStatus = async () => {
      try {
        const response = await fetch('http://localhost:8001/api/system/health');
        if (response.ok) {
          const data = await response.json();
          backendStatus.value = { text: 'Connected', class: 'connected', message: 'Backend is running' };
          llmStatus.value = data.llm_status ?
            { text: 'Ready', class: 'connected', message: 'LLM is ready' } :
            { text: 'Error', class: 'error', message: 'LLM connection failed' };
          redisStatus.value = data.redis_status ?
            { text: 'Connected', class: 'connected', message: 'Redis is running' } :
            { text: 'Error', class: 'error', message: 'Redis connection failed' };
        } else {
          backendStatus.value = { text: 'Error', class: 'error', message: 'Backend connection failed' };
        }
      } catch (error) {
        backendStatus.value = { text: 'Offline', class: 'error', message: 'Cannot reach backend' };
        llmStatus.value = { text: 'Unknown', class: 'warning', message: 'Status unknown' };
        redisStatus.value = { text: 'Unknown', class: 'warning', message: 'Status unknown' };
      }
    };

    let statusCheckInterval;

    onMounted(() => {
      checkConnectionStatus();
      statusCheckInterval = setInterval(checkConnectionStatus, 10000);

      // Simulate dashboard updates
      setInterval(() => {
        activeSessions.value = Math.floor(Math.random() * 5) + 1;
        performance.value = Math.floor(Math.random() * 20) + 80;
      }, 5000);
    });

    onUnmounted(() => {
      if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
      }
    });

    return {
      activeTab,
      activeChatId,
      navbarOpen,
      backendStatus,
      llmStatus,
      redisStatus,
      pageTitle,
      activeSessions,
      knowledgeItems,
      tasksCompleted,
      performance,
      toggleNavbar,
      newChat,
      uploadFile,
      refreshStats
    };
  }
};
</script>

<style>
@import './assets/tailwind.css';
@import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css');

/* Transitions */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.3s ease;
}

.fade-slide-enter-from {
  transform: translateY(10px);
  opacity: 0;
}

.fade-slide-leave-to {
  transform: translateY(-10px);
  opacity: 0;
}

/* Custom scrollbar */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: #f1f5f9;
}

::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}
</style>
