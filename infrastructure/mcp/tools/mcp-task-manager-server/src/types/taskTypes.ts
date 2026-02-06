/**
 * Represents the possible status values for a task.
 * Using string literal union as per .clinerules (no enums).
 */
export type TaskStatus = 'todo' | 'in-progress' | 'review' | 'done';

/**
 * Represents the possible priority levels for a task.
 * Using string literal union as per .clinerules (no enums).
 */
export type TaskPriority = 'high' | 'medium' | 'low';

/**
 * Interface representing a Task object as returned by the API.
 */
export interface Task {
    task_id: string; // UUID format
    project_id: string; // UUID format
    parent_task_id: string | null; // UUID format or null
    description: string;
    status: TaskStatus;
    priority: TaskPriority;
    created_at: string; // ISO8601 format
    updated_at: string; // ISO8601 format
    dependencies?: string[]; // Array of task_ids this task depends on
    subtasks?: Task[]; // Array of subtasks (populated if requested, e.g., listTasks with include_subtasks=true)
}

/**
 * Interface representing the payload for updating a task (FR-011).
 * All fields are optional, but at least one must be provided for an update.
 */
export interface TaskUpdatePayload {
    description?: string;
    priority?: TaskPriority;
    dependencies?: string[]; // Represents the complete new list of dependencies
}

/**
 * Interface representing the structure of a Task as stored in the database.
 * May differ slightly from the API representation (e.g., no nested subtasks/dependencies).
 */
export interface TaskDbObject {
    task_id: string;
    project_id: string;
    parent_task_id: string | null;
    description: string;
    status: TaskStatus;
    priority: TaskPriority;
    created_at: string;
    updated_at: string;
}

/**
 * Interface representing a record in the task_dependencies table.
 */
export interface TaskDependencyDbObject {
    task_id: string;
    depends_on_task_id: string;
}
