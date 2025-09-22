# backend/main.py
import sys
import os
import subprocess
import logging
import asyncio
import re
import time
from pathlib import Path
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

# Configure logging for Connect with explicit stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.StreamHandler(sys.stderr)
    ],
    force=True
)
logger = logging.getLogger(__name__)

# Environment detection
is_connect = bool(os.getenv("RSTUDIO_CONNECT_URL"))
is_workbench = bool(os.getenv("RS_SERVER_URL")) and not is_connect
port = int(os.getenv("PORT", "8000"))

logger.info(f"🚀 Starting JazzVIBE - Environment: {'Connect' if is_connect else 'Workbench' if is_workbench else 'Local'}")

# Service initialization state - using a class for better encapsulation
class ServiceManager:
    """Manages service lifecycle and ensures proper initialization."""
    
    def __init__(self):
        self.document_service = None
        self.query_service = None
        self.storage_service = None
        self.chat_service = None
        self.initialization_complete = False
        self.initialization_error = None
        self.initialization_status = "pending"
        self._lock = asyncio.Lock()
        self._initialization_task = None
    
    async def initialize(self, force=False):
        """Initialize services with proper locking for multi-worker environments."""
        async with self._lock:
            # Skip if already initialized and not forcing
            if self.initialization_complete and not force:
                logger.info("✅ Services already initialized")
                return True
            
            # Reset state if forcing
            if force:
                logger.info("🔄 Forcing service re-initialization...")
                self.initialization_complete = False
                self.initialization_error = None
            
            try:
                self.initialization_status = "initializing"
                logger.info("🔧 Starting service initialization...")
                
                # Import and get configuration
                config = None
                if is_connect or is_workbench:
                    try:
                        from app.core.posit_config import get_posit_config
                        config = get_posit_config()
                        logger.info(f"✅ Using Posit configuration: {config.get_environment_name()}")
                    except ImportError as e:
                        logger.warning(f"Could not import Posit config: {e}, using standard config")
                        from app.core.config import get_config
                        config = get_config()
                else:
                    from app.core.config import get_config
                    config = get_config()
                
                # Log configuration details
                logger.info(f"📋 Configuration loaded:")
                logger.info(f"   - Vector store enabled: {config.use_vector_store}")
                logger.info(f"   - Vector store type: {config.vector_store_type}")
                logger.info(f"   - MongoDB enabled: {config.is_mongodb_enabled()}")
                
                # Initialize Bedrock LLM
                logger.info("🤖 Initializing Bedrock LLM...")
                llm = None
                
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
                
                logger.info("✅ Bedrock LLM initialized successfully")
                
                # Initialize storage service
                logger.info("🗄️ Initializing storage service...")
                from app.services.storage_service import StorageService
                
                if config.is_mongodb_enabled():
                    logger.info("📊 Initializing MongoDB Atlas vector store...")
                    mongodb_config = config.get_mongodb_config()
                    self.storage_service = StorageService(
                        mongodb_connection_string=mongodb_config['connection_string'],
                        database_name=mongodb_config['database_name'],
                        collection_name=mongodb_config['collection_name']
                    )
                    logger.info("✅ MongoDB storage service initialized")
                else:
                    logger.info("💾 Using in-memory vector store")
                    self.storage_service = StorageService()
                    logger.info("✅ In-memory storage service initialized")
                
                # Initialize document service
                logger.info("📄 Initializing document service...")
                from app.services.document_service import DocumentService
                self.document_service = DocumentService(
                    llm=llm,
                    storage_service=self.storage_service,
                    config=config
                )
                logger.info("✅ Document service initialized")
                
                # Initialize query service
                logger.info("🔍 Initializing query service...")
                from app.services.query_service import QueryService
                self.query_service = QueryService(
                    llm=llm,
                    storage_service=self.storage_service
                )
                logger.info("✅ Query service initialized")
                
                # Initialize chat service
                logger.info("💬 Initializing chat service...")
                from app.services.chat_service import ChatService
                self.chat_service = ChatService(
                    llm=llm,
                    storage_service=self.storage_service,
                    query_service=self.query_service
                )
                logger.info("✅ Chat service initialized")
                
                # Verify all services
                if all([self.document_service, self.query_service, 
                       self.storage_service, self.chat_service]):
                    self.initialization_complete = True
                    self.initialization_status = "complete"
                    logger.info("✅ All services initialized successfully!")
                    return True
                else:
                    raise Exception("One or more services failed to initialize")
                
            except Exception as e:
                error_msg = f"Service initialization failed: {str(e)}"
                logger.error(f"❌ {error_msg}")
                logger.exception("Full initialization error:")
                self.initialization_error = error_msg
                self.initialization_status = "failed"
                return False
    
    async def ensure_initialized(self):
        """Ensure services are initialized before use."""
        if not self.initialization_complete:
            # Try to initialize if not already done
            success = await self.initialize()
            if not success:
                raise HTTPException(
                    status_code=503,
                    detail=f"Services not available: {self.initialization_error}"
                )
        return True
    
    def get_status(self):
        """Get current initialization status."""
        return {
            "initialized": self.initialization_complete,
            "status": self.initialization_status,
            "error": self.initialization_error,
            "services": {
                "document": self.document_service is not None,
                "query": self.query_service is not None,
                "storage": self.storage_service is not None,
                "chat": self.chat_service is not None
            }
        }

# Create global service manager instance
service_manager = ServiceManager()

# Helper functions for service detection
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

def detect_connect_path() -> str:
    """Detect Connect root path from environment variables."""
    connect_url = os.getenv("RSTUDIO_CONNECT_URL")
    if not connect_url:
        return ""
    
    try:
        from urllib.parse import urlparse
        parsed = urlparse(connect_url)
        
        if '/content/' in parsed.path:
            content_match = re.search(r'(/content/[^/]+)', parsed.path)
            if content_match:
                root_path = content_match.group(1)
                logger.info(f"✅ Detected Connect content path: {root_path}")
                return root_path
        elif parsed.path and parsed.path != '/':
            root_path = parsed.path.rstrip('/')
            logger.info(f"✅ Detected Connect vanity path: {root_path}")
            return root_path
        
        logger.warning(f"⚠️  Could not extract path from Connect URL: {connect_url}")
        return ""
        
    except Exception as e:
        logger.warning(f"⚠️  Error parsing Connect URL: {e}")
        return ""

# Determine root path
if is_connect:
    root_path = detect_connect_path()
    logger.info(f"🔗 Connect environment detected, root_path: '{root_path}'")
elif is_workbench:
    root_path = get_posit_root_path(port)
    logger.info(f"🔧 Workbench environment detected, root_path: '{root_path}'")
else:
    root_path = ""
    logger.info(f"💻 Local development environment")

# Static directory setup
static_dir = Path(__file__).parent.parent / "build"
if not static_dir.exists():
    static_dir = Path(__file__).parent.parent / "frontend/build"
    if not static_dir.exists():
        static_dir = Path(__file__).parent / "frontend/build"

logger.info(f"📁 Static directory: {static_dir} (exists: {static_dir.exists()})")

# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager with improved initialization."""
    logger.info("🚀 Starting Jazz VIBE API - Lifespan startup")
    
    # Initialize services during startup
    try:
        success = await service_manager.initialize()
        if not success:
            logger.error("⚠️  Service initialization failed during startup")
            # Don't raise - let app start but services will need lazy initialization
    except Exception as e:
        logger.error(f"⚠️  Startup initialization error: {e}")
        # Continue anyway - services will initialize on first use
    
    yield
    
    # Cleanup during shutdown
    logger.info("🛑 Shutting down Jazz VIBE API")
    try:
        if service_manager.storage_service and hasattr(service_manager.storage_service, 'close_connection'):
            service_manager.storage_service.close_connection()
            logger.info("✅ Storage connections closed")
    except Exception as e:
        logger.warning(f"⚠️  Cleanup error: {e}")

# Create FastAPI app
app = FastAPI(
    title="JazzVIBE API",
    description="API for processing and querying TLF documents",
    version="1.0.0",
    lifespan=lifespan
)

# Middleware classes
class ConnectPathDetectionMiddleware(BaseHTTPMiddleware):
    """Middleware for path detection in Connect environments."""
    
    def __init__(self, app, root_path: str = ""):
        super().__init__(app)
        self.root_path = root_path.rstrip('/') if root_path else ""
        logger.info(f"🔧 Path middleware initialized with root_path: '{self.root_path}'")
    
    async def dispatch(self, request: Request, call_next):
        original_path = request.url.path
        clean_path = original_path
        
        if clean_path.startswith('//'):
            temp_path = clean_path.lstrip('/')
            if '/' in temp_path and '.' in temp_path.split('/')[0]:
                parts = temp_path.split('/', 1)
                hostname_part = parts[0]
                path_part = parts[1] if len(parts) > 1 else ""
                
                if any(hostname_part.endswith(tld) for tld in ['.com', '.org', '.net', '.edu', '.gov']):
                    clean_path = '/' + path_part
            else:
                clean_path = '/' + temp_path
        
        if self.root_path and clean_path.startswith(self.root_path):
            clean_path = clean_path[len(self.root_path):]
            if not clean_path.startswith('/'):
                clean_path = '/' + clean_path
        
        clean_path = re.sub(r'/+', '/', clean_path)
        
        if not clean_path.startswith('/'):
            clean_path = '/' + clean_path
        
        request.scope['path'] = clean_path
        request.scope['raw_path'] = clean_path.encode()
        
        response = await call_next(request)
        return response

class ReactFallbackMiddleware(BaseHTTPMiddleware):
    """Middleware to serve React app for unmatched routes."""
    
    def get_react_html(self) -> str:
        """Get processed React HTML content."""
        if not static_dir.exists():
            return None
        
        index_file = static_dir / "index.html"
        if not index_file.exists():
            return None
        
        with open(index_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        if root_path:
            html_content = html_content.replace('href="./static/', f'href="{root_path}/static/')
            html_content = html_content.replace('src="./static/', f'src="{root_path}/static/')
            html_content = html_content.replace('href="/static/', f'href="{root_path}/static/')
            html_content = html_content.replace('src="/static/', f'src="{root_path}/static/')
            html_content = html_content.replace('href="./manifest.json"', f'href="{root_path}/manifest.json"')
            html_content = html_content.replace('href="./favicon.ico"', f'href="{root_path}/favicon.ico"')
            html_content = html_content.replace('%PUBLIC_URL%', root_path)
            
            if '<base href=' not in html_content:
                base_tag = f'<base href="{root_path}/">'
                html_content = html_content.replace('<head>', f'<head>\n    {base_tag}')
            
            js_injection = f'''
    <script>
      window.__POSIT_BASE_PATH__ = '{root_path}';
      window.__POSIT_ENVIRONMENT__ = '{"connect" if is_connect else "workbench" if is_workbench else "local"}';
    </script>'''
            
            if '</head>' in html_content:
                html_content = html_content.replace('</head>', f'{js_injection}\n  </head>')
        
        return html_content
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        if response.status_code == 404:
            path = request.url.path
            accept_header = request.headers.get("accept", "")
            
            is_api_route = (path.startswith("/api/") or path.startswith("/docs") or 
                          path.startswith("/openapi.json") or path.startswith("/redoc"))
            is_json_only_request = ("application/json" in accept_header and 
                                  "text/html" not in accept_header)
            is_static_file = path.startswith("/static/")
            
            if not is_api_route and not is_json_only_request and not is_static_file:
                react_html = self.get_react_html()
                if react_html:
                    return HTMLResponse(content=react_html)
        
        return response

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if root_path or is_connect:
    app.add_middleware(ConnectPathDetectionMiddleware, root_path=root_path)

if static_dir.exists():
    app.add_middleware(ReactFallbackMiddleware)

# Dependency injection with lazy initialization
async def get_document_service():
    """Get document service with lazy initialization."""
    await service_manager.ensure_initialized()
    if service_manager.document_service is None:
        raise HTTPException(status_code=503, detail="Document service not available")
    return service_manager.document_service

async def get_query_service():
    """Get query service with lazy initialization."""
    await service_manager.ensure_initialized()
    if service_manager.query_service is None:
        raise HTTPException(status_code=503, detail="Query service not available")
    return service_manager.query_service

async def get_storage_service():
    """Get storage service with lazy initialization."""
    await service_manager.ensure_initialized()
    if service_manager.storage_service is None:
        raise HTTPException(status_code=503, detail="Storage service not available")
    return service_manager.storage_service

async def get_chat_service():
    """Get chat service with lazy initialization."""
    await service_manager.ensure_initialized()
    if service_manager.chat_service is None:
        raise HTTPException(status_code=503, detail="Chat service not available")
    return service_manager.chat_service

# Include API routes
try:
    from app.api.routes import documents, queries, health, chat
    
    app.include_router(health.router, prefix="/api/v1/health", tags=["health"])
    app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
    app.include_router(queries.router, prefix="/api/v1/queries", tags=["queries"])
    app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
    
    logger.info("✅ API routes loaded successfully")
    
except ImportError as e:
    logger.error(f"❌ Failed to import routes: {e}")

# Health endpoints
@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    status = service_manager.get_status()
    
    overall_health = "healthy" if status["initialized"] else "degraded"
    if status["status"] == "failed":
        overall_health = "unhealthy"
    
    return {
        "status": overall_health,
        "initialization": status,
        "environment": {
            "is_connect": is_connect,
            "is_workbench": is_workbench,
            "root_path": root_path
        },
        "timestamp": datetime.now()
    }

@app.get("/api/v1/health/detailed")
async def health_detailed():
    """Detailed health check endpoint."""
    status = service_manager.get_status()
    
    # Try to get service-specific stats if initialized
    service_stats = {}
    if status["initialized"]:
        try:
            if service_manager.document_service:
                doc_count = await service_manager.document_service.get_document_count()
                service_stats["documents"] = doc_count
        except:
            pass
        
        try:
            if service_manager.query_service:
                query_count = await service_manager.query_service.get_query_count()
                service_stats["queries"] = query_count
        except:
            pass
        
        try:
            if service_manager.chat_service:
                chat_stats = await service_manager.chat_service.get_chat_statistics()
                service_stats["chat_sessions"] = chat_stats.get("total_sessions", 0)
        except:
            pass
    
    return {
        "status": "healthy" if status["initialized"] else "degraded",
        "initialization": status,
        "service_statistics": service_stats,
        "environment": {
            "is_connect": is_connect,
            "is_workbench": is_workbench,
            "root_path": root_path
        },
        "timestamp": datetime.now()
    }

# Debug endpoints
@app.post("/api/v1/admin/reinitialize-services")
async def reinitialize_services():
    """Force re-initialization of services."""
    success = await service_manager.initialize(force=True)
    return {
        "success": success,
        "status": service_manager.get_status(),
        "timestamp": datetime.now()
    }

# Static file serving
if static_dir and static_dir.exists():
    @app.get("/static/{file_path:path}")
    async def serve_static_files(file_path: str):
        """Serve static files with proper MIME types."""
        # Check if this is a PDF.js file request
        if file_path.startswith('pdfjs/'):
            # PDF.js files should be in public/static/pdfjs in the React build
            static_file_path = static_dir / "static" / file_path
        else:
            # Regular static files
            static_file_path = static_dir / "static" / file_path
        
        if not static_file_path.exists():
            # Try alternative location for PDF.js files
            if file_path.startswith('pdfjs/'):
                # Check if files are directly in build folder
                alt_path = static_dir / file_path
                if alt_path.exists():
                    static_file_path = alt_path
                else:
                    logger.warning(f"PDF.js file not found: {static_file_path}")
                    raise HTTPException(status_code=404, detail=f"Static file not found: {file_path}")
            else:
                raise HTTPException(status_code=404, detail="Static file not found")
        
        # Determine MIME type - COMPREHENSIVE list
        if file_path.endswith('.html'):
            media_type = "text/html"
        elif file_path.endswith('.css'):
            media_type = "text/css"
        elif file_path.endswith('.js') or file_path.endswith('.mjs'):
            media_type = "application/javascript"
        elif file_path.endswith('.json'):
            media_type = "application/json"
        elif file_path.endswith('.pdf'):
            media_type = "application/pdf"
        elif file_path.endswith('.png'):
            media_type = "image/png"
        elif file_path.endswith('.jpg') or file_path.endswith('.jpeg'):
            media_type = "image/jpeg"
        elif file_path.endswith('.gif'):
            media_type = "image/gif"
        elif file_path.endswith('.svg'):
            media_type = "image/svg+xml"
        elif file_path.endswith('.ico'):
            media_type = "image/x-icon"
        elif file_path.endswith('.woff'):
            media_type = "font/woff"
        elif file_path.endswith('.woff2'):
            media_type = "font/woff2"
        elif file_path.endswith('.ttf'):
            media_type = "font/ttf"
        elif file_path.endswith('.otf'):
            media_type = "font/otf"
        elif file_path.endswith('.eot'):
            media_type = "application/vnd.ms-fontobject"
        elif file_path.endswith('.map'):
            media_type = "application/json"  # Source maps
        elif file_path.endswith('.webmanifest'):
            media_type = "application/manifest+json"
        elif file_path.endswith('.xml'):
            media_type = "application/xml"
        elif file_path.endswith('.txt'):
            media_type = "text/plain"
        elif file_path.endswith('.md'):
            media_type = "text/markdown"
        elif file_path.endswith('.webp'):
            media_type = "image/webp"
        elif file_path.endswith('.mp4'):
            media_type = "video/mp4"
        elif file_path.endswith('.webm'):
            media_type = "video/webm"
        elif file_path.endswith('.mp3'):
            media_type = "audio/mpeg"
        elif file_path.endswith('.wav'):
            media_type = "audio/wav"
        elif file_path.endswith('.zip'):
            media_type = "application/zip"
        elif file_path.endswith('.tar'):
            media_type = "application/x-tar"
        elif file_path.endswith('.gz'):
            media_type = "application/gzip"
        else:
            # Default for unknown types
            media_type = "application/octet-stream"
        
        # Log PDF.js file requests for debugging
        if 'pdfjs' in file_path.lower():
            logger.info(f"Serving PDF.js file: {file_path} as {media_type}")
        
        # Special handling for HTML files to prevent download
        headers = {
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*"  # Allow cross-origin for PDF.js
        }
        
        # Ensure HTML files are displayed, not downloaded
        if media_type == "text/html":
            headers["Content-Disposition"] = "inline"
        
        return FileResponse(
            static_file_path, 
            media_type=media_type,
            headers=headers
        )
    
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

# Root endpoint
@app.get("/")
async def root(request: Request):
    """Root endpoint - serves API info or React app."""
    accept_header = request.headers.get("accept", "")
    
    if "application/json" in accept_header and "text/html" not in accept_header:
        return {
            "message": "JazzVIBE API",
            "version": "1.0.0",
            "status": service_manager.get_status(),
            "environment": {
                "is_connect": is_connect,
                "is_workbench": is_workbench,
                "root_path": root_path
            }
        }
    
    # Serve React app
    if static_dir.exists():
        middleware = ReactFallbackMiddleware(app)
        react_html = middleware.get_react_html()
        if react_html:
            return HTMLResponse(content=react_html)
    
    return {"message": "JazzVIBE API", "error": "React app not available"}

# Additional endpoints that require services
@app.get("/api/v1/mongodb/status")
async def get_mongodb_status(document_service=Depends(get_document_service)):
    """Get MongoDB status."""
    try:
        mongodb_stats = await document_service.get_mongodb_statistics()
        return mongodb_stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/storage/info")
async def get_storage_info(storage_service=Depends(get_storage_service)):
    """Get storage information."""
    try:
        storage_info = await storage_service.get_storage_info()
        return storage_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/debug/chat-status/{document_id}")
async def debug_chat_status(document_id: str):
    """Debug endpoint to check why chat might not be working."""
    
    result = {
        "document_id": document_id,
        "timestamp": datetime.now(),
        "services_initialized": service_manager.get_status(),
        "chat_checks": {},
        "vector_store_checks": {},
        "document_checks": {}
    }
    
    # Check if services are initialized
    if not service_manager.initialization_complete:
        result["error"] = "Services not fully initialized"
        result["initialization_error"] = service_manager.initialization_error
        return result
    
    # Check document exists and status
    try:
        if service_manager.document_service:
            doc_info = await service_manager.document_service.get_document_info(document_id)
            if doc_info:
                result["document_checks"]["exists"] = True
                result["document_checks"]["status"] = doc_info.status
                result["document_checks"]["total_chunks"] = doc_info.total_chunks
                result["document_checks"]["filename"] = doc_info.filename
            else:
                result["document_checks"]["exists"] = False
        else:
            result["document_checks"]["error"] = "Document service not available"
    except Exception as e:
        result["document_checks"]["error"] = str(e)
    
    # Check vector store configuration
    try:
        if service_manager.document_service:
            vector_status = await service_manager.document_service.get_vector_store_status()
            result["vector_store_checks"]["enabled"] = vector_status.get("enabled", False)
            result["vector_store_checks"]["type"] = vector_status.get("type", "unknown")
            result["vector_store_checks"]["storage_service_available"] = vector_status.get("storage_service_info", {})
    except Exception as e:
        result["vector_store_checks"]["error"] = str(e)
    
    # Check if vector index exists for document
    try:
        if service_manager.storage_service:
            vector_index = await service_manager.storage_service.get_index(document_id)
            result["vector_store_checks"]["index_exists"] = vector_index is not None
            
            if vector_index:
                # Try to get some stats about the index
                try:
                    # This is MongoDB specific but wrapped in try/catch
                    stats = await service_manager.storage_service.get_document_statistics(document_id)
                    result["vector_store_checks"]["index_stats"] = stats
                except:
                    result["vector_store_checks"]["index_stats"] = "Not available"
        else:
            result["vector_store_checks"]["storage_service"] = "Not available"
    except Exception as e:
        result["vector_store_checks"]["index_error"] = str(e)
    
    # Check chat service availability
    try:
        if service_manager.chat_service:
            result["chat_checks"]["service_available"] = True
            
            # Try to get chat sessions for this document
            try:
                sessions = await service_manager.chat_service.list_chat_sessions(
                    document_id=document_id,
                    limit=1
                )
                result["chat_checks"]["can_list_sessions"] = True
                result["chat_checks"]["existing_sessions"] = len(sessions)
            except Exception as e:
                result["chat_checks"]["session_list_error"] = str(e)
                
        else:
            result["chat_checks"]["service_available"] = False
    except Exception as e:
        result["chat_checks"]["error"] = str(e)
    
    # Final determination
    chat_ready = (
        result["document_checks"].get("exists", False) and
        result["document_checks"].get("status") == "completed" and
        result["vector_store_checks"].get("index_exists", False) and
        result["chat_checks"].get("service_available", False)
    )
    
    result["chat_ready"] = chat_ready
    result["chat_ready_reason"] = []
    
    if not result["document_checks"].get("exists", False):
        result["chat_ready_reason"].append("Document not found")
    if result["document_checks"].get("status") != "completed":
        result["chat_ready_reason"].append(f"Document status is {result['document_checks'].get('status')}")
    if not result["vector_store_checks"].get("index_exists", False):
        result["chat_ready_reason"].append("Vector index not found")
    if not result["chat_checks"].get("service_available", False):
        result["chat_ready_reason"].append("Chat service not available")
    
    return result

@app.get("/api/v1/document/{document_id}/chat-ready")
async def check_document_chat_ready(
    document_id: str,
    document_service=Depends(get_document_service),
    storage_service=Depends(get_storage_service),
    query_service=Depends(get_query_service)
):
    """Check if document is ready for chat with comprehensive checks."""
    try:
        # Initialize response
        response = {
            "chat_ready": False,
            "status": "checking",
            "message": "Checking chat readiness...",
            "checks": {
                "document_exists": False,
                "document_completed": False,
                "vector_index_exists": False,
                "chat_service_available": False
            }
        }
        
        # Check 1: Document exists
        doc_info = await document_service.get_document_info(document_id)
        if not doc_info:
            response["status"] = "document_not_found"
            response["message"] = "Document not found"
            return response
        
        response["checks"]["document_exists"] = True
        response["document_info"] = {
            "filename": doc_info.filename,
            "total_pages": doc_info.total_pages,
            "total_chunks": doc_info.total_chunks,
            "tlf_outputs_found": doc_info.tlf_outputs_found
        }
        
        # Check 2: Document is completed
        if doc_info.status != "completed":
            response["status"] = doc_info.status
            response["message"] = f"Document still processing: {doc_info.status}"
            return response
        
        response["checks"]["document_completed"] = True
        
        # Check 3: Vector index exists
        try:
            vector_index = await storage_service.get_index(document_id)
            if not vector_index:
                response["status"] = "no_index"
                response["message"] = "Document processed but vector index not available"
                
                # Check if vector store is enabled
                vector_status = await document_service.get_vector_store_status()
                response["vector_store_info"] = {
                    "enabled": vector_status.get("enabled", False),
                    "type": vector_status.get("type", "unknown")
                }
                
                if not vector_status.get("enabled", False):
                    response["message"] = "Vector store is disabled - chat not available"
                
                return response
            
            response["checks"]["vector_index_exists"] = True
        except Exception as e:
            logger.error(f"Error checking vector index for {document_id}: {e}")
            response["status"] = "index_error"
            response["message"] = f"Error checking vector index: {str(e)}"
            return response
        
        # Check 4: Chat service is available
        try:
            # Test that we can access the chat service
            if not service_manager.chat_service:
                response["status"] = "chat_service_unavailable"
                response["message"] = "Chat service is not initialized"
                return response
            
            response["checks"]["chat_service_available"] = True
        except Exception as e:
            logger.error(f"Error checking chat service: {e}")
            response["status"] = "chat_service_error"
            response["message"] = f"Chat service error: {str(e)}"
            return response
        
        # Check 5: Try to get available sources
        try:
            sources = await query_service.get_available_sources(document_id)
            response["available_sources"] = sources
        except Exception as e:
            logger.warning(f"Could not get sources for {document_id}: {e}")
            # This is not a fatal error
        
        # All checks passed
        response["chat_ready"] = True
        response["status"] = "ready"
        response["message"] = "Document is ready for chat"
        
        # Add storage statistics if available
        try:
            if hasattr(storage_service, 'get_document_statistics'):
                doc_stats = await storage_service.get_document_statistics(document_id)
                response["storage_stats"] = doc_stats
        except Exception as e:
            logger.warning(f"Could not get document statistics: {e}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking chat readiness for document {document_id}: {e}")
        logger.exception("Full error:")
        return {
            "chat_ready": False,
            "status": "error",
            "message": f"Error checking chat readiness: {str(e)}",
            "error_details": str(e)
        }

@app.get("/api/v1/debug/connect-environment")
async def debug_connect_environment():
    """Debug Connect-specific environment and service issues."""
    
    result = {
        "environment": {
            "is_connect": is_connect,
            "is_workbench": is_workbench,
            "connect_url": os.getenv("RSTUDIO_CONNECT_URL", "not_set"),
            "root_path": root_path,
            "port": port
        },
        "service_manager": service_manager.get_status(),
        "config_check": {},
        "mongodb_check": {},
        "aws_check": {}
    }
    
    # Check configuration
    try:
        if is_connect:
            from app.core.posit_config import get_posit_config
            config = get_posit_config()
            result["config_check"] = {
                "environment_name": config.get_environment_name(),
                "vector_store_enabled": config.use_vector_store,
                "vector_store_type": config.vector_store_type,
                "mongodb_enabled": config.is_mongodb_enabled(),
                "storage_path": str(config.base_storage_path)
            }
            
            # MongoDB specific checks
            if config.is_mongodb_enabled():
                mongo_config = config.get_mongodb_config()
                result["mongodb_check"] = {
                    "connection_string_set": bool(mongo_config.get("connection_string")),
                    "database": mongo_config.get("database_name"),
                    "collection": mongo_config.get("collection_name")
                }
                
                # Test MongoDB connection
                if service_manager.storage_service:
                    try:
                        storage_info = await service_manager.storage_service.get_storage_info()
                        result["mongodb_check"]["connection_test"] = "success"
                        result["mongodb_check"]["storage_info"] = storage_info
                    except Exception as e:
                        result["mongodb_check"]["connection_test"] = "failed"
                        result["mongodb_check"]["connection_error"] = str(e)
            
            # AWS checks
            result["aws_check"] = {
                "access_key_set": bool(os.getenv("AWS_ACCESS_KEY_ID")),
                "secret_key_set": bool(os.getenv("AWS_SECRET_ACCESS_KEY")),
                "region": config.aws_region
            }
            
    except Exception as e:
        result["config_check"]["error"] = str(e)
    
    # Check specific services
    if service_manager.initialization_complete:
        # Test each service
        tests = {}
        
        # Test document service
        try:
            if service_manager.document_service:
                doc_count = await service_manager.document_service.get_document_count()
                tests["document_service"] = f"OK - {doc_count} documents"
        except Exception as e:
            tests["document_service"] = f"Error: {str(e)}"
        
        # Test storage service
        try:
            if service_manager.storage_service:
                storage_info = await service_manager.storage_service.get_storage_info()
                tests["storage_service"] = f"OK - {storage_info.get('storage_type', 'unknown')} type"
        except Exception as e:
            tests["storage_service"] = f"Error: {str(e)}"
        
        # Test chat service
        try:
            if service_manager.chat_service:
                stats = await service_manager.chat_service.get_chat_statistics()
                tests["chat_service"] = f"OK - {stats.get('total_sessions', 0)} sessions"
        except Exception as e:
            tests["chat_service"] = f"Error: {str(e)}"
        
        result["service_tests"] = tests
    
    return result

@app.get("/api/v1/debug/reinitialize-for-document/{document_id}")
async def reinitialize_for_document(document_id: str):
    """Reinitialize services and check specific document readiness."""
    
    result = {
        "document_id": document_id,
        "timestamp": datetime.now(),
        "steps": []
    }
    
    # Step 1: Force service reinitialization
    result["steps"].append("Reinitializing services...")
    init_success = await service_manager.initialize(force=True)
    result["service_init_success"] = init_success
    
    if not init_success:
        result["error"] = "Service initialization failed"
        result["error_details"] = service_manager.initialization_error
        return result
    
    result["steps"].append("Services reinitialized successfully")
    
    # Step 2: Check document
    result["steps"].append(f"Checking document {document_id}...")
    
    try:
        # Get document info
        doc_info = await service_manager.document_service.get_document_info(document_id)
        if not doc_info:
            result["error"] = "Document not found"
            return result
        
        result["document"] = {
            "exists": True,
            "status": doc_info.status,
            "filename": doc_info.filename,
            "chunks": doc_info.total_chunks
        }
        
        # Check vector index
        result["steps"].append("Checking vector index...")
        vector_index = await service_manager.storage_service.get_index(document_id)
        result["vector_index_exists"] = vector_index is not None
        
        if not vector_index:
            # Try to rebuild index if document has chunks
            if doc_info.total_chunks > 0:
                result["steps"].append("Vector index missing but chunks exist - may need reprocessing")
            else:
                result["steps"].append("No chunks found - document may need reprocessing")
        
        # Final chat readiness
        chat_ready = (
            doc_info.status == "completed" and
            vector_index is not None and
            service_manager.chat_service is not None
        )
        
        result["chat_ready"] = chat_ready
        result["chat_ready_details"] = {
            "document_completed": doc_info.status == "completed",
            "vector_index_exists": vector_index is not None,
            "chat_service_available": service_manager.chat_service is not None
        }
        
    except Exception as e:
        result["error"] = str(e)
        logger.exception("Error checking document:")
    
    return result

@app.get("/api/v1/chat/examples")
async def get_chat_examples():
    """Get example chat queries."""
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
            ]
        },
        "tips": [
            "Ask follow-up questions to get more detailed information",
            "Reference specific table numbers if you know them",
            "Ask for comparisons between treatment groups"
        ]
    }

@app.get("/debug-paths")
async def debug_path_detection_simple(request: Request):
    """Debug endpoint for path detection issues."""
    
    # Get request details
    request_url = str(request.url)
    request_path = request.url.path
    
    logger.info(f"=== Debug Path Extraction ===")
    logger.info(f"Original request_path: '{request_path}'")
    
    clean_request_path = request_path
    extraction_steps = []
    
    if clean_request_path.startswith('//'):
        extraction_steps.append(f"Step 1: Starts with '//', original: '{clean_request_path}'")
        # Remove leading double slashes and extract path
        clean_request_path = clean_request_path.lstrip('/')
        extraction_steps.append(f"Step 2: After lstrip('/'): '{clean_request_path}'")
        
        # Look for any hostname pattern (generic domain detection)
        if '.' in clean_request_path and '/' in clean_request_path:
            extraction_steps.append("Step 3: Contains '.' and '/', checking for hostname")
            parts = clean_request_path.split('/', 1)
            if len(parts) > 1:
                first_part = parts[0]
                if '.' in first_part and (first_part.endswith('.com') or first_part.endswith('.org') or first_part.endswith('.net')):
                    clean_request_path = '/' + parts[1]
                    extraction_steps.append(f"Step 4: Hostname detected '{first_part}', extracted path: '{clean_request_path}'")
                else:
                    clean_request_path = '/' + clean_request_path
                    extraction_steps.append(f"Step 4: No hostname pattern, added leading slash: '{clean_request_path}'")
            else:
                clean_request_path = '/'
                extraction_steps.append("Step 4: Single part, using root '/'")
        else:
            clean_request_path = '/' + clean_request_path
            extraction_steps.append(f"Step 3: No hostname pattern, added leading slash: '{clean_request_path}'")
    
    # Clean up any remaining double slashes
    pre_cleanup = clean_request_path
    clean_request_path = re.sub(r'/+', '/', clean_request_path)
    if pre_cleanup != clean_request_path:
        extraction_steps.append(f"Step 5: Cleaned double slashes: '{pre_cleanup}' -> '{clean_request_path}'")
    
    # Pattern matching
    detected_base_path = ""
    pattern_info = {}
    
    # Posit Workbench pattern: /s/{session}/p/{port}/
    workbench_match = re.search(r'^(/s/[^/]+/p/[^/]+)', clean_request_path)
    if workbench_match:
        detected_base_path = workbench_match.group(1)
        pattern_info["workbench_detected"] = True
        pattern_info["workbench_match"] = detected_base_path
    else:
        pattern_info["workbench_detected"] = False
    
    # Posit Connect pattern: /connect/...
    if clean_request_path.startswith('/connect/'):
        connect_match = re.search(r'^(/connect/[^/]*)', clean_request_path)
        if connect_match:
            detected_base_path = connect_match.group(1)
            pattern_info["connect_detected"] = True
            pattern_info["connect_match"] = detected_base_path
        else:
            pattern_info["connect_detected"] = False
    else:
        pattern_info["connect_detected"] = False
    
    # Additional analysis
    hostname_analysis = {}
    if request_path.startswith('//'):
        stripped = request_path.lstrip('/')
        if '/' in stripped:
            potential_hostname = stripped.split('/')[0]
            if '.' in potential_hostname:
                hostname_analysis["hostname_detected"] = potential_hostname
                hostname_analysis["is_domain"] = any(potential_hostname.endswith(tld) for tld in ['.com', '.org', '.net', '.edu'])
            else:
                hostname_analysis["hostname_detected"] = None
                hostname_analysis["is_domain"] = False
    
    return {
        "request_url": request_url,
        "request_path": request_path,
        "clean_request_path": clean_request_path,
        "detected_base_path": detected_base_path,
        "fastapi_root_path": app.root_path if 'app' in globals() else "unknown",
        "extraction_steps": extraction_steps,
        "pattern_info": pattern_info,
        "hostname_analysis": hostname_analysis,
        "detection_patterns": {
            "workbench_pattern": r'^(/s/[^/]+/p/[^/]+)',
            "connect_pattern": r'^(/connect/[^/]*)',
        },
        "path_analysis": {
            "starts_with_double_slash": request_path.startswith('//'),
            "contains_domain": '.' in request_path and any(tld in request_path for tld in ['.com', '.org', '.net']),
            "path_after_cleanup": clean_request_path,
            "environment_detected": "workbench" if workbench_match else ("connect" if clean_request_path.startswith('/connect/') else "unknown")
        },
        "environment_vars": {
            "RS_SERVER_URL": os.getenv("RS_SERVER_URL", "not_set"),
            "RSTUDIO_CONNECT_URL": os.getenv("RSTUDIO_CONNECT_URL", "not_set"),
            "PORT": os.getenv("PORT", "8000")
        }
    }

@app.get("/debug/static-files")
async def debug_static_files():
    """Debug endpoint to check static file availability."""
    import os
    
    result = {
        "static_dir": str(static_dir),
        "static_dir_exists": static_dir.exists() if static_dir else False,
        "pdfjs_locations_checked": [],
        "pdfjs_found": False,
        "files_in_static": [],
        "build_structure": {}
    }
    
    if static_dir and static_dir.exists():
        # Check for PDF.js in various locations
        pdfjs_paths = [
            static_dir / "static" / "pdfjs" / "web" / "viewer.html",
            static_dir / "pdfjs" / "web" / "viewer.html",
            static_dir / "static" / "pdfjs" / "viewer.html",
        ]
        
        for path in pdfjs_paths:
            result["pdfjs_locations_checked"].append({
                "path": str(path),
                "exists": path.exists()
            })
            if path.exists():
                result["pdfjs_found"] = True
                result["pdfjs_actual_path"] = str(path)
        
        # List files in static directory
        try:
            static_subdir = static_dir / "static"
            if static_subdir.exists():
                for item in static_subdir.iterdir():
                    if item.is_dir():
                        result["files_in_static"].append(f"[DIR] {item.name}")
                        # If it's pdfjs dir, check its contents
                        if item.name == "pdfjs":
                            pdfjs_contents = []
                            for pdfjs_item in item.iterdir():
                                pdfjs_contents.append(pdfjs_item.name)
                            result["pdfjs_contents"] = pdfjs_contents
                    else:
                        result["files_in_static"].append(item.name)
        except Exception as e:
            result["static_listing_error"] = str(e)
        
        # Check build directory structure
        try:
            for root, dirs, files in os.walk(str(static_dir)):
                rel_path = os.path.relpath(root, str(static_dir))
                if 'pdfjs' in rel_path.lower() or rel_path == '.':
                    result["build_structure"][rel_path] = {
                        "dirs": dirs[:5],  # Limit to first 5
                        "files": [f for f in files if f.endswith(('.html', '.js'))][:5]
                    }
        except Exception as e:
            result["walk_error"] = str(e)
    
    return result

@app.get("/debug/pdfjs-test")
async def test_pdfjs_viewer():
    """Test endpoint to verify PDF.js viewer accessibility."""
    
    # Create a simple test page that loads PDF.js viewer
    test_html = """<!DOCTYPE html>
<html>
<head>
    <title>PDF.js Test</title>
</head>
<body>
    <h1>PDF.js Viewer Test</h1>
    <p>Testing PDF.js viewer loading...</p>
    
    <h2>Test 1: Direct iframe load</h2>
    <iframe src="/static/pdfjs/web/viewer.html" width="800" height="400" style="border: 1px solid black;"></iframe>
    
    <h2>Test 2: JavaScript detection</h2>
    <div id="test-result"></div>
    
    <script>
        // Test if viewer.html is accessible
        fetch('/static/pdfjs/web/viewer.html')
            .then(response => {
                const result = document.getElementById('test-result');
                if (response.ok) {
                    result.innerHTML = '<p style="color: green;">✓ viewer.html is accessible (Status: ' + response.status + ')</p>';
                    result.innerHTML += '<p>Content-Type: ' + response.headers.get('content-type') + '</p>';
                } else {
                    result.innerHTML = '<p style="color: red;">✗ viewer.html not accessible (Status: ' + response.status + ')</p>';
                }
            })
            .catch(error => {
                document.getElementById('test-result').innerHTML = '<p style="color: red;">✗ Error: ' + error + '</p>';
            });
    </script>
</body>
</html>"""
    
    return HTMLResponse(content=test_html)

if __name__ == "__main__":
    import uvicorn
    
    if is_connect:
        logger.info("🚀 Running on Posit Connect")
        # Connect handles the server startup
    elif is_workbench:
        logger.info("🚀 Starting on Posit Workbench")
        uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info", reload=True)
    else:
        logger.info("🚀 Starting in local development")
        uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info", reload=True)
