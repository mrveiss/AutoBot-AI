/**
 * Custom error types for the Task Management Server.
 * These can be caught in the service layer and mapped to specific
 * McpError codes in the tool layer.
 */

// Example: Base service error
export class ServiceError extends Error {
    constructor(message: string, public details?: any) {
        super(message);
        this.name = 'ServiceError';
    }
}

// Example: Validation specific error
export class ValidationError extends ServiceError {
    constructor(message: string, details?: any) {
        super(message, details);
        this.name = 'ValidationError';
    }
}

// Example: Not found specific error
export class NotFoundError extends ServiceError {
    constructor(message: string = "Resource not found", details?: any) {
        super(message, details);
        this.name = 'NotFoundError';
    }
}

// Example: Conflict specific error (e.g., trying to create something that exists)
export class ConflictError extends ServiceError {
    constructor(message: string = "Resource conflict", details?: any) {
        super(message, details);
        this.name = 'ConflictError';
    }
}

// Add other custom error types as needed
