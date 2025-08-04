# backend/app/services/storage_service.py
from typing import Dict, List, Optional, Any
import logging
from datetime import datetime

from llama_index.core import VectorStoreIndex
from llama_index.core.schema import BaseNode

logger = logging.getLogger(__name__)


class StorageService:
    """Service for managing vector store and document storage."""
    
    def __init__(self):
        # In-memory storage for now
        # In production, use persistent vector store like OpenSearch or MongoDB.
        self._indexes: Dict[str, VectorStoreIndex] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._index_links: Dict[str, str] = {}  # document_id -> original_document_id for duplicates

    async def create_index(self, document_id: str, nodes: List[BaseNode]) -> str:
        """Create vector index for document nodes."""
        
        try:
            # Create vector index
            vector_index = VectorStoreIndex(nodes)
            
            # Store index
            self._indexes[document_id] = vector_index
            
            # Store metadata
            self._metadata[document_id] = {
                "created_at": datetime.now(),
                "node_count": len(nodes),
                "document_id": document_id
            }
            
            logger.info(f"Created vector index for document {document_id} with {len(nodes)} nodes")
            
            return document_id
            
        except Exception as e:
            logger.error(f"Error creating index for document {document_id}: {e}")
            raise

    async def link_index(self, new_document_id: str, existing_document_id: str) -> bool:
        """Link a new document ID to an existing document's index (for duplicates)."""
        
        try:
            if existing_document_id not in self._indexes:
                raise ValueError(f"Existing document {existing_document_id} not found")
            
            # Create link to existing index
            self._index_links[new_document_id] = existing_document_id
            
            # Store metadata for the link
            self._metadata[new_document_id] = {
                "created_at": datetime.now(),
                "node_count": self._metadata[existing_document_id]["node_count"],
                "document_id": new_document_id,
                "linked_to": existing_document_id
            }
            
            logger.info(f"Linked document {new_document_id} to existing index {existing_document_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error linking document {new_document_id} to {existing_document_id}: {e}")
            return False

    async def get_index(self, document_id: str) -> Optional[VectorStoreIndex]:
        """Get vector index for a document."""
        
        # Check if this is a linked document
        if document_id in self._index_links:
            original_document_id = self._index_links[document_id]
            return self._indexes.get(original_document_id)
        
        # Return direct index
        return self._indexes.get(document_id)

    async def delete_index(self, document_id: str) -> bool:
        """Delete vector index for a document."""
        
        try:
            # Check if this is a linked document
            if document_id in self._index_links:
                # Just remove the link, don't delete the actual index
                original_document_id = self._index_links.pop(document_id)
                self._metadata.pop(document_id, None)
                logger.info(f"Removed link for document {document_id} (original: {original_document_id})")
            else:
                # Check if any other documents link to this one
                linked_documents = [
                    doc_id for doc_id, original_id in self._index_links.items()
                    if original_id == document_id
                ]
                
                if linked_documents:
                    # Don't delete the index, just remove this document's metadata
                    self._metadata.pop(document_id, None)
                    logger.info(f"Document {document_id} has linked documents {linked_documents}, keeping index")
                else:
                    # Safe to delete the actual index
                    self._indexes.pop(document_id, None)
                    self._metadata.pop(document_id, None)
                    logger.info(f"Deleted index for document {document_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting index for document {document_id}: {e}")
            return False

    async def get_storage_info(self) -> Dict[str, Any]:
        """Get storage information."""
        
        total_nodes = sum([
            metadata.get("node_count", 0) 
            for metadata in self._metadata.values()
        ])
        
        return {
            "total_indexes": len(self._indexes),
            "total_documents": len(self._metadata),
            "total_nodes": total_nodes,
            "linked_documents": len(self._index_links),
            "indexes": list(self._indexes.keys()),
            "links": dict(self._index_links)
        }

    async def get_total_chunks(self) -> int:
        """Get total number of chunks across all documents."""
        
        return sum([
            metadata.get("node_count", 0) 
            for metadata in self._metadata.values()
        ])
