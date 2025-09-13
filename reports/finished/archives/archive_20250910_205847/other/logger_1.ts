import winston from 'winston';

// Define log levels
const levels = {
  error: 0,
  warn: 1,
  info: 2,
  http: 3,
  debug: 4,
};

// Define colors for each level
const colors = {
  error: 'red',
  warn: 'yellow',
  info: 'green',
  http: 'magenta',
  debug: 'white',
};

// Tell winston about the colors
winston.addColors(colors);

// Custom format function
const format = winston.format.combine(
  winston.format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss:ms' }),
  winston.format.colorize({ all: true }),
  winston.format.printf(
    (info) => `${info.timestamp} ${info.level}: ${info.message}`
  )
);

// Define which transports the logger must use
const transports: winston.transport[] = [
  // Console transport
  new winston.transports.Console({
    format: winston.format.combine(
      winston.format.colorize(),
      winston.format.simple()
    ),
  }),
  
  // File transport for errors
  new winston.transports.File({
    filename: 'logs/error.log',
    level: 'error',
    format: winston.format.combine(
      winston.format.timestamp(),
      winston.format.json()
    ),
  }),
  
  // File transport for all logs
  new winston.transports.File({
    filename: 'logs/combined.log',
    format: winston.format.combine(
      winston.format.timestamp(),
      winston.format.json()
    ),
  }),
];

// Create the logger
const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  levels,
  format,
  transports,
});

// Create a stream object with a 'write' function that will be used by Morgan
interface LoggerStream {
  write: (message: string) => void;
}

const loggerStream: LoggerStream = {
  write: (message: string) => {
    // Remove the trailing newline
    logger.http(message.trim());
  },
};

// Add stream property to logger
(logger as any).stream = loggerStream;

// Export logger with proper typing
interface Logger extends winston.Logger {
  stream: LoggerStream;
}

export default logger as Logger;

// Export individual log level functions for convenience
export const logError = (message: string, error?: Error): void => {
  if (error) {
    logger.error(`${message}: ${error.message}`, { stack: error.stack });
  } else {
    logger.error(message);
  }
};

export const logWarn = (message: string): void => {
  logger.warn(message);
};

export const logInfo = (message: string): void => {
  logger.info(message);
};

export const logDebug = (message: string): void => {
  logger.debug(message);
};

// Log HTTP requests
export const logHttp = (message: string): void => {
  logger.http(message);
};

// Log with context
export const logWithContext = (
  level: string,
  message: string,
  context?: Record<string, any>
): void => {
  logger.log(level, message, context);
};

// Create child logger with additional context
export const createChildLogger = (context: Record<string, any>): winston.Logger => {
  return logger.child(context);
};

// Performance logging utility
export const logPerformance = (operation: string, startTime: number): void => {
  const duration = Date.now() - startTime;
  logger.info(`${operation} completed in ${duration}ms`);
};

// Database query logging
export const logQuery = (query: string, duration?: number): void => {
  const message = duration
    ? `Query executed in ${duration}ms: ${query}`
    : `Query executed: ${query}`;
  logger.debug(message);
};

// User action logging
export const logUserAction = (
  userId: string,
  action: string,
  details?: Record<string, any>
): void => {
  const message = `User ${userId} performed action: ${action}`;
  logger.info(message, details);
};

// Security event logging
export const logSecurityEvent = (
  event: string,
  details: Record<string, any>
): void => {
  logger.warn(`Security event: ${event}`, details);
};

// API request logging
export const logApiRequest = (
  method: string,
  url: string,
  statusCode: number,
  duration: number,
  userId?: string
): void => {
  const message = `${method} ${url} - ${statusCode} (${duration}ms)`;
  const context = userId ? { userId } : {};
  logger.http(message, context);
};

// Environment-specific logging configuration
if (process.env.NODE_ENV === 'production') {
  // In production, reduce console logging
  logger.remove(logger.transports[0]);
  logger.add(new winston.transports.Console({
    level: 'warn',
    format: winston.format.simple(),
  }));
}

if (process.env.NODE_ENV === 'test') {
  // In test environment, minimize logging
  logger.level = 'error';
}