import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { McpError, ErrorCode } from "@modelcontextprotocol/sdk/types.js";
// Import the base schema shape for registration and the refined schema for validation/types
import { TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS, UPDATE_TASK_BASE_SCHEMA, UpdateTaskArgs } from "./updateTaskParams.js";
import { TaskService, FullTaskData } from "../services/TaskService.js"; // Assuming TaskService is exported from index
import { logger } from '../utils/logger.js';
import { NotFoundError, ValidationError } from "../utils/errors.js"; // Import custom errors

/**
 * Registers the updateTask tool with the MCP server.
 *
 * @param server - The McpServer instance.
 * @param taskService - An instance of the TaskService.
 */
export const updateTaskTool = (server: McpServer, taskService: TaskService): void => {

    const processRequest = async (args: UpdateTaskArgs): Promise<{ content: { type: 'text', text: string }[] }> => {
        logger.info(`[${TOOL_NAME}] Received request with args:`, { ...args, dependencies: args.dependencies ? `[${args.dependencies.length} items]` : undefined }); // Avoid logging potentially large arrays
        try {
            // Call the service method to update the task
            // The service method now returns FullTaskData
            const updatedTask: FullTaskData = await taskService.updateTask({
                project_id: args.project_id,
                task_id: args.task_id,
                description: args.description,
                priority: args.priority,
                dependencies: args.dependencies,
            });

            // Format the successful response
            logger.info(`[${TOOL_NAME}] Successfully updated task ${args.task_id} in project ${args.project_id}`);
            return {
                content: [{
                    type: "text" as const,
                    text: JSON.stringify(updatedTask) // Return the full updated task details
                }]
            };
        } catch (error: unknown) {
            // Handle potential errors according to systemPatterns.md mapping
            logger.error(`[${TOOL_NAME}] Error processing request:`, error);

            if (error instanceof ValidationError) {
                // Validation error from service (e.g., no fields provided, invalid deps)
                 throw new McpError(ErrorCode.InvalidParams, error.message);
            } else if (error instanceof NotFoundError) {
                // Project or task not found - Map to InvalidParams as per SDK limitations/convention
                throw new McpError(ErrorCode.InvalidParams, error.message);
            } else {
                // Generic internal error
                const message = error instanceof Error ? error.message : 'An unknown error occurred while updating the task.';
                throw new McpError(ErrorCode.InternalError, message);
            }
        }
    };

    // Register the tool with the server using the base schema's shape
    server.tool(TOOL_NAME, TOOL_DESCRIPTION, UPDATE_TASK_BASE_SCHEMA.shape, processRequest);

    logger.info(`[${TOOL_NAME}] Tool registered successfully.`);
};
