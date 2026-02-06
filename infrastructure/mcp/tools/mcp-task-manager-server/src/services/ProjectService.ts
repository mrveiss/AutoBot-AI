import { v4 as uuidv4 } from 'uuid';
import { Database as Db } from 'better-sqlite3'; // Import Db type
import { ProjectRepository, ProjectData } from '../repositories/ProjectRepository.js';
import { TaskRepository, TaskData, DependencyData } from '../repositories/TaskRepository.js';
import { logger } from '../utils/logger.js';
import { NotFoundError, ValidationError, ConflictError } from '../utils/errors.js'; // Import errors

// Define structure for the export/import JSON
interface ExportTask extends TaskData {
    dependencies: string[]; // List of task IDs this task depends on
    subtasks: ExportTask[]; // Nested subtasks
}

interface ExportData {
    project_metadata: ProjectData;
    tasks: ExportTask[]; // Root tasks
}


export class ProjectService {
    private projectRepository: ProjectRepository;
    private taskRepository: TaskRepository;
    private db: Db; // Add db instance

    constructor(
        db: Db, // Inject Db instance
        projectRepository: ProjectRepository,
        taskRepository: TaskRepository
    ) {
        this.db = db; // Store db instance
        this.projectRepository = projectRepository;
        this.taskRepository = taskRepository;
    }

    /**
     * Creates a new project.
     */
    public async createProject(projectName?: string): Promise<ProjectData> {
        const projectId = uuidv4();
        const now = new Date().toISOString();
        const finalProjectName = projectName?.trim() || `New Project ${now}`;
        const newProject: ProjectData = {
            project_id: projectId,
            name: finalProjectName,
            created_at: now,
        };
        logger.info(`[ProjectService] Attempting to create project: ${projectId} with name "${finalProjectName}"`);
        try {
            this.projectRepository.create(newProject);
            logger.info(`[ProjectService] Successfully created project: ${projectId}`);
            return newProject;
        } catch (error) {
            logger.error(`[ProjectService] Error creating project ${projectId}:`, error);
            throw error;
        }
    }

    /**
     * Retrieves a project by its ID.
     */
    public async getProjectById(projectId: string): Promise<ProjectData | undefined> {
        logger.info(`[ProjectService] Attempting to find project: ${projectId}`);
        try {
            const project = this.projectRepository.findById(projectId);
            if (project) {
                logger.info(`[ProjectService] Found project: ${projectId}`);
            } else {
                logger.warn(`[ProjectService] Project not found: ${projectId}`);
            }
            return project;
        } catch (error) {
            logger.error(`[ProjectService] Error finding project ${projectId}:`, error);
            throw error;
        }
    }

    /**
     * Exports all data for a given project as a JSON string.
     */
    public async exportProject(projectId: string): Promise<string> {
        logger.info(`[ProjectService] Attempting to export project: ${projectId}`);
        const projectMetadata = this.projectRepository.findById(projectId);
        if (!projectMetadata) {
            logger.warn(`[ProjectService] Project not found for export: ${projectId}`);
            throw new NotFoundError(`Project with ID ${projectId} not found.`);
        }

        try {
            const allTasks = this.taskRepository.findAllTasksForProject(projectId);
            const allDependencies = this.taskRepository.findAllDependenciesForProject(projectId);

            const taskMap: Map<string, ExportTask> = new Map();
            const rootTasks: ExportTask[] = [];
            const dependencyMap: Map<string, string[]> = new Map();

            for (const dep of allDependencies) {
                if (!dependencyMap.has(dep.task_id)) {
                    dependencyMap.set(dep.task_id, []);
                }
                dependencyMap.get(dep.task_id)!.push(dep.depends_on_task_id);
            }

            for (const task of allTasks) {
                taskMap.set(task.task_id, {
                    ...task,
                    dependencies: dependencyMap.get(task.task_id) || [],
                    subtasks: [],
                });
            }

            for (const task of allTasks) {
                const exportTask = taskMap.get(task.task_id)!;
                if (task.parent_task_id && taskMap.has(task.parent_task_id)) {
                    const parent = taskMap.get(task.parent_task_id)!;
                    if (!parent.subtasks) parent.subtasks = [];
                    parent.subtasks.push(exportTask);
                } else if (!task.parent_task_id) {
                    rootTasks.push(exportTask);
                }
            }

            const exportData: ExportData = {
                project_metadata: projectMetadata,
                tasks: rootTasks,
            };

            const jsonString = JSON.stringify(exportData, null, 2);
            logger.info(`[ProjectService] Successfully prepared export data for project ${projectId}`);
            return jsonString;

        } catch (error) {
            logger.error(`[ProjectService] Error exporting project ${projectId}:`, error);
            throw error;
        }
    }

    /**
     * Imports project data from a JSON string, creating a new project.
     */
    public async importProject(projectDataString: string, newProjectName?: string): Promise<{ project_id: string }> {
        logger.info(`[ProjectService] Attempting to import project...`);
        let importData: ExportData;
        try {
            if (projectDataString.length > 10 * 1024 * 1024) { // Example 10MB limit
                throw new ValidationError('Input data exceeds size limit (e.g., 10MB).');
            }
            importData = JSON.parse(projectDataString);
            // TODO: Implement rigorous schema validation (Zod?)
            if (!importData || !importData.project_metadata || !Array.isArray(importData.tasks)) {
                throw new ValidationError('Invalid import data structure: Missing required fields.');
            }
            logger.debug(`[ProjectService] Successfully parsed import data.`);
        } catch (error) {
            logger.error('[ProjectService] Failed to parse or validate import JSON:', error);
            if (error instanceof SyntaxError) {
                throw new ValidationError(`Invalid JSON format: ${error.message}`);
            }
            throw new ValidationError(`Invalid import data: ${error instanceof Error ? error.message : 'Unknown validation error'}`);
        }

        const importTransaction = this.db.transaction(() => {
            const newProjectId = uuidv4();
            const now = new Date().toISOString();
            const finalProjectName = newProjectName?.trim() || `${importData.project_metadata.name} (Imported ${now})`;
            const newProject: ProjectData = {
                project_id: newProjectId,
                name: finalProjectName.substring(0, 255),
                created_at: now,
            };
            this.projectRepository.create(newProject);
            logger.info(`[ProjectService] Created new project ${newProjectId} for import.`);

            const idMap = new Map<string, string>();
            const processTask = (task: ExportTask, parentDbId: string | null) => {
                const newTaskId = uuidv4();
                idMap.set(task.task_id, newTaskId);
                const newTaskData: TaskData = {
                    task_id: newTaskId,
                    project_id: newProjectId,
                    parent_task_id: parentDbId,
                    description: task.description,
                    status: task.status,
                    priority: task.priority,
                    created_at: task.created_at,
                    updated_at: task.updated_at,
                };
                this.taskRepository.create(newTaskData, []); // Create task first
                if (task.subtasks && task.subtasks.length > 0) {
                    task.subtasks.forEach(subtask => processTask(subtask, newTaskId));
                }
            };
            importData.tasks.forEach(rootTask => processTask(rootTask, null));
            logger.info(`[ProjectService] Processed ${idMap.size} tasks for import.`);

            const insertDependencyStmt = this.db.prepare(`
                INSERT INTO task_dependencies (task_id, depends_on_task_id)
                VALUES (?, ?) ON CONFLICT DO NOTHING
            `);
            let depCount = 0;
            const processDeps = (task: ExportTask) => {
                const newTaskId = idMap.get(task.task_id);
                if (newTaskId && task.dependencies && task.dependencies.length > 0) {
                    for (const oldDepId of task.dependencies) {
                        const newDepId = idMap.get(oldDepId);
                        if (newDepId) {
                            insertDependencyStmt.run(newTaskId, newDepId);
                            depCount++;
                        } else {
                            logger.warn(`[ProjectService] Dependency task ID ${oldDepId} not found in import map for task ${task.task_id}. Skipping dependency.`);
                        }
                    }
                }
                if (task.subtasks && task.subtasks.length > 0) {
                    task.subtasks.forEach(processDeps);
                }
            };
            importData.tasks.forEach(processDeps);
            logger.info(`[ProjectService] Processed ${depCount} dependencies for import.`);

            return { project_id: newProjectId };
        });

        try {
            const result = importTransaction();
            logger.info(`[ProjectService] Successfully imported project. New project ID: ${result.project_id}`);
            return result;
        } catch (error) {
            logger.error(`[ProjectService] Error during import transaction:`, error);
            if (error instanceof NotFoundError || error instanceof ValidationError || error instanceof ConflictError) {
                throw error;
            }
            throw new Error(`Failed to import project: ${error instanceof Error ? error.message : 'Unknown database error'}`);
        }
    }

    /**
     * Deletes a project and all its associated data (tasks, dependencies).
     * @param projectId - The ID of the project to delete.
     * @returns A boolean indicating success (true if deleted, false if not found initially).
     * @throws {NotFoundError} If the project is not found.
     * @throws {Error} If the database operation fails.
     */
    public async deleteProject(projectId: string): Promise<boolean> {
        logger.info(`[ProjectService] Attempting to delete project: ${projectId}`);

        // 1. Validate Project Existence *before* attempting delete
        const projectExists = this.projectRepository.findById(projectId);
        if (!projectExists) {
            logger.warn(`[ProjectService] Project not found for deletion: ${projectId}`);
            throw new NotFoundError(`Project with ID ${projectId} not found.`);
        }

        // 2. Call Repository delete method
        try {
            // The repository method handles the actual DELETE operation on the projects table.
            // Cascade delete defined in the schema handles tasks and dependencies.
            const deletedCount = this.projectRepository.deleteProject(projectId);

            if (deletedCount !== 1) {
                // This shouldn't happen if findById succeeded, but log a warning if it does.
                logger.warn(`[ProjectService] Expected to delete 1 project, but repository reported ${deletedCount} deletions for project ${projectId}.`);
                // Still return true as the project is gone, but log indicates potential issue.
            }

            logger.info(`[ProjectService] Successfully deleted project ${projectId} and associated data.`);
            return true; // Indicate success

        } catch (error) {
            logger.error(`[ProjectService] Error deleting project ${projectId}:`, error);
            throw error; // Re-throw database or other errors
        }
    }
}
