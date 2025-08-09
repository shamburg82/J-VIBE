# backend/app/api/routes/documents.py (Complete working version)
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse
from typing import List, Optional
import uuid
import asyncio
import json
from datetime import datetime
import logging

from ...core.models import (
    DocumentUploadRequest, ProcessingStatus, DocumentInfo, 
    DocumentSummary, StreamingQueryChunk, ErrorResponse
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Working dependency function
def get_document_service():
    """Get document service from main module."""
    import main
    return main.get_document_service()

@router.post("/upload", response_model=ProcessingStatus)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    compound: str = None,
    study_id: str = None,
    deliverable: str = None,
    description: Optional[str] = None,
    document_service=Depends(get_document_service)
):
    """Upload and process a PDF document."""
    
    # Validate required fields
    if not compound:
        raise HTTPException(status_code=400, detail="Compound is required")
    if not study_id:
        raise HTTPException(status_code=400, detail="Study ID is required")
    if not deliverable:
        raise HTTPException(status_code=400, detail="Deliverable is required")

    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    if file.size and file.size > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=400, detail="File size too large (max 50MB)")
    
    try:
        # Generate document ID
        document_id = str(uuid.uuid4())
        
        # Read file content completely before starting background task
        file_content = await file.read()
        filename = file.filename
        
        # Validate file content is not empty
        if not file_content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        
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
            description=description
        )
        
        logger.info(f"✅ Document upload started for {filename} -> {document_id}")
        return status
        
    except Exception as e:
        logger.error(f"❌ Upload failed: {e}")
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
            while True:
                status = await document_service.get_processing_status(document_id)
                
                if not status:
                    yield f"data: {json.dumps({'error': 'Document not found'})}\n\n"
                    break
                
                # Send status update
                yield f"data: {status.model_dump_json()}\n\n"
                
                # If completed or failed, end stream
                if status.status in ["completed", "failed"]:
                    break
                
                # Wait before next update
                await asyncio.sleep(2)
                
        except Exception as e:
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
    
    status = await document_service.get_processing_status(document_id)
    if not status:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return status

@router.get("/info/{document_id}", response_model=DocumentInfo)
async def get_document_info(
    document_id: str,
    document_service=Depends(get_document_service)
):
    """Get detailed information about a processed document."""
    
    info = await document_service.get_document_info(document_id)
    if not info:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return info

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
    
    documents = await document_service.list_documents(
        limit=limit,
        offset=offset,
        status_filter=status_filter,
        compound_filter=compound_filter,
        study_filter=study_filter,
        deliverable_filter=deliverable_filter
    )
    
    return documents

@router.get("/compounds")
async def get_available_compounds(
    document_service=Depends(get_document_service)
):
    """Get list of available compounds."""
    
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

@router.get("/studies/{compound}")
async def get_studies_for_compound(
    compound: str,
    document_service=Depends(get_document_service)
):
    """Get list of studies for a specific compound."""
    
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

@router.get("/deliverables/{compound}/{study_id}")
async def get_deliverables_for_study(
    compound: str, 
    study_id: str,
    document_service=Depends(get_document_service)
):
    """Get list of deliverables for a specific compound and study."""
    
    structure = await document_service.get_documents_by_structure()
    
    if compound not in structure:
        raise HTTPException(status_code=404, detail=f"Compound '{compound}' not found")
    
    if study_id not in structure[compound]:
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found for compound '{compound}'")
    
    # Build deliverable summary with stats
    deliverable_summary = []
    for deliverable, documents in structure[compound][study_id].items():
        document_count = len(documents)
        latest_document = max(documents, key=lambda d: d.get("created_at", datetime.min))
        
        deliverable_summary.append({
            "deliverable": deliverable,
            "document_count": document_count,
            "latest_upload": latest_document.get("created_at"),
            "documents": documents
        })
    
    return {
        "compound": compound,
        "study_id": study_id,
        "deliverables": [d["deliverable"] for d in deliverable_summary],
        "deliverable_details": deliverable_summary,
        "total_deliverables": len(deliverable_summary)
    }

@router.get("/documents/{compound}/{study_id}/{deliverable}")
async def get_documents_for_deliverable(
    compound: str, 
    study_id: str, 
    deliverable: str,
    document_service=Depends(get_document_service)
):
    """Get all documents for a specific compound/study/deliverable combination."""
    
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

@router.get("/summary", response_model=DocumentSummary)
async def get_documents_summary(
    document_service=Depends(get_document_service)
):
    """Get summary statistics for all documents."""
    
    summary = await document_service.get_documents_summary()
    return summary

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
