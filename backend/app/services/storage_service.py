# backend/app/services/storage_service.py
from typing import Dict, List, Optional, Any
import logging
from datetime import datetime
import os

from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.core.schema import BaseNode
from llama_index.vector_stores.mongodb import MongoDBAtlasVectorSearch
from pymongo import MongoClient

logger = logging.getLogger(__name__)


class StorageService:
    """Service for managing vector store and document storage."""    
    
    def __init__(self, mongodb_connection_string: str = None, database_name: str = "jazzvibe", collection_name: str = "vector_store"):
        """
        Initialize storage service with MongoDB Atlas.
        
        Args:
            mongodb_connection_string: MongoDB connection string
            database_name: Name of the database to use
            collection_name: Name of the collection to use for vector storage
        """
        
        # MongoDB configuration
        self.mongodb_connection_string = mongodb_connection_string or self._get_mongodb_connection_string()
        self.database_name = database_name
        self.collection_name = collection_name
        
        # Initialize MongoDB client and vector store
        self._mongo_client = None
        self._vector_store = None
        self._initialize_mongodb()
        
        # Metadata tracking (can be stored in MongoDB or kept in memory for performance)
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._index_links: Dict[str, str] = {}  # document_id -> original_document_id for duplicates
        
        # Cache for vector indexes
        self._index_cache: Dict[str, VectorStoreIndex] = {}
        
    def _get_mongodb_connection_string(self) -> str:
        """Get MongoDB connection string from environment variables."""
        
        # Try different environment variable names
        connection_string = (
            os.getenv("MONGODB_CONNECTION_STRING") or
            os.getenv("MONGO_CONNECTION_STRING") or 
            os.getenv("MONGODB_URI") or
            os.getenv("MONGO_URI")
        )
        
        if not connection_string:
            # Construct from individual components if available
            username = os.getenv("MONGODB_USERNAME")
            password = os.getenv("MONGODB_PASSWORD") 
            host = os.getenv("MONGODB_HOST", "na2-dsejazzvibe01-pl-0.os021j.mongodb.net")
            
            if username and password:
                connection_string = f"mongodb+srv://{username}:{password}@{host}/"
            else:
                # Default connection string - you'll need to set credentials
                logger.warning("No MongoDB credentials found in environment variables")
                connection_string = f"mongodb+srv://{host}/"
        
        return connection_string
    
    def _initialize_mongodb(self):
        """Initialize MongoDB client and vector store."""
        
        try:
            logger.info("Connecting to MongoDB Atlas...")
            logger.info(f"Connection target: {self.mongodb_connection_string.split('@')[-1] if '@' in self.mongodb_connection_string else 'Unknown'}")
            
            # Create MongoDB client with timeout settings
            self._mongo_client = MongoClient(
                self.mongodb_connection_string,
                serverSelectionTimeoutMS=30000,  # 30 second timeout
                connectTimeoutMS=20000,          # 20 second connection timeout
                maxPoolSize=10,                  # Limit connection pool
                retryWrites=True
            )
            
            # Test connection
            self._mongo_client.admin.command('ping')
            logger.info("✅ Successfully connected to MongoDB Atlas")
            
            # Get database and collection
            database = self._mongo_client[self.database_name]
            collection = database[self.collection_name]
            
            # Create vector search index if it doesn't exist
            self._ensure_vector_search_index(collection)
            
            # Initialize the vector store
            self._vector_store = MongoDBAtlasVectorSearch(
                mongodb_client=self._mongo_client,
                database_name=self.database_name,
                collection_name=self.collection_name,
                vector_index_name="vector_index",  # Name of the search index
                embedding_key="embedding",  # Field name for embeddings
                text_key="text",           # Field name for text content
                metadata_key="metadata"    # Field name for metadata
            )
            
            logger.info(f"✅ MongoDB vector store initialized - Database: {self.database_name}, Collection: {self.collection_name}")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize MongoDB: {e}")
            logger.error(f"Connection string format: {'mongodb+srv://' if 'mongodb+srv://' in self.mongodb_connection_string else 'Other'}")
            
            # Provide specific error guidance
            error_msg = str(e).lower()
            if "authentication failed" in error_msg:
                logger.error("💡 Check your MongoDB username and password")
            elif "network" in error_msg or "timeout" in error_msg:
                logger.error("💡 Check your network connection and MongoDB host")
            elif "ssl" in error_msg or "tls" in error_msg:
                logger.error("💡 Check SSL/TLS configuration for MongoDB Atlas")
            
            raise Exception(f"MongoDB initialization failed: {e}")
    
    def _ensure_vector_search_index(self, collection):
        """Ensure vector search index exists on the collection."""
        
        try:
            # First, ensure the collection exists by inserting a dummy document if needed
            if collection.count_documents({}) == 0:
                logger.info("Collection is empty, creating initial document to establish collection...")
                # Insert a temporary document to create the collection
                temp_doc = {
                    "_id": "temp_init_doc",
                    "text": "Temporary initialization document",
                    "embedding": [0.0] * 1536,  # Dummy embedding
                    "metadata": {
                        "temp": True,
                        "created_at": datetime.now().isoformat()
                    }
                }
                collection.insert_one(temp_doc)
                logger.info("Collection created with temporary document")
            
            # Check if vector search index exists
            try:
                indexes = list(collection.list_search_indexes())
                vector_index_exists = any(idx.get('name') == 'vector_index' for idx in indexes)
            except Exception as list_error:
                logger.warning(f"Could not list search indexes: {list_error}")
                vector_index_exists = False
            
            if not vector_index_exists:
                logger.info("Creating vector search index...")
                
                # Atlas Search index definition for vector search
                index_definition = {
                    "name": "vector_index",
                    "definition": {
                        "mappings": {
                            "dynamic": False,
                            "fields": {
                                "embedding": {
                                    "type": "knnVector",
                                    "dimensions": 1536,
                                    "similarity": "cosine"
                                },
                                "metadata": {
                                    "type": "document",
                                    "fields": {
                                        "document_id": {
                                            "type": "token"
                                        },
                                        "tlf_type": {
                                            "type": "token"
                                        },
                                        "clinical_domain": {
                                            "type": "token"
                                        },
                                        "page_number": {
                                            "type": "number"
                                        },
                                        "output_number": {
                                            "type": "token"
                                        }
                                    }
                                },
                                "text": {
                                    "type": "string"
                                }
                            }
                        }
                    }
                }
            
                # Create the search index
                try:
                    result = collection.create_search_index(index_definition)
                    logger.info(f"✅ Vector search index created successfully: {result}")
                    
                    # Note: Index creation is asynchronous and may take a few minutes to be fully available
                    logger.warning("⚠️  Vector search index is being created. It may take a few minutes to be fully available.")
                    
                except Exception as create_error:
                    logger.error(f"Failed to create vector search index: {create_error}")
                    # Try alternative approach for older MongoDB versions
                    self._create_fallback_index(collection)
                
            else:
                logger.info("✅ Vector search index already exists")
                
        except Exception as e:
            logger.warning(f"⚠️  Could not create/check vector search index: {e}")
            logger.warning("You may need to create the vector search index manually in MongoDB Atlas")

    def _create_simple_vector_index(self, collection):
        """Create a simplified vector search index as fallback."""
        
        try:
            logger.info("Trying simplified vector index format...")
            
            # Simplified index definition
            simple_index_definition = {
                "name": "vector_index",
                "definition": {
                    "mappings": {
                        "fields": {
                            "embedding": {
                                "type": "knnVector",
                                "dimensions": 1536,
                                "similarity": "cosine"
                            }
                        }
                    }
                }
            }
            
            result = collection.create_search_index(simple_index_definition)
            logger.info(f"✅ Simplified vector search index created: {result}")
            
        except Exception as simple_error:
            logger.error(f"❌ Even simplified vector index creation failed: {simple_error}")
            logger.warning("Manual index creation in Atlas UI will be required")
            
            # Create basic fallback indexes
            self._create_fallback_index(collection)

    def _create_fallback_index(self, collection):
        """Create fallback indexes for older MongoDB versions or when Atlas Search isn't available."""
        
        try:
            logger.info("Creating fallback indexes...")
            
            # Create compound index for filtering
            collection.create_index([
                ("metadata.document_id", 1),
                ("metadata.tlf_type", 1),
                ("metadata.clinical_domain", 1)
            ])
            
            # Create text index for basic text search
            collection.create_index([("text", "text")])
            
            logger.info("✅ Fallback indexes created")
            
        except Exception as fallback_error:
            logger.warning(f"⚠️  Could not create fallback indexes: {fallback_error}")

    async def create_index(self, document_id: str, nodes: List[BaseNode]) -> str:
        """Create vector index for document nodes using MongoDB with better error handling."""
        
        try:
            # Add document_id to all node metadata for filtering
            for node in nodes:
                if not hasattr(node, 'metadata'):
                    node.metadata = {}
                node.metadata['document_id'] = document_id
                node.metadata['created_at'] = datetime.now().isoformat()
            
            logger.info(f"Creating vector index for document {document_id} with {len(nodes)} nodes")
            
            # FIX: Create storage context more carefully
            try:
                # Method 1: Try with explicit vector store
                from llama_index.core import StorageContext
                storage_context = StorageContext.from_defaults(vector_store=self._vector_store)
                
                logger.info("✅ Created storage context successfully")
                
            except Exception as storage_error:
                logger.error(f"❌ Storage context creation failed: {storage_error}")
                
                # Method 2: Fallback - create vector store with fresh MongoDB client
                logger.info("🔄 Trying fallback MongoDB vector store creation...")
                
                from llama_index.vector_stores.mongodb import MongoDBAtlasVectorSearch
                from llama_index.core import StorageContext
                
                # Create a fresh vector store instance
                fallback_vector_store = MongoDBAtlasVectorSearch(
                    mongodb_client=self._mongo_client,
                    database_name=self.database_name,
                    collection_name=self.collection_name,
                    vector_index_name="vector_index",
                    embedding_key="embedding",
                    text_key="text",
                    metadata_key="metadata"
                )
                
                storage_context = StorageContext.from_defaults(vector_store=fallback_vector_store)
                logger.info("✅ Created fallback storage context")
            
            # Create vector index with error handling
            try:
                logger.info("🚀 Creating VectorStoreIndex...")
                vector_index = VectorStoreIndex(nodes, storage_context=storage_context)
                logger.info("✅ VectorStoreIndex created successfully")
                
            except Exception as index_error:
                logger.error(f"❌ VectorStoreIndex creation failed: {index_error}")
                
                # Method 3: Manual vector storage fallback
                logger.info("🔄 Trying manual vector storage...")
                return await self._manual_vector_storage(document_id, nodes)
            
            # Cache the index
            self._index_cache[document_id] = vector_index
            
            # Store metadata
            self._metadata[document_id] = {
                "created_at": datetime.now(),
                "node_count": len(nodes),
                "document_id": document_id,
                "storage_type": "mongodb_atlas"
            }
            
            # Persist metadata to MongoDB
            await self._store_document_metadata(document_id, self._metadata[document_id])
            
            logger.info(f"✅ Created MongoDB vector index for document {document_id} with {len(nodes)} nodes")
            
            return document_id
            
        except Exception as e:
            logger.error(f"❌ Error creating MongoDB index for document {document_id}: {e}")
            logger.exception("Full error details:")
            
            # Try manual fallback
            logger.info("🔄 Attempting manual vector storage as final fallback...")
            try:
                return await self._manual_vector_storage(document_id, nodes)
            except Exception as fallback_error:
                logger.error(f"❌ Manual fallback also failed: {fallback_error}")
                raise e

    async def _manual_vector_storage(self, document_id: str, nodes: List[BaseNode]) -> str:
        """Manual vector storage fallback method."""
        
        try:
            logger.info(f"📝 Manual vector storage for {len(nodes)} nodes...")
            
            # Get embedding model from Settings
            from llama_index.core import Settings
            
            if not Settings.embed_model:
                raise Exception("No embedding model available")
            
            embed_model = Settings.embed_model
            logger.info(f"🔤 Using embedding model: {embed_model.__class__.__name__}")
            
            # Get database and collection directly
            database = self._mongo_client[self.database_name]
            collection = database[self.collection_name]
            
            # Process nodes in batches
            batch_size = 10
            total_stored = 0
            
            for i in range(0, len(nodes), batch_size):
                batch = nodes[i:i + batch_size]
                batch_docs = []
                
                logger.info(f"📊 Processing batch {i//batch_size + 1}/{(len(nodes)-1)//batch_size + 1}")
                
                for node in batch:
                    try:
                        # Generate embedding for the node
                        text = node.get_content()
                        embedding = await embed_model.aget_text_embedding(text)
                        
                        # Create document for MongoDB
                        doc = {
                            "_id": f"{document_id}_{node.node_id}",
                            "text": text,
                            "embedding": embedding,
                            "metadata": node.metadata,
                            "node_id": node.node_id,
                            "document_id": document_id,
                            "created_at": datetime.now()
                        }
                        
                        batch_docs.append(doc)
                        
                    except Exception as node_error:
                        logger.warning(f"⚠️  Failed to process node {node.node_id}: {node_error}")
                        continue
                
                # Insert batch into MongoDB
                if batch_docs:
                    try:
                        result = collection.insert_many(batch_docs, ordered=False)
                        inserted_count = len(result.inserted_ids)
                        total_stored += inserted_count
                        logger.info(f"✅ Stored {inserted_count} vectors from batch")
                        
                    except Exception as batch_error:
                        logger.error(f"❌ Failed to store batch: {batch_error}")
                        # Try individual inserts
                        for doc in batch_docs:
                            try:
                                collection.insert_one(doc)
                                total_stored += 1
                            except Exception as doc_error:
                                logger.warning(f"⚠️  Failed to store individual document: {doc_error}")
            
            logger.info(f"✅ Manual vector storage completed: {total_stored}/{len(nodes)} nodes stored")
            
            # Create a simple index representation for caching
            # This won't have all VectorStoreIndex functionality but allows basic operations
            self._index_cache[document_id] = "manual_storage"
            
            # Store metadata
            self._metadata[document_id] = {
                "created_at": datetime.now(),
                "node_count": total_stored,
                "document_id": document_id,
                "storage_type": "mongodb_manual"
            }
            
            await self._store_document_metadata(document_id, self._metadata[document_id])
            
            if total_stored < len(nodes):
                logger.warning(f"⚠️  Only {total_stored}/{len(nodes)} nodes stored successfully")
            
            return document_id
            
        except Exception as manual_error:
            logger.error(f"❌ Manual vector storage failed: {manual_error}")
            raise

    async def link_index(self, new_document_id: str, existing_document_id: str) -> bool:
        """Link a new document ID to an existing document's index (for duplicates)."""
        
        try:
            # Check if existing document actually has data in MongoDB
            existing_metadata = await self._get_document_metadata(existing_document_id)
            if not existing_metadata:
                logger.warning(f"Cannot link to non-existent document {existing_document_id}")
                return False
            
            # Create link to existing document
            self._index_links[new_document_id] = existing_document_id
            
            # Store metadata for the link
            link_metadata = {
                "created_at": datetime.now(),
                "node_count": existing_metadata.get("node_count", 0),
                "document_id": new_document_id,
                "linked_to": existing_document_id,
                "storage_type": "mongodb_atlas_linked"
            }
            
            self._metadata[new_document_id] = link_metadata
            await self._store_document_metadata(new_document_id, link_metadata)
            
            logger.info(f"✅ Linked document {new_document_id} to existing MongoDB document {existing_document_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error linking document {new_document_id} to {existing_document_id}: {e}")
            return False

    async def get_index(self, document_id: str) -> Optional[VectorStoreIndex]:
        """Get vector index for a document."""
        
        try:
            # Check cache first
            cached_index = self._index_cache.get(document_id)
            
            if cached_index == "manual_storage":
                # For manual storage, create a basic index that can query the collection
                logger.info(f"📊 Creating query interface for manually stored document {document_id}")
                
                # Create a basic vector store interface
                storage_context = StorageContext.from_defaults(vector_store=self._vector_store)
                
                # Create empty index that can query existing data
                vector_index = VectorStoreIndex([], storage_context=storage_context)
                
                # Cache for future use
                self._index_cache[document_id] = vector_index
                return vector_index
                
            elif isinstance(cached_index, VectorStoreIndex):
                return cached_index
            
            # Check if this is a linked document
            original_doc_id = document_id
            if document_id in self._index_links:
                original_doc_id = self._index_links[document_id]
                cached_original = self._index_cache.get(original_doc_id)
                if cached_original:
                    return cached_original
            
            # Check if document has data in MongoDB
            metadata = await self._get_document_metadata(original_doc_id)
            if not metadata:
                logger.warning(f"No metadata found for document {original_doc_id}")
                return None
            
            # Create vector index from MongoDB data
            storage_context = StorageContext.from_defaults(vector_store=self._vector_store)
            
            # Create index that will query MongoDB for this document's vectors
            vector_index = VectorStoreIndex([], storage_context=storage_context)
            
            # Cache the index
            self._index_cache[original_doc_id] = vector_index
            if document_id != original_doc_id:
                self._index_cache[document_id] = vector_index
            
            return vector_index
            
        except Exception as e:
            logger.error(f"❌ Error getting index for document {document_id}: {e}")
            return None

    async def delete_index(self, document_id: str) -> bool:
        """Delete vector index for a document."""
        
        try:
            # Check if this is a linked document
            if document_id in self._index_links:
                # Just remove the link, don't delete the actual data
                original_document_id = self._index_links.pop(document_id)
                self._metadata.pop(document_id, None)
                await self._delete_document_metadata(document_id)
                self._index_cache.pop(document_id, None)
                logger.info(f"✅ Removed link for document {document_id} (original: {original_document_id})")
                return True
            
            # Check if any other documents link to this one
            linked_documents = [
                doc_id for doc_id, original_id in self._index_links.items()
                if original_id == document_id
            ]
            
            if linked_documents:
                # Don't delete the vectors, just remove this document's metadata
                self._metadata.pop(document_id, None)
                await self._delete_document_metadata(document_id)
                self._index_cache.pop(document_id, None)
                logger.info(f"✅ Document {document_id} has linked documents {linked_documents}, keeping vectors")
                return True
            
            # Safe to delete the actual vectors from MongoDB
            database = self._mongo_client[self.database_name]
            collection = database[self.collection_name]
            
            # Delete all vectors for this document
            result = collection.delete_many({"metadata.document_id": document_id})
            logger.info(f"✅ Deleted {result.deleted_count} vectors for document {document_id}")
            
            # Remove from local tracking
            self._metadata.pop(document_id, None)
            await self._delete_document_metadata(document_id)
            self._index_cache.pop(document_id, None)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error deleting index for document {document_id}: {e}")
            return False

    async def _store_document_metadata(self, document_id: str, metadata: Dict[str, Any]):
        """Store document metadata in MongoDB."""
        
        try:
            database = self._mongo_client[self.database_name]
            metadata_collection = database["document_metadata"]
            
            # Upsert metadata
            metadata_doc = {
                "document_id": document_id,
                "metadata": metadata,
                "updated_at": datetime.now()
            }
            
            metadata_collection.replace_one(
                {"document_id": document_id},
                metadata_doc,
                upsert=True
            )
            
        except Exception as e:
            logger.warning(f"⚠️  Failed to store metadata for document {document_id}: {e}")

    async def _get_document_metadata(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get document metadata from MongoDB."""
        
        try:
            database = self._mongo_client[self.database_name]
            metadata_collection = database["document_metadata"]
            
            doc = metadata_collection.find_one({"document_id": document_id})
            if doc:
                return doc.get("metadata", {})
            
            # Fallback to in-memory metadata
            return self._metadata.get(document_id)
            
        except Exception as e:
            logger.warning(f"⚠️  Failed to get metadata for document {document_id}: {e}")
            return self._metadata.get(document_id)

    async def _delete_document_metadata(self, document_id: str):
        """Delete document metadata from MongoDB."""
        
        try:
            database = self._mongo_client[self.database_name]
            metadata_collection = database["document_metadata"]
            
            metadata_collection.delete_one({"document_id": document_id})
            
        except Exception as e:
            logger.warning(f"⚠️  Failed to delete metadata for document {document_id}: {e}")

    async def get_storage_info(self) -> Dict[str, Any]:
        """Get storage information from MongoDB."""
        
        try:
            database = self._mongo_client[self.database_name]
            collection = database[self.collection_name]
            metadata_collection = database["document_metadata"]
            
            # Count total documents in vector collection
            total_vectors = collection.count_documents({})
            
            # Count unique documents
            unique_documents = len(collection.distinct("metadata.document_id"))
            
            # Get metadata collection stats
            total_metadata_docs = metadata_collection.count_documents({})
            
            # Calculate storage stats
            collection_stats = database.command("collStats", self.collection_name)
            storage_size = collection_stats.get("storageSize", 0)
            
            return {
                "storage_type": "mongodb_atlas",
                "database_name": self.database_name,
                "collection_name": self.collection_name,
                "total_vectors": total_vectors,
                "unique_documents": unique_documents,
                "total_metadata_documents": total_metadata_docs,
                "linked_documents": len(self._index_links),
                "cached_indexes": len(self._index_cache),
                "storage_size_bytes": storage_size,
                "storage_size_mb": round(storage_size / (1024 * 1024), 2),
                "connection_string": self.mongodb_connection_string.split('@')[-1]  # Don't expose credentials
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting storage info: {e}")
            return {
                "storage_type": "mongodb_atlas",
                "error": str(e),
                "cached_indexes": len(self._index_cache),
                "linked_documents": len(self._index_links)
            }

    async def get_total_chunks(self) -> int:
        """Get total number of chunks across all documents from MongoDB."""
        
        try:
            database = self._mongo_client[self.database_name]
            collection = database[self.collection_name]
            
            return collection.count_documents({})
            
        except Exception as e:
            logger.error(f"❌ Error getting total chunks: {e}")
            return 0

    async def get_document_statistics(self, document_id: str) -> Dict[str, Any]:
        """Get detailed statistics for a specific document."""
        
        try:
            database = self._mongo_client[self.database_name]
            collection = database[self.collection_name]
            
            # Count vectors for this document
            vector_count = collection.count_documents({"metadata.document_id": document_id})
            
            # Get unique TLF types and clinical domains
            pipeline = [
                {"$match": {"metadata.document_id": document_id}},
                {"$group": {
                    "_id": None,
                    "tlf_types": {"$addToSet": "$metadata.tlf_type"},
                    "clinical_domains": {"$addToSet": "$metadata.clinical_domain"},
                    "pages": {"$addToSet": "$metadata.page_number"}
                }}
            ]
            
            result = list(collection.aggregate(pipeline))
            
            if result:
                stats = result[0]
                return {
                    "document_id": document_id,
                    "total_vectors": vector_count,
                    "unique_tlf_types": [t for t in stats.get("tlf_types", []) if t],
                    "unique_clinical_domains": [d for d in stats.get("clinical_domains", []) if d],
                    "pages_covered": [p for p in stats.get("pages", []) if p],
                    "tlf_type_count": len([t for t in stats.get("tlf_types", []) if t]),
                    "clinical_domain_count": len([d for d in stats.get("clinical_domains", []) if d]),
                    "page_count": len([p for p in stats.get("pages", []) if p])
                }
            
            return {
                "document_id": document_id,
                "total_vectors": vector_count,
                "error": "No aggregation results found"
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting document statistics for {document_id}: {e}")
            return {
                "document_id": document_id,
                "error": str(e)
            }

    def close_connection(self):
        """Close MongoDB connection."""
        
        if self._mongo_client:
            self._mongo_client.close()
            logger.info("✅ MongoDB connection closed")

    def __del__(self):
        """Cleanup on object destruction."""
        self.close_connection()
