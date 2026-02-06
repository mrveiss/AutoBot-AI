// Real User Monitoring (RUM) Plugin
export default {
  install(_app) {
    // Initialize RUM monitoring
    if (typeof window !== 'undefined') {
      window.rum = {
        track: (event, data) => {
          if (import.meta.env.DEV) {
            console.log('[RUM]', event, data);
          }
        },
        trackUserInteraction: (action, element, metadata = {}) => {
          if (import.meta.env.DEV) {
            console.log('[RUM] User Interaction:', { action, element, metadata });
          }
          // You could send this to your analytics service here
        },
        trackError: (error, context = {}) => {
          if (import.meta.env.DEV) {
            console.error('[RUM] Error:', error, context);
          }
          // You could send this to your error reporting service here
        },
        trackPageView: (path, metadata = {}) => {
          if (import.meta.env.DEV) {
            console.log('[RUM] Page View:', { path, metadata });
          }
        },
        trackTiming: (name, duration, metadata = {}) => {
          if (import.meta.env.DEV) {
            console.log('[RUM] Timing:', { name, duration, metadata });
          }
        }
      };
    }
  }
}
