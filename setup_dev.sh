#!/bin/bash

# Simplified development setup script for JazzVIBE on Posit Workbench

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

# Function to build frontend with fallback options
build_frontend_with_fallbacks() {
    echo "🏗️  Building React frontend with fallback strategies..."
    cd frontend
    
    # Install dependencies if node_modules doesn't exist
    if [ ! -d "node_modules" ]; then
        echo "📦 Installing frontend dependencies..."
        
        # Use npm ci for faster, more reliable installs in CI environments
        if [ -f "package-lock.json" ]; then
            npm ci --prefer-offline --no-audit --silent
        else
            npm install --prefer-offline --no-audit --silent
        fi
    fi
    
    # Strategy 1: Try normal build first
    echo "🔧 Attempting normal build..."
    if [ "$WORKBENCH" = true ]; then
        export NODE_OPTIONS="--max-old-space-size=3072"
        if npm run build-workbench; then
            echo "✅ Normal build succeeded!"
            cd ..
            return 0
        fi
        echo "❌ Normal build failed, trying with reduced memory..."
    fi
    
    # Strategy 2: Reduced memory build
    echo "🔧 Attempting reduced memory build..."
    export NODE_OPTIONS="--max-old-space-size=2048"
    export LOW_MEMORY_BUILD=true
    if npm run build-workbench-minimal; then
        echo "✅ Reduced memory build succeeded!"
        cd ..
        return 0
    fi
    echo "❌ Reduced memory build failed, trying minimal build..."
    
    # Strategy 3: Minimal build with even less memory
    echo "🔧 Attempting minimal build..."
    export NODE_OPTIONS="--max-old-space-size=1024"
    export DISABLE_ESLINT_PLUGIN=true
    
    # Create a temporary minimal build script
    cat > temp_build.js << 'EOF'
const { execSync } = require('child_process');
process.env.GENERATE_SOURCEMAP = 'false';
process.env.PUBLIC_URL = '.';
process.env.CI = 'true'; // Disable interactive mode
execSync('npx react-scripts build', { stdio: 'inherit' });
EOF
    
    if node temp_build.js; then
        echo "✅ Minimal build succeeded!"
        rm -f temp_build.js
        cd ..
        return 0
    fi
    
    # Strategy 4: Ultra minimal - build without optimizations
    echo "🔧 Attempting ultra-minimal build..."
    rm -f temp_build.js
    export NODE_OPTIONS="--max-old-space-size=512"
    
    # Try building with webpack directly (bypasses some CRA overhead)
    if npx webpack --mode production --entry ./src/index.js --output-path ./build --output-filename static/js/[name].js; then
        echo "✅ Ultra-minimal build succeeded!"
        cd ..
        return 0
    fi
    
    echo "❌ All build strategies failed!"
    cd ..
    return 1
}

# Function to start backend only (simplified)
start_backend_simple() {
    echo "🔧 Starting FastAPI backend..."
    cd backend
    
    # Use the simplified main.py that doesn't set root_path in FastAPI config
    # This avoids the URL construction issues we were seeing
    
    if [ "$WORKBENCH" = true ]; then
        echo "📁 Starting for Workbench environment (no root_path config)"
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

# Main execution based on argument
case "$1" in
    "build")
        build_frontend_with_fallbacks
        ;;
    "clean")
        clean_build
        ;;
    "rebuild")
        clean_build
        build_frontend_with_fallbacks
        ;;
    "backend")
        # Check if build exists for production serving
        if [ "$WORKBENCH" = true ]; then
            if ! check_build; then
                echo "🔨 Building frontend first..."
                build_frontend_with_fallbacks
            fi
        fi
        start_backend_simple
        ;;
    "dev"|"local")
        # Local development with both servers
        if [ "$WORKBENCH" = true ]; then
            echo "⚠️  Warning: 'dev' mode requested but in Workbench environment"
            echo "    Use 'backend' instead for Workbench, or run locally"
            exit 1
        fi
        
        # Start backend
        start_backend_simple &
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
            build_frontend_with_fallbacks
            
            # Start backend which serves the built frontend
            start_backend_simple
            
        else
            echo "🔧 Local development mode: Separate servers"
            
            # Start backend
            start_backend_simple &
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
        echo "  help        - Show this help"
        echo ""
        echo "Environment Detection:"
        if [ "$WORKBENCH" = true ]; then
            echo "  📋 Current: Workbench mode"
            echo "      - Builds React app and serves via FastAPI"
            echo "      - Uses dynamic path detection"
            echo "      - Single integrated server"
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
        else
            echo "  ./setup_dev.sh           # Start both servers for development"
            echo "  ./setup_dev.sh backend   # Start only backend"
        fi
        ;;
    *)
        echo "❌ Unknown command: $1"
        echo "Use './setup_dev.sh help' for usage information"
        exit 1
        ;;
esac
