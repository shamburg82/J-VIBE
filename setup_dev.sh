#!/bin/bash

# Development setup script for JazzVIBE on Posit Workbench/Connect

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

# Function to build frontend
build_frontend() {
    echo "🏗️  Building React frontend..."
    cd frontend
    
    # Install dependencies if node_modules doesn't exist
    if [ ! -d "node_modules" ]; then
        echo "📦 Installing frontend dependencies..."
        npm install --prefer-offline --no-audit --silent
    fi
    
    # Set build environment variables for Posit environments
    export PUBLIC_URL="."
    export GENERATE_SOURCEMAP=false
    export NODE_OPTIONS="--max-old-space-size=3072"
    
    if [ "$WORKBENCH" = true ]; then
        echo "🔧 Building for Workbench with optimizations..."
        if npm run build-workbench; then
            echo "✅ Build succeeded!"
            cd ..
            return 0
        fi
    else
        echo "🔧 Building for local development..."
        if npm run build; then
            echo "✅ Build succeeded!"
            cd ..
            return 0
        fi
    fi
    
    echo "❌ Build failed!"
    cd ..
    return 1
}

# Function to start backend
start_backend() {
    echo "🔧 Starting FastAPI backend..."
    cd backend
    
    if [ "$WORKBENCH" = true ]; then
        echo "📁 Starting for Workbench environment"
        # Use the fixed main.py that properly handles path normalization
        python -m uvicorn main:app --host 0.0.0.0 --port $PORT --log-level info
    else
        echo "📁 Starting for local development with reload"  
        python -m uvicorn main:app --host 0.0.0.0 --port $PORT --reload --log-level info
    fi
}

# Function to start frontend dev server (local only)
start_frontend_dev() {
    if [ "$WORKBENCH" = false ]; then
        echo "⚛️  Starting React development server..."
        cd frontend
        npm start &
        FRONTEND_PID=$!
        echo "Frontend dev server PID: $FRONTEND_PID"
        cd ..
    else
        echo "ℹ️  In Workbench mode, frontend is served by the backend after building."
    fi
}

# Function to clean build
clean_build() {
    echo "🧹 Cleaning previous builds..."
    cd frontend
    rm -rf build/
    rm -rf node_modules/.cache/
    echo "✅ Clean complete!"
    cd ..
}

# Function to check if build exists and is recent
check_build() {
    if [ -d "frontend/build" ]; then
        # Check if build is less than 1 hour old
        if [ $(find frontend/build -maxdepth 0 -mmin -60 2>/dev/null | wc -l) -eq 1 ]; then
            echo "✅ Recent build found (less than 1 hour old)"
            return 0
        else
            echo "⚠️  Build exists but is older than 1 hour"
            return 1
        fi
    else
        echo "❌ No build found"
        return 1
    fi
}

# Function to test API endpoints
test_api() {
    echo "🧪 Testing API endpoints..."
    
    # Wait for server to start
    sleep 5
    
    local base_url="http://localhost:$PORT"
    if [ "$WORKBENCH" = true ]; then
        echo "ℹ️  Note: In Workbench, API will be available through the proxy URL"
        echo "    Direct localhost testing may not reflect actual proxy behavior"
    fi
    
    # Test health endpoint
    echo "Testing health endpoint..."
    if curl -s "$base_url/api/v1/health" > /dev/null; then
        echo "✅ Health endpoint responsive"
    else
        echo "❌ Health endpoint failed"
    fi
    
    # Test compounds endpoint
    echo "Testing compounds endpoint..."
    if curl -s "$base_url/api/v1/documents/compounds" > /dev/null; then
        echo "✅ Compounds endpoint responsive"
    else
        echo "❌ Compounds endpoint failed"
    fi
}

# Main execution based on argument
case "$1" in
    "build")
        build_frontend
        ;;
    "clean")
        clean_build
        ;;
    "rebuild")
        clean_build
        build_frontend
        ;;
    "backend")
        # Check if build exists for production serving
        if [ "$WORKBENCH" = true ]; then
            if ! check_build; then
                echo "🔨 Building frontend first..."
                build_frontend
            fi
        fi
        start_backend
        ;;
    "test")
        # Start backend and test endpoints
        start_backend &
        BACKEND_PID=$!
        echo "Backend PID: $BACKEND_PID"
        
        test_api
        
        echo "Press Ctrl+C to stop server"
        wait $BACKEND_PID
        ;;
    "dev"|"local")
        # Local development with both servers
        if [ "$WORKBENCH" = true ]; then
            echo "⚠️  Warning: 'dev' mode requested but in Workbench environment"
            echo "    Use 'backend' instead for Workbench, or run locally"
            exit 1
        fi
        
        # Start backend
        start_backend &
        BACKEND_PID=$!
        echo "Backend PID: $BACKEND_PID"
        
        sleep 3
        
        # Start frontend dev server
        start_frontend_dev
        
        # Wait for processes
        echo "✅ Both servers running. Press Ctrl+C to stop."
        wait $BACKEND_PID $FRONTEND_PID
        ;;
    ""|"start")
        # Default: Smart startup based on environment
        if [ "$WORKBENCH" = true ]; then
            echo "🔧 Workbench mode: Build + serve via FastAPI"
            
            # Always build in Workbench for latest changes
            if ! build_frontend; then
                echo "❌ Frontend build failed, but starting backend anyway"
                echo "    You can run './setup_dev.sh build' to try building again"
            fi
            
            # Start backend which serves the built frontend
            start_backend
            
        else
            echo "🔧 Local development mode: Separate servers"
            
            # Start backend
            start_backend &
            BACKEND_PID=$!
            echo "Backend PID: $BACKEND_PID"
            
            sleep 3
            
            # Start frontend dev server
            start_frontend_dev
            
            # Wait for processes
            echo "✅ Both servers running. Press Ctrl+C to stop."
            wait $BACKEND_PID $FRONTEND_PID
        fi
        ;;
    "debug")
        # Debug mode - show environment info and test paths
        echo "🔍 Debug Information"
        echo "===================="
        echo "Environment Variables:"
        echo "  RS_SERVER_URL: ${RS_SERVER_URL:-'not set'}"
        echo "  RSTUDIO_CONNECT_URL: ${RSTUDIO_CONNECT_URL:-'not set'}"
        echo "  PORT: ${PORT:-'8000'}"
        echo "  WORKBENCH: $WORKBENCH"
        echo ""
        echo "Path Information:"
        if [ "$WORKBENCH" = true ]; then
            echo "  Detected Workbench mode"
            if command -v /usr/lib/rstudio-server/bin/rserver-url >/dev/null 2>&1; then
                echo "  rserver-url available: ✅"
                echo "  Root path for port $PORT: $(/usr/lib/rstudio-server/bin/rserver-url -l $PORT 2>/dev/null || echo 'Failed to get path')"
            else
                echo "  rserver-url available: ❌"
            fi
        else
            echo "  Local development mode"
        fi
        echo ""
        echo "File System:"
        echo "  Frontend build exists: $([ -d 'frontend/build' ] && echo '✅' || echo '❌')"
        echo "  Backend main.py exists: $([ -f 'backend/main.py' ] && echo '✅' || echo '❌')"
        echo "  Setup script location: $0"
        echo ""
        
        # Start in debug mode
        if [ "$WORKBENCH" = true ]; then
            echo "Starting backend in debug mode..."
            cd backend
            python -m uvicorn main:app --host 0.0.0.0 --port $PORT --log-level debug
        else
            echo "Use './setup_dev.sh start' to run in local development mode"
        fi
        ;;
    "help"|"-h"|"--help")
        echo ""
        echo "JazzVIBE Development Setup Script"
        echo "================================="
        echo ""
        echo "Usage: $0 [COMMAND]"
        echo ""
        echo "Commands:"
        echo "  start       - Smart startup (default)"
        echo "  backend     - Start only FastAPI backend"
        echo "  dev         - Local development (both servers)"
        echo "  build       - Build React app for production"
        echo "  rebuild     - Clean and build React app"
        echo "  clean       - Clean previous builds"
        echo "  test        - Start backend and test API endpoints"
        echo "  debug       - Show debug info and start in debug mode"
        echo "  help        - Show this help"
        echo ""
        echo "Environment Detection:"
        if [ "$WORKBENCH" = true ]; then
            echo "  📋 Current: Workbench mode"
            echo "      - Builds React app and serves via FastAPI"
            echo "      - Uses rserver-url for dynamic path detection"
            echo "      - Single integrated server with middleware path handling"
        else
            echo "  📋 Current: Local development mode"
            echo "      - Runs separate backend and frontend servers"
            echo "      - Frontend has hot reload"
            echo "      - Uses proxy for API calls"
        fi
        echo ""
        echo "Quick Start:"
        if [ "$WORKBENCH" = true ]; then
            echo "  ./setup_dev.sh           # Build and start integrated server"
            echo "  ./setup_dev.sh backend   # Just start backend (if already built)"
            echo "  ./setup_dev.sh debug     # Debug mode with detailed logging"
        else
            echo "  ./setup_dev.sh           # Start both servers for development"
            echo "  ./setup_dev.sh backend   # Start only backend"
        fi
        echo ""
        echo "Troubleshooting:"
        echo "  - If API routes return 404, try './setup_dev.sh debug'"
        echo "  - If frontend won't load, try './setup_dev.sh rebuild'"
        echo "  - For path issues in Workbench, check RS_SERVER_URL variable"
        ;;
    *)
        echo "❌ Unknown command: $1"
        echo "Use './setup_dev.sh help' for usage information"
        exit 1
        ;;
esac
