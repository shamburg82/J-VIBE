# backend/app/api/routes/health.py
from fastapi import APIRouter, Depends
from datetime import datetime
import psutil
import os

from ...core.models import HealthResponse, SystemStats

router = APIRouter()

# Track startup time for uptime calculation
startup_time = datetime.now()


@router.get("/", response_model=HealthResponse)
async def health_check():
    """Basic health check endpoint."""
    
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(),
        services={
            "api": "healthy",
            "bedrock": "healthy",  # Could add actual Bedrock health check
            "storage": "healthy"
        },
        version="1.0.0"
    )


@router.get("/detailed")
async def detailed_health_check():
    """Detailed health check with service statuses."""
    
    try:
        from ...main import get_document_service, get_query_service, get_storage_service
        
        # Check each service
        services_status = {}
        
        # Document service health
        try:
            document_service = get_document_service()
            doc_count = await document_service.get_document_count()
            services_status["document_service"] = f"healthy - {doc_count} documents"
        except Exception as e:
            services_status["document_service"] = f"unhealthy - {str(e)}"
        
        # Query service health
        try:
            query_service = get_query_service()
            query_count = await query_service.get_query_count()
            services_status["query_service"] = f"healthy - {query_count} queries processed"
        except Exception as e:
            services_status["query_service"] = f"unhealthy - {str(e)}"
        
        # Storage service health
        try:
            storage_service = get_storage_service()
            storage_info = await storage_service.get_storage_info()
            services_status["storage_service"] = f"healthy - {storage_info.get('total_indexes', 0)} indexes"
        except Exception as e:
            services_status["storage_service"] = f"unhealthy - {str(e)}"
        
        # System resources
        memory_usage = psutil.virtual_memory()
        disk_usage = psutil.disk_usage('/')
        
        return {
            "status": "healthy",
            "timestamp": datetime.now(),
            "services": services_status,
            "system": {
                "memory_usage_percent": memory_usage.percent,
                "memory_available_gb": round(memory_usage.available / (1024**3), 2),
                "disk_usage_percent": disk_usage.percent,
                "disk_free_gb": round(disk_usage.free / (1024**3), 2),
                "cpu_count": psutil.cpu_count(),
                "uptime_seconds": int((datetime.now() - startup_time).total_seconds())
            },
            "version": "1.0.0"
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "timestamp": datetime.now(),
            "error": str(e),
            "version": "1.0.0"
        }


@router.get("/stats", response_model=SystemStats)
async def get_system_stats():
    """Get system statistics."""
    
    try:
        from ...main import get_document_service, get_query_service, get_storage_service
        
        # Gather stats from all services
        document_service = get_document_service()
        query_service = get_query_service()
        storage_service = get_storage_service()
        
        doc_count = await document_service.get_document_count()
        query_count = await query_service.get_query_count()
        chunk_count = await storage_service.get_total_chunks()
        avg_processing_time = await document_service.get_average_processing_time()
        
        uptime_seconds = int((datetime.now() - startup_time).total_seconds())
        
        return SystemStats(
            total_documents=doc_count,
            total_chunks=chunk_count,
            total_queries=query_count,
            average_processing_time_seconds=avg_processing_time,
            uptime_seconds=uptime_seconds
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to gather system stats: {str(e)}")
