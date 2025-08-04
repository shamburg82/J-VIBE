# .run_server(port=8000)
# # backend/app/main.py
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import asyncio
import json
import logging
import uuid
from typing import Dict, List, Optional, AsyncGenerator
from contextlib import asynccontextmanager
import os
from pathlib import Path

from .api.routes import documents, queries, health
from .core.bedrock_setup import configure_bedrock_llm
from .core.models import QueryRequest, QueryResponse, ProcessingStatus, DocumentInfo
from .services.document_service import DocumentService
from .services.query_service import QueryService
from .services.storage_service import StorageService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global services - will be initialized on startup
document_service: Optional[DocumentService] = None
query_service: Optional[QueryService] = None
storage_service: Optional[StorageService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - startup and shutdown."""
    
    # Startup
    logger.info("🚀 Starting TLF Analyzer API")
    
    try:
        # Detect environment and get appropriate config
        import os
        is_posit = bool(os.getenv("RSTUDIO_CONNECT_URL")) or bool(os.getenv("RS_SERVER_URL"))
        
        config = None
        if is_posit:
            # Use Posit-specific configuration
            try:
                from .core.posit_config import get_posit_config
                config = get_posit_config()
                logger.info(f"Using Posit configuration: {config.get_environment_name()}")
            except ImportError as e:
                logger.warning(f"Could not import Posit config: {e}, using standard config")
                from .core.config import get_config
                config = get_config()
        else:
            # Use standard configuration
            from .core.config import get_config
            config = get_config()
        
        # Initialize Bedrock LLM with appropriate setup
        if is_posit:
            try:
                from .core.posit_bedrock_setup import configure_bedrock_for_posit
                llm = await configure_bedrock_for_posit()
            except ImportError:
                logger.warning("Could not import Posit Bedrock setup, using standard setup")
                from .core.bedrock_setup import configure_bedrock_llm
                llm = await configure_bedrock_llm()
        else:
            from .core.bedrock_setup import configure_bedrock_llm
            llm = await configure_bedrock_llm()
            
        if not llm:
            raise Exception("Failed to initialize Bedrock LLM")
        
        # Initialize services with config
        global document_service, query_service, storage_service
        
        storage_service = StorageService()
        document_service = DocumentService(
            llm=llm, 
            storage_service=storage_service,
            config=config if is_posit else None
        )
        query_service = QueryService(llm=llm, storage_service=storage_service)
        
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


# Create FastAPI app with lifespan
app = FastAPI(
    title="TLF Analyzer API",
    description="API for processing and querying clinical trial TLF documents",
    version="1.0.0",
    lifespan=lifespan,
    # Posit Workbench/Connect compatibility
    root_path=os.getenv("FASTAPI_ROOT_PATH", "")
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # React dev servers
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api/v1/health", tags=["health"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
app.include_router(queries.router, prefix="/api/v1/queries", tags=["queries"])


# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Clinical TLF Analyzer API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health"
    }


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Global exception: {exc}")
    return HTTPException(
        status_code=500,
        detail=f"Internal server error: {str(exc)}"
    )


# Dependency to get services
def get_document_service() -> DocumentService:
    if document_service is None:
        raise HTTPException(status_code=503, detail="Document service not initialized")
    return document_service


def get_query_service() -> QueryService:
    if query_service is None:
        raise HTTPException(status_code=503, detail="Query service not initialized")
    return query_service


def get_storage_service() -> StorageService:
    if storage_service is None:
        raise HTTPException(status_code=503, detail="Storage service not initialized")
    return storage_service


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
