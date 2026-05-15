import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { McpError, ErrorCode } from "@modelcontextprotocol/sdk/types.js";
import { TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS, ShowTaskArgs } from "./showTaskParams.js";
import { TaskService } from "../services/TaskService.js";
import { logger } from '../utils/logger.js';
import { NotFoundError } from "../utils/errors.js";

/**
 * Registers the showTask tool with the MCP server.
 *
 * @param server - The McpServer instance.
 * @param taskService - An instance of the TaskService.
 */
export const showTaskTool = (server: McpServer, taskService: TaskService): void => {

    const processRequest = async (args: ShowTaskArgs) => {
        logger.info(`[${TOOL_NAME}] Received request with args:`, args);
        try {
            // Call the service method to get the task details
            const task = await taskService.getTaskById(args.project_id, args.task_id);

            // Format the successful response
            logger.info(`[${TOOL_NAME}] Found task ${args.task_id} in project ${args.project_id}`);
            return {
                content: [{
                    type: "text" as const,
                    text: JSON.stringify(task) // Return the full task object
                }]
            };
        } catch (error: unknown) {
            // Handle potential errors
            logger.error(`[${TOOL_NAME}] Error processing request:`, error);

            if (error instanceof NotFoundError) {
                // Specific error if the project or task wasn't found
                // Map to InvalidParams as the provided ID(s) are invalid in this context
                throw new McpError(ErrorCode.InvalidParams, error.message);
            } else {
                // Generic internal error
                const message = error instanceof Error ? error.message : 'An unknown error occurred while retrieving the task.';
                throw new McpError(ErrorCode.InternalError, message);
            }
        }
    };

    // Register the tool with the server
    server.tool(TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS.shape, processRequest);

    logger.info(`[${TOOL_NAME}] Tool registered successfully.`);
};
