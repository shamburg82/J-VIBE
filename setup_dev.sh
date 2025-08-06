#!/bin/bash

# Development setup script for TLF Analyzer on Posit Workbench

echo "🚀 Setting up JazzVIBE for Posit Workbench development..."

# Check if we're in Posit Workbench
if [ -n "$RS_SERVER_URL" ]; then
    echo "✅ Detected Posit Workbench environment"
    export WORKBENCH=true
else
    echo "ℹ️  Running in local development mode"
    export WORKBENCH=false
fi

# Set up environment variables
export PORT=8000
export DEVELOPMENT_MODE=true

# Function to start backend
start_backend() {
    echo "🔧 Starting FastAPI backend..."
    cd backend
    
    if [ "$WORKBENCH" = true ]; then
        # Option 1: Use the start.py script
        echo "📁 Using start.py script for Workbench"
        python start.py
    else
        # Option 2: Use uvicorn directly with app.py
        echo "📁 Using uvicorn directly for local development"  
        python -m uvicorn main:app --host 0.0.0.0 --port $PORT --reload
    fi
}

# Function to start frontend
start_frontend() {
    echo "⚛️  Starting React frontend..."
    cd frontend
    
    if [ "$WORKBENCH" = true ]; then
        echo "ℹ️  In Workbench mode, frontend is served by the backend after building."
        echo "ℹ️  No separate frontend server needed."
    else
        # Local development with hot reload
        npm start
    fi
}

# Function to build everything
build_all() {
    echo "🏗️  Building React frontend..."
    cd frontend
    
    # Install dependencies if node_modules doesn't exist
    if [ ! -d "node_modules" ]; then
        echo "📦 Installing frontend dependencies..."
        npm install
    fi
    
    if [ "$WORKBENCH" = true ]; then
        npm run build-workbench
    else
        npm run build
    fi
    cd ..
    echo "✅ Build complete!"
}


# Function to clean build
clean_build() {
    echo "🧹 Cleaning previous builds..."
    cd frontend
    rm -rf build/
    rm -rf node_modules/.cache/
    echo "✅ Clean complete!"
}

# Function for complete Workbench setup
workbench_setup() {
    echo "🔧 Workbench Complete Setup:"
    echo "  1. Installing dependencies..."
    echo "  2. Building React app..."
    echo "  3. Starting integrated server..."
    
    # Step 1: Install frontend dependencies
    cd frontend
    if [ ! -d "node_modules" ]; then
        echo "📦 Installing frontend dependencies..."
        npm install
    fi
    
    # Step 2: Build frontend
    echo "🏗️  Building React app for Workbench..."
    npm run build-workbench
    
    # Step 3: Start backend (which serves the built frontend)
    cd ../backend
    echo "🚀 Starting FastAPI backend (serves built React app)..."
    python start.py
}

# Function for complete local setup
local_setup() {
    echo "🔧 Local Development Setup:"
    echo "  1. Installing dependencies..."
    echo "  2. Starting backend..."
    echo "  3. Starting frontend with hot reload..."
    
    # Step 1: Install dependencies
    cd frontend
    if [ ! -d "node_modules" ]; then
        echo "📦 Installing frontend dependencies..."
        npm install
    fi
    cd ..
    
    # Step 2 & 3: Start both servers
    echo "🚀 Starting backend server..."
    start_backend &
    BACKEND_PID=$!
    
    sleep 3
    
    echo "🚀 Starting frontend development server..."
    start_frontend &
    FRONTEND_PID=$!
    
    # Wait for both processes
    echo "✅ Both servers running. Press Ctrl+C to stop."
    wait $BACKEND_PID $FRONTEND_PID
}

case "$1" in
    "backend")
        start_backend
        ;;
    "frontend")
        start_frontend
        ;;
    "build")
        build_all
        ;;
    "clean")
        clean_build
        ;;
    "rebuild")
        clean_build
        build_all
        ;;
    "setup"|"both"|"")
        # Complete setup based on environment
        if [ "$WORKBENCH" = true ]; then
            workbench_setup
        else
            local_setup
        fi
        ;;
    *)
        echo "Usage: $0 [backend|frontend|build|clean|rebuild|setup|both]"
        echo ""
        echo "Commands:"
        echo "  backend  - Start only the FastAPI backend"
        echo "  frontend - Start only the React frontend"
        echo "  build    - Build React app for production"
        echo "  clean    - Clean previous builds"
        echo "  rebuild  - Clean and build"
        echo "  setup    - Complete setup (default)"
        echo "  both     - Same as setup"
        echo ""
        echo "Environment-specific behavior:"
        if [ "$WORKBENCH" = true ]; then
            echo "  📋 Workbench mode: Builds React app and serves via FastAPI"
        else
            echo "  📋 Local mode: Runs separate backend and frontend servers"
        fi
        exit 1
        ;;
esac
