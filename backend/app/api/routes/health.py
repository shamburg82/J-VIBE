# backend/app/api/routes/health.py
from fastapi import APIRouter, Depends, Request
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


@router.get("/debug-paths")
async def debug_path_detection_simple(request: Request):
    """Debug endpoint for simplified main.py path detection issues."""
    
    import re
    
    # Get request details
    request_url = str(request.url)
    request_path = request.url.path
    
    # Use the same path cleaning logic as simplified main.py
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
