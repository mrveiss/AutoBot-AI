// Export all types and interfaces from this barrel file
export * from './exampleServiceTypes.js';
export * from './taskTypes.js'; // Added export for task types
// export * from './yourServiceTypes.js'; // Add new type exports here

// Define common types used across services/tools if any
export interface CommonContext {
    sessionId?: string;
    userId?: string;
}
