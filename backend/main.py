# backend/main.py (Clean production version)
import os
import subprocess
import logging
import re
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global service variables
document_service = None
query_service = None
storage_service = None
chat_service = None

def get_posit_root_path(port: int = 8000) -> str:
    """Get root path for Posit Workbench using rserver-url."""
    if 'RS_SERVER_URL' not in os.environ or not os.environ['RS_SERVER_URL']:
        return ''
    
    try:
        result = subprocess.run(
            f'/usr/lib/rstudio-server/bin/rserver-url -l {port}', 
            stdout=subprocess.PIPE, shell=True, timeout=10
        )
        
        if result.returncode == 0:
            full_url = result.stdout.decode().strip()
            logger.info(f"✅ rserver-url returned: {full_url}")
            
            if full_url.startswith('http'):
                from urllib.parse import urlparse
                parsed = urlparse(full_url)
                path = parsed.path.rstrip('/')
                logger.info(f"✅ Extracted root path: {path}")
                return path
            else:
                return full_url.rstrip('/')
        return ''
    except Exception as e:
        logger.warning(f"⚠️  Error getting root path: {e}")
        return ''

# Environment detection
is_connect = bool(os.getenv("RSTUDIO_CONNECT_URL"))
is_workbench = bool(os.getenv("RS_SERVER_URL")) and not is_connect
port = int(os.getenv("PORT", "8000"))
root_path = get_posit_root_path(port) if is_workbench or is_connect else ""

logger.info(f"🚀 Starting TLF Analyzer - Environment: {'Connect' if is_connect else 'Workbench' if is_workbench else 'Local'}")
logger.info(f"📁 Root path: '{root_path}'")

# Define static_dir early
static_dir = Path(__file__).parent.parent / "frontend/build"

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - startup and shutdown."""
    global document_service, query_service, storage_service, chat_service
    
    # Startup
    logger.info("🚀 Starting TLF Analyzer API services")
    
    try:
        # Detect environment and get appropriate config
        config = None
        if is_connect or is_workbench:
            # Use Posit-specific configuration
            try:
                from app.core.posit_config import get_posit_config
                config = get_posit_config()
                logger.info(f"Using Posit configuration: {config.get_environment_name()}")
            except ImportError as e:
                logger.warning(f"Could not import Posit config: {e}, using standard config")
                from app.core.config import get_config
                config = get_config()
        else:
            # Use standard configuration
            from app.core.config import get_config
            config = get_config()
        
        # Initialize Bedrock LLM with appropriate setup
        if is_connect or is_workbench:
            try:
                from app.core.posit_bedrock_setup import configure_bedrock_for_posit
                llm = await configure_bedrock_for_posit()
            except ImportError:
                logger.warning("Could not import Posit Bedrock setup, using standard setup")
                from app.core.bedrock_setup import configure_bedrock_llm
                llm = await configure_bedrock_llm()
        else:
            from app.core.bedrock_setup import configure_bedrock_llm
            llm = await configure_bedrock_llm()
            
        if not llm:
            raise Exception("Failed to initialize Bedrock LLM")
        
        # Initialize services with config
        from app.services.storage_service import StorageService
        from app.services.document_service import DocumentService
        from app.services.query_service import QueryService
        from app.services.chat_service import ChatService
        
        storage_service = StorageService()
        document_service = DocumentService(
            llm=llm, 
            storage_service=storage_service,
            config=config
        )
        query_service = QueryService(llm=llm, storage_service=storage_service)
        
        # Initialize chat service
        chat_service = ChatService(
            llm=llm, 
            storage_service=storage_service, 
            query_service=query_service
        )
        
        logger.info("✅ All services initialized successfully")
        if config and hasattr(config, 'get_storage_path'):
            logger.info(f"📁 Storage path: {config.get_storage_path()}")
        elif config and hasattr(config, 'base_storage_path'):
            logger.info(f"📁 Storage path: {config.base_storage_path}")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize services: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down TLF Analyzer API")

class PathNormalizationMiddleware(BaseHTTPMiddleware):
    """Middleware to normalize paths for Posit environments."""
    
    def __init__(self, app, root_path: str = ""):
        super().__init__(app)
        self.root_path = root_path.rstrip('/') if root_path else ""
        
    async def dispatch(self, request: Request, call_next):
        original_path = request.url.path
        clean_path = original_path
        
        # Handle malformed paths with hostnames
        if clean_path.startswith('//') and '.' in clean_path:
            temp_path = clean_path.lstrip('/')
            if '/' in temp_path:
                parts = temp_path.split('/', 1)
                if '.' in parts[0]:  # Likely a hostname
                    clean_path = '/' + parts[1]
        
        # Remove root path prefix
        if self.root_path and clean_path.startswith(self.root_path):
            clean_path = clean_path[len(self.root_path):]
            if not clean_path.startswith('/'):
                clean_path = '/' + clean_path
        
        # Clean up double slashes
        clean_path = re.sub(r'/+', '/', clean_path)
        
        # Update request
        request.scope['path'] = clean_path
        request.scope['raw_path'] = clean_path.encode()
        
        response = await call_next(request)
        return response

class ReactFallbackMiddleware(BaseHTTPMiddleware):
    """Middleware to serve React app for unmatched routes."""
    
    def __init__(self, app):
        super().__init__(app)
    
    def get_react_html(self) -> str:
        """Get processed React HTML content."""
        if not static_dir.exists():
            return None
            
        index_file = static_dir / "index.html"
        if not index_file.exists():
            return None
        
        # Read HTML file
        with open(index_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Process base path if we have one
        if root_path:
            # Replace paths
            html_content = html_content.replace('href="./static/', f'href="{root_path}/static/')
            html_content = html_content.replace('src="./static/', f'src="{root_path}/static/')
            html_content = html_content.replace('href="/static/', f'href="{root_path}/static/')
            html_content = html_content.replace('src="/static/', f'src="{root_path}/static/')
            html_content = html_content.replace('href="./manifest.json"', f'href="{root_path}/manifest.json"')
            html_content = html_content.replace('href="./favicon.ico"', f'href="{root_path}/favicon.ico"')
            html_content = html_content.replace('href="/manifest.json"', f'href="{root_path}/manifest.json"')
            html_content = html_content.replace('href="/favicon.ico"', f'href="{root_path}/favicon.ico"')
            html_content = html_content.replace('%PUBLIC_URL%', root_path)
            
            # Inject base tag
            if '<base href=' not in html_content:
                base_tag = f'<base href="{root_path}/">'
                html_content = html_content.replace('<head>', f'<head>\n    {base_tag}')
            
            # Inject JavaScript variable
            js_injection = f'''
    <script>
      window.__POSIT_BASE_PATH__ = '{root_path}';
      console.log('Server set base path:', window.__POSIT_BASE_PATH__);
    </script>'''
            
            if '</head>' in html_content:
                html_content = html_content.replace('</head>', f'    {js_injection}\n  </head>')
        
        return html_content
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # If we get a 404 and this might be a React route, serve React app
        if response.status_code == 404:
            path = request.url.path
            accept_header = request.headers.get("accept", "")
            
            # Don't serve React for API routes, JSON requests, or static files
            is_api_route = (path.startswith("/api/") or 
                          path.startswith("/docs") or 
                          path.startswith("/openapi.json") or 
                          path.startswith("/redoc") or
                          path == "/health")
            
            is_json_only_request = ("application/json" in accept_header and 
                                  "text/html" not in accept_header)
            
            is_static_file = path.startswith("/static/")
            
            if not is_api_route and not is_json_only_request and not is_static_file:
                react_html = self.get_react_html()
                if react_html:
                    return HTMLResponse(content=react_html)
        
        return response

# Create FastAPI app with lifespan
app = FastAPI(
    title="JazzVIBE API",
    description="API for processing and querying TLF Bundles",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add middlewares in order
if root_path:
    app.add_middleware(PathNormalizationMiddleware, root_path=root_path)

if static_dir.exists():
    app.add_middleware(ReactFallbackMiddleware)

# Dependency functions to get services
def get_document_service():
    if document_service is None:
        raise HTTPException(status_code=503, detail="Document service not initialized")
    return document_service

def get_query_service():
    if query_service is None:
        raise HTTPException(status_code=503, detail="Query service not initialized")
    return query_service

def get_storage_service():
    if storage_service is None:
        raise HTTPException(status_code=503, detail="Storage service not initialized")
    return storage_service

def get_chat_service():
    if chat_service is None:
        raise HTTPException(status_code=503, detail="Chat service not initialized")
    return chat_service

# Import and include API routes
try:
    from app.api.routes import documents, queries, health, chat
    
    # Mount API routes
    app.include_router(health.router, prefix="/api/v1/health", tags=["health"])
    app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])  
    app.include_router(queries.router, prefix="/api/v1/queries", tags=["queries"])
    app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
    
    logger.info("✅ API routes loaded successfully")
    
except ImportError as e:
    logger.error(f"❌ Failed to import routes: {e}")

# Direct health endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "root_path": root_path,
        "environment": {
            "is_connect": is_connect,
            "is_workbench": is_workbench,
            "port": os.getenv("PORT", "8000")
        },
        "services_initialized": {
            "document_service": document_service is not None,
            "query_service": query_service is not None,
            "storage_service": storage_service is not None,
            "chat_service": chat_service is not None
        }
    }

# Add explicit route for health without trailing slash
@app.get("/api/v1/health")
async def health_no_slash():
    """Health endpoint without trailing slash to match frontend expectations."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(),
        "services": {
            "api": "healthy",
            "bedrock": "healthy" if document_service else "not_initialized",
            "storage": "healthy" if storage_service else "not_initialized"
        },
        "version": "1.0.0"
    }

# Static files and specific routes
if static_dir.exists():
    logger.info(f"📁 Serving React static files from: {static_dir}")
    
    @app.get("/static/{file_path:path}")
    async def serve_static_files(file_path: str):
        """Serve static files with correct MIME types."""
        static_file_path = static_dir / "static" / file_path
        
        if not static_file_path.exists():
            raise HTTPException(status_code=404, detail="Static file not found")
        
        # Determine MIME type based on file extension
        if file_path.endswith('.css'):
            media_type = "text/css"
        elif file_path.endswith('.js'):
            media_type = "application/javascript"
        elif file_path.endswith('.json'):
            media_type = "application/json"
        elif file_path.endswith(('.png', '.jpg', '.jpeg')):
            media_type = f"image/{file_path.split('.')[-1]}"
        elif file_path.endswith('.svg'):
            media_type = "image/svg+xml"
        elif file_path.endswith('.ico'):
            media_type = "image/x-icon"
        elif file_path.endswith(('.woff', '.woff2')):
            media_type = "font/woff2" if file_path.endswith('.woff2') else "font/woff"
        elif file_path.endswith('.ttf'):
            media_type = "font/ttf"
        else:
            media_type = "application/octet-stream"
        
        return FileResponse(static_file_path, media_type=media_type)
    
    # Specific file routes
    @app.get("/manifest.json")
    async def serve_manifest():
        manifest_file = static_dir / "manifest.json"
        if manifest_file.exists():
            return FileResponse(manifest_file, media_type="application/json")
        raise HTTPException(status_code=404, detail="Manifest not found")
    
    @app.get("/favicon.ico")  
    async def serve_favicon():
        favicon_file = static_dir / "favicon.ico"
        if favicon_file.exists():
            return FileResponse(favicon_file, media_type="image/x-icon")
        raise HTTPException(status_code=404, detail="Favicon not found")
    
    # Root endpoint - smart routing
    @app.get("/")
    async def root(request: Request):
        accept_header = request.headers.get("accept", "")
        
        # If the request specifically wants JSON (API clients/tests)
        if ("application/json" in accept_header and "text/html" not in accept_header):
            return {
                "message": "JazzVIBE API",
                "version": "1.0.0", 
                "root_path": root_path,
                "docs": f"{root_path}/docs" if root_path else "/docs",
                "health": f"{root_path}/api/v1/health" if root_path else "/api/v1/health"
            }
        
        # Otherwise, serve React app (browsers)
        index_file = static_dir / "index.html"
        if not index_file.exists():
            return {"error": "React app not available", "message": "Frontend not built"}
        
        # Use the ReactFallbackMiddleware's method
        middleware = ReactFallbackMiddleware(app)
        react_html = middleware.get_react_html()
        if react_html:
            return HTMLResponse(content=react_html)
        else:
            return {"error": "React app not available"}

else:
    logger.warning("📁 React build directory not found")
    
    @app.get("/")
    async def root():
        return {
            "message": "JazzVIBE API",
            "version": "1.0.0",
            "root_path": root_path,
            "error": "React app not built"
        }

# Additional convenience endpoints for chat integration
@app.get("/api/v1/document/{document_id}/chat-ready")
async def check_document_chat_ready(document_id: str):
    """Check if a document is ready for chat (processed and indexed)."""
    
    try:
        # Check if document exists and is processed
        doc_info = await document_service.get_document_info(document_id)
        if not doc_info:
            raise HTTPException(status_code=404, detail="Document not found")
        
        if doc_info.status != "completed":
            return {
                "chat_ready": False,
                "status": doc_info.status,
                "message": f"Document is still being processed (status: {doc_info.status})"
            }
        
        # Check if vector index exists
        vector_index = await storage_service.get_index(document_id)
        if not vector_index:
            return {
                "chat_ready": False,
                "status": "no_index",
                "message": "Document processed but vector index not available"
            }
        
        # Get available sources for context
        sources = await query_service.get_available_sources(document_id)
        
        return {
            "chat_ready": True,
            "status": "ready",
            "message": "Document is ready for chat",
            "document_info": {
                "filename": doc_info.filename,
                "total_pages": doc_info.total_pages,
                "total_chunks": doc_info.total_chunks,
                "tlf_outputs_found": doc_info.tlf_outputs_found
            },
            "available_sources": sources
        }
        
    except Exception as e:
        logger.error(f"Error checking chat readiness for document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/chat/examples")
async def get_chat_examples():
    """Get example chat queries for different types of clinical data."""
    
    return {
        "examples": {
            "demographics": [
                "What are the baseline demographics of the study participants?",
                "How many patients were enrolled in each treatment group?",
                "What was the average age of participants?"
            ],
            "safety": [
                "What were the most common adverse events?",
                "Were there any serious adverse events related to treatment?",
                "How did the safety profile compare between treatment groups?"
            ],
            "efficacy": [
                "What were the primary efficacy results?",
                "Did the treatment show statistical significance?",
                "How did efficacy compare between different dose levels?"
            ],
            "follow_up": [
                "Can you explain that in more detail?",
                "What about the secondary endpoints?",
                "How does this compare to what you mentioned earlier?",
                "Were there any subgroup analyses?"
            ]
        },
        "tips": [
            "Ask follow-up questions to get more detailed information",
            "Reference specific table numbers if you know them",
            "Ask for comparisons between treatment groups",
            "Request clarification on clinical terminology",
            "Ask about statistical significance and confidence intervals"
        ]
    }

# For running directly
if __name__ == "__main__":
    import uvicorn
    
    if is_connect:
        logger.info("🚀 Starting on Posit Connect (Production)")
    elif is_workbench:
        logger.info("🚀 Starting on Posit Workbench (Development)")
        uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info", reload=True)
    else:
        logger.info("🚀 Starting in local development")
        uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info", reload=True)
