# backend/app/api/routes/chat.py
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from typing import List, Optional, AsyncGenerator
import logging
from datetime import datetime

from ...core.chat_models import (
    ChatSession, ChatRequest, ChatResponse, NewChatRequest,
    ChatSessionSummary, UpdateChatRequest, StreamingChatChunk
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/new", response_model=ChatSession)
async def create_new_chat(request: NewChatRequest):
    """Create a new chat session for a document."""
    
    from ...main import get_chat_service
    chat_service = get_chat_service()
    
    try:
        session = await chat_service.create_new_chat(request)
        return session
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating new chat: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create chat session: {str(e)}")


@router.post("/message", response_model=ChatResponse)
async def send_chat_message(request: ChatRequest):
    """Send a message in a chat session."""
    
    from ...main import get_chat_service
    chat_service = get_chat_service()
    
    try:
        response = await chat_service.send_message(request)
        return response
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error sending chat message: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process message: {str(e)}")


@router.post("/message-stream")
async def send_chat_message_stream(request: ChatRequest):
    """Send a message with streaming response."""
    
    from ...main import get_chat_service
    chat_service = get_chat_service()
    
    async def generate_chat_stream() -> AsyncGenerator[str, None]:
        """Generate streaming chat response."""
        try:
            async for chunk in chat_service.send_message_stream(request):
                yield f"data: {chunk.model_dump_json()}\n\n"
                
        except Exception as e:
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
async def get_chat_session(session_id: str):
    """Get a specific chat session."""
    
    from ...main import get_chat_service
    chat_service = get_chat_service()
    
    session = await chat_service.get_chat_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    return session


@router.get("/sessions", response_model=List[ChatSessionSummary])
async def list_chat_sessions(
    document_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """List chat sessions with optional filtering."""
    
    from ...main import get_chat_service
    chat_service = get_chat_service()
    
    sessions = await chat_service.list_chat_sessions(
        document_id=document_id,
        limit=limit,
        offset=offset
    )
    
    return sessions


@router.put("/session/{session_id}", response_model=ChatSession)
async def update_chat_session(session_id: str, request: UpdateChatRequest):
    """Update chat session settings."""
    
    from ...main import get_chat_service
    chat_service = get_chat_service()
    
    try:
        session = await chat_service.update_chat_session(session_id, request)
        return session
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating chat session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update session: {str(e)}")


@router.delete("/session/{session_id}")
async def delete_chat_session(session_id: str):
    """Delete a chat session."""
    
    from ...main import get_chat_service
    chat_service = get_chat_service()
    
    success = await chat_service.delete_chat_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    return {"message": "Chat session deleted successfully"}


@router.post("/session/{session_id}/clear", response_model=ChatSession)
async def clear_chat_history(
    session_id: str, 
    keep_system_messages: bool = True
):
    """Clear chat history but keep the session."""
    
    from ...main import get_chat_service
    chat_service = get_chat_service()
    
    try:
        session = await chat_service.clear_chat_history(session_id, keep_system_messages)
        return session
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error clearing chat history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear history: {str(e)}")


@router.get("/sessions/document/{document_id}", response_model=List[ChatSessionSummary])
async def get_document_chat_sessions(
    document_id: str,
    limit: int = 20,
    offset: int = 0
):
    """Get all chat sessions for a specific document."""
    
    from ...main import get_chat_service
    chat_service = get_chat_service()
    
    sessions = await chat_service.list_chat_sessions(
        document_id=document_id,
        limit=limit,
        offset=offset
    )
    
    return sessions


@router.get("/stats")
async def get_chat_statistics():
    """Get chat service statistics."""
    
    from ...main import get_chat_service
    chat_service = get_chat_service()
    
    stats = await chat_service.get_chat_statistics()
    return {
        "chat_statistics": stats,
        "timestamp": datetime.now()
    }


# Convenience endpoints for common operations

@router.post("/quick-start")
async def quick_start_chat(
    document_id: str,
    first_message: str,
    title: Optional[str] = None
):
    """Quick start: Create new chat session and send first message."""
    
    from ...main import get_chat_service
    chat_service = get_chat_service()
    
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
        
        return {
            "session": session,
            "first_response": response
        }
        
    except Exception as e:
        logger.error(f"Error in quick start chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quick-start-stream")
async def quick_start_chat_stream(
    document_id: str,
    first_message: str,
    title: Optional[str] = None
):
    """Quick start with streaming: Create new chat and stream first response."""
    
    from ...main import get_chat_service
    chat_service = get_chat_service()
    
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
