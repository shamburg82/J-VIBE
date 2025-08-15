# backend/app/api/routes/documents.py (Complete working version)
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, BackgroundTasks, Form, Request
from fastapi.responses import Response, StreamingResponse, FileResponse
from typing import List, Optional, AsyncGenerator
from pathlib import Path
import os
import uuid
import asyncio
import json
from datetime import datetime
import logging

from ...core.models import (
    DocumentUploadRequest, ProcessingStatus, DocumentInfo, 
    DocumentSummary, StreamingQueryChunk, ErrorResponse, ProcessingStatusEnum
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Working dependency function
def get_document_service():
    """Get document service from main module."""
    import main
    return main.get_document_service()

def get_storage_service():
    """Get storage service from main module.""" 
    import main
    return main.get_storage_service()

@router.post("/upload", response_model=ProcessingStatus)
async def upload_document(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    compound: Optional[str] = Form(None),
    study_id: Optional[str] = Form(None),
    deliverable: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    document_service=Depends(get_document_service)
):
    """Upload and process a PDF document with comprehensive error handling."""
    
    try:
        # Log request details for debugging
        logger.info("=== UPLOAD REQUEST DEBUG ===")
        logger.info(f"Content-Type: {request.headers.get('content-type')}")
        logger.info(f"File: {file.filename if file else 'None'}")
        
        # Get form data and log it
        form_data = await request.form()
        logger.info("Form data received:")
        for key, value in form_data.items():
            if hasattr(value, 'filename'):
                logger.info(f"  {key}: FILE - {value.filename} ({value.content_type})")
            else:
                logger.info(f"  {key}: '{value}' (len: {len(str(value))})")
        
        # Extract form values with fallback to form_data
        if compound is None:
            compound = form_data.get('compound', '')
        if study_id is None:
            study_id = form_data.get('study_id', '')
        if deliverable is None:
            deliverable = form_data.get('deliverable', '')
        if description is None:
            description = form_data.get('description', '')
        
        # Convert to strings and strip whitespace
        compound = str(compound).strip() if compound else ''
        study_id = str(study_id).strip() if study_id else ''
        deliverable = str(deliverable).strip() if deliverable else ''
        description = str(description).strip() if description else ''
        
        logger.info("Processed form values:")
        logger.info(f"  compound: '{compound}' (valid: {bool(compound)})")
        logger.info(f"  study_id: '{study_id}' (valid: {bool(study_id)})")
        logger.info(f"  deliverable: '{deliverable}' (valid: {bool(deliverable)})")
        logger.info(f"  description: '{description}'")
        
        # Validate required fields
        validation_errors = []
        
        if not compound:
            validation_errors.append("Compound is required")
            logger.error(f"❌ Compound validation failed: empty or None")
        
        if not study_id:
            validation_errors.append("Study ID is required")
            logger.error(f"❌ Study ID validation failed: empty or None")
        
        if not deliverable:
            validation_errors.append("Deliverable is required")
            logger.error(f"❌ Deliverable validation failed: empty or None")
        
        if validation_errors:
            error_msg = "; ".join(validation_errors)
            logger.error(f"❌ Validation failed: {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)

        # Validate file
        if not file or not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
            
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")
        
        # Check file size
        if file.size and file.size > 50 * 1024 * 1024:  # 50MB limit
            raise HTTPException(status_code=400, detail="File size too large (max 50MB)")
        
        # Generate document ID
        document_id = str(uuid.uuid4())
        logger.info(f"Generated document ID: {document_id}")
        
        # Read file content
        file_content = await file.read()
        filename = file.filename
        
        if not file_content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        
        logger.info(f"File read successfully: {len(file_content)} bytes")
        
        # Create initial processing status
        status = ProcessingStatus(
            document_id=document_id,
            status="queued",
            progress=0,
            message="Document uploaded, queued for processing",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        # Start background processing
        background_tasks.add_task(
            document_service.process_document_async,
            document_id=document_id,
            file_content=file_content,
            filename=filename,          
            compound=compound,
            study_id=study_id,
            deliverable=deliverable,
            description=description if description else None
        )
        
        logger.info(f"✅ Document upload initiated: {filename} -> {document_id}")
        logger.info("=== END UPLOAD REQUEST ===")
        
        return status
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected upload error: {e}")
        logger.exception("Upload exception details:")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/upload-stream/{document_id}")
async def stream_processing_status(
    document_id: str,
    document_service=Depends(get_document_service)
):
    """Stream processing status updates for a document."""
    
    async def generate_status_stream():
        """Generate status updates as Server-Sent Events."""
        try:
            # Import here to avoid circular imports
            from ...core.models import ProcessingStatusEnum, ProcessingStatus
            
            # First check if document exists
            doc_info = await document_service.get_document_info(document_id)
            if not doc_info:
                yield f"data: {json.dumps({'error': 'Document not found'})}\n\n"
                return
            
            # If already completed, send final status and close
            if doc_info.status == ProcessingStatusEnum.COMPLETED:
                final_status = ProcessingStatus(
                    document_id=document_id,
                    status=doc_info.status,
                    progress=100,
                    message="Processing completed",
                    created_at=doc_info.created_at,
                    updated_at=doc_info.processed_at or doc_info.created_at,
                    total_pages=doc_info.total_pages,
                    total_chunks=doc_info.total_chunks,
                    tlf_outputs_found=doc_info.tlf_outputs_found
                )
                yield f"data: {final_status.model_dump_json()}\n\n"
                return
            
            # Poll for status updates
            max_polls = 60  # Maximum 2 minutes of polling
            poll_count = 0
            
            while poll_count < max_polls:
                status = await document_service.get_processing_status(document_id)
                
                if status:
                    yield f"data: {status.model_dump_json()}\n\n"
                    
                    # If completed or failed, end stream
                    if status.status in [ProcessingStatusEnum.COMPLETED, ProcessingStatusEnum.FAILED]:
                        break
                else:
                    # No status found, send a default one
                    default_status = ProcessingStatus(
                        document_id=document_id,
                        status=ProcessingStatusEnum.PROCESSING,
                        progress=50,
                        message="Processing in progress...",
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    yield f"data: {default_status.model_dump_json()}\n\n"
                
                # Wait before next update
                await asyncio.sleep(2)
                poll_count += 1
                
        except Exception as e:
            logger.error(f"Error in status stream for {document_id}: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_status_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.get("/status/{document_id}", response_model=ProcessingStatus)
async def get_processing_status(
    document_id: str,
    document_service=Depends(get_document_service)
):
    """Get current processing status for a document."""
    
    try:
        status = await document_service.get_processing_status(document_id)
        if not status:
            # Create a basic status if document exists but no processing status
            doc_info = await document_service.get_document_info(document_id)
            if doc_info:
                return ProcessingStatus(
                    document_id=document_id,
                    status=doc_info.status,
                    progress=100 if doc_info.status == "completed" else 0,
                    message=f"Document {doc_info.status}",
                    created_at=doc_info.created_at,
                    updated_at=doc_info.processed_at or doc_info.created_at,
                    total_pages=doc_info.total_pages,
                    total_chunks=doc_info.total_chunks,
                    tlf_outputs_found=doc_info.tlf_outputs_found
                )
            raise HTTPException(status_code=404, detail="Document not found")
        
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting processing status for {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get processing status: {str(e)}")

@router.get("/info/{document_id}", response_model=DocumentInfo)
async def get_document_info(
    document_id: str,
    document_service=Depends(get_document_service)
):
    """Get detailed information about a processed document."""
    
    try:
        info = await document_service.get_document_info(document_id)
        if not info:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document info for {document_id}: {e}")

@router.get("/structure")
async def get_documents_structure(
    document_service=Depends(get_document_service)
):
    """Get documents organized by compound/study/deliverable structure."""
    
    structure = await document_service.get_documents_by_structure()
    return {
        "structure": structure,
        "compounds": list(structure.keys()),
        "total_compounds": len(structure),
        "total_studies": sum(len(studies) for studies in structure.values()),
        "total_deliverables": sum(
            sum(len(deliverables) for deliverables in studies.values()) 
            for studies in structure.values()
        )
    }

@router.get("/list", response_model=List[DocumentInfo])
async def list_documents(
    limit: int = 50,
    offset: int = 0,
    status_filter: Optional[str] = None,
    compound_filter: Optional[str] = None,
    study_filter: Optional[str] = None,
    deliverable_filter: Optional[str] = None,
    document_service=Depends(get_document_service)
):
    """List all documents with optional filtering by structure."""
    
    try:
        documents = await document_service.list_documents(
            limit=limit,
            offset=offset,
            status_filter=status_filter,
            compound_filter=compound_filter,
            study_filter=study_filter,
            deliverable_filter=deliverable_filter
        )
        
        return documents
        
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {str(e)}")

@router.get("/compounds")
async def get_available_compounds(
    document_service=Depends(get_document_service)
):
    """Get list of available compounds."""
    
    try:
        structure = await document_service.get_documents_by_structure()
        
        # Build compound summary with stats
        compound_summary = []
        for compound, studies in structure.items():
            study_count = len(studies)
            total_deliverables = sum(len(deliverables) for deliverables in studies.values())
            total_documents = sum(
                sum(len(docs) for docs in deliverables.values()) 
                for deliverables in studies.values()
            )
            
            compound_summary.append({
                "compound": compound,
                "study_count": study_count,
                "deliverable_count": total_deliverables,
                "document_count": total_documents,
                "studies": list(studies.keys())
            })
        
        return {
            "compounds": [c["compound"] for c in compound_summary],
            "compound_details": compound_summary,
            "total_compounds": len(compound_summary)
        }
        
    except Exception as e:
        logger.error(f"Error getting compounds: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get compounds: {str(e)}")

@router.get("/studies/{compound}")
async def get_studies_for_compound(
    compound: str,
    document_service=Depends(get_document_service)
):
    """Get list of studies for a specific compound."""
    
    try:
        structure = await document_service.get_documents_by_structure()
        
        if compound not in structure:
            raise HTTPException(status_code=404, detail=f"Compound '{compound}' not found")
        
        # Build study summary with stats
        study_summary = []
        for study_id, deliverables in structure[compound].items():
            deliverable_count = len(deliverables)
            total_documents = sum(len(docs) for docs in deliverables.values())
            
            study_summary.append({
                "study_id": study_id,
                "deliverable_count": deliverable_count,
                "document_count": total_documents,
                "deliverables": list(deliverables.keys())
            })
        
        return {
            "compound": compound,
            "studies": [s["study_id"] for s in study_summary],
            "study_details": study_summary,
            "total_studies": len(study_summary)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting studies for compound {compound}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get studies: {str(e)}")

@router.get("/deliverables/{compound}/{study_id}")
async def get_deliverables_for_study(
    compound: str, 
    study_id: str,
    document_service=Depends(get_document_service)
):
    """Get list of deliverables for a specific compound and study."""
    
    try:
        structure = await document_service.get_documents_by_structure()
        
        if compound not in structure:
            raise HTTPException(status_code=404, detail=f"Compound '{compound}' not found")
        
        if study_id not in structure[compound]:
            raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found for compound '{compound}'")
        
        # Build deliverable summary with stats
        deliverable_summary = []
        for deliverable, documents in structure[compound][study_id].items():
            document_count = len(documents)
            
            # Find latest document
            latest_document = None
            if documents:
                latest_document = max(documents, key=lambda d: d.get("created_at", datetime.min))
            
            deliverable_summary.append({
                "deliverable": deliverable,
                "document_count": document_count,
                "latest_upload": latest_document.get("created_at") if latest_document else None,
                "documents": documents
            })
        
        return {
            "compound": compound,
            "study_id": study_id,
            "deliverables": [d["deliverable"] for d in deliverable_summary],
            "deliverable_details": deliverable_summary,
            "total_deliverables": len(deliverable_summary)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting deliverables for {compound}/{study_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get deliverables: {str(e)}")

@router.get("/documents/{compound}/{study_id}/{deliverable}")
async def get_documents_for_deliverable(
    compound: str, 
    study_id: str, 
    deliverable: str,
    document_service=Depends(get_document_service)
):
    """Get all documents for a specific compound/study/deliverable combination."""
    
    try:
        structure = await document_service.get_documents_by_structure()
        
        if compound not in structure:
            raise HTTPException(status_code=404, detail=f"Compound '{compound}' not found")
        
        if study_id not in structure[compound]:
            raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found for compound '{compound}'")
        
        if deliverable not in structure[compound][study_id]:
            raise HTTPException(status_code=404, detail=f"Deliverable '{deliverable}' not found for {compound}/{study_id}")
        
        documents = structure[compound][study_id][deliverable]
        
        return {
            "compound": compound,
            "study_id": study_id,
            "deliverable": deliverable,
            "documents": documents,
            "document_count": len(documents)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting documents for {compound}/{study_id}/{deliverable}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get documents: {str(e)}")

@router.get("/summary", response_model=DocumentSummary)
async def get_documents_summary(
    document_service=Depends(get_document_service)
):
    """Get summary statistics for all documents."""
    
    try:
        summary = await document_service.get_documents_summary()
        return summary
        
    except Exception as e:
        logger.error(f"Error getting documents summary: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get summary: {str(e)}")

@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    document_service=Depends(get_document_service)
):
    """Delete a document and its associated data."""
    
    success = await document_service.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {"message": "Document deleted successfully"}

@router.api_route("/serve/{document_id}", methods=["GET", "HEAD"])
async def serve_pdf_file(
    request: Request,
    document_id: str,
    document_service=Depends(get_document_service)
):
    """Serve the actual PDF file for viewing - supports both GET and HEAD."""
    
    try:
        # Get document info
        doc_info = await document_service.get_document_info(document_id)
        if not doc_info:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Check if document is completed
        if doc_info.status != "completed":
            raise HTTPException(
                status_code=400, 
                detail=f"Document not ready for viewing (status: {doc_info.status})"
            )
        
        # Check if file exists and file_path is available
        if not hasattr(doc_info, 'file_path') or not doc_info.file_path:
            raise HTTPException(status_code=404, detail="File path not available")
        
        file_path = Path(doc_info.file_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found on disk")
        
        # Check if it's actually a PDF file
        if not file_path.suffix.lower() == '.pdf':
            raise HTTPException(status_code=400, detail="File is not a PDF")
        
        logger.info(f"Serving PDF ({request.method}): {file_path} for document {document_id}")
        
        # For HEAD requests, return headers only
        if request.method == "HEAD":
            file_size = file_path.stat().st_size
            return Response(
                headers={
                    "Content-Type": "application/pdf",
                    "Content-Length": str(file_size),
                    "Content-Disposition": f"inline; filename={doc_info.filename}",
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "public, max-age=3600",
                }
            )
        
        # For GET requests, return the file
        return FileResponse(
            path=str(file_path),
            media_type="application/pdf",
            filename=doc_info.filename,
            headers={
                "Content-Disposition": f"inline; filename={doc_info.filename}",
                "Cache-Control": "public, max-age=3600",
                "Accept-Ranges": "bytes",
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving PDF file for document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to serve file: {str(e)}")


@router.get("/chat-ready/{document_id}")
async def check_document_chat_ready(
    document_id: str,
    document_service=Depends(get_document_service),
    storage_service=Depends(get_storage_service)
):
    """Check if a document is ready for chat (has vector index)."""
    
    try:
        # Check if document exists and is processed
        doc_info = await document_service.get_document_info(document_id)
        if not doc_info:
            raise HTTPException(status_code=404, detail="Document not found")
        
        if doc_info.status != ProcessingStatusEnum.COMPLETED:
            return {
                "chat_ready": False,
                "status": doc_info.status,
                "message": f"Document is still being processed (status: {doc_info.status})",
                "file_available": bool(doc_info.file_path and Path(doc_info.file_path).exists() if doc_info.file_path else False)
            }
        
        # Check if vector index exists
        vector_index = await storage_service.get_index(document_id)
        chat_ready = vector_index is not None
        
        return {
            "chat_ready": chat_ready,
            "status": "ready" if chat_ready else "no_index",
            "message": "Document is ready for chat" if chat_ready else "Document processed but chat not available (vector store disabled)",
            "document_info": {
                "filename": doc_info.filename,
                "total_pages": doc_info.total_pages,
                "total_chunks": doc_info.total_chunks,
                "tlf_outputs_found": doc_info.tlf_outputs_found,
                "file_available": bool(doc_info.file_path and Path(doc_info.file_path).exists() if doc_info.file_path else False)
            },
            "vector_store_enabled": await document_service.get_vector_store_status()
        }
        
    except Exception as e:
        logger.error(f"Error checking chat readiness for document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Debug endpoint to test form data reception
@router.post("/upload-test")
async def upload_test(
    request: Request
):
    """Test endpoint to debug form data reception."""
    
    try:
        logger.info("=== UPLOAD TEST REQUEST ===")
        
        # Get headers
        headers = dict(request.headers)
        logger.info(f"Headers: {headers}")
        
        # Get form data
        form = await request.form()
        
        result = {
            "content_type": request.headers.get("content-type"),
            "method": request.method,
            "url": str(request.url),
            "form_fields": {},
            "files": {},
            "validation_results": {}
        }
        
        # Process each form field
        for key, value in form.items():
            if hasattr(value, 'filename'):  # File field
                result["files"][key] = {
                    "filename": value.filename,
                    "content_type": value.content_type,
                    "size": value.size if hasattr(value, 'size') else "unknown"
                }
                logger.info(f"File field '{key}': {value.filename}")
            else:  # Text field
                str_value = str(value)
                result["form_fields"][key] = {
                    "value": str_value,
                    "length": len(str_value),
                    "stripped_length": len(str_value.strip()),
                    "is_empty": not str_value.strip(),
                    "type": type(value).__name__
                }
                logger.info(f"Text field '{key}': '{str_value}' (len: {len(str_value)})")
        
        # Test validation
        compound = form.get('compound', '')
        study_id = form.get('study_id', '')
        deliverable = form.get('deliverable', '')
        
        result["validation_results"] = {
            "compound_valid": bool(str(compound).strip()),
            "study_id_valid": bool(str(study_id).strip()),
            "deliverable_valid": bool(str(deliverable).strip()),
            "compound_value": str(compound),
            "study_id_value": str(study_id),
            "deliverable_value": str(deliverable)
        }
        
        logger.info(f"Validation results: {result['validation_results']}")
        logger.info("=== END UPLOAD TEST ===")
        
        return result
        
    except Exception as e:
        logger.error(f"Test endpoint error: {e}")
        logger.exception("Test endpoint exception:")
        return {
            "error": str(e),
            "type": type(e).__name__
        }

# Alternative upload endpoint using different parameter handling
@router.post("/upload-alt")
async def upload_document_alternative(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    compound: str = Form(..., description="Compound identifier"),
    study_id: str = Form(..., description="Study identifier"),
    deliverable: str = Form(..., description="Deliverable type"),
    description: Optional[str] = Form(None, description="Optional description"),
    document_service=Depends(get_document_service)
):
    """Alternative upload endpoint with stricter form validation."""
    
    logger.info("=== ALTERNATIVE UPLOAD ===")
    logger.info(f"Received: compound='{compound}', study_id='{study_id}', deliverable='{deliverable}'")
    
    # This version should work if the form data is being sent correctly
    # because FastAPI will validate that the required Form fields are present
    
    try:
        # Validate non-empty after stripping
        compound = compound.strip()
        study_id = study_id.strip() 
        deliverable = deliverable.strip()
        
        if not compound:
            raise HTTPException(status_code=400, detail="Compound cannot be empty")
        if not study_id:
            raise HTTPException(status_code=400, detail="Study ID cannot be empty")
        if not deliverable:
            raise HTTPException(status_code=400, detail="Deliverable cannot be empty")
            
        # Same processing as main endpoint...
        document_id = str(uuid.uuid4())
        file_content = await file.read()
        
        if not file_content:
            raise HTTPException(status_code=400, detail="File is empty")
            
        status = ProcessingStatus(
            document_id=document_id,
            status="queued", 
            progress=0,
            message="Document uploaded via alternative endpoint",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        background_tasks.add_task(
            document_service.process_document_async,
            document_id=document_id,
            file_content=file_content,
            filename=file.filename,
            compound=compound,
            study_id=study_id,
            deliverable=deliverable,
            description=description.strip() if description else None
        )
        
        logger.info(f"✅ Alternative upload successful: {document_id}")
        return status
        
    except Exception as e:
        logger.error(f"❌ Alternative upload failed: {e}")
        raise
