import { z } from 'zod';
import { TaskPriority, TaskStatus } from '../types/taskTypes.js'; // Import shared types

export const TOOL_NAME = "updateTask";

export const TOOL_DESCRIPTION = `
Updates specific details of an existing task within a project.
Requires the project ID and task ID. Allows updating description, priority, and/or dependencies.
At least one optional field (description, priority, dependencies) must be provided.
Returns the full details of the updated task upon success.
`;

// Define the possible priority values based on the shared type
const priorities: [TaskPriority, ...TaskPriority[]] = ['high', 'medium', 'low'];

// Base Zod schema without refinement - needed for server.tool registration
export const UPDATE_TASK_BASE_SCHEMA = z.object({
    project_id: z.string()
        .uuid("The project_id must be a valid UUID.")
        .describe("The unique identifier (UUID) of the project containing the task to update. This project must exist."), // Required, UUID format

    task_id: z.string()
        .uuid("The task_id must be a valid UUID.") // Assuming task IDs are UUIDs for consistency
        .describe("The unique identifier (UUID) of the task to update. This task must exist within the specified project."), // Required, UUID format

    description: z.string()
        .min(1, "Description cannot be empty if provided.")
        .max(1024, "Description cannot exceed 1024 characters.")
        .optional()
        .describe("Optional. The new textual description for the task (1-1024 characters)."), // Optional, string, limits

    priority: z.enum(priorities)
        .optional()
        .describe("Optional. The new priority level for the task ('high', 'medium', or 'low')."), // Optional, enum

    dependencies: z.array(
            z.string()
                .uuid("Each dependency task ID must be a valid UUID.")
                .describe("A task ID (UUID) that this task should depend on.")
        )
        .max(50, "A task cannot have more than 50 dependencies.")
        .optional()
        .describe("Optional. The complete list of task IDs (UUIDs) that this task depends on. Replaces the existing list entirely. Max 50 dependencies."), // Optional, array of UUID strings, limit
});

// Refined schema for validation and type inference
export const TOOL_PARAMS = UPDATE_TASK_BASE_SCHEMA.refine(
    data => data.description !== undefined || data.priority !== undefined || data.dependencies !== undefined, {
        message: "At least one field to update (description, priority, or dependencies) must be provided.",
        // path: [], // No specific path, applies to the object
    }
);

// Define the expected type for arguments based on the *refined* Zod schema
export type UpdateTaskArgs = z.infer<typeof TOOL_PARAMS>;
