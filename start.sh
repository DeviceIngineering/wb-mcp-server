#!/bin/bash
echo "Запуск WB MCP Server..."
docker compose up -d --build
echo ""
echo "WB MCP Server запущен!"
echo "  Dashboard:  http://localhost:8001"
echo "  SSE:        http://localhost:8001/sse"
echo "  Health:     http://localhost:8001/api/health"
