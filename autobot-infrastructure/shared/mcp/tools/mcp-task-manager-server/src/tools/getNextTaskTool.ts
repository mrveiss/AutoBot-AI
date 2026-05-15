import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { McpError, ErrorCode } from "@modelcontextprotocol/sdk/types.js";
import { TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS, GetNextTaskArgs } from "./getNextTaskParams.js";
import { TaskService } from "../services/TaskService.js";
import { logger } from '../utils/logger.js';
import { NotFoundError } from "../utils/errors.js";

/**
 * Registers the getNextTask tool with the MCP server.
 *
 * @param server - The McpServer instance.
 * @param taskService - An instance of the TaskService.
 */
export const getNextTaskTool = (server: McpServer, taskService: TaskService): void => {

    const processRequest = async (args: GetNextTaskArgs) => {
        logger.info(`[${TOOL_NAME}] Received request with args:`, args);
        try {
            // Call the service method to get the next task
            const nextTask = await taskService.getNextTask(args.project_id);

            // Format the successful response
            if (nextTask) {
                logger.info(`[${TOOL_NAME}] Next task found: ${nextTask.task_id} in project ${args.project_id}`);
            } else {
                logger.info(`[${TOOL_NAME}] No ready task found for project ${args.project_id}`);
            }

            return {
                content: [{
                    type: "text" as const,
                    // Return the full task object or null
                    text: JSON.stringify(nextTask)
                }]
            };
        } catch (error: unknown) {
            // Handle potential errors
            logger.error(`[${TOOL_NAME}] Error processing request:`, error);

            if (error instanceof NotFoundError) {
                // Project not found
                throw new McpError(ErrorCode.InvalidParams, error.message);
            } else {
                // Generic internal error
                const message = error instanceof Error ? error.message : 'An unknown error occurred while getting the next task.';
                throw new McpError(ErrorCode.InternalError, message);
            }
        }
    };

    // Register the tool with the server
    server.tool(TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS.shape, processRequest);

    logger.info(`[${TOOL_NAME}] Tool registered successfully.`);
};
