# backend/app/api/routes/chat.py (Complete working version)
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from typing import List, Optional, AsyncGenerator
import logging
from datetime import datetime

from ...core.models import (
    ChatSession, ChatRequest, ChatResponse, NewChatRequest,
    ChatSessionSummary, UpdateChatRequest, StreamingChatChunk
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Working dependency function
def get_chat_service():
    """Get chat service from main module."""
    import main
    return main.get_chat_service()

@router.post("/new", response_model=ChatSession)
async def create_new_chat(
    request: NewChatRequest,
    chat_service=Depends(get_chat_service)
):
    """Create a new chat session for a document."""
    
    try:
        session = await chat_service.create_new_chat(request)
        logger.info(f"✅ Created new chat session {session.id}")
        return session
        
    except ValueError as e:
        logger.warning(f"⚠️  Chat creation validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Error creating new chat: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create chat session: {str(e)}")

@router.post("/message", response_model=ChatResponse)
async def send_chat_message(
    request: ChatRequest,
    chat_service=Depends(get_chat_service)
):
    """Send a message in a chat session."""
    
    try:
        response = await chat_service.send_message(request)
        logger.info(f"✅ Chat message sent in session {request.session_id}")
        return response
        
    except ValueError as e:
        logger.warning(f"⚠️  Chat message validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Error sending chat message: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process message: {str(e)}")

@router.post("/message-stream")
async def send_chat_message_stream(
    request: ChatRequest,
    chat_service=Depends(get_chat_service)
):
    """Send a message with streaming response."""
    
    async def generate_chat_stream() -> AsyncGenerator[str, None]:
        """Generate streaming chat response."""
        try:
            async for chunk in chat_service.send_message_stream(request):
                yield f"data: {chunk.model_dump_json()}\n\n"
                
        except Exception as e:
            logger.error(f"❌ Streaming chat error: {e}")
            error_chunk = StreamingChatChunk(
                session_id=request.session_id,
                message_id="error",
                type="error",
                data={"error": str(e)},
                timestamp=datetime.now()
            )
            yield f"data: {error_chunk.model_dump_json()}\n\n"
    
    return StreamingResponse(
        generate_chat_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

@router.get("/session/{session_id}", response_model=ChatSession)
async def get_chat_session(
    session_id: str,
    chat_service=Depends(get_chat_service)
):
    """Get a specific chat session."""
    
    try:
        session = await chat_service.get_chat_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Chat session not found")
        
        return session
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting chat session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get chat session: {str(e)}")

@router.get("/sessions", response_model=List[ChatSessionSummary])
async def list_chat_sessions(
    document_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    chat_service=Depends(get_chat_service)
):
    """List chat sessions with optional filtering."""
    
    try:
        sessions = await chat_service.list_chat_sessions(
            document_id=document_id,
            limit=limit,
            offset=offset
        )
        
        logger.info(f"✅ Retrieved {len(sessions)} chat sessions")
        return sessions
        
    except Exception as e:
        logger.error(f"❌ Error listing chat sessions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list chat sessions: {str(e)}")

@router.put("/session/{session_id}", response_model=ChatSession)
async def update_chat_session(
    session_id: str, 
    request: UpdateChatRequest,
    chat_service=Depends(get_chat_service)
):
    """Update chat session settings."""
    
    try:
        session = await chat_service.update_chat_session(session_id, request)
        logger.info(f"✅ Updated chat session {session_id}")
        return session
        
    except ValueError as e:
        logger.warning(f"⚠️  Chat update validation error: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Error updating chat session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update session: {str(e)}")

@router.delete("/session/{session_id}")
async def delete_chat_session(
    session_id: str,
    chat_service=Depends(get_chat_service)
):
    """Delete a chat session."""
    
    try:
        success = await chat_service.delete_chat_session(session_id)
        if not success:
            raise HTTPException(status_code=404, detail="Chat session not found")
        
        logger.info(f"✅ Deleted chat session {session_id}")
        return {"message": "Chat session deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error deleting chat session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete session: {str(e)}")

@router.post("/session/{session_id}/clear", response_model=ChatSession)
async def clear_chat_history(
    session_id: str, 
    keep_system_messages: bool = True,
    chat_service=Depends(get_chat_service)
):
    """Clear chat history but keep the session."""
    
    try:
        session = await chat_service.clear_chat_history(session_id, keep_system_messages)
        logger.info(f"✅ Cleared chat history for session {session_id}")
        return session
        
    except ValueError as e:
        logger.warning(f"⚠️  Chat clear validation error: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Error clearing chat history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear history: {str(e)}")

@router.get("/sessions/document/{document_id}", response_model=List[ChatSessionSummary])
async def get_document_chat_sessions(
    document_id: str,
    limit: int = 20,
    offset: int = 0,
    chat_service=Depends(get_chat_service)
):
    """Get all chat sessions for a specific document."""
    
    try:
        sessions = await chat_service.list_chat_sessions(
            document_id=document_id,
            limit=limit,
            offset=offset
        )
        
        logger.info(f"✅ Retrieved {len(sessions)} chat sessions for document {document_id}")
        return sessions
        
    except Exception as e:
        logger.error(f"❌ Error getting document chat sessions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get document chat sessions: {str(e)}")

@router.get("/stats")
async def get_chat_statistics(
    chat_service=Depends(get_chat_service)
):
    """Get chat service statistics."""
    
    try:
        stats = await chat_service.get_chat_statistics()
        return {
            "chat_statistics": stats,
            "timestamp": datetime.now()
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting chat statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get chat statistics: {str(e)}")

# Convenience endpoints for common operations

@router.post("/quick-start")
async def quick_start_chat(
    document_id: str,
    first_message: str,
    title: Optional[str] = None,
    chat_service=Depends(get_chat_service)
):
    """Quick start: Create new chat session and send first message."""
    
    try:
        # Create new session
        new_chat_request = NewChatRequest(
            document_id=document_id,
            title=title or "Quick Chat"
        )
        session = await chat_service.create_new_chat(new_chat_request)
        
        # Send first message
        chat_request = ChatRequest(
            session_id=session.id,
            message=first_message
        )
        response = await chat_service.send_message(chat_request)
        
        logger.info(f"✅ Quick start chat created for document {document_id}")
        return {
            "session": session,
            "first_response": response
        }
        
    except Exception as e:
        logger.error(f"❌ Error in quick start chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/quick-start-stream")
async def quick_start_chat_stream(
    document_id: str,
    first_message: str,
    title: Optional[str] = None,
    chat_service=Depends(get_chat_service)
):
    """Quick start with streaming: Create new chat and stream first response."""
    
    async def generate_quick_start_stream():
        try:
            # Create session
            new_chat_request = NewChatRequest(
                document_id=document_id,
                title=title or "Quick Chat"
            )
            session = await chat_service.create_new_chat(new_chat_request)
            
            # Send session info first
            session_chunk = StreamingChatChunk(
                session_id=session.id,
                message_id="session_info",
                type="session_created",
                data={"session_id": session.id, "title": session.title}
            )
            yield f"data: {session_chunk.model_dump_json()}\n\n"
            
            # Stream first message response
            chat_request = ChatRequest(
                session_id=session.id,
                message=first_message
            )
            
            async for chunk in chat_service.send_message_stream(chat_request):
                yield f"data: {chunk.model_dump_json()}\n\n"
                
        except Exception as e:
            logger.error(f"❌ Error in quick start stream: {e}")
            error_chunk = StreamingChatChunk(
                session_id="error",
                message_id="error",
                type="error",
                data={"error": str(e)}
            )
            yield f"data: {error_chunk.model_dump_json()}\n\n"
    
    return StreamingResponse(
        generate_quick_start_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
