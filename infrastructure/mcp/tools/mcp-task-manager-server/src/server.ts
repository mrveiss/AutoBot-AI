import { createServer } from "./createServer.js";
import { logger } from "./utils/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
// import { WebSocketServerTransport } from "@modelcontextprotocol/sdk/server/ws.js"; // Example for WebSocket

const main = async () => {
    try {
        const server = createServer();
        logger.info("Starting MCP server");

        // Choose your transport
        const transport = new StdioServerTransport();
        // const transport = new WebSocketServerTransport({ port: 8080 }); // Example

        logger.info("Connecting transport", { transport: transport.constructor.name });
        await server.connect(transport);

        logger.info("MCP Server connected and listening");

    } catch (error) {
        logger.error("Failed to start server", error);
        process.exit(1); // Exit if server fails to start
    }
};

main();
