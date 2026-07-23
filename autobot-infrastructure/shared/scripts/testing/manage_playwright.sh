#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0

# Playwright Service Management Script for AutoBot
# Usage: ./manage_playwright.sh [start|stop|restart|status|logs]

ACTION=${1:-status}

case "$ACTION" in
    start)
        echo "🚀 Starting Playwright service..."

        # Check if docker-compose is available
        if command -v docker-compose &> /dev/null; then
            COMPOSE_CMD="docker-compose"
        elif command -v docker &> /dev/null && docker compose version &> /dev/null; then
            COMPOSE_CMD="docker compose"
        else
            echo "❌ Neither docker-compose nor docker compose is available."
            exit 1
        fi

        # Start the service
        $COMPOSE_CMD -f docker-compose.playwright.yml up -d

        # Wait for health check
        echo "⏳ Waiting for Playwright service to be ready..."
        for i in {1..30}; do
            if curl -sf http://localhost:3000/health > /dev/null 2>&1; then
                echo "✅ Playwright service is healthy and ready."
                exit 0
            fi
            echo "⏳ Waiting for Playwright service... (attempt $i/30)"
            sleep 2
        done

        echo "⚠️ Playwright service may not be fully ready. Check logs with: $0 logs"
        ;;

    stop)
        echo "🛑 Stopping Playwright service..."

        if command -v docker-compose &> /dev/null; then
            docker-compose -f docker-compose.playwright.yml down
        elif command -v docker &> /dev/null && docker compose version &> /dev/null; then
            docker compose -f docker-compose.playwright.yml down
        else
            # Fallback to direct docker commands
            docker stop autobot-playwright || true
            docker rm autobot-playwright || true
        fi

        echo "✅ Playwright service stopped."
        ;;

    restart)
        echo "🔄 Restarting Playwright service..."
        $0 stop
        sleep 2
        $0 start
        ;;

    status)
        echo "📊 Checking Playwright service status..."

        # Check if container is running
        if docker ps --format '{{.Names}}' | grep -q '^autobot-playwright$'; then
            echo "✅ Container 'autobot-playwright' is running."

            # Check health endpoint
            if curl -sf http://localhost:3000/health > /dev/null 2>&1; then
                echo "✅ Service is healthy and responding."

                # Get service info
                HEALTH_INFO=$(curl -s http://localhost:3000/health 2>/dev/null)
                echo "📡 Service info: $HEALTH_INFO"
            else
                echo "⚠️ Service is not responding to health checks."
            fi
        else
            echo "❌ Container 'autobot-playwright' is not running."

            # Check if container exists but is stopped
            if docker ps -a --format '{{.Names}}' | grep -q '^autobot-playwright$'; then
                echo "📋 Container exists but is stopped. Use '$0 start' to start it."
            else
                echo "📋 Container does not exist. Run setup_agent.sh to create it."
            fi
        fi
        ;;

    logs)
        echo "📄 Showing Playwright service logs..."

        if docker ps -a --format '{{.Names}}' | grep -q '^autobot-playwright$'; then
            docker logs autobot-playwright --tail=50 -f
        else
            echo "❌ Container 'autobot-playwright' not found."
        fi
        ;;

    test)
        echo "🧪 Testing Playwright service..."

        # Test health endpoint
        echo "Testing health endpoint..."
        if curl -f http://localhost:3000/health; then
            echo "✅ Health endpoint OK"
        else
            echo "❌ Health endpoint failed"
            exit 1
        fi

        # Test search endpoint
        echo -e "\nTesting search endpoint..."
        SEARCH_RESULT=$(curl -sf -X POST http://localhost:3000/search \
            -H "Content-Type: application/json" \
            -d '{"query": "playwright testing", "search_engine": "duckduckgo"}')

        if [ $? -eq 0 ]; then
            echo "✅ Search endpoint OK"
            echo "📊 Sample result: $(echo "$SEARCH_RESULT" | jq -r '.results[0].title' 2>/dev/null || echo "Could not parse JSON")"
        else
            echo "❌ Search endpoint failed"
        fi
        ;;

    *)
        echo "AutoBot Playwright Service Manager"
        echo "Usage: $0 [start|stop|restart|status|logs|test]"
        echo ""
        echo "Commands:"
        echo "  start   - Start the Playwright service"
        echo "  stop    - Stop the Playwright service"
        echo "  restart - Restart the Playwright service"
        echo "  status  - Show service status and health"
        echo "  logs    - Show service logs (follow mode)"
        echo "  test    - Test service endpoints"
        echo ""
        echo "Examples:"
        echo "  $0 start          # Start the service"
        echo "  $0 status         # Check if service is running"
        echo "  $0 test           # Test service functionality"
        ;;
esac
