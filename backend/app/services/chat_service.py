# backend/app/services/chat_service.py
from typing import List, Dict, Optional, Any, AsyncGenerator
import asyncio
import time
import logging
from datetime import datetime, timedelta
import uuid

from ..core.models import (
    ChatSession, ChatMessage, ChatRequest, ChatResponse, NewChatRequest,
    ChatSessionSummary, UpdateChatRequest, StreamingChatChunk, MessageRole
)
from ..core.models import QuerySource
from .storage_service import StorageService
from .query_service import QueryService

logger = logging.getLogger(__name__)


class ChatService:
    """Service for handling conversational chat with documents."""
    
    def __init__(self, llm, storage_service: StorageService, query_service: QueryService):
        self.llm = llm
        self.storage_service = storage_service
        self.query_service = query_service
        
        # In-memory storage for chat sessions
        # In production, use persistent storage like Redis or database
        self._chat_sessions: Dict[str, ChatSession] = {}
        
        # Session cleanup settings
        self._max_inactive_hours = 24  # Clean up sessions inactive for 24 hours
        self._max_sessions_per_document = 50  # Limit sessions per document
        
        # Conversational prompt template
        self.conversational_prompt_template = """You are a clinical data analyst having a conversation about clinical trial outputs (Tables, Listings, Figures - TLFs). 

Previous conversation context:
{conversation_context}

Current User Query: {current_query}

Relevant Clinical Trial Data:
{retrieved_context}

Instructions:
- Consider the conversation history when answering the current query
- If the user is asking follow-up questions, reference your previous responses appropriately
- If the user asks for clarification or "what did you mean by...", refer back to the conversation
- Reference specific table/output numbers when citing data
- If data is incomplete or unclear, state what's missing
- Use appropriate clinical terminology
- Maintain conversation flow and context
- If no relevant data is found for the current query, clearly state this
- When referencing previous parts of the conversation, be specific about what you said before

Analysis:"""

    async def create_new_chat(self, request: NewChatRequest) -> ChatSession:
        """Create a new chat session."""
        
        try:
            # Verify document exists
            vector_index = await self.storage_service.get_index(request.document_id)
            if not vector_index:
                raise ValueError(f"Document {request.document_id} not found or not processed")
            
            # Create new session
            session = ChatSession(
                document_id=request.document_id,
                title=request.title or f"Chat about {request.document_id[:8]}...",
                context_window=request.context_window
            )
            
            # Add system message if provided
            if request.system_message:
                system_msg = ChatMessage(
                    role=MessageRole.SYSTEM,
                    content=request.system_message
                )
                session.messages.append(system_msg)
            
            # Store session
            self._chat_sessions[session.id] = session
            
            # Clean up old sessions if needed
            await self._cleanup_old_sessions(request.document_id)
            
            logger.info(f"Created new chat session {session.id} for document {request.document_id}")
            return session
            
        except Exception as e:
            logger.error(f"Error creating chat session: {e}")
            raise

    async def send_message(self, request: ChatRequest) -> ChatResponse:
        """Send a message in a chat session."""
        
        start_time = time.time()
        
        try:
            # Get session
            session = self._chat_sessions.get(request.session_id)
            if not session:
                raise ValueError(f"Chat session {request.session_id} not found")
            
            # Add user message to session
            user_message = ChatMessage(
                role=MessageRole.USER,
                content=request.message
            )
            session.messages.append(user_message)
            
            # Prepare conversational context
            conversation_context = ""
            if request.include_context:
                conversation_context = self._build_conversation_context(session)
            
            # Get vector index for document
            vector_index = await self.storage_service.get_index(session.document_id)
            if not vector_index:
                raise ValueError(f"Document {session.document_id} not found")
            
            # Retrieve relevant chunks using enhanced query
            enhanced_query = self._enhance_query_with_context(request.message, conversation_context)
            relevant_chunks = await self.query_service._retrieve_relevant_chunks(
                vector_index, enhanced_query, request.top_k, request.min_confidence
            )
            
            # Generate response with conversation context
            if not relevant_chunks:
                response_text = f"I couldn't find relevant clinical trial data for your query: '{request.message}'. Could you try rephrasing your question or using broader search terms?"
                sources = []
            else:
                retrieved_context = self.query_service._prepare_context(relevant_chunks)
                response_text = await self._query_llm_with_context(
                    request.message, conversation_context, retrieved_context
                )
                sources = self.query_service._extract_sources(relevant_chunks)
            
            # Create assistant message
            assistant_message = ChatMessage(
                role=MessageRole.ASSISTANT,
                content=response_text,
                sources_used=sources,
                chunks_retrieved=len(relevant_chunks),
                processing_time_ms=int((time.time() - start_time) * 1000)
            )
            
            # Add to session
            session.messages.append(assistant_message)
            session.total_queries += 1
            session.updated_at = datetime.now()
            
            # Create response
            response = ChatResponse(
                session_id=session.id,
                message_id=assistant_message.id,
                response=response_text,
                sources_used=sources,
                chunks_retrieved=len(relevant_chunks),
                processing_time_ms=int((time.time() - start_time) * 1000),
                context_messages_used=min(session.context_window * 2, len(session.messages) - 2),  # Exclude current user/assistant pair
                total_messages_in_session=len(session.messages)
            )
            
            logger.info(f"Processed message in session {session.id}, {len(relevant_chunks)} chunks retrieved")
            return response
            
        except Exception as e:
            logger.error(f"Error processing chat message: {e}")
            raise

    async def send_message_stream(self, request: ChatRequest) -> AsyncGenerator[StreamingChatChunk, None]:
        """Send a message with streaming response."""
        
        try:
            # Get session
            session = self._chat_sessions.get(request.session_id)
            if not session:
                yield StreamingChatChunk(
                    session_id=request.session_id,
                    message_id="error",
                    type="error",
                    data={"error": f"Chat session {request.session_id} not found"}
                )
                return
            
            # Add user message
            user_message = ChatMessage(
                role=MessageRole.USER,
                content=request.message
            )
            session.messages.append(user_message)
            
            # Prepare context
            conversation_context = ""
            if request.include_context:
                conversation_context = self._build_conversation_context(session)
            
            # Get relevant chunks
            vector_index = await self.storage_service.get_index(session.document_id)
            enhanced_query = self._enhance_query_with_context(request.message, conversation_context)
            relevant_chunks = await self.query_service._retrieve_relevant_chunks(
                vector_index, enhanced_query, request.top_k, request.min_confidence
            )
            
            if not relevant_chunks:
                # No relevant data found
                response_text = f"I couldn't find relevant clinical trial data for your query: '{request.message}'. Could you try rephrasing your question?"
                
                assistant_message = ChatMessage(
                    role=MessageRole.ASSISTANT,
                    content=response_text
                )
                session.messages.append(assistant_message)
                
                yield StreamingChatChunk(
                    session_id=session.id,
                    message_id=assistant_message.id,
                    type="content",
                    data=response_text
                )
                
                yield StreamingChatChunk(
                    session_id=session.id,
                    message_id=assistant_message.id,
                    type="complete",
                    data={"chunks_retrieved": 0, "sources_used": []}
                )
                return
            
            # Create assistant message for streaming
            assistant_message = ChatMessage(
                role=MessageRole.ASSISTANT,
                content="",  # Will be built up during streaming
                sources_used=self.query_service._extract_sources(relevant_chunks),
                chunks_retrieved=len(relevant_chunks)
            )
            
            # Stream the response
            retrieved_context = self.query_service._prepare_context(relevant_chunks)
            full_response = ""
            
            async for content_chunk in self._stream_llm_with_context(
                request.message, conversation_context, retrieved_context
            ):
                full_response += content_chunk
                
                yield StreamingChatChunk(
                    session_id=session.id,
                    message_id=assistant_message.id,
                    type="content",
                    data=content_chunk
                )
            
            # Update assistant message with full content
            assistant_message.content = full_response
            session.messages.append(assistant_message)
            session.total_queries += 1
            session.updated_at = datetime.now()
            
            # Send sources
            yield StreamingChatChunk(
                session_id=session.id,
                message_id=assistant_message.id,
                type="sources",
                data=assistant_message.sources_used
            )
            
            # Send completion
            yield StreamingChatChunk(
                session_id=session.id,
                message_id=assistant_message.id,
                type="complete",
                data={
                    "chunks_retrieved": len(relevant_chunks),
                    "context_messages_used": min(session.context_window * 2, len(session.messages) - 2),
                    "total_messages_in_session": len(session.messages)
                }
            )
            
        except Exception as e:
            logger.error(f"Error in streaming chat: {e}")
            yield StreamingChatChunk(
                session_id=request.session_id,
                message_id="error",
                type="error",
                data={"error": str(e)}
            )

    async def get_chat_session(self, session_id: str) -> Optional[ChatSession]:
        """Get a chat session by ID."""
        return self._chat_sessions.get(session_id)

    async def list_chat_sessions(
        self, 
        document_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[ChatSessionSummary]:
        """List chat sessions with optional filtering."""
        
        sessions = list(self._chat_sessions.values())
        
        # Filter by document if specified
        if document_id:
            sessions = [s for s in sessions if s.document_id == document_id]
        
        # Sort by last update (newest first)
        sessions.sort(key=lambda x: x.updated_at, reverse=True)
        
        # Apply pagination
        paginated_sessions = sessions[offset:offset + limit]
        
        # Convert to summaries
        summaries = []
        for session in paginated_sessions:
            last_message = session.messages[-1] if session.messages else None
            last_message_preview = None
            
            if last_message:
                preview_text = last_message.content[:100]
                if len(last_message.content) > 100:
                    preview_text += "..."
                last_message_preview = preview_text
            
            summary = ChatSessionSummary(
                id=session.id,
                document_id=session.document_id,
                title=session.title,
                created_at=session.created_at,
                updated_at=session.updated_at,
                total_messages=len(session.messages),
                total_queries=session.total_queries,
                last_message_preview=last_message_preview
            )
            summaries.append(summary)
        
        return summaries

    async def update_chat_session(self, session_id: str, request: UpdateChatRequest) -> ChatSession:
        """Update chat session settings."""
        
        session = self._chat_sessions.get(session_id)
        if not session:
            raise ValueError(f"Chat session {session_id} not found")
        
        # Update fields if provided
        if request.title is not None:
            session.title = request.title
        
        if request.context_window is not None:
            session.context_window = request.context_window
        
        session.updated_at = datetime.now()
        
        logger.info(f"Updated chat session {session_id}")
        return session

    async def delete_chat_session(self, session_id: str) -> bool:
        """Delete a chat session."""
        
        if session_id in self._chat_sessions:
            del self._chat_sessions[session_id]
            logger.info(f"Deleted chat session {session_id}")
            return True
        
        return False

    async def clear_chat_history(self, session_id: str, keep_system_messages: bool = True) -> ChatSession:
        """Clear chat history but keep the session."""
        
        session = self._chat_sessions.get(session_id)
        if not session:
            raise ValueError(f"Chat session {session_id} not found")
        
        if keep_system_messages:
            # Keep only system messages
            session.messages = [msg for msg in session.messages if msg.role == MessageRole.SYSTEM]
        else:
            # Clear all messages
            session.messages = []
        
        session.total_queries = 0
        session.updated_at = datetime.now()
        
        logger.info(f"Cleared chat history for session {session_id}")
        return session

    def _build_conversation_context(self, session: ChatSession) -> str:
        """Build conversation context from recent messages."""
        
        # Get recent messages within context window
        recent_messages = session.messages[-(session.context_window * 2):]  # User + Assistant pairs
        
        if not recent_messages:
            return ""
        
        context_parts = []
        for message in recent_messages:
            if message.role == MessageRole.SYSTEM:
                continue  # Skip system messages in context
            
            role_label = "You" if message.role == MessageRole.ASSISTANT else "User"
            context_parts.append(f"{role_label}: {message.content}")
        
        return "\n".join(context_parts)

    def _enhance_query_with_context(self, current_query: str, conversation_context: str) -> str:
        """Enhance the current query with conversation context for better retrieval."""
        
        if not conversation_context:
            return current_query
        
        # Extract key terms from recent conversation
        context_keywords = []
        for line in conversation_context.split('\n')[-4:]:  # Last 4 exchanges
            if line.startswith("User:") or line.startswith("You:"):
                # Extract potential clinical terms, table numbers, etc.
                content = line.split(":", 1)[1].strip()
                # Simple keyword extraction - could be enhanced with NLP
                words = content.split()
                clinical_keywords = [w for w in words if 
                                   len(w) > 3 and 
                                   (w.lower() in ['table', 'listing', 'figure', 'adverse', 'events', 'safety', 'efficacy'] or
                                    '.' in w)]  # Table numbers like "14.3.1"
                context_keywords.extend(clinical_keywords)
        
        # Combine current query with relevant context keywords
        if context_keywords:
            enhanced_query = f"{current_query} {' '.join(set(context_keywords))}"
            return enhanced_query
        
        return current_query

    async def _query_llm_with_context(self, current_query: str, conversation_context: str, retrieved_context: str) -> str:
        """Query LLM with both conversation and retrieved context."""
        
        prompt = self.conversational_prompt_template.format(
            conversation_context=conversation_context or "No previous conversation.",
            current_query=current_query,
            retrieved_context=retrieved_context
        )
        
        try:
            if hasattr(self.llm, 'acomplete'):
                response = await self.llm.acomplete(prompt)
            else:
                response = self.llm.complete(prompt)
            
            return str(response).strip()
            
        except Exception as e:
            logger.error(f"LLM query error in chat: {e}")
            return f"I apologize, but I encountered an error while processing your query: {str(e)}"

    async def _stream_llm_with_context(self, current_query: str, conversation_context: str, retrieved_context: str) -> AsyncGenerator[str, None]:
        """Stream LLM response with context."""
        
        prompt = self.conversational_prompt_template.format(
            conversation_context=conversation_context or "No previous conversation.",
            current_query=current_query,
            retrieved_context=retrieved_context
        )
        
        try:
            # Use the same streaming logic as query service
            if hasattr(self.llm, 'astream_complete'):
                stream_response = self.llm.astream_complete(prompt)
                
                if hasattr(stream_response, '__await__'):
                    stream_response = await stream_response
                
                if hasattr(stream_response, '__aiter__'):
                    async for chunk in stream_response:
                        content = str(chunk.delta) if hasattr(chunk, 'delta') else str(chunk)
                        if content:
                            yield content
                else:
                    response_text = str(stream_response)
                    # Simulate streaming
                    words = response_text.split()
                    for i in range(0, len(words), 5):
                        chunk_words = words[i:i + 5]
                        yield ' '.join(chunk_words) + (' ' if i + 5 < len(words) else '')
                        await asyncio.sleep(0.1)
            else:
                # Fallback to regular completion
                response = await self._query_llm_with_context(current_query, conversation_context, retrieved_context)
                words = response.split()
                for i in range(0, len(words), 5):
                    chunk_words = words[i:i + 5]
                    yield ' '.join(chunk_words) + (' ' if i + 5 < len(words) else '')
                    await asyncio.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"Streaming error in chat: {e}")
            yield f"I apologize, but I encountered an error: {str(e)}"

    async def _cleanup_old_sessions(self, document_id: str):
        """Clean up old inactive sessions for a document."""
        
        try:
            # Get sessions for this document
            document_sessions = [s for s in self._chat_sessions.values() if s.document_id == document_id]
            
            # Remove sessions inactive for more than max_inactive_hours
            cutoff_time = datetime.now() - timedelta(hours=self._max_inactive_hours)
            inactive_sessions = [s for s in document_sessions if s.updated_at < cutoff_time]
            
            for session in inactive_sessions:
                del self._chat_sessions[session.id]
                logger.info(f"Cleaned up inactive session {session.id}")
            
            # If still too many sessions, remove oldest ones
            remaining_sessions = [s for s in self._chat_sessions.values() if s.document_id == document_id]
            if len(remaining_sessions) > self._max_sessions_per_document:
                # Sort by update time and remove oldest
                remaining_sessions.sort(key=lambda x: x.updated_at)
                sessions_to_remove = remaining_sessions[:-self._max_sessions_per_document]
                
                for session in sessions_to_remove:
                    del self._chat_sessions[session.id]
                    logger.info(f"Cleaned up excess session {session.id}")
                    
        except Exception as e:
            logger.error(f"Error cleaning up sessions: {e}")

    async def get_chat_statistics(self) -> Dict[str, Any]:
        """Get chat service statistics."""
        
        total_sessions = len(self._chat_sessions)
        total_messages = sum(len(s.messages) for s in self._chat_sessions.values())
        total_queries = sum(s.total_queries for s in self._chat_sessions.values())
        
        # Sessions by document
        sessions_by_document = {}
        for session in self._chat_sessions.values():
            doc_id = session.document_id
            if doc_id not in sessions_by_document:
                sessions_by_document[doc_id] = 0
            sessions_by_document[doc_id] += 1
        
        return {
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "total_queries": total_queries,
            "sessions_by_document": sessions_by_document,
            "average_messages_per_session": total_messages / total_sessions if total_sessions > 0 else 0
        }
