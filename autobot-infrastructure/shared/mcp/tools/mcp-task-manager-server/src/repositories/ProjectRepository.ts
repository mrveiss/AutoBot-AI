import { Database as Db } from 'better-sqlite3';
import { logger } from '../utils/logger.js'; // Assuming logger exists

export interface ProjectData {
    project_id: string;
    name: string;
    created_at: string; // ISO8601 format
}

export class ProjectRepository {
    private db: Db;

    // Pass the database connection instance
    constructor(db: Db) {
        this.db = db;
    }

    /**
     * Creates a new project record in the database.
     * @param project - The project data to insert.
     * @throws {Error} If the database operation fails.
     */
    public create(project: ProjectData): void {
        const sql = `
            INSERT INTO projects (project_id, name, created_at)
            VALUES (@project_id, @name, @created_at)
        `;
        try {
            const stmt = this.db.prepare(sql);
            const info = stmt.run(project);
            logger.info(`[ProjectRepository] Created project ${project.project_id}, changes: ${info.changes}`);
        } catch (error) {
            logger.error(`[ProjectRepository] Failed to create project ${project.project_id}:`, error);
            // Re-throw the error to be handled by the service layer
            throw error;
        }
    }

    /**
     * Finds a project by its ID.
     * @param projectId - The ID of the project to find.
     * @returns The project data if found, otherwise undefined.
     */
    public findById(projectId: string): ProjectData | undefined {
        const sql = `SELECT project_id, name, created_at FROM projects WHERE project_id = ?`;
        try {
            const stmt = this.db.prepare(sql);
            const project = stmt.get(projectId) as ProjectData | undefined;
            return project;
        } catch (error) {
            logger.error(`[ProjectRepository] Failed to find project ${projectId}:`, error);
            throw error; // Re-throw
        }
    }

    /**
     * Deletes a project by its ID.
     * Relies on ON DELETE CASCADE in the schema to remove associated tasks/dependencies.
     * @param projectId - The ID of the project to delete.
     * @returns The number of projects deleted (0 or 1).
     * @throws {Error} If the database operation fails.
     */
    public deleteProject(projectId: string): number {
        const sql = `DELETE FROM projects WHERE project_id = ?`;
        try {
            const stmt = this.db.prepare(sql);
            const info = stmt.run(projectId);
            logger.info(`[ProjectRepository] Attempted to delete project ${projectId}. Rows affected: ${info.changes}`);
            // Cascade delete handles tasks/dependencies in the background via schema definition.
            return info.changes;
        } catch (error) {
            logger.error(`[ProjectRepository] Failed to delete project ${projectId}:`, error);
            throw error; // Re-throw
        }
    }

    // Add other methods as needed (e.g., update, list)
}
