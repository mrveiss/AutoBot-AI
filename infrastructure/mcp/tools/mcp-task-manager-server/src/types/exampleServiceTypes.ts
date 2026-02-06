// Types specific to the ExampleService

/**
 * Configuration options for ExampleService.
 */
export interface ExampleServiceConfig {
    greeting: string;
    enableDetailedLogs: boolean;
}

/**
 * Data structure handled by ExampleService.
 */
export interface ExampleServiceData {
    name: string;
    message: string;
    processedTimestamp: string;
    metrics?: ExampleServiceMetrics;
}

/**
 * Metrics collected during ExampleService processing.
 */
export interface ExampleServiceMetrics {
    processingTimeMs: number;
}
