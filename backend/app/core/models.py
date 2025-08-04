# backend/app/core/models.py
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Union
from enum import Enum
from datetime import datetime
import uuid


class ProcessingStatusEnum(str, Enum):
    QUEUED = "queued"
    EXTRACTING_TEXT = "extracting_text"
    CHUNKING = "chunking"
    EXTRACTING_TLF_METADATA = "extracting_tlf_metadata"
    BUILDING_INDEX = "building_index"
    COMPLETED = "completed"
    FAILED = "failed"


class TLFType(str, Enum):
    TABLE = "table"
    LISTING = "listing"
    FIGURE = "figure"


class ClinicalDomain(str, Enum):
    DEMOGRAPHICS = "demographics"
    ADVERSE_EVENTS = "adverse_events"
    LABORATORY = "laboratory"
    VITAL_SIGNS = "vital_signs"
    ECG = "ecg"
    EFFICACY = "efficacy"
    PHARMACOKINETICS = "pharmacokinetics"
    DISPOSITION = "disposition"
    EXPOSURE = "exposure"
    TABLE_OF_CONTENTS = "table_of_contents"


# Request Models
class DocumentUploadRequest(BaseModel):
    """Request model for document upload."""
    filename: str = Field(..., description="Original filename")
    compound: str = Field(..., description="Compound name (e.g., 'JZPxxx')")
    study_id: str = Field(..., description="Study identifier (e.g., 'JZPxxx-xxx')")
    deliverable: str = Field(..., description="Deliverable type (e.g., 'Final CSR', 'Interim Analysis 1')")
    description: Optional[str] = Field(None, description="Document description")


class DocumentStructureResponse(BaseModel):
    """Response model for document structure."""
    compounds: List[str] = Field(..., description="Available compounds")
    structure: Dict[str, Any] = Field(..., description="Full hierarchical structure")


class QueryRequest(BaseModel):
    """Request model for querying documents."""
    query: str = Field(..., description="Natural language query", min_length=1)
    document_id: str = Field(..., description="Document ID to query against")
    top_k: int = Field(default=15, description="Number of chunks to retrieve", ge=1, le=50)
    min_confidence: float = Field(default=0.4, description="Minimum confidence threshold", ge=0.0, le=1.0)
    stream_response: bool = Field(default=True, description="Whether to stream the response")


class QueryFilters(BaseModel):
    """Optional filters for queries."""
    tlf_types: Optional[List[TLFType]] = Field(None, description="Filter by TLF types")
    clinical_domains: Optional[List[ClinicalDomain]] = Field(None, description="Filter by clinical domains")
    output_numbers: Optional[List[str]] = Field(None, description="Filter by specific output numbers")
    populations: Optional[List[str]] = Field(None, description="Filter by analysis populations")


class EnhancedQueryRequest(QueryRequest):
    """Enhanced query request with filters."""
    filters: Optional[QueryFilters] = Field(None, description="Additional query filters")


# Response Models
class ProcessingStatus(BaseModel):
    """Response model for processing status."""
    document_id: str = Field(..., description="Unique document identifier")
    status: ProcessingStatusEnum = Field(..., description="Current processing status")
    progress: int = Field(..., description="Progress percentage (0-100)", ge=0, le=100)
    message: Optional[str] = Field(None, description="Status message")
    created_at: datetime = Field(..., description="When processing started")
    updated_at: datetime = Field(..., description="Last update time")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    
    # Processing details
    total_pages: Optional[int] = Field(None, description="Total pages in document")
    processed_pages: Optional[int] = Field(None, description="Pages processed so far")
    total_chunks: Optional[int] = Field(None, description="Total chunks created")
    tlf_outputs_found: Optional[int] = Field(None, description="Number of TLF outputs identified")


class TLFMetadata(BaseModel):
    """TLF metadata extracted from document."""
    tlf_type: Optional[TLFType] = Field(None, description="Type of TLF output")
    output_number: Optional[str] = Field(None, description="Output identifier (e.g., 9.1.1)")
    title: Optional[str] = Field(None, description="Title of the output")
    clinical_domain: Optional[ClinicalDomain] = Field(None, description="Clinical domain")
    population: Optional[str] = Field(None, description="Analysis population")
    treatment_groups: List[str] = Field(default_factory=list, description="Treatment groups mentioned")
    overall_confidence: float = Field(..., description="Overall extraction confidence", ge=0.0, le=1.0)
    page_info: Dict[str, Any] = Field(default_factory=dict, description="Page information")


class DocumentChunk(BaseModel):
    """Individual document chunk with metadata."""
    chunk_id: str = Field(..., description="Unique chunk identifier")
    text: str = Field(..., description="Chunk text content")
    page_number: Optional[int] = Field(None, description="Page number")
    tlf_metadata: TLFMetadata = Field(..., description="Extracted TLF metadata")
    similarity_score: Optional[float] = Field(None, description="Similarity score for queries")


class DocumentInfo(BaseModel):
    """Document information response."""
    document_id: str = Field(..., description="Unique document identifier")
    filename: str = Field(..., description="Original filename")
    study_id: Optional[str] = Field(None, description="Study identifier")
    description: Optional[str] = Field(None, description="Document description")
    
    # Storage structure fields
    compound: Optional[str] = Field(None, description="Compound name")
    deliverable: Optional[str] = Field(None, description="Deliverable type")
    file_path: Optional[str] = Field(None, description="Stored file path")
    file_hash: Optional[str] = Field(None, description="File content hash for deduplication")
    
    # Processing info
    status: ProcessingStatusEnum = Field(..., description="Processing status")
    created_at: datetime = Field(..., description="Upload time")
    processed_at: Optional[datetime] = Field(None, description="Processing completion time")
    
    # Document stats
    total_pages: Optional[int] = Field(None, description="Total pages")
    total_chunks: int = Field(0, description="Total chunks created")
    tlf_outputs_found: int = Field(0, description="Number of TLF outputs found")
    
    # TLF summary
    tlf_types_distribution: Dict[str, int] = Field(default_factory=dict, description="Distribution of TLF types")
    clinical_domains_distribution: Dict[str, int] = Field(default_factory=dict, description="Distribution of clinical domains")


class QuerySource(BaseModel):
    """Source information for query responses."""
    output_type: Optional[str] = Field(None, description="TLF type")
    output_number: Optional[str] = Field(None, description="Output number")
    title: Optional[str] = Field(None, description="Output title")
    page_number: Optional[int] = Field(None, description="Page number")
    confidence: float = Field(..., description="Confidence score")
    chunk_count: int = Field(..., description="Number of chunks from this source")


class QueryResponse(BaseModel):
    """Response model for queries."""
    query: str = Field(..., description="Original query")
    response: str = Field(..., description="Generated response")
    document_id: str = Field(..., description="Document ID queried")
    
    # Metadata
    processing_time_ms: int = Field(..., description="Processing time in milliseconds")
    chunks_retrieved: int = Field(..., description="Number of chunks retrieved")
    sources_used: List[QuerySource] = Field(default_factory=list, description="Sources used in response")
    
    # Query parameters used
    top_k: int = Field(..., description="Top K parameter used")
    min_confidence: float = Field(..., description="Minimum confidence used")
    
    created_at: datetime = Field(default_factory=datetime.now, description="Response timestamp")


class StreamingQueryChunk(BaseModel):
    """Streaming query response chunk."""
    type: str = Field(..., description="Chunk type: 'content', 'sources', 'complete', 'error'")
    data: Union[str, List[QuerySource], Dict[str, Any]] = Field(..., description="Chunk data")
    timestamp: datetime = Field(default_factory=datetime.now, description="Chunk timestamp")


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.now, description="Error timestamp")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Service status")
    timestamp: datetime = Field(default_factory=datetime.now, description="Health check timestamp")
    services: Dict[str, str] = Field(..., description="Individual service statuses")
    version: str = Field(..., description="API version")


# Utility models
class DocumentSummary(BaseModel):
    """Summary of all documents."""
    total_documents: int = Field(..., description="Total number of documents")
    by_status: Dict[ProcessingStatusEnum, int] = Field(..., description="Documents by status")
    total_tlf_outputs: int = Field(..., description="Total TLF outputs across all documents")
    recent_documents: List[DocumentInfo] = Field(..., description="Recently uploaded documents")


class SystemStats(BaseModel):
    """System statistics."""
    total_documents: int = Field(..., description="Total documents processed")
    total_chunks: int = Field(..., description="Total chunks in system")
    total_queries: int = Field(..., description="Total queries processed")
    average_processing_time_seconds: float = Field(..., description="Average document processing time")
    uptime_seconds: int = Field(..., description="System uptime in seconds")


# Chat Models
class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    """Individual message in a chat conversation."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique message ID")
    role: MessageRole = Field(..., description="Message role (user/assistant/system)")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=datetime.now, description="Message timestamp")
    
    # Query-specific metadata (for assistant messages)
    sources_used: List[QuerySource] = Field(default_factory=list, description="Sources used in response")
    chunks_retrieved: int = Field(default=0, description="Number of chunks retrieved")
    processing_time_ms: int = Field(default=0, description="Processing time in milliseconds")
    
    # Additional metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional message metadata")


class ChatSession(BaseModel):
    """Chat session containing conversation history."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique session ID")
    document_id: str = Field(..., description="Document ID for this chat session")
    title: str = Field(default="New Chat", description="Chat session title")
    created_at: datetime = Field(default_factory=datetime.now, description="Session creation time")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update time")
    
    messages: List[ChatMessage] = Field(default_factory=list, description="Conversation messages")
    
    # Session settings
    context_window: int = Field(default=10, description="Number of previous messages to include in context")
    max_tokens: int = Field(default=4096, description="Maximum tokens for responses")
    temperature: float = Field(default=0.2, description="Response creativity (0.0-1.0)")
    
    # Session metadata
    total_queries: int = Field(default=0, description="Total queries in this session")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional session metadata")


class ChatRequest(BaseModel):
    """Request for sending a message in a chat session."""
    session_id: str = Field(..., description="Chat session ID")
    message: str = Field(..., description="User message", min_length=1)
    
    # Query parameters
    top_k: int = Field(default=15, description="Number of chunks to retrieve", ge=1, le=50)
    min_confidence: float = Field(default=0.4, description="Minimum confidence threshold", ge=0.0, le=1.0)
    include_context: bool = Field(default=True, description="Whether to include conversation context")


class ChatResponse(BaseModel):
    """Response from chat query."""
    session_id: str = Field(..., description="Chat session ID")
    message_id: str = Field(..., description="ID of the assistant's response message")
    response: str = Field(..., description="Assistant's response")
    
    # Query metadata
    sources_used: List[QuerySource] = Field(default_factory=list, description="Sources used in response")
    chunks_retrieved: int = Field(..., description="Number of chunks retrieved")
    processing_time_ms: int = Field(..., description="Processing time in milliseconds")
    
    # Context information
    context_messages_used: int = Field(..., description="Number of previous messages included in context")
    total_messages_in_session: int = Field(..., description="Total messages in session after this response")


class NewChatRequest(BaseModel):
    """Request to create a new chat session."""
    document_id: str = Field(..., description="Document ID to chat about")
    title: Optional[str] = Field(None, description="Optional chat title")
    context_window: int = Field(default=10, description="Number of previous messages to include", ge=1, le=50)
    system_message: Optional[str] = Field(None, description="Optional system message to set context")


class ChatSessionSummary(BaseModel):
    """Summary information about a chat session."""
    id: str = Field(..., description="Session ID")
    document_id: str = Field(..., description="Document ID")
    title: str = Field(..., description="Session title")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: datetime = Field(..., description="Last update time")
    total_messages: int = Field(..., description="Number of messages in session")
    total_queries: int = Field(..., description="Number of user queries")
    last_message_preview: Optional[str] = Field(None, description="Preview of last message")


class UpdateChatRequest(BaseModel):
    """Request to update chat session settings."""
    title: Optional[str] = Field(None, description="New session title")
    context_window: Optional[int] = Field(None, description="New context window size", ge=1, le=50)


class StreamingChatChunk(BaseModel):
    """Streaming chat response chunk."""
    session_id: str = Field(..., description="Chat session ID")
    message_id: str = Field(..., description="Message ID being streamed")
    type: str = Field(..., description="Chunk type: 'content', 'sources', 'complete', 'error'")
    data: Any = Field(..., description="Chunk data")
    timestamp: datetime = Field(default_factory=datetime.now, description="Chunk timestamp")
