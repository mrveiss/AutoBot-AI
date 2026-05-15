import { pino, Logger } from 'pino'; // Try named import for the function

/**
 * Pino logger instance configured for structured JSON logging to stderr.
 * MCP servers typically use stdout for protocol messages, so logs go to stderr.
 */
export const logger: Logger = pino(
    {
        level: process.env.LOG_LEVEL || 'info', // Default to 'info', configurable via env var
        formatters: {
            level: (label: string) => { // Add type for label
                // Standardize level labels if desired, e.g., uppercase
                return { level: label.toUpperCase() };
            },
            // bindings: (bindings) => {
            //     // Add custom bindings if needed, e.g., hostname, pid
            //     return { pid: bindings.pid, hostname: bindings.hostname };
            // },
        },
        timestamp: pino.stdTimeFunctions.isoTime, // Use ISO 8601 timestamps
    },
    pino.destination(2) // Direct output to stderr (file descriptor 2)
);

// Example usage (replace console.log/error calls throughout the app):
// logger.info('Server starting...');
// logger.debug({ userId: '123' }, 'User logged in');
// logger.error(new Error('Something failed'), 'Failed to process request');
