# backend/app/api/routes/queries.py
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from typing import List, Optional, AsyncGenerator
import json
import time
from datetime import datetime

from ...core.models import (
    QueryRequest, EnhancedQueryRequest, QueryResponse, 
    StreamingQueryChunk, QuerySource
)

router = APIRouter()


@router.post("/ask", response_model=QueryResponse)
async def query_document(request: QueryRequest):
    """Query a document with natural language."""
    
    from ...main import get_query_service
    query_service = get_query_service()
    
    start_time = time.time()
    
    try:
        # Process query
        response = await query_service.process_query(request)
        
        # Calculate processing time
        processing_time_ms = int((time.time() - start_time) * 1000)
        response.processing_time_ms = processing_time_ms
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")


@router.post("/ask-stream")
async def query_document_stream(request: QueryRequest):
    """Query a document with streaming response."""
    
    from ...main import get_query_service
    query_service = get_query_service()
    
    async def generate_query_stream() -> AsyncGenerator[str, None]:
        """Generate streaming query response."""
        try:
            async for chunk in query_service.process_query_stream(request):
                yield f"data: {chunk.model_dump_json()}\n\n"
                
        except Exception as e:
            error_chunk = StreamingQueryChunk(
                type="error",
                data={"error": str(e)},
                timestamp=datetime.now()
            )
            yield f"data: {error_chunk.model_dump_json()}\n\n"
    
    return StreamingResponse(
        generate_query_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/ask-enhanced", response_model=QueryResponse)
async def query_document_enhanced(request: EnhancedQueryRequest):
    """Enhanced query with filters and advanced options."""
    
    from ...main import get_query_service
    query_service = get_query_service()
    
    start_time = time.time()
    
    try:
        response = await query_service.process_enhanced_query(request)
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        response.processing_time_ms = processing_time_ms
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Enhanced query processing failed: {str(e)}")


@router.get("/history/{document_id}")
async def get_query_history(
    document_id: str,
    limit: int = 20,
    offset: int = 0
):
    """Get query history for a document."""
    
    from ...main import get_query_service
    query_service = get_query_service()
    
    history = await query_service.get_query_history(
        document_id=document_id,
        limit=limit,
        offset=offset
    )
    
    return {
        "document_id": document_id,
        "queries": history,
        "total_returned": len(history),
        "limit": limit,
        "offset": offset
    }


@router.get("/sources/{document_id}")
async def get_available_sources(document_id: str):
    """Get available TLF sources in a document for building queries."""
    
    from ...main import get_query_service
    query_service = get_query_service()
    
    sources = await query_service.get_available_sources(document_id)
    if not sources:
        raise HTTPException(status_code=404, detail="Document not found or no sources available")
    
    return sources
