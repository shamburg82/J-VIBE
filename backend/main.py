# backend/main.py
import sys
import os
import subprocess
import logging
import importlib.util
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
import threading
from functools import partial
import atexit

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

# Global state for initialization
# INITIALIZATION_LOCK = threading.Lock()
INITIALIZATION_COMPLETE = False
INITIALIZATION_ERROR = None
INITIALIZATION_STATUS = "pending"

# Global service variables - Initialize to None but will be set during startup
document_service = None
query_service = None
storage_service = None
chat_service = None

def install_package_runtime(package_spec, timeout=300):
    """Install a package at runtime with better error handling."""
    cmd = [sys.executable, "-m", "pip", "install", "--no-cache-dir", "--no-deps", "--quiet", package_spec]
    
    logger.info(f"Installing {package_spec} with --no-deps")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        
        if result.returncode == 0:
            logger.info(f"✅ Successfully installed {package_spec}")
            return True
        else:
            logger.error(f"❌ Failed to install {package_spec}: {result.stderr}")
            logger.error(f"   stdout: {result.stdout}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error(f"❌ Installation of {package_spec} timed out after {timeout}s")
        return False
    except Exception as e:
        logger.error(f"❌ Exception during installation of {package_spec}: {e}")
        return False

def check_and_install_packages():
    """Check and install required packages for Connect environment."""
    global INITIALIZATION_ERROR, INITIALIZATION_STATUS
    
    try:
        INITIALIZATION_STATUS = "installing_packages"
        logger.info("🔧 Checking required packages for Connect deployment...")
        
        # Check current package availability
        packages_needed = []
        
        try:
            import llama_index.llms.bedrock_converse
            logger.info("✅ bedrock_converse available")
        except ImportError:
            logger.info("❌ bedrock_converse not available, will install")
            packages_needed.append("llama-index-llms-bedrock-converse==0.6.0")
        
        try:
            import aioboto3
            logger.info("✅ aioboto3 available") 
        except ImportError:
            logger.info("❌ aioboto3 not available, will install")
            packages_needed.append("aioboto3==13.4.0")
        
        # Install missing packages
        if packages_needed:
            logger.info(f"Installing {len(packages_needed)} missing packages...")
            
            for package in packages_needed:
                success = install_package_runtime(package)
                if not success:
                    error_msg = f"Failed to install {package}"
                    logger.error(f"❌ {error_msg}")
                    INITIALIZATION_ERROR = error_msg
                    return False
            
            # Verify installations
            logger.info("🔍 Verifying package installations...")
            
            try:
                import llama_index.llms.bedrock_converse
                logger.info("✅ bedrock_converse import successful after installation")
            except ImportError as e:
                error_msg = f"bedrock_converse still not importable after installation: {e}"
                logger.error(f"❌ {error_msg}")
                INITIALIZATION_ERROR = error_msg
                return False
            
            try:
                import aioboto3
                logger.info("✅ aioboto3 import successful after installation")
            except ImportError as e:
                error_msg = f"aioboto3 still not importable after installation: {e}"
                logger.error(f"❌ {error_msg}")
                INITIALIZATION_ERROR = error_msg
                return False
        
        logger.info("✅ All required packages are available")
        return True
        
    except Exception as e:
        error_msg = f"Package check/installation failed: {str(e)}"
        logger.error(f"❌ {error_msg}")
        INITIALIZATION_ERROR = error_msg
        return False
 
# Run package installation immediately for Connect
SKIP_PACKAGE_INSTALL = os.getenv("SKIP_PACKAGE_INSTALL", "false").lower() == "true"

if not SKIP_PACKAGE_INSTALL:
    # Your existing package installation code
    package_install_success = check_and_install_packages()
else:
    logger.info("Skipping package installation (SKIP_PACKAGE_INSTALL=true)")
    package_install_success = True

if not package_install_success:
    logger.error("❌ Package installation failed - some features may not work")
    logger.error(f"   Error: {INITIALIZATION_ERROR}")



# Continue with regular imports
import re
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
# try:
#     from app.services.storage_service import StorageService
#     from app.services.document_service import DocumentService  
#     from app.services.query_service import QueryService
#     from app.services.chat_service import ChatService
#     logger.info("✅ Service imports successful")
# except ImportError as e:
#     logger.error(f"❌ Service imports failed: {e}")

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
    
    # Check for Connect URL in environment
    connect_url = os.getenv("RSTUDIO_CONNECT_URL")
    if not connect_url:
        return ""
    
    try:
        from urllib.parse import urlparse
        parsed = urlparse(connect_url)
        
        # Extract path component, it should be something like:
        # https://dse-prod-cn.jazzpharma.com/content/{guid}
        # or https://dse-prod-cn.jazzpharma.com/{custom_name}
        
        # Check for content pattern (GUID-based URLs)
        if '/content/' in parsed.path:
            # Extract content path
            content_match = re.search(r'(/content/[^/]+)', parsed.path)
            if content_match:
                root_path = content_match.group(1)
                logger.info(f"✅ Detected Connect content path: {root_path}")
                return root_path
        
        # Check for custom vanity URL pattern
        elif parsed.path and parsed.path != '/':
            # For custom URLs, the path itself is the root path
            root_path = parsed.path.rstrip('/')
            logger.info(f"✅ Detected Connect vanity path: {root_path}")
            return root_path
        
        logger.warning(f"⚠️  Could not extract path from Connect URL: {connect_url}")
        return ""
        
    except Exception as e:
        logger.warning(f"⚠️  Error parsing Connect URL: {e}")
        return ""

# Environment detection with improved Connect detection
is_connect = bool(os.getenv("RSTUDIO_CONNECT_URL"))
is_workbench = bool(os.getenv("RS_SERVER_URL")) and not is_connect
port = int(os.getenv("PORT", "8000"))

# Determine root path based on environment
if is_connect:
    root_path = detect_connect_path()
    logger.info(f"🔗 Connect environment detected")
elif is_workbench:
    root_path = get_posit_root_path(port)
    logger.info(f"🔧 Workbench environment detected")
else:
    root_path = ""
    logger.info(f"💻 Local development environment")

logger.info(f"🚀 Starting JazzVIBE - Environment: {'Connect' if is_connect else 'Workbench' if is_workbench else 'Local'}")
logger.info(f"📁 Root path: '{root_path}'")

# Log environment variables for debugging
if is_connect:
    connect_url = os.getenv('RSTUDIO_CONNECT_URL', 'not set')
    logger.info(f"🔍 Connect URL: {connect_url}")
        
if is_workbench:
    logger.info(f"🔍 Server URL: {os.getenv('RS_SERVER_URL', 'not set')}")

# Define static_dir early
static_dir = Path(__file__).parent.parent / "build"
if not static_dir.exists():
    # Try alternative paths
    static_dir = Path(__file__).parent.parent / "frontend/build"
    if not static_dir.exists():
        static_dir = Path(__file__).parent / "frontend/build"

logger.info(f"📁 Static directory: {static_dir} (exists: {static_dir.exists()})")

async def initialize_services_with_retry(max_retries=3, delay=5):
    """Initialize services with retry logic for Connect deployment."""
    global document_service, query_service, storage_service, chat_service
    global INITIALIZATION_COMPLETE, INITIALIZATION_ERROR, INITIALIZATION_STATUS
    
    for attempt in range(max_retries):
        try:
            INITIALIZATION_STATUS = f"initializing_attempt_{attempt + 1}"
            logger.info(f"🔧 Service initialization attempt {attempt + 1}/{max_retries}")
            
            # Import and get configuration
            config = None
            if is_connect or is_workbench:
                try:
                    from app.core.posit_config import get_posit_config
                    config = get_posit_config()
                    logger.info(f"Using Posit configuration: {config.get_environment_name()}")
                except ImportError as e:
                    logger.warning(f"Could not import Posit config: {e}, using standard config")
                    from app.core.config import get_config
                    config = get_config()
            else:
                from app.core.config import get_config
                config = get_config()
            
            # Log configuration details
            logger.info(f"Vector store configuration:")
            logger.info(f"  - Enabled: {config.use_vector_store}")
            logger.info(f"  - Type: {config.vector_store_type}")
            
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
            
            if config.is_mongodb_enabled():
                logger.info("📊 Initializing MongoDB Atlas vector store...")
                from app.services.storage_service import StorageService
                
                mongodb_config = config.get_mongodb_config()
                storage_service = StorageService(
                    mongodb_connection_string=mongodb_config['connection_string'],
                    database_name=mongodb_config['database_name'],
                    collection_name=mongodb_config['collection_name']
                )
                
                logger.info("✅ MongoDB storage service initialized")
            else:
                logger.info("💾 Using in-memory vector store (fallback)")
                from app.services.storage_service import StorageService
                storage_service = StorageService()
                logger.warning("⚠️ MongoDB storage service loaded but will use fallback behavior")
            
            # Initialize document service
            logger.info("📄 Initializing document service...")
            from app.services.document_service import DocumentService
            document_service = DocumentService(
                llm=llm, 
                storage_service=storage_service,
                config=config
            )
            logger.info("✅ Document service initialized")
            
            # Initialize query service
            logger.info("🔍 Initializing query service...")
            from app.services.query_service import QueryService
            query_service = QueryService(llm=llm, storage_service=storage_service)
            logger.info("✅ Query service initialized")
            
            # Initialize chat service
            logger.info("💬 Initializing chat service...")
            from app.services.chat_service import ChatService
            chat_service = ChatService(
                llm=llm, 
                storage_service=storage_service, 
                query_service=query_service
            )
            logger.info("✅ Chat service initialized")
            
            # Verify all services are properly initialized
            if all([document_service, query_service, storage_service, chat_service]):
                INITIALIZATION_COMPLETE = True
                INITIALIZATION_STATUS = "complete"
                logger.info("✅ All services initialized successfully!")
                return True
            else:
                raise Exception("One or more services failed to initialize properly")
                
        except Exception as e:
            error_msg = f"Service initialization attempt {attempt + 1} failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            INITIALIZATION_ERROR = error_msg
            
            if attempt < max_retries - 1:
                logger.info(f"⏳ Retrying in {delay} seconds...")
                await asyncio.sleep(delay)
            else:
                INITIALIZATION_STATUS = "failed"
                logger.error("❌ All initialization attempts failed")
                return False
    
    return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - startup and shutdown."""
    global document_service, query_service, storage_service, chat_service
    
    # Startup
    logger.info("🚀 Starting Jazz VIBE API services")
    
    # Initialize services with retry logic
    success = await initialize_services_with_retry()
    
    if not success:
        logger.error("❌ Failed to initialize services after all retries")
        # Don't raise exception - let app start but services will show as not initialized
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Jazz VIBE API")
    
    # Clean up MongoDB connections
    if storage_service and hasattr(storage_service, 'close_connection'):
        try:
            storage_service.close_connection()
            logger.info("✅ MongoDB connections closed")
        except Exception as e:
            logger.warning(f"⚠️  Error closing MongoDB connections: {e}")

class ConnectPathDetectionMiddleware(BaseHTTPMiddleware):
    """Enhanced middleware for path detection in Connect environments."""
    
    def __init__(self, app, root_path: str = ""):
        super().__init__(app)
        self.root_path = root_path.rstrip('/') if root_path else ""
        logger.info(f"🔧 Path middleware initialized with root_path: '{self.root_path}'")
        
    async def dispatch(self, request: Request, call_next):
        original_path = request.url.path
        clean_path = original_path
        
        logger.debug(f"🔍 Processing request: {original_path}")
        
        # Handle Connect-style URLs that may come with full hostnames
        if clean_path.startswith('//'):
            logger.debug(f"🔧 Double slash detected: {clean_path}")
            temp_path = clean_path.lstrip('/')
            
            # Look for hostname patterns
            if '/' in temp_path and '.' in temp_path.split('/')[0]:
                parts = temp_path.split('/', 1)
                hostname_part = parts[0]
                path_part = parts[1] if len(parts) > 1 else ""
                
                # Check if first part looks like a hostname
                if any(hostname_part.endswith(tld) for tld in ['.com', '.org', '.net', '.edu', '.gov']):
                    clean_path = '/' + path_part
                    logger.debug(f"🔧 Extracted path from hostname URL: {clean_path}")
                else:
                    clean_path = '/' + temp_path
            else:
                clean_path = '/' + temp_path
        
        # Remove configured root path prefix if present
        if self.root_path and clean_path.startswith(self.root_path):
            clean_path = clean_path[len(self.root_path):]
            if not clean_path.startswith('/'):
                clean_path = '/' + clean_path
            logger.debug(f"🔧 Removed root path prefix: {clean_path}")
        
        # Clean up multiple slashes
        clean_path = re.sub(r'/+', '/', clean_path)
        
        # Special handling for Connect patterns
        if is_connect:
            # Look for Connect-specific patterns in the URL
            connect_patterns = [
                r'/connect/apps/[^/]+(/.*)?$',  # /connect/apps/{guid}/...
                r'/connect/#/apps/[^/]+(/.*)?$',  # /connect/#/apps/{guid}/...
                r'/content/[^/]+(/.*)?$',       # /content/{guid}/...
            ]
            
            for pattern in connect_patterns:
                match = re.search(pattern, original_path)
                if match:
                    # Extract the app-specific part
                    app_path = match.group(1) if match.group(1) else '/'
                    clean_path = app_path
                    logger.debug(f"🔗 Connect pattern matched, extracted: {clean_path}")
                    break
        
        # Ensure clean path starts with /
        if not clean_path.startswith('/'):
            clean_path = '/' + clean_path
        
        logger.debug(f"🔧 Final clean path: {clean_path}")
        
        # Update request scope
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
            logger.warning(f"📁 Static directory not found: {static_dir}")
            return None
            
        index_file = static_dir / "index.html"
        if not index_file.exists():
            logger.warning(f"📁 Index file not found: {index_file}")
            return None
        
        # Read HTML file
        with open(index_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Process base path if we have one
        if root_path:
            logger.debug(f"🔧 Processing HTML with root_path: {root_path}")
            
            # Replace static file paths
            html_content = html_content.replace('href="./static/', f'href="{root_path}/static/')
            html_content = html_content.replace('src="./static/', f'src="{root_path}/static/')
            html_content = html_content.replace('href="/static/', f'href="{root_path}/static/')
            html_content = html_content.replace('src="/static/', f'src="{root_path}/static/')
            
            # Replace manifest and favicon
            html_content = html_content.replace('href="./manifest.json"', f'href="{root_path}/manifest.json"')
            html_content = html_content.replace('href="./favicon.ico"', f'href="{root_path}/favicon.ico"')
            html_content = html_content.replace('href="/manifest.json"', f'href="{root_path}/manifest.json"')
            html_content = html_content.replace('href="/favicon.ico"', f'href="{root_path}/favicon.ico"')
            
            # Replace PUBLIC_URL placeholder
            html_content = html_content.replace('%PUBLIC_URL%', root_path)
            
            # Inject base tag if not present
            if '<base href=' not in html_content:
                base_tag = f'<base href="{root_path}/">'
                html_content = html_content.replace('<head>', f'<head>\n    {base_tag}')
            
            # Inject JavaScript configuration
            js_injection = f'''
    <script>
      window.__POSIT_BASE_PATH__ = '{root_path}';
      window.__POSIT_ENVIRONMENT__ = '{"connect" if is_connect else "workbench" if is_workbench else "local"}';
      console.log('JazzVIBE: Base path set to:', window.__POSIT_BASE_PATH__);
      console.log('JazzVIBE: Environment:', window.__POSIT_ENVIRONMENT__);
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
                    logger.debug(f"🔧 Serving React app for route: {path}")
                    return HTMLResponse(content=react_html)
                else:
                    logger.warning(f"⚠️  Could not serve React app for route: {path}")
        
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
if root_path or is_connect:
    app.add_middleware(ConnectPathDetectionMiddleware, root_path=root_path)

if static_dir.exists():
    app.add_middleware(ReactFallbackMiddleware)
    logger.info(f"📁 React app will be served from: {static_dir}")
else:
    logger.warning(f"📁 React build directory not found: {static_dir}")

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
    global INITIALIZATION_COMPLETE, INITIALIZATION_ERROR, INITIALIZATION_STATUS
    
    # Get service status
    services_initialized = {
        "document_service": document_service is not None,
        "query_service": query_service is not None,
        "storage_service": storage_service is not None,
        "chat_service": chat_service is not None
    }
    
    # Get vector store status if document service is available
    vector_status = {}
    if document_service:
        try:
            vector_status = await document_service.get_vector_store_status()
        except Exception as e:
            logger.warning(f"Could not get vector store status: {e}")
            vector_status = {"error": str(e)}
    
    overall_status = "healthy" if INITIALIZATION_COMPLETE else "degraded"
    if INITIALIZATION_STATUS == "failed":
        overall_status = "unhealthy"
    
    return {
        "status": overall_status,
        "initialization": {
            "complete": INITIALIZATION_COMPLETE,
            "status": INITIALIZATION_STATUS,
            "error": INITIALIZATION_ERROR
        },
        "root_path": root_path,
        "environment": {
            "is_connect": is_connect,
            "is_workbench": is_workbench,
            "port": os.getenv("PORT", "8000"),
            "connect_url": os.getenv("RSTUDIO_CONNECT_URL", "not_set"),
            "server_url": os.getenv("RS_SERVER_URL", "not_set")
        },
        "services_initialized": services_initialized,
        "vector_store": vector_status
    }

# Detailed health endpoint
@app.get("/api/v1/health")
async def health_detailed():
    """Detailed health endpoint with comprehensive status."""
    global INITIALIZATION_COMPLETE, INITIALIZATION_ERROR, INITIALIZATION_STATUS
    
    # Check each service individually
    services_status = {}
    
    if document_service:
        try:
            doc_count = await document_service.get_document_count()
            services_status["document_service"] = f"healthy - {doc_count} documents"
        except Exception as e:
            services_status["document_service"] = f"error - {str(e)}"
    else:
        services_status["document_service"] = "not initialized"
    
    if query_service:
        try:
            query_count = await query_service.get_query_count()
            services_status["query_service"] = f"healthy - {query_count} queries processed"
        except Exception as e:
            services_status["query_service"] = f"error - {str(e)}"
    else:
        services_status["query_service"] = "not initialized"
    
    if storage_service:
        try:
            storage_info = await storage_service.get_storage_info()
            services_status["storage_service"] = f"healthy - {storage_info.get('total_indexes', 0)} indexes"
        except Exception as e:
            services_status["storage_service"] = f"error - {str(e)}"
    else:
        services_status["storage_service"] = "not initialized"
    
    if chat_service:
        try:
            chat_stats = await chat_service.get_chat_statistics()
            services_status["chat_service"] = f"healthy - {chat_stats.get('total_sessions', 0)} sessions"
        except Exception as e:
            services_status["chat_service"] = f"error - {str(e)}"
    else:
        services_status["chat_service"] = "not initialized"
    
    # System resources
    try:
        import psutil
        memory_usage = psutil.virtual_memory()
        disk_usage = psutil.disk_usage('/')
        
        system_stats = {
            "memory_usage_percent": memory_usage.percent,
            "memory_available_gb": round(memory_usage.available / (1024**3), 2),
            "disk_usage_percent": disk_usage.percent,
            "disk_free_gb": round(disk_usage.free / (1024**3), 2),
            "cpu_count": psutil.cpu_count(),
            "uptime_seconds": int(time.time() - (time.time() - psutil.boot_time()))
        }
    except Exception as e:
        system_stats = {"error": f"Could not get system stats: {e}"}
    
    overall_status = "healthy" if INITIALIZATION_COMPLETE else "degraded"
    if INITIALIZATION_STATUS == "failed":
        overall_status = "unhealthy"
    
    return {
        "status": overall_status,
        "timestamp": datetime.now(),
        "initialization": {
            "complete": INITIALIZATION_COMPLETE,
            "status": INITIALIZATION_STATUS,
            "error": INITIALIZATION_ERROR,
            "packages_installed": package_install_success
        },
        "services": services_status,
        "system": system_stats,
        "environment": {
            "is_connect": is_connect,
            "is_workbench": is_workbench,
            "detected_root_path": root_path,
            "static_files_available": static_dir.exists()
        },
        "version": "1.0.0"
    }

# Enhanced debug endpoint for Connect path detection
@app.get("/debug/path-info")
async def debug_path_info(request: Request):
    """Enhanced debug endpoint for Connect path detection."""
    
    original_path = str(request.url.path)
    full_url = str(request.url)
    
    # Analyze the current request
    path_analysis = {
        "original_request": {
            "full_url": full_url,
            "path": original_path,
            "query": str(request.url.query),
            "hostname": request.url.hostname,
            "port": request.url.port,
            "scheme": request.url.scheme
        },
        "environment": {
            "is_connect": is_connect,
            "is_workbench": is_workbench,
            "detected_root_path": root_path,
            "connect_url": os.getenv("RSTUDIO_CONNECT_URL", "not_set"),
            "server_url": os.getenv("RS_SERVER_URL", "not_set")
        },
        "path_detection": {
            "configured_root_path": root_path,
            "static_dir_exists": static_dir.exists(),
            "static_dir_path": str(static_dir)
        },
        "request_headers": dict(request.headers),
        "connect_patterns": {
            "content_pattern": bool(re.search(r'/content/[^/]+', original_path)),
            "connect_apps_pattern": bool(re.search(r'/connect/apps/[^/]+', original_path)),
            "vanity_url_pattern": bool(re.search(r'^/[^/]+/?', original_path) and not original_path.startswith('/api'))
        }
    }
    
    # Test Connect URL parsing if available
    if is_connect and os.getenv("RSTUDIO_CONNECT_URL"):
        try:
            from urllib.parse import urlparse
            parsed = urlparse(os.getenv("RSTUDIO_CONNECT_URL"))
            path_analysis["connect_url_analysis"] = {
                "parsed_scheme": parsed.scheme,
                "parsed_hostname": parsed.hostname,
                "parsed_path": parsed.path,
                "content_pattern_in_env": '/content/' in parsed.path,
                "extracted_content_path": None
            }
            
            # Try to extract content path
            content_match = re.search(r'(/content/[^/]+)', parsed.path)
            if content_match:
                path_analysis["connect_url_analysis"]["extracted_content_path"] = content_match.group(1)
                
        except Exception as e:
            path_analysis["connect_url_analysis"] = {"error": str(e)}
    
    return path_analysis

# MongoDB-specific endpoints
@app.get("/api/v1/mongodb/status")
async def get_mongodb_status():
    """Get MongoDB Atlas vector store status and statistics."""
    
    if not document_service:
        raise HTTPException(status_code=503, detail="Document service not initialized")
    
    try:
        mongodb_stats = await document_service.get_mongodb_statistics()
        return mongodb_stats
    except Exception as e:
        logger.error(f"Error getting MongoDB status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get MongoDB status: {str(e)}")

@app.get("/api/v1/storage/info")
async def get_storage_info():
    """Get detailed storage information."""
    
    if not storage_service:
        raise HTTPException(status_code=503, detail="Storage service not initialized")
    
    try:
        storage_info = await storage_service.get_storage_info()
        return storage_info
    except Exception as e:
        logger.error(f"Error getting storage info: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get storage info: {str(e)}")

# Static files and specific routes
if static_dir and static_dir.exists():
    logger.info(f"📁 Serving React static files from: {static_dir}")
    
    @app.get("/static/{file_path:path}")
    async def serve_static_files(file_path: str):
        """Serve static files with correct MIME types."""
        static_file_path = static_dir / "static" / file_path
        
        if not static_file_path.exists():
            logger.warning(f"Static file not found: {static_file_path}")
            raise HTTPException(status_code=404, detail="Static file not found")
        
        # Determine MIME type based on file extension
        if file_path.endswith('.css'):
            media_type = "text/css"
        elif file_path.endswith('.js') or file_path.endswith('.mjs'):
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
        elif file_path.endswith('.html'):
            media_type = "text/html"
        elif file_path.endswith('.xml'):
            media_type = "application/xml"
        elif file_path.endswith('.txt'):
            media_type = "text/plain"
        elif file_path.endswith('.pdf'):
            media_type = "application/pdf"
        elif file_path.endswith('.zip'):
            media_type = "application/zip"
        elif file_path.endswith('.map'):
            media_type = "application/json"  # Source maps
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
            vector_status = await document_service.get_vector_store_status() if document_service else {}
            
            return {
                "message": "JazzVIBE API",
                "version": "1.0.0", 
                "root_path": root_path,
                "docs": f"{root_path}/docs" if root_path else "/docs",
                "health": f"{root_path}/api/v1/health" if root_path else "/api/v1/health",
                "vector_store": {
                    "enabled": vector_status.get("enabled", False),
                    "type": vector_status.get("type", "unknown")
                },
                "environment": {
                    "is_connect": is_connect,
                    "is_workbench": is_workbench,
                    "root_path_detected": bool(root_path)
                }
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
        vector_status = await document_service.get_vector_store_status() if document_service else {}
        
        return {
            "message": "JazzVIBE API",
            "version": "1.0.0",
            "root_path": root_path,
            "error": "React app not built",
            "vector_store": {
                "enabled": vector_status.get("enabled", False),
                "type": vector_status.get("type", "unknown")
            },
                "environment": {
                    "is_connect": is_connect,
                    "is_workbench": is_workbench,
                    "root_path_detected": bool(root_path)
                }
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
        
        # Get storage statistics for this document
        doc_stats = {}
        if hasattr(storage_service, 'get_document_statistics'):
            try:
                doc_stats = await storage_service.get_document_statistics(document_id)
            except Exception as e:
                logger.warning(f"Could not get document statistics: {e}")
        
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
            "available_sources": sources,
            "storage_stats": doc_stats
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


@app.get("/debug/service-initialization")
async def debug_service_initialization():
    """Debug service initialization step by step."""
    
    debug_info = {
        "timestamp": datetime.now(),
        "global_state": {
            "INITIALIZATION_COMPLETE": INITIALIZATION_COMPLETE,
            "INITIALIZATION_ERROR": INITIALIZATION_ERROR,
            "INITIALIZATION_STATUS": INITIALIZATION_STATUS,
        },
        "services_state": {
            "document_service": document_service is not None,
            "query_service": query_service is not None,
            "storage_service": storage_service is not None,
            "chat_service": chat_service is not None,
        },
        "manual_test_results": {},
        "step_by_step_test": []
    }
    
    # Test 1: Can we import the services?
    try:
        debug_info["step_by_step_test"].append("Testing service imports...")
        
        from app.core.config import get_config
        debug_info["step_by_step_test"].append("✅ Config import successful")
        
        from app.core.bedrock_setup import configure_bedrock_llm
        debug_info["step_by_step_test"].append("✅ Bedrock setup import successful")
        
        from app.services.storage_service import StorageService
        debug_info["step_by_step_test"].append("✅ Storage service import successful")
        
        from app.services.document_service import DocumentService
        debug_info["step_by_step_test"].append("✅ Document service import successful")
        
        from app.services.query_service import QueryService
        debug_info["step_by_step_test"].append("✅ Query service import successful")
        
        from app.services.chat_service import ChatService
        debug_info["step_by_step_test"].append("✅ Chat service import successful")
        
    except Exception as e:
        debug_info["step_by_step_test"].append(f"❌ Import failed: {str(e)}")
        debug_info["manual_test_results"]["import_error"] = str(e)
    
    # Test 2: Can we get config?
    try:
        debug_info["step_by_step_test"].append("Testing config loading...")
        
        if is_connect or is_workbench:
            try:
                from app.core.posit_config import get_posit_config
                config = get_posit_config()
                debug_info["step_by_step_test"].append("✅ Posit config loaded")
                debug_info["manual_test_results"]["config_type"] = "posit"
            except ImportError:
                from app.core.config import get_config
                config = get_config()
                debug_info["step_by_step_test"].append("✅ Standard config loaded (Posit import failed)")
                debug_info["manual_test_results"]["config_type"] = "standard"
        else:
            from app.core.config import get_config
            config = get_config()
            debug_info["step_by_step_test"].append("✅ Standard config loaded")
            debug_info["manual_test_results"]["config_type"] = "standard"
        
        debug_info["manual_test_results"]["vector_store_enabled"] = config.use_vector_store
        debug_info["manual_test_results"]["vector_store_type"] = config.vector_store_type
        debug_info["manual_test_results"]["mongodb_enabled"] = config.is_mongodb_enabled()
        
    except Exception as e:
        debug_info["step_by_step_test"].append(f"❌ Config loading failed: {str(e)}")
        debug_info["manual_test_results"]["config_error"] = str(e)
        return debug_info  # Stop here if config fails
    
    # Test 3: Can we create Bedrock LLM?
    try:
        debug_info["step_by_step_test"].append("Testing Bedrock LLM creation...")
        
        if is_connect or is_workbench:
            try:
                from app.core.posit_bedrock_setup import configure_bedrock_for_posit
                llm = await configure_bedrock_for_posit()
                debug_info["step_by_step_test"].append("✅ Posit Bedrock setup successful")
            except ImportError:
                from app.core.bedrock_setup import configure_bedrock_llm
                llm = await configure_bedrock_llm()
                debug_info["step_by_step_test"].append("✅ Standard Bedrock setup successful (Posit import failed)")
        else:
            from app.core.bedrock_setup import configure_bedrock_llm
            llm = await configure_bedrock_llm()
            debug_info["step_by_step_test"].append("✅ Standard Bedrock setup successful")
        
        debug_info["manual_test_results"]["llm_created"] = llm is not None
        
    except Exception as e:
        debug_info["step_by_step_test"].append(f"❌ Bedrock LLM creation failed: {str(e)}")
        debug_info["manual_test_results"]["llm_error"] = str(e)
        return debug_info  # Stop here if LLM fails
    
    # Test 4: Can we create storage service?
    try:
        debug_info["step_by_step_test"].append("Testing storage service creation...")
        
        if config.is_mongodb_enabled():
            debug_info["step_by_step_test"].append("Attempting MongoDB storage service...")
            mongodb_config = config.get_mongodb_config()
            test_storage = StorageService(
                mongodb_connection_string=mongodb_config['connection_string'],
                database_name=mongodb_config['database_name'],
                collection_name=mongodb_config['collection_name']
            )
            debug_info["step_by_step_test"].append("✅ MongoDB storage service created")
        else:
            debug_info["step_by_step_test"].append("Attempting in-memory storage service...")
            test_storage = StorageService()
            debug_info["step_by_step_test"].append("✅ In-memory storage service created")
        
        debug_info["manual_test_results"]["storage_created"] = True
        
    except Exception as e:
        debug_info["step_by_step_test"].append(f"❌ Storage service creation failed: {str(e)}")
        debug_info["manual_test_results"]["storage_error"] = str(e)
        test_storage = None
    
    # Test 5: Can we create document service?
    try:
        debug_info["step_by_step_test"].append("Testing document service creation...")
        
        test_doc_service = DocumentService(
            llm=llm, 
            storage_service=test_storage,
            config=config
        )
        debug_info["step_by_step_test"].append("✅ Document service created")
        debug_info["manual_test_results"]["document_service_created"] = True
        
    except Exception as e:
        debug_info["step_by_step_test"].append(f"❌ Document service creation failed: {str(e)}")
        debug_info["manual_test_results"]["document_service_error"] = str(e)
    
    # Test 6: Can we create other services?
    try:
        debug_info["step_by_step_test"].append("Testing query service creation...")
        test_query_service = QueryService(llm=llm, storage_service=test_storage)
        debug_info["step_by_step_test"].append("✅ Query service created")
        
        debug_info["step_by_step_test"].append("Testing chat service creation...")
        test_chat_service = ChatService(
            llm=llm, 
            storage_service=test_storage, 
            query_service=test_query_service
        )
        debug_info["step_by_step_test"].append("✅ Chat service created")
        
        debug_info["manual_test_results"]["all_services_created"] = True
        
    except Exception as e:
        debug_info["step_by_step_test"].append(f"❌ Additional service creation failed: {str(e)}")
        debug_info["manual_test_results"]["additional_services_error"] = str(e)
    
    # Summary
    debug_info["summary"] = {
        "can_create_services_manually": debug_info["manual_test_results"].get("all_services_created", False),
        "likely_issue": "Manual creation works but lifespan/async initialization doesn't" if debug_info["manual_test_results"].get("all_services_created", False) else "Service creation fundamentally broken",
        "recommendation": "Check lifespan function and async initialization logic" if debug_info["manual_test_results"].get("all_services_created", False) else "Fix service creation issues first"
    }
    
    return debug_info

@app.get("/debug/force-initialize-services")
async def force_initialize_services():
    """Force run the service initialization outside of lifespan."""
    global document_service, query_service, storage_service, chat_service
    global INITIALIZATION_COMPLETE, INITIALIZATION_ERROR, INITIALIZATION_STATUS
    
    result = {
        "timestamp": datetime.now(),
        "previous_state": {
            "INITIALIZATION_COMPLETE": INITIALIZATION_COMPLETE,
            "INITIALIZATION_STATUS": INITIALIZATION_STATUS,
            "services_initialized": {
                "document_service": document_service is not None,
                "query_service": query_service is not None,
                "storage_service": storage_service is not None,
                "chat_service": chat_service is not None,
            }
        },
        "initialization_steps": [],
        "final_state": {},
        "success": False
    }
    
    try:
        # Reset status
        INITIALIZATION_STATUS = "manual_initialization"
        INITIALIZATION_ERROR = None
        result["initialization_steps"].append("Starting manual initialization...")
        
        # Get config
        result["initialization_steps"].append("Loading configuration...")
        if is_connect or is_workbench:
            try:
                from app.core.posit_config import get_posit_config
                config = get_posit_config()
                result["initialization_steps"].append("✅ Posit config loaded")
            except ImportError:
                from app.core.config import get_config
                config = get_config()
                result["initialization_steps"].append("✅ Standard config loaded (posit import failed)")
        else:
            from app.core.config import get_config
            config = get_config()
            result["initialization_steps"].append("✅ Standard config loaded")
        
        # Initialize LLM
        result["initialization_steps"].append("Initializing Bedrock LLM...")
        if is_connect or is_workbench:
            try:
                from app.core.posit_bedrock_setup import configure_bedrock_for_posit
                llm = await configure_bedrock_for_posit()
            except ImportError:
                from app.core.bedrock_setup import configure_bedrock_llm
                llm = await configure_bedrock_llm()
        else:
            from app.core.bedrock_setup import configure_bedrock_llm
            llm = await configure_bedrock_llm()
        
        if not llm:
            raise Exception("Failed to initialize Bedrock LLM")
        result["initialization_steps"].append("✅ Bedrock LLM initialized")
        
        # Initialize storage service
        result["initialization_steps"].append("Initializing storage service...")
        try:
            from app.services.storage_service import StorageService  # Add this import
            
            if config.is_mongodb_enabled():
                mongodb_config = config.get_mongodb_config()
                storage_service = StorageService(
                    mongodb_connection_string=mongodb_config['connection_string'],
                    database_name=mongodb_config['database_name'],
                    collection_name=mongodb_config['collection_name']
                )
                result["initialization_steps"].append("✅ MongoDB storage service initialized")
            else:
                storage_service = StorageService()
                result["initialization_steps"].append("✅ In-memory storage service initialized")
        except ImportError as import_error:
            result["initialization_steps"].append(f"❌ StorageService import failed: {str(import_error)}")
            raise Exception(f"StorageService import failed: {str(import_error)}")
            
        
        # Initialize services
        result["initialization_steps"].append("Initializing document service...")
        document_service = DocumentService(llm=llm, storage_service=storage_service, config=config)
        result["initialization_steps"].append("✅ Document service initialized")
        
        result["initialization_steps"].append("Initializing query service...")
        query_service = QueryService(llm=llm, storage_service=storage_service)
        result["initialization_steps"].append("✅ Query service initialized")
        
        result["initialization_steps"].append("Initializing chat service...")
        chat_service = ChatService(llm=llm, storage_service=storage_service, query_service=query_service)
        result["initialization_steps"].append("✅ Chat service initialized")
        
        # Update global state
        INITIALIZATION_COMPLETE = True
        INITIALIZATION_STATUS = "complete"
        result["initialization_steps"].append("✅ All services initialized successfully!")
        result["success"] = True
        
    except Exception as e:
        error_msg = f"Manual initialization failed: {str(e)}"
        result["initialization_steps"].append(f"❌ {error_msg}")
        INITIALIZATION_ERROR = error_msg
        INITIALIZATION_STATUS = "failed"
        result["success"] = False
        result["error"] = str(e)
    
    # Final state
    result["final_state"] = {
        "INITIALIZATION_COMPLETE": INITIALIZATION_COMPLETE,
        "INITIALIZATION_STATUS": INITIALIZATION_STATUS,
        "INITIALIZATION_ERROR": INITIALIZATION_ERROR,
        "services_initialized": {
            "document_service": document_service is not None,
            "query_service": query_service is not None,
            "storage_service": storage_service is not None,
            "chat_service": chat_service is not None,
        }
    }
    
    return result

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
