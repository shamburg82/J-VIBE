# backend/app.py (Posit Connect/Workbench entry point)
"""
Posit Connect/Workbench entry point for FastAPI application.
This file is required for Posit Connect to recognize the FastAPI app.
"""

import os
import subprocess
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_posit_root_path(port: int = 8000) -> str:
    """Get root path for Posit Workbench."""
    
    if 'RS_SERVER_URL' not in os.environ or not os.environ['RS_SERVER_URL']:
        return ''
    
    try:
        result = subprocess.run(
            f'echo $(/usr/lib/rstudio-server/bin/rserver-url -l {port})', 
            stdout=subprocess.PIPE, 
            shell=True,
            timeout=10
        )
        
        if result.returncode == 0:
            path = result.stdout.decode().strip()
            print(f"✅ Posit Workbench root path: {path}")
            return path
        else:
            logger.warning(f"⚠️  rserver-url failed with return code: {result.returncode}")
            logger.warning(f"⚠️  stdout: {result.stdout}")
            logger.warning(f"⚠️  stderr: {result.stderr}")
            return ''
            
    except subprocess.TimeoutExpired:
        logger.error("⚠️  Timeout getting root path")
        return ''
    except Exception as e:
        logger.warning(f"⚠️  Error getting Posit Workbench root path: {e}")
        return ''

# Detect environment
is_connect = bool(os.getenv("RSTUDIO_CONNECT_URL"))
is_workbench = bool(os.getenv("RS_SERVER_URL")) and not is_connect

# Determine root path
root_path = ""
if is_workbench or is_connect:
    port = int(os.getenv("PORT", "8000"))
    root_path = get_posit_root_path(port)

logger.info(f"🚀 Starting TLF Analyzer - Environment: {'Connect' if is_connect else 'Workbench' if is_workbench else 'Other'}")
logger.info(f"📁 Root path: {root_path}")

# Create FastAPI app with root_path
app = FastAPI(
    title="JazzVIBE API",
    description="API for processing and querying TLF Bundles",
    version="1.0.0",
    root_path=root_path
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your Posit Connect URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include your routes after app creation to avoid circular imports
try:
    from app.api.routes import documents, queries, health, chat
    
    app.include_router(health.router, prefix="/api/v1/health", tags=["health"])
    app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
    app.include_router(queries.router, prefix="/api/v1/queries", tags=["queries"])
    app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
    
    logger.info("✅ API routes loaded successfully")
    
except ImportError as e:
    logger.error(f"❌ Failed to import routes: {e}")
    # Create a basic health endpoint as fallback
    @app.get("/api/v1/health")
    async def fallback_health():
        return {"status": "error", "message": "Routes not loaded", "error": str(e)}

# Serve static files for the React frontend (for production deployment)
static_dir = Path(__file__).parent.parent / "frontend/build"
if static_dir.exists():
    logger.info(f"📁 Serving React static files from: {static_dir}")
    
    # Mount static files with the correct path
    app.mount("/static", StaticFiles(directory=static_dir / "static"), name="static")
    
    # Also serve from root/static for compatibility
    if root_path:
        # When we have a root path, also mount at the root level
        try:
            app.mount(f"{root_path}/static", StaticFiles(directory=static_dir / "static"), name="static_root")
        except Exception as e:
            logger.warning(f"Could not mount static files at root path: {e}")

    # Serve manifest.json and other root files
    @app.get("/manifest.json")
    async def serve_manifest():
        manifest_file = static_dir / "manifest.json"
        if manifest_file.exists():
            return FileResponse(manifest_file)
        return {"error": "Manifest not found"}
    
    @app.get("/favicon.ico")
    async def serve_favicon():
        favicon_file = static_dir / "favicon.ico"
        if favicon_file.exists():
            return FileResponse(favicon_file)
        return {"error": "Favicon not found"}
    
    # Also handle these files with the root path prefix
    if root_path:
        @app.get(f"{root_path}/manifest.json")
        async def serve_manifest_with_root():
            manifest_file = static_dir / "manifest.json"
            if manifest_file.exists():
                return FileResponse(manifest_file)
            return {"error": "Manifest not found"}
        
        @app.get(f"{root_path}/favicon.ico")
        async def serve_favicon_with_root():
            favicon_file = static_dir / "favicon.ico"
            if favicon_file.exists():
                return FileResponse(favicon_file)
            return {"error": "Favicon not found"}
    
    # Serve React app for all non-API routes
    @app.get("/{path:path}")
    async def serve_react_app(path: str):
        """Serve React app for all non-API routes."""
        # If it's an API route, let FastAPI handle it normally
        if path.startswith("api/"):
            return {"error": "API endpoint not found"}
        
        # If it's a static file request, try to serve it
        if path.startswith("static/"):
            static_file = static_dir / path
            if static_file.exists():
                return FileResponse(static_file)
            # If not found, return 404 instead of HTML
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Static file not found")
        
        # For all other routes, serve the React app with proper base path injection
        index_file = static_dir / "index.html"
        if index_file.exists():
            # Read the index.html file
            with open(index_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Debug: Log what we're processing
            logger.info(f"Processing HTML for path: {path}, root_path: {root_path}")
            
            # Process the HTML content
            if root_path:
                # Replace relative paths with absolute paths that include root_path
                # This handles both ./static and /static patterns
                html_content = html_content.replace('href="./static/', f'href="{root_path}/static/')
                html_content = html_content.replace('src="./static/', f'src="{root_path}/static/')
                html_content = html_content.replace('href="/static/', f'href="{root_path}/static/')
                html_content = html_content.replace('src="/static/', f'src="{root_path}/static/')
                
                # Handle manifest and favicon
                html_content = html_content.replace('href="./manifest.json"', f'href="{root_path}/manifest.json"')
                html_content = html_content.replace('href="./favicon.ico"', f'href="{root_path}/favicon.ico"')
                html_content = html_content.replace('href="/manifest.json"', f'href="{root_path}/manifest.json"')
                html_content = html_content.replace('href="/favicon.ico"', f'href="{root_path}/favicon.ico"')
                
                # Replace %PUBLIC_URL% if it exists
                html_content = html_content.replace('%PUBLIC_URL%', root_path)
                
                # Inject base tag after <head>
                if '<base href=' not in html_content:
                    base_tag = f'<base href="{root_path}/">'
                    html_content = html_content.replace('<head>', f'<head>\n    {base_tag}')
                
                # Inject JavaScript variable
                js_injection = f'''
    <script>
      // Server-provided base path
      window.__POSIT_BASE_PATH__ = '{root_path}/';
      console.log('Server set base path:', window.__POSIT_BASE_PATH__);
    </script>'''
                
                if '</head>' in html_content:
                    html_content = html_content.replace('</head>', f'    {js_injection}\n  </head>')
                else:
                    # Fallback: add after <head>
                    html_content = html_content.replace('<head>', f'<head>\n    {js_injection}')
                    
                # Debug: Log the processed HTML (first 1000 chars)
                logger.info(f"Processed HTML preview: {html_content[:1000]}...")
            
            from fastapi.responses import HTMLResponse
            return HTMLResponse(content=html_content)
        else:
            return {"error": "React app not built. Run 'npm run build' first."}
else:
    logger.warning("📁 React build directory not found. Static files will not be served.")
    
    # Fallback route when no build exists
    @app.get("/{path:path}")
    async def no_build_fallback(path: str):
        if path.startswith("api/"):
            return {"error": "API endpoint not found"}
        return {
            "error": "React app not built", 
            "message": "Run 'npm run build' to build the React frontend",
            "root_path": root_path,
            "requested_path": path
        }


# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "JazzVIBE API",
        "version": "1.0.0",
        "root_path": app.root_path,
        "detected_root_path": root_path,
        "docs": f"{app.root_path}/docs" if app.root_path else "/docs",
        "health": f"{app.root_path}/api/v1/health" if app.root_path else "/api/v1/health",
        "static_dir_exists": static_dir.exists() if 'static_dir' in locals() else False
    }

# Health check that includes root path info
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "root_path": app.root_path,
        "detected_root_path": root_path,
        "environment": {
            "is_connect": is_connect,
            "is_workbench": is_workbench,
            "port": os.getenv("PORT", "8000"),
            "RS_SERVER_URL": os.getenv("RS_SERVER_URL", "not_set")
        }
    }

# Debug endpoint to test path processing
@app.get("/debug-paths")
async def debug_paths():
    return {
        "app_root_path": app.root_path,
        "detected_root_path": root_path,
        "static_dir": str(static_dir) if 'static_dir' in locals() else "not_set",
        "static_dir_exists": static_dir.exists() if 'static_dir' in locals() else False,
        "environment_vars": {
            "RS_SERVER_URL": os.getenv("RS_SERVER_URL"),
            "RSTUDIO_CONNECT_URL": os.getenv("RSTUDIO_CONNECT_URL"),
            "PORT": os.getenv("PORT", "8000")
        }
    }

# For running directly
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8000"))
    
    if is_connect:
        logger.info("🚀 Starting on Posit Connect (Production)")
        # Posit Connect handles the server setup
    elif is_workbench:
        logger.info("🚀 Starting on Posit Workbench (Development)")
        
        uvicorn.run(
            "main:app",  # Reference this file
            host="0.0.0.0",
            port=port,
            root_path=root_path,
            log_level="debug",
            reload=True
        )
    else:
        logger.info("🚀 Starting in local development")
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=port,
            log_level="info",
            reload=True
        )
