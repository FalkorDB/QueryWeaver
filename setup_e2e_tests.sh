#!/bin/bash

# QueryWeaver E2E Test Setup Script
# This script demonstrates how to set up and run E2E tests

set -e

echo "🚀 Setting up QueryWeaver E2E Tests"
echo "=================================="

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Please install it first:"
    echo "   pip install uv"
    echo "   or visit https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo "📄 Creating .env file from template..."
    cp .env.example .env
    echo "✅ .env file created. Please edit it with your configuration."
fi

# Install dependencies
echo "📦 Installing dependencies..."
uv sync

# Install Playwright browsers
echo "🌐 Installing Playwright browsers..."
uv run playwright install chromium

# Check if FalkorDB is running (optional for basic tests)
echo "🔍 Checking for FalkorDB..."
if command -v docker &> /dev/null; then
    if ! docker ps | grep -q falkordb; then
        echo "⚠️  FalkorDB not detected. Starting FalkorDB container..."
        docker run -d --name falkordb-test -p 6379:6379 falkordb/falkordb:latest
        echo "✅ FalkorDB started"
        sleep 5
    else
        echo "✅ FalkorDB is already running"
    fi
else
    echo "⚠️  Docker not found. Some tests may require FalkorDB."
fi

echo ""
echo "🎉 Setup complete! You can now run tests:"
echo ""
echo "  make test-unit         # Run unit tests"
echo "  make test-e2e          # Run E2E tests (headless)"
echo "  make test-e2e-headed   # Run E2E tests (with browser)"
echo "  make test              # Run all tests"
echo ""
echo "Or use pytest directly:"
echo "  uv run python -m pytest tests/e2e/test_basic_functionality.py -v"
echo ""
echo "To run the application:"
echo "  make run-dev"
echo ""
