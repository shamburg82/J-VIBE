# backend/app/services/query_service.py
from typing import List, Dict, Optional, Any, AsyncGenerator
import asyncio
import time
import logging
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
    """Service for handling document queries."""
    
    def __init__(self, llm, storage_service: StorageService):
        self.llm = llm
        self.storage_service = storage_service
        
        # Query history tracking
        self._query_history: Dict[str, List[QueryResponse]] = {}
        self._total_queries = 0
        
        # Clinical prompt template
        self.clinical_prompt_template = """You are a clinical data analyst reviewing clinical trial outputs (Tables, Listings, Figures - TLFs). 

User Query: {query}

Clinical Trial Data:
{context}

Instructions:
- Answer the user's query based on the provided clinical trial data
- If comparing data across groups, doses, or timepoints, clearly highlight differences
- Reference specific table/output numbers when citing data
- If data is incomplete or unclear, state what's missing
- Use appropriate clinical terminology
- If no relevant data is found, clearly state this
- Summarize all sources you referenced in determining your response (by output type and number, not by chunk)

Analysis:"""

    async def process_query(self, request: QueryRequest) -> QueryResponse:
        """Process a standard query request."""
        
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
            else:
                # Generate response
                context = self._prepare_context(relevant_chunks)
                response_text = await self._query_llm(request.query, context)
                
                # Extract sources
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
        """Process query with streaming response."""
        
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
            if hasattr(self.llm, 'astream_complete'):
                async for chunk in self.llm.astream_complete(prompt):
                    yield StreamingQueryChunk(
                        type="content",
                        data=str(chunk.delta)
                    )
            else:
                # Fallback to non-streaming
                response = await self.llm.acomplete(prompt)
                yield StreamingQueryChunk(
                    type="content",
                    data=str(response)
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

    async def process_enhanced_query(self, request: EnhancedQueryRequest) -> QueryResponse:
        """Process enhanced query with filters."""
        
        # Convert to metadata filters
        metadata_filters = self._build_metadata_filters(request.filters)
        
        # Get vector index
        vector_index = await self.storage_service.get_index(request.document_id)
        if not vector_index:
            raise Exception(f"Document {request.document_id} not found")
        
        # Retrieve with filters
        relevant_chunks = await self._retrieve_relevant_chunks(
            vector_index, request.query, request.top_k, 
            request.min_confidence, metadata_filters
        )
        
        # Process same as standard query
        return await self.process_query(request)

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

    def _build_metadata_filters(self, filters: Optional[QueryFilters]) -> Optional[MetadataFilters]:
        """Build metadata filters from query filters."""
        
        if not filters:
            return None
        
        filter_list = []
        
        # TLF type filters
        if filters.tlf_types:
            filter_list.append(
                MetadataFilter(
                    key="tlf_type",
                    value=filters.tlf_types,
                    operator="in"
                )
            )
        
        # Clinical domain filters
        if filters.clinical_domains:
            filter_list.append(
                MetadataFilter(
                    key="clinical_domain",
                    value=filters.clinical_domains,
                    operator="in"
                )
            )
        
        # Output number filters
        if filters.output_numbers:
            filter_list.append(
                MetadataFilter(
                    key="output_number",
                    value=filters.output_numbers,
                    operator="in"
                )
            )
        
        # Population filters
        if filters.populations:
            filter_list.append(
                MetadataFilter(
                    key="population",
                    value=filters.populations,
                    operator="in"
                )
            )
        
        # ADDED: Study ID filters (for future multi-document queries)
        if hasattr(filters, 'study_ids') and filters.study_ids:
            filter_list.append(
                MetadataFilter(
                    key="study_id",
                    value=filters.study_ids,
                    operator="in"
                )
            )
        
        # ADDED: Compound filters (for future multi-document queries)
        if hasattr(filters, 'compounds') and filters.compounds:
            filter_list.append(
                MetadataFilter(
                    key="compound",
                    value=filters.compounds,
                    operator="in"
                )
            )
        
        if filter_list:
            return MetadataFilters(
                filters=filter_list,
                condition=FilterCondition.AND
            )
        
        return None

    def _prepare_context(self, results: List[Any]) -> str:
        """Prepare context string from search results."""
        
        context_parts = []
        
        for i, result in enumerate(results):
            metadata = result.node.metadata
            text = result.node.text
            
            # Format context entry
            title = metadata.get("title") or "Unknown"
            output_number = metadata.get("output_number") or ""
            tlf_type = metadata.get("tlf_type") or ""
            clinical_domain = metadata.get("clinical_domain") or ""
            population = metadata.get("population") or ""
            overall_conf = metadata.get("overall_confidence") or 0
            
            entry = f"""
--- OUTPUT {i+1} ---
Type: {tlf_type.title() if tlf_type else 'Unknown'}
Number: {output_number}
Title: {title}
Clinical Domain: {clinical_domain}
Population: {population}
Confidence: {overall_conf:.2f}

Content:
{text}

---
"""
            context_parts.append(entry)
        
        return '\n'.join(context_parts)

    async def _query_llm(self, query: str, context: str) -> str:
        """Query LLM with context."""
        
        prompt = self.clinical_prompt_template.format(query=query, context=context)
        
        if hasattr(self.llm, 'acomplete'):
            response = await self.llm.acomplete(prompt)
        else:
            response = self.llm.complete(prompt)
        
        return str(response).strip()

    def _extract_sources(self, results: List[Any]) -> List[QuerySource]:
        """Extract source information from search results."""
        
        source_summary = {}
        
        for result in results:
            metadata = result.node.metadata
            tlf_type = metadata.get("tlf_type") or "Unknown"
            output_number = metadata.get("output_number") or "Unknown"
            title = metadata.get("title") or "No title"
            page_number = metadata.get("page_info", {}).get("current_page")
            overall_conf = metadata.get("overall_confidence", 0)
            
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
        
        return list(source_summary.values())

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
            # This approach works with most vector stores
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
            
            # Extract unique values from node metadata
            tlf_types = set()
            clinical_domains = set()
            output_numbers = set()
            populations = set()
            treatment_groups = set()
            
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
            
            # Build summary with counts
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
                "total_nodes_analyzed": len(nodes),
                "document_id": document_id
            }
            
            # Add some statistics
            tlf_output_nodes = len([n for n in nodes if n.metadata.get('tlf_type')])
            sources_summary["statistics"] = {
                "nodes_with_tlf_metadata": tlf_output_nodes,
                "percentage_tlf_content": round((tlf_output_nodes / len(nodes)) * 100, 1) if nodes else 0
            }
            
            logger.info(f"Extracted sources for document {document_id}: {len(tlf_types)} TLF types, {len(output_numbers)} outputs")
            
            return sources_summary
            
        except Exception as e:
            logger.error(f"Error getting available sources for document {document_id}: {e}")
            return None

    async def get_query_count(self) -> int:
        """Get total query count."""
        return self._total_queries
