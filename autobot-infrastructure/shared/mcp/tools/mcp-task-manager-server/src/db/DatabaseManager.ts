import Database, { Database as Db } from 'better-sqlite3';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url'; // Added for ES Module dirname
import { ConfigurationManager } from '../config/ConfigurationManager.js';
import { logger } from '../utils/logger.js'; // Assuming logger exists

export class DatabaseManager {
    private static instance: DatabaseManager;
    private db!: Db; // Added definite assignment assertion
    private dbPath: string;

    private constructor() {
        const configManager = ConfigurationManager.getInstance();
        // TODO: Get path from configManager once implemented
        // For now, use a default relative path
        this.dbPath = configManager.getDatabasePath(); // Assuming this method exists
        logger.info(`[DatabaseManager] Using database path: ${this.dbPath}`);

        this.initializeDatabase();
    }

    public static getInstance(): DatabaseManager {
        if (!DatabaseManager.instance) {
            DatabaseManager.instance = new DatabaseManager();
        }
        return DatabaseManager.instance;
    }

    private initializeDatabase(): void {
        try {
            const dbDir = path.dirname(this.dbPath);
            if (!fs.existsSync(dbDir)) {
                logger.info(`[DatabaseManager] Creating database directory: ${dbDir}`);
                fs.mkdirSync(dbDir, { recursive: true });
            }

            const dbExists = fs.existsSync(this.dbPath);
            logger.info(`[DatabaseManager] Database file ${this.dbPath} exists: ${dbExists}`);

            // Pass a wrapper function for verbose logging to match expected signature
            this.db = new Database(this.dbPath, {
                verbose: (message?: any, ...additionalArgs: any[]) => logger.debug({ sql: message, params: additionalArgs }, 'SQLite Query')
            });

            // Always enable foreign keys and WAL mode upon connection
            this.db.pragma('foreign_keys = ON');
            // Assert type for pragma result
            const journalMode = this.db.pragma('journal_mode = WAL') as [{ journal_mode: string }];
            logger.info(`[DatabaseManager] Journal mode set to: ${journalMode[0]?.journal_mode ?? 'unknown'}`);


            // Check if initialization is needed (simple check: does 'projects' table exist?)
            const tableCheck = this.db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='projects';").get();

            if (!tableCheck) {
                logger.info('[DatabaseManager] Projects table not found. Initializing schema...');
                // Revert to looking for schema.sql relative to the compiled JS file's directory (__dirname)
                const __filename = fileURLToPath(import.meta.url);
                const __dirname = path.dirname(__filename); // This will be dist/db when running compiled code
                const schemaPath = path.join(__dirname, 'schema.sql');

                logger.info(`[DatabaseManager] Looking for schema file at: ${schemaPath}`);
                if (!fs.existsSync(schemaPath)) {
                    logger.error(`[DatabaseManager] Schema file not found at ${schemaPath}. Ensure build process copied it correctly.`);
                    throw new Error(`Schema file not found at ${schemaPath}. Build process might be incomplete.`);
                }
                const schemaSql = fs.readFileSync(schemaPath, 'utf8');
                this.db.exec(schemaSql);
                logger.info('[DatabaseManager] Database schema initialized successfully.');
            } else {
                logger.info('[DatabaseManager] Database schema already initialized.');
            }
        } catch (error) {
            logger.error('[DatabaseManager] Failed to initialize database:', error);
            // Propagate the error to prevent the server from starting with a broken DB connection
            throw error;
        }
    }

    public getDb(): Db {
        if (!this.db) {
            // This should ideally not happen if constructor succeeded
            logger.error('[DatabaseManager] Database connection not available.');
            throw new Error('Database connection not available.');
        }
        return this.db;
    }

    // Optional: Add a close method for graceful shutdown
    public closeDb(): void {
        if (this.db) {
            this.db.close();
            logger.info('[DatabaseManager] Database connection closed.');
        }
    }
}
