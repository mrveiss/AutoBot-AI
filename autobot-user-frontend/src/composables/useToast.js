import { ref } from 'vue';

// Global toast state
const toasts = ref([]);
let nextId = 1;

export function useToast() {
  const showToast = (message, type = 'info', duration = 3000) => {
    const id = nextId++;
    const toast = {
      id,
      message,
      type, // 'info', 'success', 'warning', 'error'
      duration
    };

    toasts.value.push(toast);

    // Auto-remove after duration
    if (duration > 0) {
      setTimeout(() => {
        removeToast(id);
      }, duration);
    }

    return id;
  };

  const removeToast = (id) => {
    const index = toasts.value.findIndex(toast => toast.id === id);
    if (index > -1) {
      toasts.value.splice(index, 1);
    }
  };

  const clearAllToasts = () => {
    toasts.value.splice(0);
  };

  return {
    toasts,
    showToast,
    removeToast,
    clearAllToasts
  };
}
