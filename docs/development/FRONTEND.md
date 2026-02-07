# Frontend Development Guide

## 📱 Frontend Architecture

**Technology Stack:**
- **Framework**: Vue 3 with Composition API
- **Build Tool**: Vite
- **Styling**: Tailwind CSS
- **TypeScript**: For type safety
- **WebSocket**: Global service for real-time updates

## 🎨 Vue Component Guidelines

### Component Structure
```vue
<template>
  <!-- Accessible, semantic HTML -->
  <div class="component-wrapper" role="main" aria-label="Component description">
    <!-- Content -->
  </div>
</template>

<script>
import { ref, reactive, computed, onMounted } from 'vue';

export default {
  name: 'ComponentName',
  props: {
    // Define props with types
  },
  emits: ['event-name'],
  setup(props, { emit }) {
    // Composition API logic
    return {
      // Exposed reactive references
    };
  }
};
</script>

<style scoped>
/* Component-specific styles */
</style>
```

### Code Style Standards
- **Use Composition API** over Options API
- **TypeScript** for all new components
- **Accessible markup** with proper ARIA labels
- **Responsive design** with Tailwind CSS
- **Error boundaries** for robust UX

## 🔌 WebSocket Integration

### Global WebSocket Service
```javascript
// Use the global WebSocket service
import { useGlobalWebSocket } from '@/composables/useGlobalWebSocket.js';

const { isConnected, on, send, state } = useGlobalWebSocket();

// Listen for events
on('llm_response', (data) => {
  // Handle real-time LLM responses
});

// Send messages
send({ type: 'ping' });
```

### Event Handling Patterns
```javascript
// Chat-specific events
wsOn('connection_established', (data) => {
  console.log('✅ Chat interface connected to WebSocket');
});

wsOn('llm_response', (data) => {
  // Process LLM responses
  if (data.payload && data.payload.response) {
    handleWebSocketEvent(data);
  }
});

wsOn('error', (data) => {
  // Handle connection errors gracefully
  showUserFriendlyError(data);
});
```

## 🎯 Frontend Quick Reference

### Project Structure
```
autobot-user-frontend/
├── src/
│   ├── components/         # Vue components
│   ├── composables/        # Composition API logic
│   ├── services/          # API services
│   ├── utils/             # Utility functions
│   ├── config/            # Configuration
│   └── main.ts            # App entry point
├── public/                # Static assets
└── vite.config.ts         # Vite configuration
```

### Key Components
- **ChatInterface.vue** - Main chat UI
- **TerminalWindow.vue** - Terminal integration
- **WorkflowApproval.vue** - Workflow management
- **ErrorBoundary.vue** - Error handling
- **ResearchBrowser.vue** - Research functionality

## 🔧 Build & Optimization

### Vite Configuration
```typescript
// vite.config.ts - Code splitting optimization
export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('vue') || id.includes('vue-router')) {
            return 'vue';
          }
          if (id.includes('/src/components/Terminal')) {
            return 'terminal-workflow';
          }
          if (id.includes('node_modules')) {
            return 'vendor';
          }
        }
      }
    }
  }
});
```

### Performance Guidelines
- **Lazy load** large components with `defineAsyncComponent`
- **Code splitting** by feature area
- **Bundle optimization** for production builds
- **Image optimization** and proper loading
- **Memory management** for long-running sessions

## 🎨 UI/UX Standards

### Accessibility
```vue
<template>
  <!-- Proper ARIA labels -->
  <button
    @click="sendMessage"
    :disabled="!inputMessage.trim()"
    class="btn btn-primary"
    aria-label="Send message"
  >
    <i class="fas fa-paper-plane" aria-hidden="true"></i>
    Send
  </button>

  <!-- Keyboard navigation -->
  <div
    @keyup.enter="$event.target.click()"
    @keyup.space="$event.target.click()"
    tabindex="0"
  >
    Interactive element
  </div>
</template>
```

### Responsive Design
```css
/* Mobile-first approach */
.container {
  @apply w-full px-4;
}

/* Tablet and up */
@screen md {
  .container {
    @apply px-6 max-w-4xl mx-auto;
  }
}

/* Desktop */
@screen lg {
  .container {
    @apply px-8 max-w-6xl;
  }
}
```

### Error Handling
```javascript
// User-friendly error messages
const handleError = (error) => {
  let errorMessage = 'An unexpected error occurred';

  if (error.message?.includes('timeout')) {
    errorMessage = 'Request timeout. Please try again.';
  } else if (error.message?.includes('Network')) {
    errorMessage = 'Network connection error. Please check your internet.';
  }

  // Show error to user (non-intrusive)
  showNotification(errorMessage, 'error');
};
```

## 📊 State Management

### Reactive State Patterns
```javascript
// Use reactive refs for component state
const state = reactive({
  messages: [],
  currentChatId: null,
  isLoading: false
});

// Computed properties for derived state
const filteredMessages = computed(() => {
  return state.messages.filter(msg =>
    settings.value.message_display.show_thoughts || msg.type !== 'thought'
  );
});

// Watchers for side effects
watch(currentChatId, async (newId) => {
  if (newId) {
    await loadChatMessages(newId);
  }
});
```

### Local Storage Integration
```javascript
// Save/load user preferences
const saveSettings = () => {
  localStorage.setItem('chat-settings', JSON.stringify(settings.value));
};

const loadSettings = () => {
  try {
    const saved = localStorage.getItem('chat-settings');
    if (saved) {
      Object.assign(settings.value, JSON.parse(saved));
    }
  } catch (error) {
    console.error('Failed to load settings:', error);
    // Use defaults
  }
};
```

## 🚨 Error Boundaries & Recovery

### Error Boundary Component
```vue
<template>
  <div v-if="hasError" class="error-boundary">
    <h2>Something went wrong</h2>
    <p>{{ errorMessage }}</p>
    <button @click="retry">Try Again</button>
  </div>
  <slot v-else />
</template>

<script>
export default {
  name: 'ErrorBoundary',
  data() {
    return {
      hasError: false,
      errorMessage: ''
    };
  },
  errorCaptured(error, instance, info) {
    this.hasError = true;
    this.errorMessage = error.message;
    console.error('Error caught by boundary:', error, info);
    return false;
  },
  methods: {
    retry() {
      this.hasError = false;
      this.errorMessage = '';
    }
  }
};
</script>
```

## 🔍 Frontend Testing

### Component Testing
```javascript
// Test component behavior
import { mount } from '@vue/test-utils';
import ChatInterface from '@/components/ChatInterface.vue';

describe('ChatInterface', () => {
  it('sends message when button clicked', async () => {
    const wrapper = mount(ChatInterface);

    await wrapper.find('textarea').setValue('Test message');
    await wrapper.find('button[aria-label="Send message"]').trigger('click');

    expect(wrapper.emitted('message-sent')).toBeTruthy();
  });
});
```

### E2E Testing Guidelines
- Test critical user flows
- Verify real-time functionality
- Check accessibility features
- Validate error scenarios
