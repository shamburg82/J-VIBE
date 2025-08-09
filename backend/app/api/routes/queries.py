# backend/app/api/routes/queries.py (Complete working version)
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from typing import List, Optional, AsyncGenerator
import json
import time
from datetime import datetime
import logging

from ...core.models import (
    QueryRequest, EnhancedQueryRequest, QueryResponse, 
    StreamingQueryChunk, QuerySource
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Working dependency function
def get_query_service():
    """Get query service from main module."""
    import main
    return main.get_query_service()

@router.post("/ask", response_model=QueryResponse)
async def query_document(
    request: QueryRequest,
    query_service=Depends(get_query_service)
):
    """Query a document with natural language."""
    
    start_time = time.time()
    
    try:
        # Process query
        response = await query_service.process_query(request)
        
        # Calculate processing time
        processing_time_ms = int((time.time() - start_time) * 1000)
        response.processing_time_ms = processing_time_ms
        
        logger.info(f"✅ Query processed in {processing_time_ms}ms")
        return response
        
    except Exception as e:
        logger.error(f"❌ Query processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")

@router.post("/ask-stream")
async def query_document_stream(
    request: QueryRequest,
    query_service=Depends(get_query_service)
):
    """Query a document with streaming response."""
    
    async def generate_query_stream() -> AsyncGenerator[str, None]:
        """Generate streaming query response."""
        try:
            async for chunk in query_service.process_query_stream(request):
                yield f"data: {chunk.model_dump_json()}\n\n"
                
        except Exception as e:
            logger.error(f"❌ Streaming query failed: {e}")
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
async def query_document_enhanced(
    request: EnhancedQueryRequest,
    query_service=Depends(get_query_service)
):
    """Enhanced query with filters and advanced options."""
    
    start_time = time.time()
    
    try:
        response = await query_service.process_enhanced_query(request)
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        response.processing_time_ms = processing_time_ms
        
        logger.info(f"✅ Enhanced query processed in {processing_time_ms}ms")
        return response
        
    except Exception as e:
        logger.error(f"❌ Enhanced query processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Enhanced query processing failed: {str(e)}")

@router.get("/history/{document_id}")
async def get_query_history(
    document_id: str,
    limit: int = 20,
    offset: int = 0,
    query_service=Depends(get_query_service)
):
    """Get query history for a document."""
    
    try:
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
        
    except Exception as e:
        logger.error(f"❌ Failed to get query history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get query history: {str(e)}")

@router.get("/sources/{document_id}")
async def get_available_sources(
    document_id: str,
    query_service=Depends(get_query_service)
):
    """Get available TLF sources in a document for building queries."""
    
    try:
        sources = await query_service.get_available_sources(document_id)
        if not sources:
            raise HTTPException(status_code=404, detail="Document not found or no sources available")
        
        logger.info(f"✅ Retrieved sources for document {document_id}")
        return sources
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get sources for {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get sources: {str(e)}")
