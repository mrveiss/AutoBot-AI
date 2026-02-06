// Import config types for services as they are added
import { ExampleServiceConfig } from '../types/index.js';

// Define the structure for all configurations managed
interface ManagedConfigs {
    exampleService: Required<ExampleServiceConfig>;
// Add other service config types here:
    // yourService: Required<YourServiceConfig>;
    databasePath: string; // Added for database file location
}

/**
 * Centralized configuration management for all services.
 * Implements singleton pattern to ensure consistent configuration.
 */
export class ConfigurationManager {
    private static instance: ConfigurationManager | null = null;
    private static instanceLock = false;

    private config: ManagedConfigs;

    private constructor() {
        // Initialize with default configurations
        this.config = {
            exampleService: {
                // Define defaults for ExampleService
                greeting: "Hello",
                enableDetailedLogs: false,
            },
            // Initialize other service configs with defaults:
            // yourService: {
            //   someSetting: 'default value',
            //   retryCount: 3,
            // },
            // Default database path
            databasePath: './data/taskmanager.db',
        };

        // Optional: Load overrides from environment variables or config files here
        this.loadEnvironmentOverrides();
    }

    /**
     * Get the singleton instance of ConfigurationManager.
     * Basic lock to prevent race conditions during initial creation.
     */
    public static getInstance(): ConfigurationManager {
        if (!ConfigurationManager.instance) {
            if (!ConfigurationManager.instanceLock) {
                ConfigurationManager.instanceLock = true; // Lock
                try {
                    ConfigurationManager.instance = new ConfigurationManager();
                } finally {
                    ConfigurationManager.instanceLock = false; // Unlock
                }
            } else {
                // Basic busy wait if locked (consider a more robust async lock if high contention is expected)
                while (ConfigurationManager.instanceLock) { }
                // Re-check instance after wait
                if (!ConfigurationManager.instance) {
                    // This path is less likely but handles edge cases if lock logic needs refinement
                    return ConfigurationManager.getInstance();
                }
            }
        }
        return ConfigurationManager.instance;
    }

    // --- Getters for specific configurations ---

    public getExampleServiceConfig(): Required<ExampleServiceConfig> {
        // Return a copy to prevent accidental modification of the internal state
        return { ...this.config.exampleService };
    }

    // Add getters for other service configs:
    // public getYourServiceConfig(): Required<YourServiceConfig> {
    //   return { ...this.config.yourService };
    // }

    public getDatabasePath(): string {
        // Return a copy to prevent accidental modification (though less critical for a string)
        return this.config.databasePath;
    }

    // --- Updaters for specific configurations (if runtime updates are needed) ---

    public updateExampleServiceConfig(update: Partial<ExampleServiceConfig>): void {
        this.config.exampleService = {
            ...this.config.exampleService,
            ...update,
        };
        // Optional: Notify relevant services about the config change
    }

    // Add updaters for other service configs:
    // public updateYourServiceConfig(update: Partial<YourServiceConfig>): void {
    //   this.config.yourService = {
    //     ...this.config.yourService,
    //     ...update,
    //   };
    // }

    /**
     * Example method to load configuration overrides from environment variables.
     * Call this in the constructor.
     */
    private loadEnvironmentOverrides(): void {
        // Example for ExampleService
        if (process.env.EXAMPLE_GREETING) {
            this.config.exampleService.greeting = process.env.EXAMPLE_GREETING;
        }
        if (process.env.EXAMPLE_ENABLE_LOGS) {
            this.config.exampleService.enableDetailedLogs = process.env.EXAMPLE_ENABLE_LOGS.toLowerCase() === 'true';
        }

        // Override for Database Path
        if (process.env.DATABASE_PATH) {
            this.config.databasePath = process.env.DATABASE_PATH;
        }

        // Add logic for other services based on their environment variables
        // if (process.env.YOUR_SERVICE_RETRY_COUNT) {
        //   const retryCount = parseInt(process.env.YOUR_SERVICE_RETRY_COUNT, 10);
        //   if (!isNaN(retryCount)) {
        //     this.config.yourService.retryCount = retryCount;
        //   }
        // }
    }
}
