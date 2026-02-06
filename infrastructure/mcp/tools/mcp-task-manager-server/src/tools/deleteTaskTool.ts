import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { McpError, ErrorCode } from "@modelcontextprotocol/sdk/types.js";
import { TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS, DeleteTaskArgs } from "./deleteTaskParams.js";
import { TaskService } from "../services/TaskService.js"; // Assuming TaskService is exported from index
import { logger } from '../utils/logger.js';
import { NotFoundError } from "../utils/errors.js"; // Import custom errors

/**
 * Registers the deleteTask tool with the MCP server.
 *
 * @param server - The McpServer instance.
 * @param taskService - An instance of the TaskService.
 */
export const deleteTaskTool = (server: McpServer, taskService: TaskService): void => {

    const processRequest = async (args: DeleteTaskArgs): Promise<{ content: { type: 'text', text: string }[] }> => {
        logger.info(`[${TOOL_NAME}] Received request to delete ${args.task_ids.length} tasks from project ${args.project_id}`);
        try {
            // Call the service method to delete the tasks
            const deletedCount = await taskService.deleteTasks(args.project_id, args.task_ids);

            // Format the successful response
            logger.info(`[${TOOL_NAME}] Successfully deleted ${deletedCount} tasks from project ${args.project_id}`);
            return {
                content: [{
                    type: "text" as const,
                    text: JSON.stringify({ success: true, deleted_count: deletedCount })
                }]
            };
        } catch (error: unknown) {
            // Handle potential errors according to systemPatterns.md mapping
            logger.error(`[${TOOL_NAME}] Error processing request:`, error);

            if (error instanceof NotFoundError) {
                // Project or one/more tasks not found - Map to InvalidParams as per convention
                throw new McpError(ErrorCode.InvalidParams, error.message);
            } else {
                // Generic internal error
                const message = error instanceof Error ? error.message : 'An unknown error occurred while deleting tasks.';
                throw new McpError(ErrorCode.InternalError, message);
            }
        }
    };

    // Register the tool with the server
    server.tool(TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS.shape, processRequest); // Using .shape as this schema doesn't use .refine()

    logger.info(`[${TOOL_NAME}] Tool registered successfully.`);
};
