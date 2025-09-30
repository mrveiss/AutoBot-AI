// Global Error Handler Plugin
export default {
  install(app) {
    // Basic error handling
    window.addEventListener('error', (event) => {
      console.error('[Global Error]', event.error);
    });

    window.addEventListener('unhandledrejection', (event) => {
      console.error('[Unhandled Promise Rejection]', event.reason);
    });
  }
}