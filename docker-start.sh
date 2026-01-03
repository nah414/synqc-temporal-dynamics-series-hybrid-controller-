#!/bin/bash
# Docker Compose startup helper script
# This script validates the environment and starts Docker Compose

set -e

# Ensure we run from the repo root even if invoked from elsewhere (Git Bash friendliness)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================"
echo "SynQc Docker Compose Setup & Validation"
echo "======================================"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running"
    echo "   Please start Docker Desktop and try again"
    exit 1
fi
echo "✓ Docker is running"

# Check if docker-compose exists
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null 2>&1; then
    echo "❌ Error: docker-compose not found"
    echo "   Please install Docker Compose"
    exit 1
fi
echo "✓ Docker Compose is available"

# Check for required files
REQUIRED_FILES=(
    "docker-compose.yml"
    "backend/Dockerfile"
    "backend/pyproject.toml"
    "web/Dockerfile"
    "web/index.html"
    "web/nginx.conf"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo "❌ Error: Required file not found: $file"
        exit 1
    fi
done
echo "✓ All required files present"

# Clean up old containers and volumes if requested
if [ "$1" == "--clean" ] || [ "$1" == "-c" ]; then
    echo ""
    echo "Cleaning up old containers and volumes..."
    docker-compose down -v 2>/dev/null || docker compose down -v 2>/dev/null || true
    echo "✓ Cleanup complete"
fi

# Build and start services
echo ""
echo "Building and starting services..."
echo "This may take a few minutes on first run..."
echo ""

if command -v docker-compose &> /dev/null; then
    docker-compose up --build -d
else
    docker compose up --build -d
fi

echo ""
echo "======================================"
echo "✓ Services started successfully!"
echo "======================================"
echo ""
echo "Services:"
echo "  - API:   http://localhost:8001"
echo "  - Docs:  http://localhost:8001/docs"
echo "  - Web:   http://localhost:8080"
echo "  - Redis: localhost:6379"
echo ""
echo "To view logs:"
echo "  docker-compose logs -f"
echo ""
echo "To stop services:"
echo "  docker-compose down"
echo ""
echo "To rebuild after code changes:"
echo "  docker-compose up --build -d"
echo ""
