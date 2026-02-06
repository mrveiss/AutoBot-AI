import { Database as Db, Statement } from 'better-sqlite3';
import { logger } from '../utils/logger.js';

// Define the structure for task data in the database
// Aligning with schema.sql and feature specs
export interface TaskData {
    task_id: string; // UUID
    project_id: string; // UUID
    parent_task_id?: string | null; // UUID or null
    description: string;
    status: 'todo' | 'in-progress' | 'review' | 'done';
    priority: 'high' | 'medium' | 'low';
    created_at: string; // ISO8601
    updated_at: string; // ISO8601
}

// Define the structure for dependency data
export interface DependencyData {
    task_id: string;
    depends_on_task_id: string;
}

export class TaskRepository {
    private db: Db;
    private insertTaskStmt: Statement | null = null;
    private insertDependencyStmt: Statement | null = null;

    constructor(db: Db) {
        this.db = db;
        // Prepare statements for efficiency
        this.prepareStatements();
    }

    private prepareStatements(): void {
        try {
            this.insertTaskStmt = this.db.prepare(`
                INSERT INTO tasks (
                    task_id, project_id, parent_task_id, description,
                    status, priority, created_at, updated_at
                ) VALUES (
                    @task_id, @project_id, @parent_task_id, @description,
                    @status, @priority, @created_at, @updated_at
                )
            `);

            this.insertDependencyStmt = this.db.prepare(`
                INSERT INTO task_dependencies (task_id, depends_on_task_id)
                VALUES (@task_id, @depends_on_task_id)
                ON CONFLICT(task_id, depends_on_task_id) DO NOTHING -- Ignore if dependency already exists
            `);
        } catch (error) {
            logger.error('[TaskRepository] Failed to prepare statements:', error);
            // Handle error appropriately, maybe re-throw or set a flag
            throw error;
        }
    }

    /**
     * Creates a new task and optionally its dependencies in the database.
     * Uses a transaction to ensure atomicity.
     * @param task - The core task data to insert.
     * @param dependencies - An array of dependency task IDs for this task.
     * @throws {Error} If the database operation fails.
     */
    public create(task: TaskData, dependencies: string[] = []): void {
        if (!this.insertTaskStmt || !this.insertDependencyStmt) {
            logger.error('[TaskRepository] Statements not prepared. Cannot create task.');
            throw new Error('TaskRepository statements not initialized.');
        }

        // Use a transaction for atomicity
        const transaction = this.db.transaction((taskData: TaskData, deps: string[]) => {
            // Insert the main task
            const taskInfo = this.insertTaskStmt!.run(taskData);
            if (taskInfo.changes !== 1) {
                throw new Error(`Failed to insert task ${taskData.task_id}. Changes: ${taskInfo.changes}`);
            }

            // Insert dependencies
            for (const depId of deps) {
                const depData: DependencyData = {
                    task_id: taskData.task_id,
                    depends_on_task_id: depId,
                };
                const depInfo = this.insertDependencyStmt!.run(depData);
                // We don't strictly need to check changes here due to ON CONFLICT DO NOTHING
            }
            return taskInfo.changes; // Indicate success
        });

        try {
            transaction(task, dependencies);
            logger.info(`[TaskRepository] Created task ${task.task_id} with ${dependencies.length} dependencies.`);
        } catch (error) {
            logger.error(`[TaskRepository] Failed to create task ${task.task_id} transaction:`, error);
            throw error; // Re-throw to be handled by the service layer
        }
    }

    /**
     * Finds tasks by project ID, optionally filtering by status.
     * Does not handle subtask nesting directly in this query for V1 simplicity.
     * @param projectId - The ID of the project.
     * @param statusFilter - Optional status to filter by.
     * @returns An array of matching task data.
     */
    public findByProjectId(projectId: string, statusFilter?: TaskData['status']): TaskData[] {
        let sql = `
            SELECT task_id, project_id, parent_task_id, description, status, priority, created_at, updated_at
            FROM tasks
            WHERE project_id = ?
        `;
        const params: (string | null)[] = [projectId];

        if (statusFilter) {
            sql += ` AND status = ?`;
            params.push(statusFilter);
        }

        // For simplicity in V1, we only fetch top-level tasks or all tasks depending on include_subtasks strategy in service
        // If we only wanted top-level: sql += ` AND parent_task_id IS NULL`;
        // If fetching all and structuring in service, this query is fine.

        sql += ` ORDER BY created_at ASC`; // Default sort order

        try {
            const stmt = this.db.prepare(sql);
            const tasks = stmt.all(...params) as TaskData[];
            logger.debug(`[TaskRepository] Found ${tasks.length} tasks for project ${projectId} with status filter '${statusFilter || 'none'}'`);
            return tasks;
        } catch (error) {
            logger.error(`[TaskRepository] Failed to find tasks for project ${projectId}:`, error);
            throw error; // Re-throw
        }
    }

    /**
     * Finds a single task by its ID and project ID.
     * @param projectId - The project ID.
     * @param taskId - The task ID.
     * @returns The task data if found, otherwise undefined.
     */
    public findById(projectId: string, taskId: string): TaskData | undefined {
        const sql = `
            SELECT task_id, project_id, parent_task_id, description, status, priority, created_at, updated_at
            FROM tasks
            WHERE project_id = ? AND task_id = ?
        `;
        try {
            const stmt = this.db.prepare(sql);
            const task = stmt.get(projectId, taskId) as TaskData | undefined;
            logger.debug(`[TaskRepository] Found task ${taskId} in project ${projectId}: ${!!task}`);
            return task;
        } catch (error) {
            logger.error(`[TaskRepository] Failed to find task ${taskId} in project ${projectId}:`, error);
            throw error;
        }
    }

    /**
     * Finds the direct subtasks for a given parent task ID.
     * @param parentTaskId - The ID of the parent task.
     * @returns An array of direct subtask data.
     */
    public findSubtasks(parentTaskId: string): TaskData[] {
        const sql = `
            SELECT task_id, project_id, parent_task_id, description, status, priority, created_at, updated_at
            FROM tasks
            WHERE parent_task_id = ?
            ORDER BY created_at ASC
        `;
        try {
            const stmt = this.db.prepare(sql);
            const subtasks = stmt.all(parentTaskId) as TaskData[];
            logger.debug(`[TaskRepository] Found ${subtasks.length} subtasks for parent ${parentTaskId}`);
            return subtasks;
        } catch (error) {
            logger.error(`[TaskRepository] Failed to find subtasks for parent ${parentTaskId}:`, error);
            throw error;
        }
    }

    /**
     * Finds the IDs of tasks that the given task depends on.
     * @param taskId - The ID of the task whose dependencies are needed.
     * @returns An array of task IDs that this task depends on.
     */
    public findDependencies(taskId: string): string[] {
        const sql = `SELECT depends_on_task_id FROM task_dependencies WHERE task_id = ?`;
        try {
            const stmt = this.db.prepare(sql);
            // Ensure result is always an array of strings
            const results = stmt.all(taskId) as { depends_on_task_id: string }[];
            const dependencyIds = results.map(row => row.depends_on_task_id);
            logger.debug(`[TaskRepository] Found ${dependencyIds.length} dependencies for task ${taskId}`);
            return dependencyIds;
        } catch (error) {
            logger.error(`[TaskRepository] Failed to find dependencies for task ${taskId}:`, error);
            throw error;
        }
    }


    /**
     * Updates the status and updated_at timestamp for a list of tasks within a project.
     * Assumes task existence has already been verified.
     * @param projectId - The project ID.
     * @param taskIds - An array of task IDs to update.
     * @param status - The new status to set.
     * @param timestamp - The ISO8601 timestamp for updated_at.
     * @returns The number of rows affected by the update.
     * @throws {Error} If the database operation fails.
     */
    public updateStatus(projectId: string, taskIds: string[], status: TaskData['status'], timestamp: string): number {
        if (taskIds.length === 0) {
            return 0;
        }

        // Create placeholders for the IN clause
        const placeholders = taskIds.map(() => '?').join(',');
        const sql = `
            UPDATE tasks
            SET status = ?, updated_at = ?
            WHERE project_id = ? AND task_id IN (${placeholders})
        `;
        const params = [status, timestamp, projectId, ...taskIds];

        try {
            const stmt = this.db.prepare(sql);
            const info = stmt.run(...params);
            logger.info(`[TaskRepository] Updated status for ${info.changes} tasks in project ${projectId} to ${status}.`);
            return info.changes;
        } catch (error) {
            logger.error(`[TaskRepository] Failed to update status for tasks in project ${projectId}:`, error);
            throw error;
        }
    }

    /**
     * Checks if all provided task IDs exist within the specified project.
     * @param projectId - The project ID.
     * @param taskIds - An array of task IDs to check.
     * @returns An object indicating if all exist and a list of missing IDs if not.
     * @throws {Error} If the database operation fails.
     */
    public checkTasksExist(projectId: string, taskIds: string[]): { allExist: boolean; missingIds: string[] } {
        if (taskIds.length === 0) {
            return { allExist: true, missingIds: [] };
        }

        const placeholders = taskIds.map(() => '?').join(',');
        const sql = `
            SELECT task_id FROM tasks
            WHERE project_id = ? AND task_id IN (${placeholders})
        `;
        const params = [projectId, ...taskIds];

        try {
            const stmt = this.db.prepare(sql);
            const foundTasks = stmt.all(...params) as { task_id: string }[];
            const foundIds = new Set(foundTasks.map(t => t.task_id));

            const missingIds = taskIds.filter(id => !foundIds.has(id));
            const allExist = missingIds.length === 0;

            if (!allExist) {
                logger.warn(`[TaskRepository] Missing tasks in project ${projectId}:`, missingIds);
            }
            return { allExist, missingIds };

        } catch (error) {
            logger.error(`[TaskRepository] Failed to check task existence in project ${projectId}:`, error);
            throw error;
        }
    }

    /**
     * Deletes all direct subtasks of a given parent task.
     * @param parentTaskId - The ID of the parent task whose subtasks should be deleted.
     * @returns The number of subtasks deleted.
     * @throws {Error} If the database operation fails.
     */
    public deleteSubtasks(parentTaskId: string): number {
        const sql = `DELETE FROM tasks WHERE parent_task_id = ?`;
        try {
            const stmt = this.db.prepare(sql);
            const info = stmt.run(parentTaskId);
            logger.info(`[TaskRepository] Deleted ${info.changes} subtasks for parent ${parentTaskId}.`);
            return info.changes;
        } catch (error) {
            logger.error(`[TaskRepository] Failed to delete subtasks for parent ${parentTaskId}:`, error);
            throw error;
        }
    }

    /**
     * Finds tasks that are ready to be worked on (status 'todo' and all dependencies 'done').
     * Orders them by priority ('high', 'medium', 'low') then creation date.
     * @param projectId - The project ID.
     * @returns An array of ready task data, ordered by priority and creation date.
     */
    public findReadyTasks(projectId: string): TaskData[] {
        // This query finds tasks in the project with status 'todo'
        // AND for which no dependency exists OR all existing dependencies have status 'done'.
        const sql = `
            SELECT t.task_id, t.project_id, t.parent_task_id, t.description, t.status, t.priority, t.created_at, t.updated_at
            FROM tasks t
            WHERE t.project_id = ? AND t.status = 'todo'
            AND NOT EXISTS (
                SELECT 1
                FROM task_dependencies td
                JOIN tasks dep_task ON td.depends_on_task_id = dep_task.task_id
                WHERE td.task_id = t.task_id AND dep_task.status != 'done'
            )
            ORDER BY
                CASE t.priority
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                    ELSE 4 -- Should not happen based on CHECK constraint
                END ASC,
                t.created_at ASC
        `;
        try {
            const stmt = this.db.prepare(sql);
            const tasks = stmt.all(projectId) as TaskData[];
            logger.debug(`[TaskRepository] Found ${tasks.length} ready tasks for project ${projectId}`);
            return tasks;
        } catch (error) {
            logger.error(`[TaskRepository] Failed to find ready tasks for project ${projectId}:`, error);
            throw error;
        }
    }

    /**
     * Finds ALL tasks for a given project ID, ordered by creation date.
     * @param projectId - The project ID.
     * @returns An array of all task data for the project.
     */
    public findAllTasksForProject(projectId: string): TaskData[] {
        const sql = `
            SELECT task_id, project_id, parent_task_id, description, status, priority, created_at, updated_at
            FROM tasks
            WHERE project_id = ?
            ORDER BY created_at ASC
        `;
        try {
            const stmt = this.db.prepare(sql);
            const tasks = stmt.all(projectId) as TaskData[];
            logger.debug(`[TaskRepository] Found all ${tasks.length} tasks for project ${projectId}`);
            return tasks;
        } catch (error) {
            logger.error(`[TaskRepository] Failed to find all tasks for project ${projectId}:`, error);
            throw error;
        }
    }

    /**
     * Finds ALL dependencies for tasks within a given project ID.
     * @param projectId - The project ID.
     * @returns An array of all dependency relationships for the project.
     */
    public findAllDependenciesForProject(projectId: string): DependencyData[] {
        // Select dependencies where the *dependent* task belongs to the project
        const sql = `
            SELECT td.task_id, td.depends_on_task_id
            FROM task_dependencies td
            JOIN tasks t ON td.task_id = t.task_id
            WHERE t.project_id = ?
        `;
        try {
            const stmt = this.db.prepare(sql);
            const dependencies = stmt.all(projectId) as DependencyData[];
            logger.debug(`[TaskRepository] Found ${dependencies.length} dependencies for project ${projectId}`);
            return dependencies;
        } catch (error) {
            logger.error(`[TaskRepository] Failed to find all dependencies for project ${projectId}:`, error);
            throw error;
        }
    }


    // --- Add other methods later ---
    /**
     * Updates a task's description, priority, and/or dependencies.
     * Handles dependency replacement atomically within a transaction.
     * @param projectId - The project ID.
     * @param taskId - The task ID to update.
     * @param updatePayload - Object containing optional fields to update.
     * @param timestamp - The ISO8601 timestamp for updated_at.
     * @returns The updated task data.
     * @throws {Error} If the task doesn't exist or the database operation fails.
     */
    public updateTask(
        projectId: string,
        taskId: string,
        updatePayload: { description?: string; priority?: TaskData['priority']; dependencies?: string[] },
        timestamp: string
    ): TaskData {

        const transaction = this.db.transaction(() => {
            const setClauses: string[] = [];
            const params: (string | null)[] = [];

            if (updatePayload.description !== undefined) {
                setClauses.push('description = ?');
                params.push(updatePayload.description);
            }
            if (updatePayload.priority !== undefined) {
                setClauses.push('priority = ?');
                params.push(updatePayload.priority);
            }

            // Always update the timestamp
            setClauses.push('updated_at = ?');
            params.push(timestamp);

            // If nothing else to update, we still update the timestamp
            if (setClauses.length === 1 && updatePayload.dependencies === undefined) {
                 logger.warn(`[TaskRepository] updateTask called for ${taskId} with no fields to update other than timestamp.`);
                 // Or potentially throw an error if this shouldn't happen based on service validation
            }

            // Update the main task table if there are fields to update
            let changes = 0;
            if (setClauses.length > 0) {
                const updateSql = `
                    UPDATE tasks
                    SET ${setClauses.join(', ')}
                    WHERE project_id = ? AND task_id = ?
                `;
                params.push(projectId, taskId);

                const updateStmt = this.db.prepare(updateSql);
                const info = updateStmt.run(...params);
                changes = info.changes;

                if (changes !== 1) {
                    // Check if the task actually exists before throwing generic error
                    const exists = this.findById(projectId, taskId);
                    if (!exists) {
                         throw new Error(`Task ${taskId} not found in project ${projectId}.`); // Will be caught and mapped later
                    } else {
                        throw new Error(`Failed to update task ${taskId}. Expected 1 change, got ${changes}.`);
                    }
                }
                logger.debug(`[TaskRepository] Updated task ${taskId} fields.`);
            }


            // Handle dependencies if provided (replaces existing)
            if (updatePayload.dependencies !== undefined) {
                if (!this.insertDependencyStmt) {
                    throw new Error('TaskRepository insertDependencyStmt not initialized.');
                }
                // 1. Delete existing dependencies for this task
                const deleteDepsStmt = this.db.prepare(`DELETE FROM task_dependencies WHERE task_id = ?`);
                const deleteInfo = deleteDepsStmt.run(taskId);
                logger.debug(`[TaskRepository] Deleted ${deleteInfo.changes} existing dependencies for task ${taskId}.`);

                // 2. Insert new dependencies
                const newDeps = updatePayload.dependencies;
                for (const depId of newDeps) {
                    const depData: DependencyData = {
                        task_id: taskId,
                        depends_on_task_id: depId,
                    };
                    // ON CONFLICT DO NOTHING handles duplicates or self-references if schema allows
                    this.insertDependencyStmt.run(depData);
                }
                logger.debug(`[TaskRepository] Inserted ${newDeps.length} new dependencies for task ${taskId}.`);
            }

            // Fetch and return the updated task data
            const updatedTask = this.findById(projectId, taskId);
            if (!updatedTask) {
                // Should not happen if update succeeded, but safety check
                throw new Error(`Failed to retrieve updated task ${taskId} after update.`);
            }
            return updatedTask;
        });

        try {
            const result = transaction();
            logger.info(`[TaskRepository] Successfully updated task ${taskId}.`);
            return result;
        } catch (error) {
            logger.error(`[TaskRepository] Failed transaction for updating task ${taskId}:`, error);
            throw error; // Re-throw to be handled by the service layer
        }
    }


    /**
     * Deletes multiple tasks by their IDs within a specific project.
     * Relies on ON DELETE CASCADE for subtasks and dependencies.
     * @param projectId - The project ID.
     * @param taskIds - An array of task IDs to delete.
     * @returns The number of tasks deleted.
     * @throws {Error} If the database operation fails.
     */
    public deleteTasks(projectId: string, taskIds: string[]): number {
        if (taskIds.length === 0) {
            return 0;
        }

        // Create placeholders for the IN clause
        const placeholders = taskIds.map(() => '?').join(',');
        const sql = `
            DELETE FROM tasks
            WHERE project_id = ? AND task_id IN (${placeholders})
        `;
        const params = [projectId, ...taskIds];

        try {
            const stmt = this.db.prepare(sql);
            const info = stmt.run(...params);
            logger.info(`[TaskRepository] Deleted ${info.changes} tasks from project ${projectId}.`);
            // Note: Cascade deletes for subtasks/dependencies happen automatically via schema.
            return info.changes;
        } catch (error) {
            logger.error(`[TaskRepository] Failed to delete tasks from project ${projectId}:`, error);
            throw error;
        }
    }


    // --- Add other methods later ---
    // deleteById(taskId: string): void;
}
