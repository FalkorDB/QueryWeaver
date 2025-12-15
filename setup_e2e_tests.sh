#!/bin/bash

# QueryWeaver E2E Test Setup Script (TypeScript/Playwright)
# This script sets up the TypeScript E2E testing environment

set -e

echo "🚀 Setting up QueryWeaver E2E Tests (TypeScript)"
echo "================================================"

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 20+ first."
    exit 1
fi

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo "❌ npm is not installed. Please install npm first."
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo "📄 Creating .env file from template..."
    cp .env.example .env
    echo "✅ .env file created. Please edit it with your configuration."
fi

# Install Node dependencies
echo "📦 Installing Node.js dependencies..."
npm install

# Install Playwright browsers
echo "🌐 Installing Playwright browsers..."
npx playwright install chromium

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

# Build frontend
echo "🏗️  Building frontend..."
make build-dev

echo ""
echo "🎉 Setup complete! You can now run TypeScript E2E tests:"
echo ""
echo "  npm run test:e2e           # Run E2E tests (headless)"
echo "  npm run test:e2e:headed    # Run E2E tests (with browser)"
echo "  npm run test:e2e:ui        # Run E2E tests (UI mode)"
echo "  npm run test:e2e:debug     # Run E2E tests (debug mode)"
echo ""
echo "Or use make commands:"
echo "  make test-e2e-ts           # Run E2E tests (headless)"
echo "  make test-e2e-ts-headed    # Run E2E tests (with browser)"
echo "  make test-e2e-ts-ui        # Run E2E tests (UI mode)"
echo ""
echo "To run the application:"
echo "  make run-dev"
echo ""
