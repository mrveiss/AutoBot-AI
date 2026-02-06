import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { McpError, ErrorCode } from "@modelcontextprotocol/sdk/types.js";
import { TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS, ExpandTaskArgs } from "./expandTaskParams.js";
import { TaskService } from "../services/TaskService.js";
import { logger } from '../utils/logger.js';
import { NotFoundError, ConflictError } from "../utils/errors.js"; // Import specific errors

/**
 * Registers the expandTask tool with the MCP server.
 *
 * @param server - The McpServer instance.
 * @param taskService - An instance of the TaskService.
 */
export const expandTaskTool = (server: McpServer, taskService: TaskService): void => {

    const processRequest = async (args: ExpandTaskArgs) => {
        logger.info(`[${TOOL_NAME}] Received request with args:`, args);
        try {
            // Call the service method to expand the task
            const updatedParentTask = await taskService.expandTask({
                project_id: args.project_id,
                task_id: args.task_id,
                subtask_descriptions: args.subtask_descriptions,
                force: args.force,
            });

            // Format the successful response
            logger.info(`[${TOOL_NAME}] Successfully expanded task ${args.task_id} in project ${args.project_id}`);
            return {
                content: [{
                    type: "text" as const,
                    // Return the updated parent task details, including new subtasks
                    text: JSON.stringify(updatedParentTask)
                }]
            };
        } catch (error: unknown) {
            // Handle potential errors
            logger.error(`[${TOOL_NAME}] Error processing request:`, error);

            if (error instanceof NotFoundError) {
                // Project or parent task not found
                throw new McpError(ErrorCode.InvalidParams, error.message);
            } else if (error instanceof ConflictError) {
                // Subtasks exist and force=false - map to InvalidParams as the request is invalid without force=true
                throw new McpError(ErrorCode.InvalidParams, error.message);
            } else {
                // Generic internal error
                const message = error instanceof Error ? error.message : 'An unknown error occurred while expanding the task.';
                throw new McpError(ErrorCode.InternalError, message);
            }
        }
    };

    // Register the tool with the server
    server.tool(TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS.shape, processRequest);

    logger.info(`[${TOOL_NAME}] Tool registered successfully.`);
};
