// Global Error Handler Plugin
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('errorHandler')

export default {
  install(_app) {
    // Basic error handling
    window.addEventListener('error', (event) => {
      logger.error('[Global Error]', event.error);
    });

    window.addEventListener('unhandledrejection', (event) => {
      logger.error('[Unhandled Promise Rejection]', event.reason);
    });
  }
}