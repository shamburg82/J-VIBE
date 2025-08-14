# backend/app/services/document_service.py
from typing import List, Dict, Optional, Any
import asyncio
import uuid
import tempfile
import os
import shutil
import hashlib
import json
from datetime import datetime
from pathlib import Path
import logging
from fastapi import UploadFile

from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import TokenTextSplitter
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.extractors import QuestionsAnsweredExtractor, SummaryExtractor, KeywordExtractor
from llama_index.core.schema import TextNode

from ..extractors.tlf_extractor import TLFExtractor
from ..core.models import ProcessingStatus, DocumentInfo, DocumentSummary, ProcessingStatusEnum
from .storage_service import StorageService

logger = logging.getLogger(__name__)


class DocumentService:
    """Service for handling document upload, processing, and management."""
    
    def __init__(self, llm, storage_service: StorageService, config=None):
        self.llm = llm
        self.storage_service = storage_service
                
        if config is None:
            from ..core.config import get_config
            config = get_config()
        
        self.base_storage_path = getattr(config, 'base_storage_path', Path("//datastore/BU/RD/Restricted/DS/AIGAS/source_docs/study"))
        
        # Ensure it's a Path object
        if not isinstance(self.base_storage_path, Path):
            self.base_storage_path = Path(self.base_storage_path)
        
        logger.info(f"DocumentService initialized with storage path: {self.base_storage_path}")
        
        # **WORKAROUND: File persistence tracking**
        # Create a manifest file to track uploaded documents even without vector store
        self.manifest_file = self.base_storage_path / "document_manifest.json"
        self.file_manifest = self._load_manifest()
        
        # Flag to control vector store usage (easy to revert)
        self.use_vector_store = getattr(config, 'use_vector_store', False)
        logger.info(f"Vector store usage: {'enabled' if self.use_vector_store else 'disabled (files only)'}")
                
        # Processing status tracking
        self._processing_status: Dict[str, ProcessingStatus] = {}
        self._document_info: Dict[str, DocumentInfo] = {}

        # Document hash tracking for deduplication
        self._document_hashes: Dict[str, str] = {}

        # Initialize TLF extractor
        confidence_threshold = getattr(config,'confidence_threshold', 0.7)
        self.tlf_extractor = TLFExtractor(
            llm=llm,
            confidence_threshold=confidence_threshold,
            use_llm_validation=True
        )
        
        # Initialize text splitter
        chunk_size = getattr(config,'chunk_size', 512)
        chunk_overlap = getattr(config,'chunk_overlap', 50)
        self.text_splitter = TokenTextSplitter(
            separator=" ",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        
        # Initialize other extractors
        self.extractors = [
            self.tlf_extractor,
            QuestionsAnsweredExtractor(questions=2, llm=llm),
            SummaryExtractor(summaries=["self"], llm=llm),
            KeywordExtractor(keywords=8, llm=llm),
        ]
    
        # Extractor configuration flags
        self.enable_keyword_extraction = getattr(config, 'enable_keyword_extraction', True) if config else True
        self.enable_question_extraction = getattr(config, 'enable_question_extraction', True) if config else True
        self.enable_summary_extraction = getattr(config, 'enable_summary_extraction', False) if config else False
        

        # Load existing documents from manifest
        self._restore_documents_from_manifest()

    async def process_document_async(
        self,
        document_id: str,
        file_content: bytes,
        filename: str,
        compound: str,
        study_id: str,
        deliverable: str,
        description: Optional[str] = None
    ):
        """Process document asynchronously with status updates."""
        
        try:
            # Initialize processing status
            await self._update_status(
                document_id, ProcessingStatusEnum.EXTRACTING_TEXT, 5,
                "Processing uploaded file..."
            )
                        
            # Generate file hash for deduplication
            file_hash = hashlib.sha256(file_content).hexdigest()
        
            # Check for existing document with same hash
            existing_doc_id = self._document_hashes.get(file_hash)
            if existing_doc_id and existing_doc_id in self._document_info:
                duplicate_handled = await self._handle_duplicate_document(document_id, existing_doc_id, filename)
                if duplicate_handled:
                    return
            
            await self._update_status(
                document_id, ProcessingStatusEnum.EXTRACTING_TEXT, 10,
                "Storing file to permanent location..."
            )
            
            # Store file permanently
            stored_file_path = await self._store_file_permanently(
                file_content, filename, compound, study_id, deliverable
            )
            
            # **WORKAROUND: Always create document info, even without vector processing**
            doc_info = DocumentInfo(
                document_id=document_id,
                filename=filename,         
                compound=compound,
                study_id=study_id,       
                deliverable=deliverable,
                file_path=str(stored_file_path),
                file_hash=file_hash,
                description=description,
                status=ProcessingStatusEnum.EXTRACTING_TEXT,
                created_at=datetime.now(),
                total_pages=None,  # Will be updated if processing succeeds
                total_chunks=0,
                tlf_outputs_found=0,
                tlf_types_distribution={},
                clinical_domains_distribution={}
            )
            
            self._document_info[document_id] = doc_info
            self._document_hashes[file_hash] = document_id
            
            # Add to manifest immediately so file is tracked
            self._add_to_manifest(document_id, doc_info)

            if self.use_vector_store:
                # Full processing with vector store
                await self._process_with_vector_store(document_id, stored_file_path, doc_info)
            else:
                # Minimal processing without vector store
                await self._process_without_vector_store(document_id, stored_file_path, doc_info)
                
        except Exception as e:
            logger.error(f"Error processing document {document_id}: {e}")
            await self._update_status(
                document_id, ProcessingStatusEnum.FAILED, 0,
                f"Processing failed: {str(e)}",
                error_message=str(e)
            )

    async def _process_with_vector_store(self, document_id: str, stored_file_path: Path, doc_info: DocumentInfo):
        """Full processing with vector store (original method)."""
        
        await self._update_status(
            document_id, ProcessingStatusEnum.EXTRACTING_TEXT, 20,
            "Extracting text from PDF..."
        )
        
        # Extract text from stored PDF
        try:
            documents = SimpleDirectoryReader(input_files=[str(stored_file_path)]).load_data()
            if not documents:
                raise ValueError("PDF contains no extractable text")
                
            total_pages = len(documents)
            doc_info.total_pages = total_pages
            
        except Exception as pdf_error:
            logger.error(f"PDF extraction failed: {pdf_error}")
            await self._update_status(
                document_id, ProcessingStatusEnum.FAILED, 0,
                f"PDF extraction failed: {str(pdf_error)}",
                error_message=str(pdf_error)
            )
            return
        
        await self._update_status(
            document_id, ProcessingStatusEnum.CHUNKING, 40,
            f"Chunking document ({total_pages} pages)...",
            total_pages=total_pages
        )
    
        # Create nodes directly using the text splitter first
        try:
            # First create initial nodes from documents
            from llama_index.core.schema import TextNode
            initial_nodes = []
            
            for doc_idx, doc in enumerate(documents):
                # Split text into chunks first
                text_chunks = self.text_splitter.split_text(doc.text)
                
                for chunk_idx, chunk_text in enumerate(text_chunks):
                    if chunk_text.strip():
                        node = TextNode(
                            text=chunk_text,
                            id_=f"{document_id}_doc{doc_idx}_chunk{chunk_idx}",
                            metadata={
                                "document_id": document_id,
                                "page_number": doc.metadata.get("page_label", doc_idx + 1),
                                "source": doc.metadata.get("file_name", stored_file_path.name),
                                "doc_idx": doc_idx,
                                "chunk_idx": chunk_idx
                            }
                        )
                        initial_nodes.append(node)
            
            logger.info(f"Created {len(initial_nodes)} initial nodes")
            
            if not initial_nodes:
                raise ValueError("No text chunks created")
            
            await self._update_status(
                document_id, ProcessingStatusEnum.EXTRACTING_TLF_METADATA, 50,
                f"Extracting metadata from {len(initial_nodes)} chunks..."
            )
        
            # Apply extractors directly without the problematic pipeline
            logger.info("Running extraction pipeline...")
            
            # Apply TLF extraction first (most important)
            doc_nodes = self.tlf_extractor(initial_nodes)
            logger.info(f"TLF extraction complete, {len(doc_nodes)} nodes")
            
            # Then apply other extractors if enabled
            try:
                from llama_index.core.extractors import KeywordExtractor, QuestionsAnsweredExtractor
                
                # Apply keyword extraction in batches
                if self.llm and getattr(self, 'enable_keyword_extraction', True):
                    await self._update_status(
                        document_id, ProcessingStatusEnum.EXTRACTING_TLF_METADATA, 60,
                        "Extracting keywords..."
                    )
                    
                    keyword_extractor = KeywordExtractor(keywords=10, llm=self.llm)
                    
                    # Process in smaller batches to show progress
                    batch_size = 10
                    for i in range(0, len(doc_nodes), batch_size):
                        batch = doc_nodes[i:i+batch_size]
                        progress = 60 + int((i / len(doc_nodes)) * 10)  # 60-70% for keywords
                        
                        await self._update_status(
                            document_id, ProcessingStatusEnum.EXTRACTING_TLF_METADATA, progress,
                            f"Extracting keywords: {i+1}-{min(i+batch_size, len(doc_nodes))}/{len(doc_nodes)}..."
                        )
                        
                        # Apply keyword extraction to batch
                        try:
                            # Keyword extractor modifies nodes in place
                            keyword_extractor(batch)
                        except Exception as ke:
                            logger.warning(f"Keyword extraction failed for batch: {ke}")
                    
                    logger.info("Keyword extraction complete")
                
                # Apply question extraction if enabled
                if self.llm and getattr(self, 'enable_question_extraction', True):
                    await self._update_status(
                        document_id, ProcessingStatusEnum.EXTRACTING_TLF_METADATA, 70,
                        "Generating questions..."
                    )
                    
                    question_extractor = QuestionsAnsweredExtractor(
                        questions=3,
                        llm=self.llm,
                        prompt_template="""
                        Given the following clinical trial text, generate {num_questions} questions 
                        that this text can answer. Focus on clinical, statistical, and regulatory aspects.
                        
                        Text: {context_str}
                        
                        Questions:
                        """
                    )
                    
                    # Process in smaller batches
                    batch_size = 5  # Smaller batches for question generation (more expensive)
                    for i in range(0, len(doc_nodes), batch_size):
                        batch = doc_nodes[i:i+batch_size]
                        progress = 70 + int((i / len(doc_nodes)) * 10)  # 70-80% for questions
                        
                        await self._update_status(
                            document_id, ProcessingStatusEnum.EXTRACTING_TLF_METADATA, progress,
                            f"Generating questions: {i+1}-{min(i+batch_size, len(doc_nodes))}/{len(doc_nodes)}..."
                        )
                        
                        try:
                            # Question extractor modifies nodes in place
                            question_extractor(batch)
                        except Exception as qe:
                            logger.warning(f"Question extraction failed for batch: {qe}")
                    
                    logger.info("Question extraction complete")
                
            except Exception as extractor_error:
                logger.warning(f"Additional extractors failed: {extractor_error}, continuing with TLF metadata only")
            
            # Verify we have nodes
            if not doc_nodes:
                raise ValueError("No nodes after extraction")
            
            # Log sample metadata
            if doc_nodes:
                sample_metadata = doc_nodes[0].metadata
                logger.info(f"Sample node metadata keys: {list(sample_metadata.keys())}")
                if 'keywords' in sample_metadata:
                    logger.info(f"Sample keywords: {sample_metadata.get('keywords', [])[:5]}")
                if 'questions_this_excerpt_can_answer' in sample_metadata:
                    logger.info(f"Sample questions: {sample_metadata.get('questions_this_excerpt_can_answer', [])[:2]}")
            
        except Exception as processing_error:
            logger.error(f"Processing error: {processing_error}")
            logger.exception("Full processing error:")
            
            # Fallback: Create basic nodes with TLF extraction only
            logger.info("Falling back to basic TLF extraction")
            from llama_index.core.schema import TextNode
            doc_nodes = []
            
            total_docs = len(documents)
            for doc_idx, doc in enumerate(documents):
                progress = 50 + int((doc_idx / total_docs) * 30)
                await self._update_status(
                    document_id, ProcessingStatusEnum.EXTRACTING_TLF_METADATA, progress,
                    f"Processing document {doc_idx+1}/{total_docs} (fallback mode)..."
                )
                
                text_chunks = self.text_splitter.split_text(doc.text)
                
                for chunk_idx, chunk_text in enumerate(text_chunks):
                    if chunk_text.strip():
                        node = TextNode(
                            text=chunk_text,
                            id_=f"{document_id}_fallback_{doc_idx}_{chunk_idx}",
                            metadata={
                                "document_id": document_id,
                                "page_number": doc.metadata.get("page_label", doc_idx + 1),
                                "source": stored_file_path.name
                            }
                        )
                        doc_nodes.append(node)
            
            # Apply TLF extraction
            if doc_nodes:
                await self._update_status(
                    document_id, ProcessingStatusEnum.EXTRACTING_TLF_METADATA, 75,
                    f"Applying TLF extraction to {len(doc_nodes)} nodes..."
                )
                doc_nodes = self.tlf_extractor(doc_nodes)
                logger.info(f"Fallback: Applied TLF extraction to {len(doc_nodes)} nodes")
        
        if not doc_nodes:
            raise ValueError("No nodes created from document")
        
        await self._update_status(
            document_id, ProcessingStatusEnum.BUILDING_INDEX, 85,
            f"Building vector index with {len(doc_nodes)} nodes..."
        )
        
        # Store in vector index
        await self.storage_service.create_index(document_id, doc_nodes)
        
        # Count TLF outputs found
        tlf_outputs = await self._count_tlf_outputs(doc_nodes)
        
        # Update document info
        doc_info.status = ProcessingStatusEnum.COMPLETED
        doc_info.processed_at = datetime.now()
        doc_info.total_chunks = len(doc_nodes)
        doc_info.tlf_outputs_found = tlf_outputs["total"]
        doc_info.tlf_types_distribution = tlf_outputs["types"]
        doc_info.clinical_domains_distribution = tlf_outputs["domains"]
        
        await self._update_status(
            document_id, ProcessingStatusEnum.COMPLETED, 100,
            f"Processing complete! Found {tlf_outputs['total']} TLF outputs.",
            total_pages=total_pages,
            total_chunks=len(doc_nodes),
            tlf_outputs_found=tlf_outputs["total"]
        )
        
        # Update manifest
        self._add_to_manifest(document_id, doc_info)
        
        logger.info(f"Successfully processed document {document_id} with vector store")

    async def _manual_document_processing(self, documents) -> List:
        """Manual fallback processing when pipeline fails."""
        logger.info("Starting manual document processing fallback")
        
        try:
            # Step 1: Manual text splitting
            all_text_chunks = []
            for doc in documents:
                if doc.text and doc.text.strip():
                    # Use text splitter to create chunks
                    chunks = self.text_splitter.split_text(doc.text)
                    all_text_chunks.extend(chunks)
            
            logger.info(f"Manual text splitting produced {len(all_text_chunks)} chunks")
            
            if not all_text_chunks:
                return []
            
            # Step 2: Convert to TextNode objects
            text_nodes = []
            for i, chunk in enumerate(all_text_chunks):
                if isinstance(chunk, str) and chunk.strip():
                    node = TextNode(
                        text=chunk,
                        id_=f"manual_node_{i}",
                        metadata={"source": "manual_processing"}
                    )
                    text_nodes.append(node)
            
            logger.info(f"Created {len(text_nodes)} TextNode objects")
            return text_nodes
            
        except Exception as e:
            logger.error(f"Manual document processing failed: {e}")
            return []


    async def _store_file_permanently(
        self,
        file_content: bytes,
        filename: str,
        compound: str,
        study_id: str,
        deliverable: str
    ) -> Path:
        """Store file in the permanent directory structure."""
        
        # Create directory structure: compound/study/deliverable
        storage_dir = self.base_storage_path / compound / study_id / deliverable
        storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Sanitize filename
        safe_filename = self._sanitize_filename(filename)
        file_path = storage_dir / safe_filename
        
        logger.info(f"Storing file: {filename} -> {safe_filename} at {file_path}")
        
        # Handle existing file - create backup if different content
        if file_path.exists():
            existing_hash = await self._get_file_hash(file_path)
            new_hash = hashlib.sha256(file_content).hexdigest()
            
            if existing_hash != new_hash:
                # Create backup of existing file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = storage_dir / f"{safe_filename}.backup_{timestamp}"
                shutil.copy2(file_path, backup_path)
                logger.info(f"Created backup: {backup_path}")
        
        # Write new file
        with open(file_path, 'wb') as f:
            f.write(file_content)
        
        # Verify file was written correctly
        if not file_path.exists():
            raise IOError(f"Failed to write file to {file_path}")
        
        written_size = file_path.stat().st_size
        expected_size = len(file_content)
        
        if written_size != expected_size:
            raise IOError(f"File size mismatch: wrote {written_size} bytes, expected {expected_size}")
        
        logger.info(f"Successfully stored file: {file_path} ({written_size} bytes)")
        return file_path

    async def _get_file_hash(self, file_path: Path) -> str:
        """Get SHA-256 hash of existing file."""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe storage."""
        import re

        # Split filename and extension
        if '.' in filename:
            name, ext = filename.rsplit('.', 1)
        else:
            name, ext = filename, ''

        # Remove or replace unsafe characters
        unsafe_chars = ['<', '>', ':', '"', '|', '?', '*']        
        safe_name = name
        
        for char in unsafe_chars:
            safe_name = safe_name.replace(char, '_')
        
        # Remove multiple consecutive spaces and replace with underscores
        safe_name = re.sub(r'\s+', '_', safe_name)
        
        # Ensure it doesn't start or end with dots or spaces
        safe_name = safe_name.strip('. ')
        
        # Reconstruct with original extension
        if ext:
            return f"{safe_name}.{ext}"
        else:
            return safe_name

    async def _handle_duplicate_document(
        self,
        new_document_id: str,
        existing_document_id: str,
        filename: str
    ):
        """Handle case where document with same content already exists."""
        
        existing_doc = self._document_info[existing_document_id]
    
        if not existing_doc:
            logger.warning(f"Existing document {existing_document_id} not found in memory, treating as new document")
            # Don't treat as duplicate if we can't find the existing document
            return False
        
        await self._update_status(
            new_document_id, ProcessingStatusEnum.COMPLETED, 100,
            f"Document already exists (duplicate of {existing_document_id}). Using existing processing results.",
            total_pages=existing_doc.total_pages,
            total_chunks=existing_doc.total_chunks,
            tlf_outputs_found=existing_doc.tlf_outputs_found
        )
        
        # Create new document info pointing to same data
        duplicate_doc_info = DocumentInfo(
            document_id=new_document_id,
            filename=filename,
            study_id=existing_doc.study_id,
            description=f"Duplicate of {existing_document_id}",
            status=ProcessingStatusEnum.COMPLETED,
            created_at=datetime.now(),
            processed_at=datetime.now(),
            total_pages=existing_doc.total_pages,
            total_chunks=existing_doc.total_chunks,
            tlf_outputs_found=existing_doc.tlf_outputs_found,
            tlf_types_distribution=existing_doc.tlf_types_distribution,
            clinical_domains_distribution=existing_doc.clinical_domains_distribution
        )
        
        # Copy storage metadata
        if hasattr(existing_doc, 'compound'):
            duplicate_doc_info.compound = existing_doc.compound
            duplicate_doc_info.deliverable = existing_doc.deliverable
            duplicate_doc_info.file_path = existing_doc.file_path
            duplicate_doc_info.file_hash = existing_doc.file_hash
        
        self._document_info[new_document_id] = duplicate_doc_info
        
        # Add to manifest
        self._add_to_manifest(new_document_id, duplicate_doc_info)
    
        # Point to same vector index if using vector store
        if self.use_vector_store and existing_document_id in self._document_info:
            try:
                await self.storage_service.link_index(new_document_id, existing_document_id)
            except Exception as e:
                logger.error(f"Failed to link vector index, continuing without: {e}")
        
        logger.info(f"Document {new_document_id} is duplicate of {existing_document_id}")
        return True


    async def _update_status(
        self,
        document_id: str,
        status: ProcessingStatusEnum,
        progress: int,
        message: str,
        **kwargs
    ):
        """Update processing status."""
        
        current_status = self._processing_status.get(document_id)
        
        if current_status:
            # Update existing status
            current_status.status = status
            current_status.progress = progress
            current_status.message = message
            current_status.updated_at = datetime.now()
            
            # Update additional fields
            for key, value in kwargs.items():
                if hasattr(current_status, key):
                    setattr(current_status, key, value)
        else:
            # Create new status
            self._processing_status[document_id] = ProcessingStatus(
                document_id=document_id,
                status=status,
                progress=progress,
                message=message,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                **kwargs
            )

    async def _count_tlf_outputs(self, nodes: List) -> Dict[str, Any]:
        """Count TLF outputs and create distribution statistics."""
        
        tlf_types = {}
        clinical_domains = {}
        total = 0
        
        for node in nodes:
            metadata = getattr(node, 'metadata', {})
            
            # Count TLF types
            tlf_type = metadata.get('tlf_type')
            if tlf_type:
                tlf_types[tlf_type] = tlf_types.get(tlf_type, 0) + 1
                total += 1
            
            # Count clinical domains
            domain = metadata.get('clinical_domain')
            if domain and domain != 'table_of_contents':
                clinical_domains[domain] = clinical_domains.get(domain, 0) + 1
        
        return {
            "total": total,
            "types": tlf_types,
            "domains": clinical_domains
        }

    async def get_processing_status(self, document_id: str) -> Optional[ProcessingStatus]:
        """Get current processing status for a document."""
        status = self._processing_status.get(document_id)
        if status:
            return status
        
        # If no processing status but document exists, create a status from document info
        doc_info = self._document_info.get(document_id)
        if doc_info:
            return ProcessingStatus(
                document_id=document_id,
                status=doc_info.status,
                progress=100 if doc_info.status == ProcessingStatusEnum.COMPLETED else 0,
                message=f"Document {doc_info.status}",
                created_at=doc_info.created_at,
                updated_at=doc_info.processed_at or doc_info.created_at,
                total_pages=doc_info.total_pages,
                total_chunks=doc_info.total_chunks,
                tlf_outputs_found=doc_info.tlf_outputs_found
            )
        
        return None

    async def get_document_info(self, document_id: str) -> Optional[DocumentInfo]:
        """Get document information."""
        return self._document_info.get(document_id)

    async def list_documents(
        self,
        limit: int = 50,
        offset: int = 0,
        status_filter: Optional[str] = None,
        compound_filter: Optional[str] = None,
        study_filter: Optional[str] = None,
        deliverable_filter: Optional[str] = None
    ) -> List[DocumentInfo]:
        """List documents with optional filtering."""
        
        documents = list(self._document_info.values())
        
        # Apply filters
        if status_filter:
            documents = [doc for doc in documents if doc.status == status_filter]
        
        if compound_filter:
            documents = [doc for doc in documents 
                        if hasattr(doc, 'compound') and doc.compound == compound_filter]
        
        if study_filter:
            documents = [doc for doc in documents if doc.study_id == study_filter]
        
        if deliverable_filter:
            documents = [doc for doc in documents 
                        if hasattr(doc, 'deliverable') and doc.deliverable == deliverable_filter]
        
        # Sort by creation date (newest first)
        documents.sort(key=lambda x: x.created_at, reverse=True)
        
        # Apply pagination
        return documents[offset:offset + limit]

    async def get_documents_by_structure(self) -> Dict[str, Any]:
        """Get documents organized by compound/study/deliverable structure."""
        
        structure = {}
        
        for doc in self._document_info.values():
            if not hasattr(doc, 'compound'):
                continue
                
            compound = doc.compound
            study = doc.study_id
            deliverable = doc.deliverable
            
            if compound not in structure:
                structure[compound] = {}
            if study not in structure[compound]:
                structure[compound][study] = {}
            if deliverable not in structure[compound][study]:
                structure[compound][study][deliverable] = []
            
            
            doc_entry = {
                "document_id": doc.document_id,
                "filename": doc.filename,
                "status": doc.status,
                "tlf_outputs_found": doc.tlf_outputs_found,
                "created_at": doc.created_at,
                "processed_at": doc.processed_at,
                "has_vector_index": self.use_vector_store and doc.status == ProcessingStatusEnum.COMPLETED,
                "file_exists": Path(doc.file_path).exists() if doc.file_path else False,
            }
            
            structure[compound][study][deliverable].append(doc_entry)
        
        return structure

    async def get_documents_summary(self) -> DocumentSummary:
        """Get summary statistics for all documents."""
        
        documents = list(self._document_info.values())
        
        # Count by status
        status_counts = {}
        total_tlf_outputs = 0
        
        for doc in documents:
            status = doc.status
            status_counts[status] = status_counts.get(status, 0) + 1
            total_tlf_outputs += doc.tlf_outputs_found
        
        # Get recent documents (last 10)
        recent_documents = sorted(documents, key=lambda x: x.created_at, reverse=True)[:10]
        
        return DocumentSummary(
            total_documents=len(documents),
            by_status=status_counts,
            total_tlf_outputs=total_tlf_outputs,
            recent_documents=recent_documents
        )

    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and its associated data."""
        
        try:
            doc_info = self._document_info.get(document_id)
            
            # Remove from vector storage if using vector store
            if self.use_vector_store:
                await self.storage_service.delete_index(document_id)
            
            # Remove physical file if it exists and no other documents reference it
            if doc_info and hasattr(doc_info, 'file_path'):
                file_path = Path(doc_info.file_path)
                if file_path.exists():
                    # Check if any other documents reference this file
                    other_docs_with_same_file = [
                        d for d in self._document_info.values()
                        if (d.document_id != document_id and 
                            hasattr(d, 'file_path') and 
                            d.file_path == doc_info.file_path)
                    ]
                    
                    if not other_docs_with_same_file:
                        file_path.unlink()
                        logger.info(f"Deleted file: {file_path}")
            
            # Remove from hash tracking
            if doc_info and hasattr(doc_info, 'file_hash'):
                self._document_hashes.pop(doc_info.file_hash, None)
                
            # Remove from manifest
            self._remove_from_manifest(document_id)
            
            # Remove from local tracking
            self._processing_status.pop(document_id, None)
            self._document_info.pop(document_id, None)
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting document {document_id}: {e}")
            return False

    async def get_document_count(self) -> int:
        """Get total document count."""
        return len(self._document_info)

    async def get_average_processing_time(self) -> float:
        """Get average processing time in seconds."""
        
        completed_docs = [
            doc for doc in self._document_info.values()
            if doc.status == ProcessingStatusEnum.COMPLETED and doc.processed_at
        ]
        
        if not completed_docs:
            return 0.0
        
        total_time = sum([
            (doc.processed_at - doc.created_at).total_seconds()
            for doc in completed_docs
        ])
        
        return total_time / len(completed_docs)

    def _load_manifest(self) -> Dict[str, Any]:
        """Load the document manifest from file."""
        try:
            if self.manifest_file.exists():
                with open(self.manifest_file, 'r') as f:
                    manifest = json.load(f)
                logger.info(f"Loaded manifest with {len(manifest.get('documents', {}))} documents")
                return manifest
        except Exception as e:
            logger.warning(f"Failed to load manifest: {e}")
        
        return {
            "version": "1.0",
            "created": datetime.now().isoformat(),
            "documents": {}
        }

    def _save_manifest(self):
        """Save the document manifest to file."""
        try:
            self.manifest_file.parent.mkdir(parents=True, exist_ok=True)
            self.manifest_file.write_text(json.dumps(self.file_manifest, indent=2, default=str))
            logger.debug("Manifest saved successfully")
        except Exception as e:
            logger.error(f"Failed to save manifest: {e}")

    def _add_to_manifest(self, document_id: str, document_info: DocumentInfo):
        """Add a document to the manifest."""
        self.file_manifest["documents"][document_id] = {
            "document_id": document_id,
            "filename": document_info.filename,
            "compound": document_info.compound,
            "study_id": document_info.study_id,
            "deliverable": document_info.deliverable,
            "file_path": str(document_info.file_path) if document_info.file_path else None,
            "file_hash": document_info.file_hash,
            "description": document_info.description,
            "status": document_info.status,
            "created_at": document_info.created_at.isoformat(),
            "processed_at": document_info.processed_at.isoformat() if document_info.processed_at else None,
            "total_pages": document_info.total_pages,
            "total_chunks": document_info.total_chunks,
            "tlf_outputs_found": document_info.tlf_outputs_found,
            "tlf_types_distribution": document_info.tlf_types_distribution,
            "clinical_domains_distribution": document_info.clinical_domains_distribution,
            "has_vector_index": self.use_vector_store,
        }
        self._save_manifest()

    def _remove_from_manifest(self, document_id: str):
        """Remove a document from the manifest."""
        if document_id in self.file_manifest["documents"]:
            del self.file_manifest["documents"][document_id]
            self._save_manifest()

    def _restore_documents_from_manifest(self):
        """Restore document info from manifest on startup."""
        for doc_id, doc_data in self.file_manifest["documents"].items():
            try:
                # Convert back to DocumentInfo object
                doc_info = DocumentInfo(
                    document_id=doc_data["document_id"],
                    filename=doc_data["filename"],
                    compound=doc_data.get("compound"),
                    study_id=doc_data.get("study_id"),
                    deliverable=doc_data.get("deliverable"),
                    file_path=doc_data.get("file_path"),
                    file_hash=doc_data.get("file_hash"),
                    description=doc_data.get("description"),
                    status=ProcessingStatusEnum(doc_data["status"]),
                    created_at=datetime.fromisoformat(doc_data["created_at"]),
                    processed_at=datetime.fromisoformat(doc_data["processed_at"]) if doc_data.get("processed_at") else None,
                    total_pages=doc_data.get("total_pages"),
                    total_chunks=doc_data.get("total_chunks", 0),
                    tlf_outputs_found=doc_data.get("tlf_outputs_found", 0),
                    tlf_types_distribution=doc_data.get("tlf_types_distribution", {}),
                    clinical_domains_distribution=doc_data.get("clinical_domains_distribution", {}),
                )
                
                self._document_info[doc_id] = doc_info
                
                # Add to hash tracking if available
                if doc_info.file_hash:
                    self._document_hashes[doc_info.file_hash] = doc_id
                
                # Check if file still exists
                if doc_info.file_path and not Path(doc_info.file_path).exists():
                    logger.warning(f"File missing for document {doc_id}: {doc_info.file_path}")
                    # Update status to indicate file is missing
                    doc_info.status = ProcessingStatusEnum.FAILED
                    doc_data["status"] = "failed"
                    
            except Exception as e:
                logger.error(f"Failed to restore document {doc_id} from manifest: {e}")
        
        logger.info(f"Restored {len(self._document_info)} documents from manifest")

    # **WORKAROUND: Methods to toggle vector store usage**
    
    def enable_vector_store(self):
        """Enable vector store processing for future documents."""
        self.use_vector_store = True
        logger.info("Vector store processing enabled")

    def disable_vector_store(self):
        """Disable vector store processing (files only mode)."""
        self.use_vector_store = False
        logger.info("Vector store processing disabled - files only mode")

    async def get_vector_store_status(self) -> Dict[str, Any]:
        """Get current vector store configuration and status."""
        return {
            "enabled": self.use_vector_store,
            "documents_with_vector_index": len([
                doc for doc in self._document_info.values() 
                if doc.status == ProcessingStatusEnum.COMPLETED and self.use_vector_store
            ]),
            "documents_file_only": len([
                doc for doc in self._document_info.values() 
                if doc.status == ProcessingStatusEnum.COMPLETED and not self.use_vector_store
            ]),
            "total_documents": len(self._document_info),
            "manifest_path": str(self.manifest_file),
            "storage_path": str(self.base_storage_path)
        }
