# backend/app/services/query_service.py - Enhanced version with better source extraction
from typing import List, Dict, Optional, Any, AsyncGenerator
import asyncio
import time
import logging
import re
from datetime import datetime

from llama_index.core import VectorStoreIndex
from llama_index.core.vector_stores import MetadataFilters, MetadataFilter, FilterCondition

from ..core.models import (
    QueryRequest, EnhancedQueryRequest, QueryResponse, QuerySource,
    StreamingQueryChunk, QueryFilters
)
from .storage_service import StorageService

logger = logging.getLogger(__name__)


class QueryService:
    """Service for handling document queries with source extraction."""
    
    def __init__(self, llm, storage_service: StorageService):
        self.llm = llm
        self.storage_service = storage_service
        
        # Query history tracking
        self._query_history: Dict[str, List[QueryResponse]] = {}
        self._total_queries = 0
        
        # clinical prompt template
        self.clinical_prompt_template = """You are a clinical data analyst reviewing clinical trial outputs (Tables, Listings, Figures - TLFs). 

User Query: {query}

Clinical Trial Data:
{context}

Instructions:
- Answer the user's query based on the provided clinical trial data
- If comparing data across groups, doses, or timepoints, clearly highlight differences
- Reference specific table/output numbers when citing data (e.g., "According to Table 14.3.1...")
- If data is incomplete or unclear, state what's missing
- Use appropriate clinical terminology
- If no relevant data is found, clearly state this
- When referencing specific outputs, mention both the type (Table/Listing/Figure) and number
- For page references, use format: "Page X" or "See page X for details"

Analysis:"""

    async def process_query(self, request: QueryRequest) -> QueryResponse:
        """Process a standard query request with enhanced source extraction."""
        
        start_time = time.time()
        
        try:
            # Get vector index for document
            vector_index = await self.storage_service.get_index(request.document_id)
            if not vector_index:
                raise Exception(f"Document {request.document_id} not found or not processed")
            
            # Retrieve relevant chunks
            relevant_chunks = await self._retrieve_relevant_chunks(
                vector_index, request.query, request.top_k, request.min_confidence
            )
            
            if not relevant_chunks:
                response_text = f"No relevant clinical trial data found for query: '{request.query}'. Try using broader search terms or lowering the confidence threshold."
                sources = []
            else:
                # Generate response
                context = self._prepare_context(relevant_chunks)
                response_text = await self._query_llm(request.query, context)
                
                # Extract sources with page information
                sources = self._extract_sources(relevant_chunks)
            
            # Create response
            response = QueryResponse(
                query=request.query,
                response=response_text,
                document_id=request.document_id,
                processing_time_ms=int((time.time() - start_time) * 1000),
                chunks_retrieved=len(relevant_chunks),
                sources_used=sources if relevant_chunks else [],
                top_k=request.top_k,
                min_confidence=request.min_confidence
            )
            
            # Store in history
            self._add_to_history(request.document_id, response)
            self._total_queries += 1
            
            return response
            
        except Exception as e:
            logger.error(f"Query processing error: {e}")
            raise

    async def process_query_stream(self, request: QueryRequest) -> AsyncGenerator[StreamingQueryChunk, None]:
        """Process query with streaming response and enhanced sources."""
        
        try:
            # Get relevant chunks first
            vector_index = await self.storage_service.get_index(request.document_id)
            if not vector_index:
                yield StreamingQueryChunk(
                    type="error",
                    data={"error": f"Document {request.document_id} not found"}
                )
                return
            
            relevant_chunks = await self._retrieve_relevant_chunks(
                vector_index, request.query, request.top_k, request.min_confidence
            )
            
            if not relevant_chunks:
                yield StreamingQueryChunk(
                    type="content",
                    data=f"No relevant clinical trial data found for query: '{request.query}'"
                )
                yield StreamingQueryChunk(type="complete", data={})
                return
            
            # Prepare context and stream LLM response
            context = self._prepare_context(relevant_chunks)
            prompt = self.clinical_prompt_template.format(query=request.query, context=context)
            
            # Stream LLM response
            try:
                if hasattr(self.llm, 'astream_complete'):
                    logger.info("Using LLM async streaming")
                    
                    # Get the streaming response
                    stream_response = self.llm.astream_complete(prompt)
                     
                    # Check if it's a coroutine that needs to be awaited first
                    if hasattr(stream_response, '__await__'):
                        # This is a coroutine, await it first
                        stream_response = await stream_response
                    
                    # Now check if it's an async iterator
                    if hasattr(stream_response, '__aiter__'):
                        async for chunk in stream_response:
                            # Handle different chunk formats
                            if hasattr(chunk, 'delta'):
                                content = str(chunk.delta)
                            elif hasattr(chunk, 'text'):
                                content = str(chunk.text)
                            else:
                                content = str(chunk)
                            
                            if content:  # Only yield non-empty content
                                yield StreamingQueryChunk(
                                    type="content",
                                    data=content
                                )
                    else:
                        # Not an async iterator, treat as single response
                        response_text = str(stream_response)
                        yield StreamingQueryChunk(
                            type="content",
                            data=response_text
                        )
                        
                elif hasattr(self.llm, 'stream_complete'):
                    # Fallback to sync streaming
                    logger.info("Using LLM sync streaming")
                    stream_response = self.llm.stream_complete(prompt)
                    
                    for chunk in stream_response:
                        content = str(chunk.delta) if hasattr(chunk, 'delta') else str(chunk)
                        if content:
                            yield StreamingQueryChunk(
                                type="content",
                                data=content
                            )
                else:
                    # No streaming support, use regular completion
                    logger.info("LLM doesn't support streaming, using regular completion")
                    response = await self._query_llm(request.query, context)
                    
                    # Simulate streaming by breaking response into chunks
                    words = response.split()
                    chunk_size = 10
                    
                    for i in range(0, len(words), chunk_size):
                        chunk_words = words[i:i + chunk_size]
                        chunk_text = ' '.join(chunk_words)
                        
                        yield StreamingQueryChunk(
                            type="content",
                            data=chunk_text + (' ' if i + chunk_size < len(words) else '')
                        )
                        
                        # Small delay to simulate streaming
                        await asyncio.sleep(0.1)
                        
            except Exception as stream_error:
                logger.error(f"Streaming error: {stream_error}")
                # Small delay to simulate streaming
                response = await self._query_llm(request.query, context)
                yield StreamingQueryChunk(
                    type="content",
                    data=response
                )
            
            # Send sources
            sources = self._extract_sources(relevant_chunks)
            yield StreamingQueryChunk(
                type="sources", 
                data=sources
            )
            
            # Send completion
            yield StreamingQueryChunk(
                type="complete",
                data={
                    "chunks_retrieved": len(relevant_chunks),
                    "top_k": request.top_k,
                    "min_confidence": request.min_confidence
                }
            )
            
            self._total_queries += 1
            
        except Exception as e:
            logger.error(f"Streaming query error: {e}")
            yield StreamingQueryChunk(
                type="error",
                data={"error": str(e)}
            )

    async def _retrieve_relevant_chunks(
        self,
        vector_index: VectorStoreIndex,
        query: str,
        top_k: int,
        min_confidence: float,
        metadata_filters: Optional[MetadataFilters] = None
    ) -> List[Any]:
        """Retrieve relevant chunks from vector index."""
        
        from llama_index.core.retrievers import VectorIndexRetriever
        
        # Create retriever
        retriever = VectorIndexRetriever(
            index=vector_index,
            similarity_top_k=top_k * 2,  # Get extra for filtering
            filters=metadata_filters
        )
        
        # Retrieve results
        results = retriever.retrieve(query)
        
        # Filter by confidence
        filtered_results = []
        for result in results:
            overall_conf = result.node.metadata.get("overall_confidence", 1.0)
            domain_conf = result.node.metadata.get("domain_confidence", 1.0)
            
            max_confidence = max(overall_conf, domain_conf)
            
            if max_confidence >= min_confidence:
                filtered_results.append(result)
        
        # Sort by relevance score
        try:
            filtered_results.sort(key=lambda x: getattr(x, 'score', 1.0), reverse=True)
        except:
            pass
        
        return filtered_results[:top_k]

    def _prepare_context(self, results: List[Any]) -> str:
        """Prepare context string with better formatting for clinical data."""
        
        context_parts = []
        
        for i, result in enumerate(results):
            metadata = result.node.metadata
            text = result.node.text
            
            # Enhanced metadata extraction
            title = metadata.get("title") or "Unknown"
            output_number = metadata.get("output_number") or ""
            tlf_type = metadata.get("tlf_type") or ""
            clinical_domain = metadata.get("clinical_domain") or ""
            population = metadata.get("population") or ""
            overall_conf = metadata.get("overall_confidence") or 0
            
            # Extract page information more robustly
            page_number = None
            page_info = metadata.get("page_info", {})
            if isinstance(page_info, dict):
                page_number = page_info.get("current_page") or page_info.get("page_number")
            
            # Fallback page extraction
            if not page_number:
                page_number = metadata.get("page_number") or metadata.get("page_label")
            
            # Try to extract page from other metadata
            if not page_number:
                source_info = metadata.get("source", "")
                page_match = re.search(r'page[_\s]?(\d+)', source_info.lower())
                if page_match:
                    page_number = int(page_match.group(1))

            entry = f"""
--- OUTPUT {i+1} ---
Type: {tlf_type.title() if tlf_type else 'Unknown'}
Number: {output_number}
Title: {title}
Page: {page_number if page_number else 'Unknown'}
Clinical Domain: {clinical_domain}
Population: {population}
Confidence: {overall_conf:.2f}

Content:
{text}

---
"""
            context_parts.append(entry)
        
        return '\n'.join(context_parts)

    def _extract_sources(self, results: List[Any]) -> List[QuerySource]:
        """Extract enhanced source information with better page detection."""
        
        source_summary = {}
        
        for result in results:
            metadata = result.node.metadata
            tlf_type = metadata.get("tlf_type") or "Unknown"
            output_number = metadata.get("output_number") or "Unknown"
            title = metadata.get("title") or "No title"
            overall_conf = metadata.get("overall_confidence", 0)
            
            # Enhanced page number extraction
            page_number = self._extract_page_number(metadata)
            
            source_id = f"{tlf_type} {output_number}"
            
            if source_id not in source_summary:
                source_summary[source_id] = QuerySource(
                    output_type=tlf_type,
                    output_number=output_number,
                    title=title,
                    page_number=page_number,
                    confidence=overall_conf,
                    chunk_count=0
                )
            
            source_summary[source_id].chunk_count += 1
            source_summary[source_id].confidence = max(
                source_summary[source_id].confidence,
                overall_conf
            )
            
            # Update page number if we find a better one
            if page_number and not source_summary[source_id].page_number:
                source_summary[source_id].page_number = page_number
        
        return list(source_summary.values())

    def _extract_page_number(self, metadata: Dict[str, Any]) -> Optional[int]:
        """Extract page number from metadata with multiple fallback strategies."""
        
        # Strategy 1: Direct page_info
        page_info = metadata.get("page_info", {})
        if isinstance(page_info, dict):
            page_num = page_info.get("current_page") or page_info.get("page_number")
            if page_num:
                try:
                    return int(page_num)
                except (ValueError, TypeError):
                    pass
        
        # Strategy 2: Direct page_number or page_label
        for key in ["page_number", "page_label", "page"]:
            page_val = metadata.get(key)
            if page_val:
                try:
                    return int(page_val)
                except (ValueError, TypeError):
                    pass
        
        # Strategy 3: Extract from source path/filename
        source_info = metadata.get("source", "")
        if source_info:
            # Look for patterns like "page_5", "page-5", "p5", etc.
            patterns = [
                r'page[_\s-]?(\d+)',
                r'p[_\s-]?(\d+)',
                r'pg[_\s-]?(\d+)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, source_info.lower())
                if match:
                    try:
                        return int(match.group(1))
                    except (ValueError, TypeError):
                        continue
        
        # Strategy 4: Extract from document_id or node_id patterns
        for id_key in ["id_", "node_id", "document_id"]:
            id_val = metadata.get(id_key, "")
            if id_val:
                # Look for patterns like "doc1_page5" or similar
                match = re.search(r'(?:page|p|pg)[_\s-]?(\d+)', str(id_val).lower())
                if match:
                    try:
                        return int(match.group(1))
                    except (ValueError, TypeError):
                        continue
        
        return None

    async def _query_llm(self, query: str, context: str) -> str:
        """Query LLM with context."""
        
        prompt = self.clinical_prompt_template.format(query=query, context=context)
        
        if hasattr(self.llm, 'acomplete'):
            response = await self.llm.acomplete(prompt)
        else:
            response = self.llm.complete(prompt)
        
        return str(response).strip()

    def _add_to_history(self, document_id: str, response: QueryResponse):
        """Add query to history."""
        
        if document_id not in self._query_history:
            self._query_history[document_id] = []
        
        self._query_history[document_id].append(response)
        
        # Keep only last 100 queries per document
        if len(self._query_history[document_id]) > 100:
            self._query_history[document_id] = self._query_history[document_id][-100:]

    async def get_query_history(
        self,
        document_id: str,
        limit: int = 20,
        offset: int = 0
    ) -> List[QueryResponse]:
        """Get query history for a document."""
        
        history = self._query_history.get(document_id, [])
        
        # Sort by timestamp (newest first)
        history.sort(key=lambda x: x.created_at, reverse=True)
        
        return history[offset:offset + limit]

    async def get_available_sources(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get available TLF sources in a document by analyzing actual vector index nodes."""
        
        try:
            # Get the vector index for this document
            vector_index = await self.storage_service.get_index(document_id)
            if not vector_index:
                return None
            
            # Get all nodes from the vector store
            nodes = []
            try:
                # Try to get nodes directly from the index
                if hasattr(vector_index, '_vector_store'):
                    # For in-memory vector stores
                    vector_store = vector_index._vector_store
                    if hasattr(vector_store, '_data') and hasattr(vector_store._data, 'embedding_dict'):
                        # Get all node IDs and retrieve the nodes
                        node_ids = list(vector_store._data.embedding_dict.keys())
                        nodes = [vector_store._data.doc_store.get_document(node_id) for node_id in node_ids]
                    elif hasattr(vector_store, 'get_nodes'):
                        nodes = vector_store.get_nodes()
                elif hasattr(vector_index, 'docstore'):
                    # Alternative approach through docstore
                    doc_store = vector_index.docstore
                    if hasattr(doc_store, 'docs'):
                        nodes = list(doc_store.docs.values())
            except Exception as e:
                logger.warning(f"Could not extract nodes directly, using retrieval approach: {e}")
                
                # Fallback: Use retrieval to sample nodes
                from llama_index.core.retrievers import VectorIndexRetriever
                retriever = VectorIndexRetriever(
                    index=vector_index,
                    similarity_top_k=100  # Get a large sample
                )
                
                # Use broad search terms to get diverse results
                search_terms = ["table", "data", "analysis", "results", "clinical"]
                retrieved_nodes = []
                
                for term in search_terms:
                    try:
                        results = retriever.retrieve(term)
                        retrieved_nodes.extend([r.node for r in results])
                    except:
                        continue
                
                nodes = retrieved_nodes
            
            if not nodes:
                logger.warning(f"No nodes found for document {document_id}")
                return None
            
            # Extract unique values from node metadata with enhanced page detection
            tlf_types = set()
            clinical_domains = set()
            output_numbers = set()
            populations = set()
            treatment_groups = set()
            pages_found = set()
            
            for node in nodes:
                if not hasattr(node, 'metadata'):
                    continue
                    
                metadata = node.metadata
                
                # Collect TLF types
                tlf_type = metadata.get('tlf_type')
                if tlf_type:
                    tlf_types.add(tlf_type)
                
                # Collect clinical domains (exclude TOC)
                domain = metadata.get('clinical_domain')
                if domain and domain != 'table_of_contents':
                    clinical_domains.add(domain)
                
                # Collect output numbers
                output_num = metadata.get('output_number')
                if output_num:
                    output_numbers.add(output_num)
                
                # Collect populations
                population = metadata.get('population')
                if population:
                    populations.add(population)
                
                # Collect treatment groups
                groups = metadata.get('treatment_groups', [])
                if isinstance(groups, list):
                    treatment_groups.update(groups)
                elif isinstance(groups, str):
                    treatment_groups.add(groups)
                
                # Collect page numbers
                page_num = self._extract_page_number(metadata)
                if page_num:
                    pages_found.add(page_num)
            
            # Build enhanced summary with page information
            sources_summary = {
                "tlf_types": {
                    "available": sorted(list(tlf_types)),
                    "count": len(tlf_types)
                },
                "clinical_domains": {
                    "available": sorted(list(clinical_domains)),
                    "count": len(clinical_domains)
                },
                "output_numbers": {
                    "available": sorted(list(output_numbers), key=lambda x: [int(n) for n in x.split('.') if n.isdigit()]),
                    "count": len(output_numbers)
                },
                "populations": {
                    "available": sorted(list(populations)),
                    "count": len(populations)
                },
                "treatment_groups": {
                    "available": sorted(list(treatment_groups)),
                    "count": len(treatment_groups)
                },
                "pages": {
                    "available": sorted(list(pages_found)),
                    "count": len(pages_found),
                    "range": f"{min(pages_found)}-{max(pages_found)}" if pages_found else "Unknown"
                },
                "total_nodes_analyzed": len(nodes),
                "document_id": document_id
            }
            
            # Add statistics
            tlf_output_nodes = len([n for n in nodes if n.metadata.get('tlf_type')])
            nodes_with_pages = len([n for n in nodes if self._extract_page_number(n.metadata)])
            
            sources_summary["statistics"] = {
                "nodes_with_tlf_metadata": tlf_output_nodes,
                "nodes_with_page_info": nodes_with_pages,
                "percentage_tlf_content": round((tlf_output_nodes / len(nodes)) * 100, 1) if nodes else 0,
                "percentage_with_pages": round((nodes_with_pages / len(nodes)) * 100, 1) if nodes else 0
            }
            
            logger.info(f"Enhanced sources extracted for document {document_id}: {len(tlf_types)} TLF types, {len(output_numbers)} outputs, {len(pages_found)} pages")
            
            return sources_summary
            
        except Exception as e:
            logger.error(f"Error getting available sources for document {document_id}: {e}")
            return None

    async def get_query_count(self) -> int:
        """Get total query count."""
        return self._total_queries
