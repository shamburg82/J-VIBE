# backend/app/services/document_service.py
from typing import List, Dict, Optional, Any
import asyncio
import uuid
import tempfile
import os
import shutil
import hashlib
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

# from .config import get_config

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
        
        # # For Posit Connect, this will be updated to use RSTUDIO_CONNECT_CONTENT_DIR
        # connect_content_dir = os.getenv("RSTUDIO_CONNECT_CONTENT_DIR")
        # if connect_content_dir:
        #     self.base_storage_path = Path(connect_content_dir) / "documents"
        #     logger.info(f"Using Posit Connect content directory: {self.base_storage_path}")
            
        # # Ensure base directory exists
        # self.base_storage_path.mkdir(parents=True, exist_ok=True)
                
        # Processing status tracking
        self._processing_status: Dict[str, ProcessingStatus] = {}
        self._document_info: Dict[str, DocumentInfo] = {}

        # Document hash tracking for deduplication
        self._document_hashes: Dict[str, str] = {}  # hash -> document_id

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
        
        # Debug: Test text splitter
        try:
            test_text = "This is a test sentence to verify the text splitter is working correctly."
            test_chunks = self.text_splitter.split_text(test_text)
            logger.info(f"Text splitter test: {len(test_chunks)} chunks from test text")
        except Exception as e:
            logger.error(f"Text splitter test failed: {e}")
        
        # Initialize other extractors
        self.extractors = [
            self.tlf_extractor,
            QuestionsAnsweredExtractor(questions=2, llm=llm),
            SummaryExtractor(summaries=["self"], llm=llm),
            KeywordExtractor(keywords=8, llm=llm),
        ]

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
                await self._handle_duplicate_document(document_id, existing_doc_id, filename)
                return
            
            await self._update_status(
                document_id, ProcessingStatusEnum.EXTRACTING_TEXT, 10,
                "Storing file to permanent location..."
            )
            
            # Store file permanently
            stored_file_path = await self._store_file_permanently(
                file_content, filename, compound, study_id, deliverable
            )
            
            await self._update_status(
                document_id, ProcessingStatusEnum.EXTRACTING_TEXT, 20,
                "Extracting text from PDF..."
            )
            
            # Extract text from stored PDF with error handling
            try:
                logger.info(f"Attempting to read PDF from: {stored_file_path}")
                
                # Verify file exists and has content
                if not stored_file_path.exists():
                    raise FileNotFoundError(f"Stored file not found: {stored_file_path}")
                
                file_size = stored_file_path.stat().st_size
                if file_size == 0:
                    raise ValueError(f"Stored file is empty: {stored_file_path}")
                
                logger.info(f"File exists and has size: {file_size} bytes")
                
                # Try to read with SimpleDirectoryReader
                documents = SimpleDirectoryReader(input_files=[str(stored_file_path)]).load_data()
                logger.info(f"SimpleDirectoryReader returned {len(documents)} documents")
                
                if not documents:
                    # Try alternative PDF reading approach
                    logger.warning("SimpleDirectoryReader returned no documents, trying alternative approach")
                    
                    try:
                        import pymupdf as fitz  # PyMuPDF
                        
                        # Read PDF with PyMuPDF directly
                        doc = fitz.open(str(stored_file_path))
                        text_content = ""
                        
                        for page_num in range(len(doc)):
                            page = doc.load_page(page_num)
                            text_content += page.get_text()
                        
                        doc.close()
                        
                        if text_content.strip():
                            # Create a document manually
                            from llama_index.core.schema import Document
                            documents = [Document(text=text_content, metadata={"source": str(stored_file_path)})]
                            logger.info(f"Successfully extracted text with PyMuPDF: {len(text_content)} characters")
                        else:
                            raise ValueError("PDF appears to contain no extractable text")
                            
                    except Exception as pdf_error:
                        logger.error(f"Alternative PDF reading failed: {pdf_error}")
                        raise ValueError(f"Could not extract text from PDF: {pdf_error}")
                
                total_pages = len(documents)
                logger.info(f"Successfully extracted {total_pages} pages from PDF")
                
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
            
            # Debug: Check document content before processing
            total_text_length = sum(len(doc.text or '') for doc in documents)
            logger.info(f"Total text length across all documents: {total_text_length} characters")
            
            if total_text_length == 0:
                raise ValueError("PDF was read but contains no extractable text content")
            
            # Sample some text for debugging (first 500 chars)
            sample_text = (documents[0].text or '')[:500] if documents else ''
            logger.info(f"Sample text from first page: {repr(sample_text)}")
            
            # Create processing pipeline
            transformations = [self.text_splitter, self.tlf_extractor]
            pipeline = IngestionPipeline(transformations=transformations)
            
            logger.info(f"Starting pipeline processing with {len(transformations)} transformations")
            
            # Process documents with better error handling
            try:
                doc_nodes = await asyncio.get_event_loop().run_in_executor(
                    None, pipeline.run, documents
                )
                logger.info(f"Pipeline completed. Generated {len(doc_nodes)} nodes")
            except Exception as pipeline_error:
                logger.error(f"Pipeline processing failed: {pipeline_error}")
                # Try manual processing as fallback
                doc_nodes = await self._manual_document_processing(documents)
            
            # FIXED: Validate nodes and handle empty results
            if not doc_nodes:
                logger.warning("No nodes generated from pipeline, attempting manual processing")
                doc_nodes = await self._manual_document_processing(documents)
            
            if not doc_nodes:
                raise ValueError("No text chunks were created from the PDF content")
            
            # Ensure all nodes are proper BaseNode objects
            validated_nodes = []
            for i, node in enumerate(doc_nodes):
                if isinstance(node, str):
                    # Convert string to TextNode
                    text_node = TextNode(text=node, id_=f"node_{i}_{document_id}")
                    validated_nodes.append(text_node)
                elif hasattr(node, 'text') or hasattr(node, 'get_content'):
                    validated_nodes.append(node)
                else:
                    # Create TextNode from string representation
                    text_node = TextNode(text=str(node), id_=f"node_{i}_{document_id}")
                    validated_nodes.append(text_node)
            
            doc_nodes = validated_nodes
            logger.info(f"Validated {len(doc_nodes)} nodes")
            
            await self._update_status(
                document_id, ProcessingStatusEnum.EXTRACTING_TLF_METADATA, 70,
                f"Extracting TLF metadata from {len(doc_nodes)} chunks...",
                total_chunks=len(doc_nodes)
            )
            
            # FIXED: Apply TLF extractor manually if not already applied
            try:
                # Reset extractor context for new document
                self.tlf_extractor.reset_context()
                
                # Apply TLF extraction
                doc_nodes = self.tlf_extractor(doc_nodes)
                logger.info(f"TLF extraction completed on {len(doc_nodes)} nodes")
                
                # Apply additional extractors
                for extractor in self.extractors[1:]:  # Skip TLF extractor as it's already applied
                    try:
                        if hasattr(extractor, 'extract'):
                            extracted_metadata = extractor.extract(doc_nodes)
                            for node, metadata in zip(doc_nodes, extracted_metadata):
                                if hasattr(node, 'metadata'):
                                    node.metadata.update(metadata)
                        logger.info(f"Applied {extractor.__class__.__name__}")
                    except Exception as e:
                        logger.warning(f"Extractor {extractor.__class__.__name__} failed: {e}")
                        continue
                        
            except Exception as extraction_error:
                logger.error(f"Metadata extraction failed: {extraction_error}")
                # Continue without metadata extraction
                logger.warning("Continuing without full metadata extraction")
            
            await self._update_status(
                document_id, ProcessingStatusEnum.BUILDING_INDEX, 85,
                "Building vector index..."
            )
                
            # Store in vector index
            index_id = await self.storage_service.create_index(document_id, doc_nodes)
            
            # Count TLF outputs found
            tlf_outputs = await self._count_tlf_outputs(doc_nodes)
            
            # Create document info
            doc_info = DocumentInfo(
                document_id=document_id,
                filename=filename,         
                compound = compound,
                study_id=study_id,       
                deliverable = deliverable,
                file_path = str(stored_file_path),
                file_hash = file_hash,
                description=description,
                status=ProcessingStatusEnum.COMPLETED,
                created_at=datetime.now(),
                processed_at=datetime.now(),
                total_pages=total_pages,
                total_chunks=len(doc_nodes),
                tlf_outputs_found=tlf_outputs["total"],
                tlf_types_distribution=tlf_outputs["types"],
                clinical_domains_distribution=tlf_outputs["domains"]
            )
            
            self._document_info[document_id] = doc_info
            self._document_hashes[file_hash] = document_id
            
            await self._update_status(
                document_id, ProcessingStatusEnum.COMPLETED, 100,
                f"Processing complete! Found {tlf_outputs['total']} TLF outputs.",
                total_pages=total_pages,
                total_chunks=len(doc_nodes),
                tlf_outputs_found=tlf_outputs["total"]
            )
            
            logger.info(f"Successfully processed document {document_id} at {stored_file_path}")
                
        except Exception as e:
            logger.error(f"Error processing document {document_id}: {e}")
            await self._update_status(
                document_id, ProcessingStatusEnum.FAILED, 0,
                f"Processing failed: {str(e)}",
                error_message=str(e)
            )

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
        
        # Point to same vector index
        await self.storage_service.link_index(new_document_id, existing_document_id)
        
        logger.info(f"Document {new_document_id} is duplicate of {existing_document_id}")


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
        return self._processing_status.get(document_id)

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
            
            structure[compound][study][deliverable].append({
                "document_id": doc.document_id,
                "filename": doc.filename,
                "status": doc.status,
                "tlf_outputs_found": doc.tlf_outputs_found,
                "created_at": doc.created_at,
                "processed_at": doc.processed_at
            })
        
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
            
            # Remove from storage
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
