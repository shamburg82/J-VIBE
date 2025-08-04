# structured_extractors/base_extractor.py
"""
Base Extractor - Abstract base class for all structured extractors

Provides common functionality for structured data extraction including:
- Confidence scoring
- Text cleaning and preprocessing  
- Common extraction patterns
- Validation frameworks
"""

import re
import datetime
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class StructuredData:
    """Base class for all structured data objects."""
    document_id: str
    document_type: str
    extraction_timestamp: str
    confidence_score: float


@dataclass
class ExtractionResult:
    """Result of a structured extraction operation."""
    success: bool
    data: Optional[StructuredData]
    completeness_score: float
    extraction_metadata: Dict[str, Any] = None
    error: Optional[str] = None
    warnings: List[str] = None


class BaseExtractor(ABC):
    """Abstract base class for all structured extractors."""
    
    def __init__(self):
        self.document_type = "unknown"
        self.min_confidence_threshold = 0.5
        
    @abstractmethod
    def extract(self, document) -> ExtractionResult:
        """Extract structured data from document."""
        pass
    
    def _get_timestamp(self) -> str:
        """Get current timestamp for extraction."""
        return datetime.datetime.now().isoformat()
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        if not text:
            return ""
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove page numbers and headers/footers
        text = re.sub(r'Page\s+\d+\s+of\s+\d+', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)
        
        # Remove repeated dashes or underscores
        text = re.sub(r'[-_]{3,}', '', text)
        
        # Clean up bullet points
        text = re.sub(r'^[•\-\*]\s*', '', text, flags=re.MULTILINE)
        
        return text.strip()
    
    def _calculate_confidence(self, extracted_items: List[Any]) -> float:
        """Calculate confidence score based on extraction success."""
        if not extracted_items:
            return 0.0
        
        # Count non-empty extractions
        valid_extractions = 0
        total_extractions = len(extracted_items)
        
        for item in extracted_items:
            if isinstance(item, list) and len(item) > 0:
                valid_extractions += 1
            elif isinstance(item, dict) and any(v for v in item.values() if v != 'unknown'):
                valid_extractions += 1
            elif item and str(item) != 'unknown':
                valid_extractions += 1
        
        return valid_extractions / total_extractions if total_extractions > 0 else 0.0
    
    def _extract_with_llm(self, text: str, extraction_prompt: str) -> Dict[str, Any]:
        """Use LLM for complex extractions when patterns fail."""
        try:
            from llama_index.core import Settings
            
            if not Settings.llm:
                return {}
            
            prompt = f"""
            {extraction_prompt}
            
            Text to analyze:
            {text[:2000]}...
            
            Please provide the extracted information in a structured format.
            """
            
            response = Settings.llm.complete(prompt)
            
            # Parse LLM response (simplified - would need more robust parsing)
            return {"llm_response": response.text}
            
        except Exception as e:
            print(f"LLM extraction failed: {e}")
            return {}
