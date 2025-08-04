# backend/app/extractors/tlf_exractor.py
from llama_index.core.extractors import BaseExtractor
from llama_index.core.schema import BaseNode
import re
from typing import List, Dict, Any, Optional, Tuple, Set
import logging
from collections import defaultdict
import json

class TLFExtractor(BaseExtractor):
    """Extractor for Table, Listing, and Figure (TLF) outputs from clinical trials."""

    def __init__(self, llm=None, confidence_threshold=0.7, use_llm_validation=True, 
             enable_bundle_optimization=True, **kwargs):
        super().__init__(llm=llm, **kwargs)
        
        self._llm = llm
        self._confidence_threshold = confidence_threshold
        self._use_llm_validation = use_llm_validation
        self._enable_bundle_optimization = enable_bundle_optimization
        
        # Current TLF context
        self._current_tlf = None
        self._tlf_confidence = 0.0
        self._tlf_history = []
        self._page_context = {}
        
        # Bundle optimization cache
        self._header_cache = {}
        self._footnote_cache = {}
        self._last_processed_header = None
        self._skip_duplicate_processing = True

        # TLF type patterns - FIXED: More comprehensive patterns
        self._tlf_type_patterns = {
            "table": [
                r"table\s+\d+", r"^table\s+", r"summary\s+of\s+", 
                r"frequency\s+of\s+", r"descriptive\s+statistics" #,
                # r"demographic.*characteristics", r"baseline.*characteristics",
                # r"laboratory.*values", r"vital.*signs", r"adverse.*events"
            ],
            "listing": [
                r"listing\s+\d+", r"^listing\s+", #r"list\s+of\s+",
                r"participant\s+data", r"subject\s+data", r"patient\s+data"
            ],
            "figure": [
                r"figure\s+\d+", r"^figure\s+", r"plot\s+of\s+",
                r"graph\s+of\s+", r"chart\s+of\s+"
            ]
        }
        
        # Output number patterns
        self._output_number_pattern = r'(?:table|listing|figure|t-|l-|f-)?[\s\-]?(\d+(?:\.\d+){0,5})(?:\s|$|:)'
        
        # Improved clinical domains with better patterns
        self._clinical_domains = {
            # Demographics and Baseline
            "demographics": [
                r"demographic", r"demographics", r"baseline\s+characteristic", 
                r"baseline\s+characteristics", r"subject\s+characteristics", 
                r"patient\s+characteristics", r"participant\s+characteristics",
                r"\bage\b", r"\bsex\b", r"\brace\b", r"\bweight\b", r"\bheight\b", r"\bbmi\b"
            ],
            
            # Safety - FIXED: Added more comprehensive patterns
            "adverse_events": [
                r"adverse\s+event", r"adverse\s+events", r"treatment[\s\-]*emergent",
                r"serious\s+adverse", r"\bae\b", r"\bsae\b", r"\bteae\b",
                r"system\s+organ\s+class", r"\bsoc\b", r"preferred\s+term", r"\bpt\b",
                r"toxicity", r"side\s+effect", r"safety\s+event", r"undesirable\s+effect",
                r"treatment.*emergent.*serious", r"for\s+public\s+disclosure"
            ],
            
            # Medical History
            "medical_history": [
                r"medical\s+history", r"medical\s+condition", r"prior\s+medical\s+history", 
                r"prior\s+medical\s+condition", r"concomitant\s+medication"
            ],
            
            # Laboratory - FIXED: More comprehensive
            "laboratory": [
                r"laboratory", r"lab\s+", r"hematology", r"chemistry", r"urinalysis",
                r"glucose", r"hemoglobin", r"creatinine", r"\balt\b", r"\bast\b", r"bilirubin",
                r"white\s+blood\s+cell", r"\bwbc\b", r"platelet", r"laboratory\s+values"
            ],
            
            # Vital Signs
            "vital_signs": [
                r"vital\s+sign", r"vital\s+signs", r"vitals", r"blood\s+pressure", 
                r"heart\s+rate", r"temperature", r"respiratory\s+rate", r"pulse", 
                r"systolic", r"diastolic"
            ],
            
            # ECG
            "ecg": [
                r"electrocardiogram", r"\becg\b", r"\bekg\b", r"qt\s+interval", r"\bqrs\b", 
                r"cardiac\s+conduction", r"heart\s+rhythm"
            ],
            
            # Efficacy
            "efficacy": [
                r"efficacy", r"endpoint", r"outcome", r"response", r"efficacy\s+parameter",
                r"primary\s+endpoint", r"secondary\s+endpoint"
            ],
            
            # Pharmacokinetics
            "pharmacokinetics": [
                r"pharmacokinetic", r"\bpk\b", r"concentration", r"plasma\s+level",
                r"cmax", r"tmax", r"auc", r"half[\s\-]*life", r"clearance", r"bioavailability"
            ],
            
            # Disposition - FIXED: Better patterns
            "disposition": [
                r"disposition", r"enrollment", r"randomization", r"completion",
                r"discontinuation", r"withdrawal", r"screen\s+failure", r"subject\s+disposition"
            ],
            
            # Exposure
            "exposure": [
                r"exposure", r"dose", r"dosing", r"treatment\s+duration",
                r"compliance", r"adherence", r"drug\s+administration"
            ]
        }
        
        # Population set patterns
        self._population_patterns = {
            "screened": [r"screened", r"screened\s+participants"],
            "safety": [r"safety", r"saf", r"treated", r"as.treated"],
            "enrolled": [r"enrolled\s+analysis", r"enrolled", r"enrolled\s+analysis\s+set"],
            "mitt": [r"modified\s+intention.to.treat", r"mitt", r"modified\s+intent.to.treat", r"modified\s+itt"],
            "itt": [r"intention.to.treat", r"itt", r"intent.to.treat"],
            "pp": [r"per.protocol", r"pp", r"per\s+protocol"],
            "mfas": [r"modified\s+full\s+analysis", r"mfas", r"mfas\s+set"],
            "fas": [r"full\s+analysis", r"fas", r"full\s+analysis\s+set"],
            "pk": [r"pk\s+analysis", r"pk", r"pk\s+analysis\s+set", r"pharmocokinetic\s+analysis", r"pharmocokinetic", r"pharmocokinetic\s+analysis\s+set"],
            "evaluable": [r"evaluable", r"efficacy\s+evaluable"]
        }
        
        # Treatment group patterns
        self._treatment_patterns = [
            r"placebo", r"control", r"active", r"treatment",
            r"\d+\s*mg", r"\d+\s*μg", r"\d+\s*mcg", r"\d+\s*g",
            r"dose\s+group", r"cohort", r"arm"
        ]
        
        # Header extraction patterns
        self._header_patterns = {
            "sponsor": r"sponsor[:\s]+([^\n\r]+)",
            "protocol": r"protocol[:\s#]*([a-zA-Z0-9\-_]+)",
            "study": r"study[:\s#]*([a-zA-Z0-9\-_]+)",
            "page": r"page\s+(\d+)\s+of\s+(\d+)",
            "title": r"^(.{1,200})$",
            "date": r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{2,4}[-/]\d{1,2}[-/]\d{1,2})"
        }
        
        # LLM prompts
        self._tlf_classification_prompt = """
Analyze this clinical trial output text and extract key metadata:

TEXT: "{text}"

Extract the following information:
1. OUTPUT_TYPE: Table, Listing, or Figure
2. OUTPUT_NUMBER: The output identifier (e.g., 14.3.1, T-9.2.1)
3. TITLE: The descriptive title of the output
4. CLINICAL_DOMAIN: What clinical area this covers (demographics, adverse_events, laboratory, vital_signs, ecg, efficacy, pharmacokinetics, disposition, exposure)
5. POPULATION: The analysis population (Safety, ITT, PP, FAS, etc.)
6. TREATMENT_GROUPS: Any dose groups or treatments mentioned
7. CONFIDENCE: How confident you are (0.0 to 1.0)

Respond in this exact format:
OUTPUT_TYPE: [Table|Listing|Figure]
OUTPUT_NUMBER: [identifier or "unknown"]
TITLE: [title or "unknown"]
CLINICAL_DOMAIN: [domain or "unknown"]
POPULATION: [population or "unknown"]
TREATMENT_GROUPS: [groups separated by semicolons or "unknown"]
CONFIDENCE: [0.0 to 1.0]
"""


    def __call__(self, nodes: List[BaseNode], **kwargs) -> List[BaseNode]:
        """Transform nodes by adding TLF metadata."""
        print(f"TLFExtractor.__call__ processing {len(nodes)} nodes")
        
        # Extract metadata for all nodes
        metadata_list = self.extract(nodes)
        
        # Apply metadata to each node
        for i, (node, metadata) in enumerate(zip(nodes, metadata_list)):
            # Update node metadata with extracted TLF metadata
            node.metadata.update(metadata)
            
            # Debug: Log what we're setting
            if metadata.get('title'):
                print(f"  Node {i}: Setting title to '{metadata['title']}'")
        
        return nodes
        
    async def aextract(self, nodes: List[BaseNode]) -> List[Dict[str, Any]]:
        """Async extraction method for TLF outputs with bundle optimization."""
        metadata_list = []
        
        for i, node in enumerate(nodes):
            text = node.get_content()
            
            # Step 1: Check for strict TOC first
            if self._is_table_of_contents_strict(text):
                toc_metadata = self._create_toc_metadata(text, i)
                metadata_list.append(toc_metadata)
                continue
            
            # Step 2: Detect page boundaries and extract flexible headers
            page_analysis = self._detect_page_boundary_and_headers(text)
            
            # Step 3: Run standard pattern detection as backup
            pattern_result = self._detect_tlf_patterns(text)
            structure_result = self._analyze_structure(text)
            domain_result = self._classify_clinical_domain_dual(text)
            
            # Step 4: Choose best header extraction result
            best_header = None
            if page_analysis['headers_found']:
                # Take the header with highest confidence
                best_header = max(page_analysis['headers_found'], 
                                key=lambda h: h['confidence'])
            
            # Step 5: Properly merge flexible header results with pattern results
            if best_header and best_header['confidence'] > 0.6:
                # Use flexible header analysis results and merge with pattern results
                enhanced_pattern_result = {
                    'tlf_type': best_header['tlf_type'] or pattern_result.get('tlf_type'),
                    'output_number': best_header['output_number'] or pattern_result.get('output_number'), 
                    'title': best_header['title'] or pattern_result.get('title'),
                    'population': best_header['population'] or pattern_result.get('population'),
                    'treatment_groups': pattern_result.get('treatment_groups', []),
                    'confidence': max(best_header['confidence'], pattern_result.get('confidence', 0)),
                    'method': 'flexible_header_analysis'
                }
            else:
                # Use standard pattern results but supplement with flexible header title if available
                enhanced_pattern_result = pattern_result.copy()
                
                # If standard pattern didn't find title but flexible header did, use it
                if (not pattern_result.get('title') and 
                    best_header and best_header.get('title')):
                    enhanced_pattern_result['title'] = best_header['title']
                    enhanced_pattern_result['method'] = 'pattern_with_flexible_title'
                    # Boost confidence slightly since we found additional info
                    enhanced_pattern_result['confidence'] = min(
                        enhanced_pattern_result.get('confidence', 0) + 0.2, 1.0
                    )
            
            # Step 6: LLM validation (async) - only for uncertain data content
            llm_result = None
            if (self._use_llm_validation and self._llm and 
                not structure_result.get("is_header") and 
                not structure_result.get("is_footnote") and
                enhanced_pattern_result.get("confidence", 0) < 0.8):
                try:
                    llm_result = await self._allm_tlf_analysis(text)
                except Exception as e:
                    logging.warning(f"Async LLM analysis failed: {e}")
            
            # Step 7: Create preliminary metadata
            preliminary_metadata = self._combine_tlf_results(
                enhanced_pattern_result, structure_result, domain_result, llm_result, i
            )
            
            # Add page analysis info for debugging
            preliminary_metadata['page_analysis'] = page_analysis
            preliminary_metadata['best_header'] = best_header
            
            # Step 8: Update context FIRST if we found a good header
            context_updated = False
            if (best_header and best_header['confidence'] > 0.8 and 
                enhanced_pattern_result.get('tlf_type') and 
                enhanced_pattern_result.get('output_number')):
                
                # This is a strong new header - update context immediately
                self._update_tlf_context(preliminary_metadata, i)
                context_updated = True
            
            # Step 9: Inherit context or use new metadata?
            should_inherit = self._should_inherit_context(preliminary_metadata, text)
            
            if should_inherit and self._current_tlf:
                # Create inherited metadata but preserve newly found titles
                final_metadata = self._create_inherited_metadata(
                    preliminary_metadata, text, i
                )
                final_metadata['inheritance_decision'] = 'inherited'
            else:
                # Use new metadata
                final_metadata = preliminary_metadata
                final_metadata['inheritance_decision'] = 'new_context' if not context_updated else 'new_context_set'
                
                # Update context if this represents a new TLF (and we haven't already)
                if (not context_updated and
                    final_metadata.get('tlf_type') and 
                    final_metadata.get('output_number') and
                    final_metadata.get('overall_confidence', 0) > 0.6):
                    
                    self._update_tlf_context(final_metadata, i)
            
            # Step 10: Set current context reference
            final_metadata['current_tlf_context'] = self._current_tlf.copy() if self._current_tlf else None
            
            # Add debug info
            final_metadata['debug_info'] = {
                'should_inherit': should_inherit,
                'had_previous_context': self._current_tlf is not None,
                'preliminary_confidence': preliminary_metadata.get('overall_confidence', 0),
                'used_header_analysis': best_header is not None,
                'page_boundaries_found': len(page_analysis.get('page_boundaries', [])),
                'context_updated_early': context_updated,
                'header_confidence': best_header['confidence'] if best_header else 0,
                'title_tracking': {
                    'pattern_result_title': pattern_result.get('title'),
                    'best_header_title': best_header.get('title') if best_header else None,
                    'enhanced_pattern_title': enhanced_pattern_result.get('title'),
                    'preliminary_title': preliminary_metadata.get('title'),
                    'final_title': final_metadata.get('title'),
                    'title_source': self._determine_title_source(pattern_result, best_header, final_metadata)
                }
            }
            
            metadata_list.append(final_metadata)
        
        return metadata_list

    def extract(self, nodes: List[BaseNode]) -> List[Dict[str, Any]]:
        """Synchronous extraction method with proper domain classification and context handling."""
        metadata_list = []
    
        for i, node in enumerate(nodes):
            text = node.get_content()
            
            # Step 1: Check for strict TOC first
            if self._is_table_of_contents_strict(text):
                toc_metadata = self._create_toc_metadata(text, i)
                metadata_list.append(toc_metadata)
                continue
            
            # Step 2: Detect page boundaries and extract flexible headers
            page_analysis = self._detect_page_boundary_and_headers(text)
            
            # Step 3: Run standard pattern detection as backup
            pattern_result = self._detect_tlf_patterns(text)
            structure_result = self._analyze_structure(text)
            domain_result = self._classify_clinical_domain_dual(text)
            
            # Step 4: Choose best header extraction result
            best_header = None
            if page_analysis['headers_found']:
                # Take the header with highest confidence
                best_header = max(page_analysis['headers_found'], 
                                key=lambda h: h['confidence'])
            
            # Step 5: Use header analysis if confident, otherwise use pattern results
            if best_header and best_header['confidence'] > 0.6:
                # Use flexible header analysis results and merge with pattern results
                enhanced_pattern_result = {
                    'tlf_type': best_header['tlf_type'] or pattern_result.get('tlf_type'),
                    'output_number': best_header['output_number'] or pattern_result.get('output_number'), 
                    'title': best_header['title'] or pattern_result.get('title'),  # Prioritize flexible header title
                    'population': best_header['population'] or pattern_result.get('population'),
                    'treatment_groups': pattern_result.get('treatment_groups', []),
                    'confidence': max(best_header['confidence'], pattern_result.get('confidence', 0)),
                    'method': 'flexible_header_analysis'
                }
            else:
                # Use standard pattern results
                enhanced_pattern_result = pattern_result.copy()
            
                # If standard pattern didn't find title but flexible header did, use it
                if (not pattern_result.get('title') and 
                    best_header and best_header.get('title')):
                    enhanced_pattern_result['title'] = best_header['title']
                    enhanced_pattern_result['method'] = 'pattern_with_flexible_title'
                    # Boost confidence slightly since we found additional info
                    enhanced_pattern_result['confidence'] = min(
                        enhanced_pattern_result.get('confidence', 0) + 0.2, 1.0
                    )
            
            # Step 6: Create preliminary metadata
            preliminary_metadata = self._combine_tlf_results(
                enhanced_pattern_result, structure_result, domain_result, None, i
            )
            
            # Add page analysis info for debugging
            preliminary_metadata['page_analysis'] = page_analysis
            preliminary_metadata['best_header'] = best_header
            
            # Step 7: DECISION POINT - Update context FIRST if we found a good header
            context_updated = False
            if (best_header and best_header['confidence'] > 0.8 and 
                enhanced_pattern_result.get('tlf_type') and 
                enhanced_pattern_result.get('output_number')):
                
                # This is a strong new header - update context immediately
                self._update_tlf_context(preliminary_metadata, i)
                context_updated = True
            
            # Step 8: DECISION POINT - Inherit context or use new metadata?
            should_inherit = self._should_inherit_context(preliminary_metadata, text)
            
            if should_inherit and self._current_tlf:
                # Create inherited metadata but preserve title from flexible header analysis
                final_metadata = self._create_inherited_metadata(
                    preliminary_metadata, text, i
                )
                final_metadata['inheritance_decision'] = 'inherited'
            else:
                # Use new metadata
                final_metadata = preliminary_metadata
                final_metadata['inheritance_decision'] = 'new_context' if not context_updated else 'new_context_set'
                
                # Update context if this represents a new TLF (and we haven't already)
                if (not context_updated and
                    final_metadata.get('tlf_type') and 
                    final_metadata.get('output_number') and
                    final_metadata.get('overall_confidence', 0) > 0.6):
                    
                    self._update_tlf_context(final_metadata, i)
            
            # Step 9: Set current context reference
            final_metadata['current_tlf_context'] = self._current_tlf.copy() if self._current_tlf else None
            
            # Add debug info
            final_metadata['debug_info'] = {
                'should_inherit': should_inherit,
                'had_previous_context': self._current_tlf is not None,
                'preliminary_confidence': preliminary_metadata.get('overall_confidence', 0),
                'used_header_analysis': best_header is not None,
                'page_boundaries_found': len(page_analysis.get('page_boundaries', [])),
                'context_updated_early': context_updated,
                'header_confidence': best_header['confidence'] if best_header else 0,
                'title_tracking': {
                    'pattern_result_title': pattern_result.get('title'),
                    'best_header_title': best_header.get('title') if best_header else None,
                    'enhanced_pattern_title': enhanced_pattern_result.get('title'),
                    'preliminary_title': preliminary_metadata.get('title'),
                    'final_title': final_metadata.get('title'),
                    'title_source': self._determine_title_source(pattern_result, best_header, final_metadata)
                }
            }
            
            metadata_list.append(final_metadata)
        
        return metadata_list
        
    async def _allm_tlf_analysis(self, text: str) -> Dict[str, Any]:
        """FIXED: Async LLM analysis with proper error handling."""
        try:
            prompt = self._tlf_classification_prompt.format(text=text[:1500])
            
            # Use async completion
            if hasattr(self._llm, 'acomplete'):
                response = await self._llm.acomplete(prompt)
            else:
                # Fallback to sync if async not available
                response = self._llm.complete(prompt)
                
            response_text = str(response)
            
            # Parse structured response
            result = {}
            
            patterns = {
                "tlf_type": r'OUTPUT_TYPE:\s*([^\n]+)',
                "output_number": r'OUTPUT_NUMBER:\s*([^\n]+)',
                "title": r'TITLE:\s*([^\n]+)',
                "clinical_domain": r'CLINICAL_DOMAIN:\s*([^\n]+)',
                "population": r'POPULATION:\s*([^\n]+)',
                "treatment_groups": r'TREATMENT_GROUPS:\s*([^\n]+)',
                "confidence": r'CONFIDENCE:\s*([0-9.]+)'
            }
            
            for key, pattern in patterns.items():
                match = re.search(pattern, response_text, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    if key == "confidence":
                        result[key] = float(value) if value else 0.0
                    elif key == "treatment_groups":
                        result[key] = [g.strip() for g in value.split(';') if g.strip() and g.strip().lower() != "unknown"]
                    else:
                        result[key] = value if value.lower() != "unknown" else None
            
            result["method"] = "async_llm"
            return result
            
        except Exception as e:
            logging.error(f"Async LLM TLF analysis error: {e}")
            return {"method": "async_llm_error", "confidence": 0.0}
        
        
    def _detect_tlf_patterns(self, text: str) -> Dict[str, Any]:
        """FIXED: Improved TLF pattern detection with better type inference."""
    
        # Early exit for TOC - don't extract TLF info from TOC
        if self._is_table_of_contents(text):
            return {
                "tlf_type": None,
                "output_number": None,
                "title": "Table of Contents",
                "population": None,
                "treatment_groups": [],
                "confidence": 0.95,
                "method": "toc_detection"
            }
        
        text_lower = text.lower().strip()
        
        # Check for TLF type
        detected_type = None
        type_confidence = 0.0
        
        for tlf_type, patterns in self._tlf_type_patterns.items():
            for pattern in patterns:
                matches = re.findall(pattern, text_lower, re.IGNORECASE)
                if matches:
                    confidence = 0.9 if re.match(rf'^{pattern}', text_lower.strip()) else 0.7
                    if confidence > type_confidence:
                        detected_type = tlf_type
                        type_confidence = confidence
        
        # If no explicit TLF type found, infer from content structure
        if not detected_type and len(text.split()) > 10:
            # Look for table-like content patterns
            has_tabular_structure = any([
                re.search(r'\bn\s*\(\s*%\s*\)', text_lower),  # n (%)
                re.search(r'\bmean\s*\(\s*sd\s*\)', text_lower),  # Mean (SD)
                re.search(r'\bmedian\b', text_lower),
                re.search(r'\bmin\s*,\s*max\b', text_lower),
                re.search(r'\b95%\s*ci\b', text_lower),
                len(re.findall(r'\b\d+(?:\.\d+)?\s*\(\s*\d+(?:\.\d+)?%?\s*\)', text)) > 2
            ])
            
            if has_tabular_structure:
                detected_type = "table"
                type_confidence = 0.6
        
        # Extract other components
        output_number = self._extract_output_number(text) 
        title = self._extract_title(text)
        population = self._extract_population(text)
        treatment_groups = self._extract_treatment_groups(text)
        
        return {
            "tlf_type": detected_type,
            "output_number": output_number,
            "title": title,
            "population": population,
            "treatment_groups": treatment_groups,
            "confidence": type_confidence,
            "method": "pattern"
        }

    def _analyze_structure(self, text: str) -> Dict[str, Any]:
        """Analyze document structure to identify headers, data, footnotes."""
        
        # Check if this looks like a header section
        is_header = self._is_likely_header(text)
        
        # Check if this looks like data content
        is_data = self._is_likely_data(text)
        
        # Check if this looks like footnotes
        is_footnote = self._is_likely_footnote(text)
        
        # Extract page information
        page_info = self._extract_page_info(text)
        
        # Extract sponsor/protocol info
        sponsor_info = self._extract_sponsor_info(text)
        
        return {
            "is_header": is_header,
            "is_data": is_data,
            "is_footnote": is_footnote,
            "page_info": page_info,
            "sponsor_info": sponsor_info,
            "structure_confidence": self._calculate_structure_confidence(is_header, is_data, is_footnote)
        }

    def _is_table_of_contents(self, text: str, metadata: Dict = None) -> bool:
        """Detect if content is a Table of Contents and should be penalized."""
        text_lower = text.lower().strip()
        
        # Direct TOC indicators - most reliable
        explicit_toc_indicators = [
            "table of contents", "\btoc\b", "list of tables", "list of figures", 
            "list of listings", "index of tables", "index of figures"
        ]
        
        # Check for explicit indicators at the start of text
        for indicator in explicit_toc_indicators:
            if indicator in text_lower:
                # Make sure it's not just mentioned in passing
                # Should be near the beginning or be a standalone line
                lines = text_lower.split('\n')
                for line in lines[:3]:  # Check first 3 lines
                    if indicator in line and len(line.strip()) < 50:  # Short line with TOC indicator
                        return True
        

        # CRITICAL: If text contains actual table headers, it's NOT TOC
        # These are strong indicators of actual table content, not TOC
        table_content_indicators = [
            'jazz pharmaceuticals',
            'protocol jzp',
            'final clinical study report',
            'page \\d+ of \\d+',  # Page numbers
            'confidential'
        ]

        # If we find actual table content indicators, definitely NOT TOC
        for indicator in table_content_indicators:
            if re.search(indicator, text_lower):
                return False
        
        # Structural analysis - but much more restrictive
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        if len(lines) < 3:  # TOC should have multiple lines
            return False
        
        # Count lines that look like TOC entries vs. actual content
        toc_entry_lines = 0
        content_lines = 0
        
        for line in lines:
            line_lower = line.lower()
            
            # TOC entry patterns - very specific
            if re.search(r'^(?:table|figure|listing)\s+\d+(?:\.\d+)*\s+.{10,80}\.{3,}', line_lower):
                toc_entry_lines += 1
            elif re.search(r'^(?:table|figure|listing)\s+\d+(?:\.\d+)*\s+', line_lower) and '...' in line:
                toc_entry_lines += 1
            # Regular content (has substantial text without TOC patterns)
            elif len(line.split()) > 5 and not re.search(r'^\d+(?:\.\d+)*', line):
                content_lines += 1
        
        # For it to be TOC:
        # 1. Must have at least 3 TOC-like entries
        # 2. TOC entries should be majority of content
        # 3. Should have minimal actual content
        if len(lines) >= 5:
            toc_ratio = toc_entry_lines / len(lines)
            content_ratio = content_lines / len(lines)
            
            # Very strict criteria
            if toc_entry_lines >= 3 and toc_ratio > 0.6 and content_ratio < 0.2:
                return True
        
        return False

    def _classify_clinical_domain_dual(self, text: str, metadata: Dict = None) -> Dict[str, Any]:
        """Improved dual classification with better debugging."""

        # First check if this is TOC content
        if self._is_table_of_contents(text, metadata):
            return {
                "primary_domain": "table_of_contents",
                "domain_confidence": 0.95,  # High confidence for TOC
                "all_domains": {
                    "table_of_contents": {
                        "score": 100,
                        "matched_keywords": ["table of contents"],
                        "confidence": 0.95,
                        "unique_matches": 1
                    }
                },
                "matched_keywords": ["table of contents"]
            }

        # Call Strict matching with word boundaries
        strict_result = self._classify_clinical_domain_strict(text)
        
        # Call Loose matching without word boundaries  
        loose_result = self._classify_clinical_domain_loose(text)
        
        # Debug logging
        if strict_result.get("primary_domain") or loose_result.get("primary_domain"):
            logging.debug(f"Domain classification for text: {text[:100]}...")
            logging.debug(f"Strict result: {strict_result.get('primary_domain')} (conf: {strict_result.get('domain_confidence', 0):.2f})")
            logging.debug(f"Loose result: {loose_result.get('primary_domain')} (conf: {loose_result.get('domain_confidence', 0):.2f})")
        
        # Combine results - take superset
        combined_domains = {}
        
        # Start with strict results
        for domain, data in strict_result.get("all_domains", {}).items():
            combined_domains[domain] = data.copy()
        
        # Add/merge loose results
        for domain, data in loose_result.get("all_domains", {}).items():
            if domain in combined_domains:
                # Merge: combine scores, keywords, take higher confidence
                combined_domains[domain]["score"] += data["score"]
                combined_domains[domain]["matched_keywords"].extend(data["matched_keywords"])
                combined_domains[domain]["matched_keywords"] = list(set(combined_domains[domain]["matched_keywords"]))
                combined_domains[domain]["confidence"] = max(combined_domains[domain]["confidence"], data["confidence"])
            else:
                # New domain from loose matching
                combined_domains[domain] = data.copy()

        # Apply domain validation - check if matches make sense
        validated_domains = self._validate_domain_matches(text, combined_domains, metadata)
        
        # Determine primary domain from combined results
        primary_domain = None
        primary_confidence = 0.0
        
        if validated_domains:
            sorted_domains = sorted(validated_domains.items(), 
                                key=lambda x: (x[1]["confidence"], x[1]["score"]), 
                                reverse=True)
            primary_domain = sorted_domains[0][0]
            primary_confidence = sorted_domains[0][1]["confidence"]
        
        return {
            "primary_domain": primary_domain,
            "domain_confidence": primary_confidence,
            "all_domains": validated_domains,
            "matched_keywords": validated_domains.get(primary_domain, {}).get("matched_keywords", [])
        }

    def _validate_domain_matches(self, text: str, domains: Dict, metadata: Dict = None) -> Dict:
        """Validate that domain matches make contextual sense."""
        validated_domains = {}
        text_lower = text.lower()
        
        for domain, domain_data in domains.items():
            # Get original confidence and score
            original_confidence = domain_data["confidence"]
            original_score = domain_data["score"]
            matched_keywords = domain_data["matched_keywords"]
            
            # Apply validation rules
            validation_multiplier = 1.0
            
            # Rule 1: Laboratory domain validation
            if domain == "laboratory":
                # Must have actual lab test names or values, not just generic terms
                specific_lab_indicators = [
                    "hematology", "chemistry", "urinalysis", "glucose", "hemoglobin", 
                    "creatinine", "alt", "ast", "bilirubin", "wbc", "platelet",
                    "lab values", "lab results", "laboratory results"
                ]
                
                has_specific_lab = any(indicator in text_lower for indicator in specific_lab_indicators)
                has_generic_only = any(keyword in ["laboratory", "lab"] for keyword in matched_keywords)
                
                if not has_specific_lab and has_generic_only:
                    # Only generic "lab" mentions without specific tests
                    validation_multiplier *= 0.3  # Heavy penalty
                elif has_specific_lab:
                    # Has actual lab-specific content
                    validation_multiplier *= 1.2  # Slight boost
            
            # Rule 2: Adverse events validation
            elif domain == "adverse_events":
                # Should have actual AE terms, not just generic safety
                specific_ae_indicators = [
                    "adverse event", "serious adverse", "treatment emergent", "sae", "teae",
                    "system organ class", "preferred term", "toxicity"
                ]
                
                has_specific_ae = any(indicator in text_lower for indicator in specific_ae_indicators)
                if not has_specific_ae and len(matched_keywords) < 3:
                    validation_multiplier *= 0.7  # Moderate penalty
            
            # Rule 3: Demographics validation
            elif domain == "demographics":
                # Should have actual demographic terms
                specific_demo_indicators = [
                    "baseline characteristics", "demographics", "age", "sex", "race", 
                    "weight", "height", "bmi"
                ]
                
                has_specific_demo = any(indicator in text_lower for indicator in specific_demo_indicators)
                if not has_specific_demo and len(matched_keywords) < 2:
                    validation_multiplier *= 0.5
            
            # Rule 4: Length-based validation
            # Very short text with many matches is suspicious
            text_length = len(text.split())
            if text_length < 20 and len(matched_keywords) > 3:
                validation_multiplier *= 0.6
            
            # Rule 5: Check against title/metadata for consistency
            if metadata:
                title = (metadata.get("title") or "").lower()
                if title:
                    # Title should support the domain classification
                    title_supports_domain = any(keyword in title for keyword in matched_keywords)
                    if not title_supports_domain and original_confidence > 0.7:
                        validation_multiplier *= 0.8
            
            # Apply validation multiplier
            validated_confidence = min(original_confidence * validation_multiplier, 1.0)
            validated_score = original_score * validation_multiplier
            
            # Only include domains that still have reasonable confidence after validation
            if validated_confidence > 0.2:  # Minimum threshold after validation
                validated_domains[domain] = {
                    "score": validated_score,
                    "matched_keywords": matched_keywords,
                    "confidence": validated_confidence,
                    "unique_matches": domain_data["unique_matches"],
                    "validation_multiplier": validation_multiplier  # For debugging
                }
        
        return validated_domains
        
    def _classify_clinical_domain_strict(self, text: str) -> Dict[str, Any]:
        """FIXED: Strict matching with word boundaries and improved pattern matching."""
        text_lower = text.lower()
        
        domain_scores = {}
        
        for domain, keywords in self._clinical_domains.items():
            score = 0
            matched_keywords = []
            unique_matches = 0
            
            for keyword in keywords:
                # FIXED: Handle regex patterns properly
                try:
                    if keyword.startswith('r"') or '\\b' in keyword or '[' in keyword:
                        # This is a regex pattern
                        matches = len(re.findall(keyword, text_lower, re.IGNORECASE))
                    else:
                        # Simple string - add word boundaries
                        pattern = rf'\b{re.escape(keyword)}\b'
                        matches = len(re.findall(pattern, text_lower, re.IGNORECASE))
                    
                    if matches > 0:
                        weighted_score = 1 + (matches - 1) * 0.3
                        score += weighted_score
                        matched_keywords.append(keyword)
                        unique_matches += 1
                        
                except re.error:
                    # Fallback for problematic patterns
                    if keyword.lower() in text_lower:
                        score += 1
                        matched_keywords.append(keyword)
                        unique_matches += 1
            
            if score > 0:
                # Calculate confidence
                confidence = self._calculate_domain_confidence(
                    domain, unique_matches, score, len(keywords), len(text.split())
                )
                
                domain_scores[domain] = {
                    "score": score,
                    "matched_keywords": matched_keywords,
                    "confidence": confidence,
                    "unique_matches": unique_matches
                }
        
        # Primary domain selection
        primary_domain = None
        primary_confidence = 0.0
        
        if domain_scores:
            sorted_domains = sorted(domain_scores.items(), 
                                key=lambda x: (x[1]["confidence"], x[1]["score"]), 
                                reverse=True)
            primary_domain = sorted_domains[0][0]
            primary_confidence = sorted_domains[0][1]["confidence"]
        
        return {
            "primary_domain": primary_domain,
            "domain_confidence": primary_confidence,
            "all_domains": domain_scores,
            "matched_keywords": domain_scores.get(primary_domain, {}).get("matched_keywords", [])
        }

    def _classify_clinical_domain_loose(self, text: str) -> Dict[str, Any]:
        """FIXED: Loose matching with better handling of regex patterns."""
        text_lower = text.lower()
        
        domain_scores = {}
        
        for domain, keywords in self._clinical_domains.items():
            score = 0
            matched_keywords = []
            unique_matches = 0
            
            for keyword in keywords:
                try:
                    # FIXED: Handle regex patterns in loose matching too
                    if keyword.startswith('r"') or '\\b' in keyword or '[' in keyword:
                        # Remove word boundaries for loose matching
                        loose_pattern = keyword.replace(r'\b', '')
                        matches = len(re.findall(loose_pattern, text_lower, re.IGNORECASE))
                        if matches > 0:
                            score += matches
                            matched_keywords.append(keyword)
                            unique_matches += 1
                    else:
                        # Simple string matching
                        if keyword.lower() in text_lower:
                            score += 1
                            matched_keywords.append(keyword)
                            unique_matches += 1
                            
                except re.error:
                    # Fallback for problematic patterns
                    if keyword.lower() in text_lower:
                        score += 1
                        matched_keywords.append(keyword)
                        unique_matches += 1
            
            if score > 0:
                # Same confidence calculation as strict, but slightly lower
                confidence = self._calculate_domain_confidence(
                    domain, unique_matches, score, len(keywords), len(text.split())
                )
                
                domain_scores[domain] = {
                    "score": score,
                    "matched_keywords": matched_keywords,
                    "confidence": confidence,
                    "unique_matches": unique_matches
                }
        
        # Primary domain selection
        primary_domain = None
        primary_confidence = 0.0
        
        if domain_scores:
            sorted_domains = sorted(domain_scores.items(), 
                                key=lambda x: (x[1]["confidence"], x[1]["score"]), 
                                reverse=True)
            primary_domain = sorted_domains[0][0]
            primary_confidence = sorted_domains[0][1]["confidence"]
        
        return {
            "primary_domain": primary_domain,
            "domain_confidence": primary_confidence,
            "all_domains": domain_scores,
            "matched_keywords": domain_scores.get(primary_domain, {}).get("matched_keywords", [])
        }

    def _calculate_domain_confidence(self, domain: str, unique_matches: int, total_score: float, 
                                        total_keywords: int, text_length: int) -> float:
        """ Confidence calculation focused on practical results. """
        
        # Start with score-based confidence
        confidence = 0.0
        
        if total_score >= 15:       # Very strong match
            confidence = 0.9
        elif total_score >= 10:     # Strong match  
            confidence = 0.8
        elif total_score >= 5:      # Good match
            confidence = 0.7
        elif total_score >= 3:      # Moderate match
            confidence = 0.6
        elif total_score >= 1:      # Weak match
            confidence = 0.4
        
        # Adjust for number of unique matches
        if unique_matches >= 5:
            confidence = min(confidence + 0.1, 1.0)  # 0.9 + 0.1 = 1.0
        elif unique_matches >= 3:
            confidence = min(confidence + 0.05, 1.0)
        elif unique_matches == 1:
            confidence *= 0.8  # Single match is less reliable
        
        # Domain-specific boosts
        if domain in ['adverse_events', 'demographics'] and unique_matches >= 3:
            confidence = min(confidence + 0.1, 1.0)  # Additional boost for domains with many key words
        
        return confidence

    def _combine_tlf_results(self, pattern_result: Dict, structure_result: Dict, 
                           domain_result: Dict, llm_result: Optional[Dict], node_index: int) -> Dict[str, Any]:
        """ Result combination """
        
        # Start with pattern results
        metadata = {
            # Core TLF metadata
            "tlf_type": pattern_result.get("tlf_type"),
            "output_number": pattern_result.get("output_number"),
            "title": pattern_result.get("title"),
            "population": pattern_result.get("population"),
            "treatment_groups": pattern_result.get("treatment_groups", []),
            
            # Domain results
            "clinical_domain": domain_result.get("primary_domain"),
            "domain_confidence": domain_result.get("domain_confidence", 0.0),
            "matched_keywords": domain_result.get("matched_keywords", []),
            "all_clinical_domains": domain_result.get("all_domains", {}),
            
            # Structure information
            "content_type": self._determine_content_type(structure_result),
            "is_header": structure_result.get("is_header", False),
            "is_data_content": structure_result.get("is_data", False),
            "is_footnote": structure_result.get("is_footnote", False),
            
            # Page and document context
            "page_info": structure_result.get("page_info", {}),
            "sponsor_info": structure_result.get("sponsor_info", {}),
            
            # Detection metadata
            "detection_method": pattern_result.get("method", "pattern"),
            "pattern_confidence": pattern_result.get("confidence", 0.0),
            "structure_confidence": structure_result.get("structure_confidence", 0.0),
            "overall_confidence": 0.0,  # Will be calculated below
            
            # Context
            "node_position": node_index,
            "current_tlf_context": self._current_tlf,
            "tlf_transitions": len(self._tlf_history)
        }
        
        # Override with LLM results if available and confident (but preserve title if LLM doesn't have one)
        if llm_result and llm_result.get("confidence", 0) > 0.7:
            for key in ["tlf_type", "output_number", "clinical_domain", "population", "treatment_groups"]:
                if llm_result.get(key):
                    metadata[key] = llm_result[key]
        
            # Only override title if LLM has one and current doesn't, OR if LLM is very confident
            llm_title = llm_result.get("title")
            current_title = metadata.get("title")
            
            if llm_title and (not current_title or llm_result.get("confidence", 0) > 0.9):
                metadata["title"] = llm_title
            
            metadata["detection_method"] = "pattern+llm"
            metadata["llm_confidence"] = llm_result.get("confidence", 0.0)
        
        # Calculate overall confidence
        metadata["overall_confidence"] = self._calculate_overall_confidence(
            pattern_result, structure_result, domain_result, llm_result
        )
        
        # Inheritance logic that preserves domain classifications
        if (metadata["overall_confidence"] < self._confidence_threshold and 
            self._current_tlf and not metadata["is_header"]):
            
            # Only inherit missing TLF metadata, preserve domain classification
            metadata["tlf_type"] = metadata["tlf_type"] or self._current_tlf.get("tlf_type")
            metadata["output_number"] = metadata["output_number"] or self._current_tlf.get("output_number")
            metadata["population"] = metadata["population"] or self._current_tlf.get("population")
            
            # Only inherit title if we didn't find one
            if not metadata["title"]:
                metadata["title"] = self._current_tlf.get("title")
                
            # Only inherit clinical domain if none was detected
            if not metadata["clinical_domain"]:
                metadata["clinical_domain"] = self._current_tlf.get("clinical_domain")
            
            metadata["detection_method"] += "_inherited"
        
        return metadata

    def _update_tlf_context(self, metadata: Dict, node_index: int):
        """Handles chunk overlaps within a table."""
        """ENHANCED: Better context update with TOC handling and transition detection."""
    
        # Never update context with TOC information
        if self._is_table_of_contents(metadata.get("text", ""), metadata):
            return  # Skip TOC entirely for context updates
        
        confidence = metadata.get("overall_confidence", 0.0)
        
        # Check if this represents a genuine TLF transition
        should_update = False
        
        if metadata.get("is_header"):
            # Header updates - but be more selective
            if (metadata.get("output_number") and 
                metadata.get("tlf_type") and
                confidence > 0.6):
                
                # Check if this is genuinely new
                if self._detect_tlf_transition(metadata, self._current_tlf):
                    should_update = True
                    
        elif confidence >= self._confidence_threshold and not metadata.get("is_footnote"):
            # High confidence content that might indicate new TLF
            if self._detect_tlf_transition(metadata, self._current_tlf):
                should_update = True
        
        if should_update:
            new_tlf = {
                "tlf_type": metadata.get("tlf_type"),
                "output_number": metadata.get("output_number"),
                "title": metadata.get("title"),
                "population": metadata.get("population"),
                "clinical_domain": metadata.get("clinical_domain"),
                "treatment_groups": metadata.get("treatment_groups", []),
                "node_index": node_index  # Track where this context started
            }
            
            # Additional validation - don't update with incomplete information
            # unless we have strong indicators
            required_fields = sum(1 for field in ["tlf_type", "output_number", "title"] 
                                if new_tlf.get(field))
            
            if required_fields >= 2 or confidence > 0.8:
                self._current_tlf = new_tlf
                self._tlf_confidence = confidence
                self._tlf_history.append((self._current_tlf.copy(), confidence, node_index))

    def _determine_title_source(self, pattern_result: Dict, best_header: Dict, final_metadata: Dict) -> str:
        """Helper method to track where the final title came from for debugging."""
        
        final_title = final_metadata.get('title')
        if not final_title:
            return 'none_found'
        
        pattern_title = pattern_result.get('title')
        header_title = best_header.get('title') if best_header else None
        
        if header_title and final_title == header_title:
            return 'flexible_header'
        elif pattern_title and final_title == pattern_title:
            return 'pattern_detection'
        elif self._current_tlf and final_title == self._current_tlf.get('title'):
            return 'inherited_context'
        else:
            return 'unknown_source'

    # Rest of the methods with key fixes
    def _extract_output_number(self, text: str) -> Optional[str]:
        """Extract output number from text."""
    
        # Don't extract from TOC content at all
        if self._is_table_of_contents(text):
            return None
        
        # Only look in first few lines for headers
        lines = text.split('\n')[:4]  # Only first 4 lines
        header_text = '\n'.join(lines).strip()
        
        # Pattern 1: Explicit table/listing/figure headers (highest confidence)
        explicit_patterns = [
            r'(?:table|listing|figure)\s+(\d+(?:\.\d+){1,4})(?:\s|$|:|\n)',
            r'(?:t|l|f)-(\d+(?:\.\d+){1,4})(?:\s|$|:|\n)'
        ]
        
        for pattern in explicit_patterns:
            match = re.search(pattern, header_text, re.IGNORECASE)
            if match:
                number = match.group(1)
                # Validate format (not too many parts, reasonable length)
                parts = number.split('.')
                if 2 <= len(parts) <= 5 and all(len(part) <= 3 and part.isdigit() for part in parts):
                    return number
        
        # Pattern 2: Header-like context (medium confidence)
        # Only if it's clearly at the start and followed by descriptive text
        first_line = lines[0].strip() if lines else ""
        standalone_match = re.match(r'^(\d+(?:\.\d+){1,4})(?:\s|$)', first_line)
        if standalone_match:
            number = standalone_match.group(1)
            parts = number.split('.')
            
            # Very restrictive for standalone - must look like section numbering
            if (2 <= len(parts) <= 4 and 
                all(len(part) <= 2 and part.isdigit() for part in parts) and
                len(first_line) < 20):  # Short line suggesting it's a header
                return number
        
        return None


    def _extract_title(self, text: str) -> Optional[str]:
        """FIXED: Extract the title from text with improved filtering."""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        if not lines:
            return None
        
        # Look for title-like patterns
        for i, line in enumerate(lines[:5]):  # Check first 5 lines
            # Skip lines that look like headers or metadata
            if any(x in line.lower() for x in ['page', 'protocol', 'sponsor', 'date', 'confidential']):
                continue
            
            # Skip lines that are too short or too long
            if len(line) < 10 or len(line) > 200:
                continue
            
            # Skip lines that look like output numbers only (Table 9.1.5.1)
            if re.match(r"^(?:table|listing|figure)?\s*\d+(?:\.\d+)*\s*", line, re.IGNORECASE):
                continue
                
            # Skip population lines in parentheses (Safety Analysis Set)
            if re.match(r"^\([^)]*(?:analysis|population|set|safety|itt|pp|fas)[^)]*\)\s*", line, re.IGNORECASE):
                continue
                
            # Skip date-like patterns (common in table headers)
            if re.search(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b", line):
                continue
                
            # Skip lines that look like column headers with mostly single words or abbreviations
            words = line.split()
            if len(words) > 2 and all(len(word) <= 4 or word.isupper() for word in words):
                continue
                
            # Skip lines with lots of numbers (likely data rows)
            if len(re.findall(r'\d+', line)) > len(words) * 0.5:
                continue
            
            # This could be a title - must have meaningful content
            if len(line.split()) >= 3:  # At least 3 words
                # Additional check: should contain common title words
                title_indicators = ['summary', 'analysis', 'disposition', 'overview', 'results', 
                                'listing', 'table', 'figure', 'by', 'of', 'and', 'for', 'demographic', 
                                'baseline', 'characteristics', 'adverse', 'events', 'treatment']
                if any(indicator in line.lower() for indicator in title_indicators):
                    return line
            
            # Even without title indicators, if it's a standalone descriptive line, it might be a title
            if (len(words) >= 2 and len(words) <= 8 and 
                not any(char.isdigit() for char in line) and  # No numbers
                ('&' in line or 'and' in line.lower())):  # Contains connecting words
                return line
        
        return None

    def _extract_population(self, text: str) -> Optional[str]:
        """Extract analysis population."""
        text_lower = text.lower()
        
        for pop_type, patterns in self._population_patterns.items():
            for pattern in patterns:
                if re.search(rf'\b{pattern}\b', text_lower):
                    return pop_type.upper()
        
        return None

    def _extract_treatment_groups(self, text: str) -> List[str]:
        """Extract treatment groups mentioned in text."""
        text_lower = text.lower()
        groups = []
        
        # Look for dose level patterns
        dose_level_matches = re.findall(r'dose\s+level\s+\d+(?:\s*\([^)]+\))?', text_lower)
        groups.extend(dose_level_matches)
        
        # Look for dose mentions with units including per area (mg/m2, mg/kg, etc.)
        dose_matches = re.findall(r'\d+(?:\.\d+)?\s*(?:mg|μg|mcg|g)(?:/\w+\d*)?', text_lower)
        groups.extend(dose_matches)
        
        # Look for "No Treatment" or similar control groups
        if re.search(r'\bno\s+treatment\b', text_lower):
            groups.append('no treatment')
        
        # Look for placebo/control
        if re.search(r'\bplacebo\b', text_lower):
            groups.append('placebo')
        if re.search(r'\bcontrol\b', text_lower):
            groups.append('control')
        
        # Look for "Overall" summaries
        if re.search(r'\boverall\b', text_lower):
            groups.append('overall')
        
        # Look for cohort/arm mentions
        cohort_matches = re.findall(r'(?:cohort|arm)\s+[a-z0-9]+', text_lower)
        groups.extend(cohort_matches)
        
        # Look for sample size indicators (N=X) and extract the group they belong to
        n_pattern = r'([^()\n]+)\s*\(n=\d+\)'
        n_matches = re.findall(n_pattern, text_lower)
        for match in n_matches:
            clean_match = match.strip()
            if clean_match and len(clean_match) > 2:  # Avoid very short matches
                groups.append(clean_match)
        
        return list(set(groups))

    def _is_likely_header(self, text: str) -> bool:
        """Determine if text looks like a header section."""
        text_lower = text.lower()
        
        # Header indicators
        header_indicators = [
            'protocol', 'sponsor', 'table', 'listing', 'figure',
            'page', 'of', 'date', 'population', 'confidential'
        ]
        
        # Count indicators
        indicator_count = sum(1 for indicator in header_indicators if indicator in text_lower)
        
        # Short text with multiple indicators likely header
        if len(text.split()) < 50 and indicator_count >= 2:
            return True
        
        # Look for specific header patterns
        if re.search(r'(?:table|listing|figure)\s+\d+', text_lower):
            return True
        
        if re.search(r'page\s+\d+\s+of\s+\d+', text_lower):
            return True
        
        return False

    def _is_likely_data(self, text: str) -> bool:
        """Determine if text looks like data content."""
        # Look for tabular data indicators
        has_numbers = bool(re.search(r'\b\d+(?:\.\d+)?\b', text))
        has_percentages = bool(re.search(r'\d+(?:\.\d+)?%', text))
        has_statistical = bool(re.search(r'\b(?:mean|median|std|n=|95%\s*ci|min|max)\b', text, re.IGNORECASE))
        
        # Count data-like elements
        data_score = sum([has_numbers, has_percentages, has_statistical])
        
        return data_score >= 2

    def _is_likely_footnote(self, text: str) -> bool:
        """Determine if text looks like footnotes."""
        text_lower = text.lower().strip()
        
        # Early return for very short text that's unlikely to be footnotes
        if len(text_lower) < 5:
            return False
        
        # Footnote patterns
        footnote_patterns = [
            r'^notes?:', r'^\d+\.?\s', r'^\*+\s', r'^†\s', r'^‡\s',
            r'^abbreviations?:', r'^source:', r'^ci\s*=', r'^n\s*=',
            r'^data\s+cutoff', r'^program:', r'^produced\s+on'
        ]
        
        # Check for explicit footnote indicators
        explicit_match = any(re.search(pattern, text_lower) for pattern in footnote_patterns)
        if explicit_match:
            return True
        
        # Check for footnote-like content characteristics
        lines = text.strip().split('\n')
        
        # Multiple short lines with definitions/explanations
        if len(lines) > 1:
            short_definition_lines = sum(1 for line in lines 
                                       if 10 < len(line) < 80 and '=' in line)
            if short_definition_lines >= 2:
                return True
        
        # Single line with typical footnote content
        footnote_keywords = ['abbreviation', 'definition', 'note', 'source', 'produced', 
                           'program', 'cutoff', 'ci =', 'n =']
        keyword_matches = sum(1 for keyword in footnote_keywords if keyword in text_lower)
        
        # Don't classify regular data content as footnotes
        if keyword_matches >= 1 and not self._is_likely_data(text):
            return True
        
        return False

    def _extract_page_info(self, text: str) -> Dict[str, Any]:
        """Extract page information."""
        page_match = re.search(r'page\s+(\d+)\s+of\s+(\d+)', text, re.IGNORECASE)
        if page_match:
            return {
                "current_page": int(page_match.group(1)),
                "total_pages": int(page_match.group(2))
            }
        return {}

    def _extract_sponsor_info(self, text: str) -> Dict[str, Any]:
        """Extract sponsor and protocol information."""
        info = {}
        
        # Extract sponsor            
        match = re.search(r'sponsor[:\s]+([^\n\r]+)', text, re.IGNORECASE)
        if not match:
            match = re.search(r'(Jazz Pharmaceuticals|Zymeworks|Chimerix)', text, re.IGNORECASE)

        if match:
            info["sponsor"] = match.group(1).strip()
        
        # Extract protocol
        protocol_match = re.search(r'protocol[:\s#]*([a-zA-Z0-9\-_]+)', text, re.IGNORECASE)
        if protocol_match:
            info["protocol"] = protocol_match.group(1).strip()
        
        return info

    def _detect_tlf_transition(self, current_metadata: Dict, previous_context: Dict) -> bool:
        """Detect when we've transitioned to a new TLF output."""
        
        if not previous_context:
            return True  # First output
        
        current_output = current_metadata.get("output_number")
        current_title = current_metadata.get("title") or ""
        current_title = current_title.lower()
        current_type = current_metadata.get("tlf_type")
        
        previous_output = previous_context.get("output_number") 
        previous_title = previous_context.get("title") or ""
        previous_title = previous_title.lower()
        previous_type = previous_context.get("tlf_type")
        
        # Clear transition indicators
        if current_output and previous_output and current_output != previous_output:
            return True
        
        if current_title and previous_title and current_title != previous_title:
            # Check for substantial title difference (not just minor variations)
            if len(current_title) > 10 and len(previous_title) > 10:
                common_words = set(current_title.split()) & set(previous_title.split())
                title_similarity = len(common_words) / max(len(current_title.split()), len(previous_title.split()))
                if title_similarity < 0.4:  # Less than 40% word overlap
                    return True
        
        if current_type and previous_type and current_type != previous_type:
            return True
        
        return False

    def _detect_page_boundary_and_headers(self, text: str) -> Dict[str, Any]:
        """
        Detect page boundaries and extract headers that might be split across chunks.
        
        A chunk might contain:
        - End of previous page + start of new page
        - Middle of a page
        - Complete page
        """
        
        # Look for page boundary indicators
        boundary_patterns = [
            # Page numbers (most reliable)
            r'page\s+\d+\s+of\s+\d+',
            # Protocol patterns (flexible for different sponsors)
            r'protocol\s+[a-zA-Z0-9\-_]{3,20}',
            # Company/sponsor patterns (generic)
            r'(?:pharmaceuticals?|jazz|biotech|therapeutics?|inc\.?|ltd\.?|corp\.?)',
            # Document type patterns
            r'(?:clinical\s+study\s+report|interim\s+analysis|final\s+report|safety\s+report)',
            # Confidentiality markers
            r'confidential|proprietary',
            # Date cutoff patterns
            r'(?:data\s+)?cut[\-\s]*off|as\s+of\s+\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}'
        ]
        
        # Split text into lines for analysis
        lines = text.split('\n')
        
        # Find potential page boundaries (where new headers start)
        page_boundaries = []
        for i, line in enumerate(lines):
            line_clean = ' '.join(line.split()).lower()  # Normalize whitespace
            
            # Score line based on boundary indicators
            boundary_score = 0
            matched_patterns = []
            
            for pattern in boundary_patterns:
                if re.search(pattern, line_clean, re.IGNORECASE):
                    boundary_score += 1
                    matched_patterns.append(pattern)
            
            # If line has multiple boundary indicators, likely a page boundary
            if boundary_score >= 2 or re.search(r'page\s+\d+\s+of\s+\d+', line_clean):
                page_boundaries.append({
                    'line_index': i,
                    'score': boundary_score,
                    'patterns': matched_patterns,
                    'text': line.strip()
                })
        
        # Extract headers from each boundary region
        headers_found = []
        
        for boundary in page_boundaries:
            boundary_idx = boundary['line_index']
            # Look at wider range around boundary
            start_idx = max(0, boundary_idx - 3)
            end_idx = min(len(lines), boundary_idx + 12)  # Generous range for headers
            
            header_section = lines[start_idx:end_idx]
            header_info = self._extract_flexible_header(header_section, boundary)
            
            if header_info['has_header_content']:
                headers_found.append(header_info)
        
        # If no clear boundaries found, scan entire chunk for header patterns
        if not headers_found:
            # Look for TLF patterns anywhere in first portion of text
            header_info = self._extract_flexible_header(lines[:20], None)
            if header_info['has_header_content']:
                headers_found.append(header_info)
        
        return {
            'page_boundaries': page_boundaries,
            'headers_found': headers_found,
            'has_new_page': len(page_boundaries) > 0
        }

    def _extract_header_from_section(self, lines: List[str], boundary_info: Dict = None) -> Dict[str, Any]:
        """
        Extract TLF header information from a section of lines.
        """
        
        header_info = {
            'has_header_content': False,
            'tlf_type': None,
            'output_number': None,
            'title': None,
            'population': None,
            'confidence': 0.0,
            'header_lines': [],
            'document_context': {},
            'boundary_info': boundary_info
        }
        
        # Clean and filter lines
        clean_lines = [line.strip() for line in lines if line.strip()]
        
        if len(clean_lines) < 2:
            return header_info
        
        # Track what we find
        found_components = {
            'protocol_line': None,
            'tlf_line': None, 
            'title_lines': [],
            'population_line': None,
            'document_context': {}
        }
        
        # Scan all lines for header components
        for i, line in enumerate(clean_lines):
            line_lower = line.lower()
            line_normalized = ' '.join(line.split())  # Normalize whitespace
            
            # Skip obvious page headers/footers (but extract useful info)
            if self._is_page_header_footer(line_lower):
                self._extract_document_context(line_normalized, found_components['document_context'])
                continue
            
            # 1. Protocol identification (flexible)
            protocol_match = re.search(r'protocol\s+([a-zA-Z0-9\-_]{3,20})', line_lower)
            if protocol_match and not found_components['protocol_line']:
                found_components['protocol_line'] = i
                found_components['document_context']['protocol'] = protocol_match.group(1)
                header_info['has_header_content'] = True
                continue
            
            # 2. TLF identification (flexible - same line or separate)
            tlf_patterns = [
                # Standard format: "Table 9.1.1"
                r'(table|listing|figure)\s+(\d+(?:\.\d+){1,5})',
                # With title on same line: "Table 9.1.1: Participant Disposition"  
                r'(table|listing|figure)\s+(\d+(?:\.\d+){1,5})\s*[:\-]\s*(.+)',
                # Abbreviated: "T-9.1.1" or "L-14.2.1"
                r'([tlf])[\-\s](\d+(?:\.\d+){1,5})',
            ]
            
            for pattern in tlf_patterns:
                tlf_match = re.search(pattern, line_lower)
                if tlf_match:
                    found_components['tlf_line'] = i
                    
                    # Extract type and number
                    tlf_type = tlf_match.group(1)
                    if tlf_type in ['t', 'l', 'f']:
                        type_map = {'t': 'table', 'l': 'listing', 'f': 'figure'}
                        header_info['tlf_type'] = type_map[tlf_type]
                    else:
                        header_info['tlf_type'] = tlf_type
                    
                    header_info['output_number'] = tlf_match.group(2)
                    
                    # Check if title is on same line
                    if len(tlf_match.groups()) > 2 and tlf_match.group(3):
                        title_on_same_line = tlf_match.group(3).strip()
                        if len(title_on_same_line) > 3:  # Substantial title
                            found_components['title_lines'].append(title_on_same_line)
                    
                    header_info['has_header_content'] = True
                    header_info['header_lines'].append(line)
                    break
            
            # 3. Population identification (flexible)
            population_patterns = [
                r'^\s*\(\s*([^)]{5,50})\s*\)\s*$',  # Standard: (Safety Analysis Set)
                r'^\s*\[\s*([^\]]{5,50})\s*\]\s*$',  # Alternative: [ITT Population]
                # Population mentioned inline
                r'(?:population|analysis\s+set|participants?):\s*([a-z\s]{5,30})',
            ]
            
            for pattern in population_patterns:
                pop_match = re.search(pattern, line_lower)
                if pop_match:
                    found_components['population_line'] = i
                    pop_text = pop_match.group(1).strip()
                    header_info['population'] = self._standardize_population(pop_text)
                    header_info['header_lines'].append(line)
                    break
            
            # 4. Title lines (collect lines between TLF and population, or after TLF)
            if (found_components['tlf_line'] is not None and 
                i > found_components['tlf_line'] and
                (found_components['population_line'] is None or i < found_components['population_line'])):
                
                # Check if this looks like a title line
                if self._is_potential_title_line(line, line_lower):
                    found_components['title_lines'].append(line.strip())
                    header_info['header_lines'].append(line)
        
        # Construct final title
        if found_components['title_lines']:
            # Clean and join title parts
            title_parts = []
            for title_part in found_components['title_lines']:
                cleaned = re.sub(r'[:\-]\s*$', '', title_part.strip())  # Remove trailing colons/dashes
                if len(cleaned) > 2:
                    title_parts.append(cleaned)
            
            if title_parts:
                header_info['title'] = ' '.join(title_parts)
        
        # Store document context
        header_info['document_context'] = found_components['document_context']
        
        # Calculate confidence
        header_info['confidence'] = self._calculate_header_confidence(found_components, header_info)
        
        return header_info

    def _is_page_header_footer(self, line_lower: str) -> bool:
        """Check if line is a page header/footer (contains useful context but not TLF content)."""
        header_footer_indicators = [
            'page ', 'confidential', 'proprietary',
            'clinical study report', 'interim analysis', 'final report',
            'cut-off', 'as of ', 'date:', 'abbreviations', 'note:', 'source:'
        ]
        return any(indicator in line_lower for indicator in header_footer_indicators)

    def _extract_document_context(self, line: str, context_dict: Dict):
        """Extract useful document context from header/footer lines."""
        
        # Page numbers
        page_match = re.search(r'page\s+(\d+)\s+of\s+(\d+)', line.lower())
        if page_match:
            context_dict['current_page'] = int(page_match.group(1))
            context_dict['total_pages'] = int(page_match.group(2))
        
        # Data cutoff dates
        date_patterns = [
            r'cut[\-\s]*off[:\s]+(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})',
            r'as\s+of\s+(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})',
            r'data\s+as\s+of[:\s]+(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})'
        ]
        
        for pattern in date_patterns:
            date_match = re.search(pattern, line.lower())
            if date_match:
                context_dict['data_cutoff'] = date_match.group(1)
                break
        
        # Document type
        doc_types = [
            'clinical study report', 'interim analysis', 'final report', 
            'safety report', 'efficacy report'
        ]
        for doc_type in doc_types:
            if doc_type in line.lower():
                context_dict['document_type'] = doc_type
                break

    def _is_potential_title_line(self, line: str, line_lower: str) -> bool:
        """Check if a line could be part of a title."""
        
        # Skip if it looks like other header components
        if any(skip in line_lower for skip in [
            'protocol', 'page ', 'confidential', 'cut-off',
            'jazz', 'pharmaceuticals', 'inc.', 'ltd.', 'corp.'
        ]):
            return False
        
        # Skip if it's very short or very long
        words = line.split()
        if len(words) < 2 or len(words) > 15:
            return False
        
        # Skip if it's mostly numbers/symbols
        alpha_chars = sum(1 for c in line if c.isalpha())
        if alpha_chars < len(line) * 0.5:
            return False
        
        # Skip if it looks like data
        if re.search(r'\d+\s*\(\s*\d+', line_lower):  # n (%)
            return False
        
        return True

    def _standardize_population(self, pop_text: str) -> str:
        """Standardize population names to consistent format."""
        
        pop_lower = pop_text.lower().strip()
        
        # Common population mappings
        population_map = {
            'safety analysis set': 'Safety',
            'safety': 'Safety',
            'saf': 'Safety',
            'treated': 'Safety',
            'intention to treat': 'ITT',
            'intent to treat': 'ITT', 
            'itt': 'ITT',
            'modified intention to treat': 'mITT',
            'modified intent to treat': 'mITT',
            'mitt': 'mITT',
            'per protocol': 'PP',
            'pp': 'PP',
            'full analysis set': 'FAS',
            'fas': 'FAS',
            'efficacy evaluable': 'Efficacy Evaluable',
            'pk analysis set': 'PK',
            'pharmacokinetic': 'PK',
            'all screened': 'Screened',
            'screened participants': 'Screened',
            'enrolled': 'Enrolled'
        }
        
        # Check for exact matches first
        if pop_lower in population_map:
            return population_map[pop_lower]
        
        # Check for partial matches
        for key, value in population_map.items():
            if key in pop_lower:
                return value
        
        # If no match, return cleaned original
        return pop_text.title()

    def _calculate_header_confidence(self, found_components: Dict, header_info: Dict) -> float:
        """Calculate confidence score for header detection."""
        
        confidence_score = 0.0
        
        # Core TLF identification (most important)
        if header_info['tlf_type'] and header_info['output_number']:
            confidence_score += 0.5
        
        # Title present
        if header_info['title'] and len(header_info['title']) > 5:
            confidence_score += 0.3
        
        # Population identified
        if header_info['population']:
            confidence_score += 0.1
        
        # Protocol context
        if found_components['document_context'].get('protocol'):
            confidence_score += 0.1
        
        # Bonus for having multiple header components
        component_count = sum(1 for comp in [
            found_components['protocol_line'],
            found_components['tlf_line'],
            found_components['title_lines'],
            found_components['population_line']
        ] if comp is not None or comp)
        
        if component_count >= 3:
            confidence_score += 0.1
        
        return min(confidence_score, 1.0)

    def _calculate_structure_confidence(self, is_header: bool, is_data: bool, is_footnote: bool) -> float:
        """Calculate confidence in structure classification."""
        if is_header:
            return 0.9
        elif is_data:
            return 0.8
        elif is_footnote:
            return 0.7
        else:
            return 0.3

    def _should_inherit_context(self, current_metadata: Dict, chunk_text: str) -> bool:
        """
        Determine inheritance with logic for various content types.
        """
        
        # Never inherit if we found a strong new header with high confidence
        if (current_metadata.get('tlf_type') and 
            current_metadata.get('output_number') and
            current_metadata.get('overall_confidence', 0) > 0.8):
            return False
        
        # Never inherit for TOC
        if current_metadata.get('clinical_domain') == 'table_of_contents':
            return False
        
        # Don't inherit if we have no previous context
        if not self._current_tlf:
            return False
        
        # Always inherit for clear data content
        content_type = current_metadata.get('content_type', '')
        if content_type in ['data', 'footnote']:
            return True
        
        # Inherit if this looks like continuation content
        chunk_lower = chunk_text.lower()
        
        # Strong continuation indicators (statistical/tabular content)
        strong_continuation = [
            'mean (sd)', 'median', 'min, max', '95% ci', 'std dev',
            'analysis set', 'n (%)', 'continued', 'footnote'
        ]
        
        # Statistical/tabular patterns that indicate data content
        statistical_patterns = [
            r'\d+\s*\(\s*\d+\.\d+%?\s*\)',  # n (x.x%) or n (x.x)
            r'\d+\.\d+\s*\(\s*\d+\.\d+\s*\)',  # Mean (SD)
            r'\b\d+\.\d+\s*,\s*\d+\.\d+\b',  # Min, Max pairs
            r'\b\d+\.\d+\s+\d+\.\d+\s*\(',  # Multiple numeric values
            r'objective\s+disease\s+progression',  # Clinical terms
            r'lost\s+to\s+follow\s+up',
            r'study\s+enrollment\s+closed'
        ]
        
        continuation_score = 0
        
        # Count text-based indicators
        continuation_score += sum(1 for indicator in strong_continuation 
                                if indicator in chunk_lower)
        
        # Count pattern-based indicators  
        continuation_score += sum(1 for pattern in statistical_patterns
                                if re.search(pattern, chunk_text))
        
        # Additional scoring for obvious data content
        # Look for multiple numeric values (common in tables)
        numeric_values = len(re.findall(r'\b\d+(?:\.\d+)?\b', chunk_text))
        if numeric_values > 10:  # Lots of numbers = likely data
            continuation_score += 1
        
        # Look for parenthetical percentages
        pct_patterns = len(re.findall(r'\(\s*\d+(?:\.\d+)?%?\s*\)', chunk_text))
        if pct_patterns > 2:
            continuation_score += 1
        
        # Inherit if strong continuation evidence
        if continuation_score >= 2:
            return True
        
        # Inherit if low confidence and we have previous context
        # BUT not if we detected any header elements (which would suggest new output)
        has_header_elements = (current_metadata.get('tlf_type') or 
                            current_metadata.get('output_number') or 
                            current_metadata.get('is_header', False))
        
        if (current_metadata.get('overall_confidence', 0) < 0.5 and 
            not has_header_elements):
            return True
        
        return False

    def debug_flexible_header_extraction(self, text: str) -> Dict:
        """Debug method to test flexible header extraction."""
        
        lines = text.split('\n')
        page_analysis = self._detect_page_boundary_and_headers(text)
        
        # Test header extraction on entire text
        header_result = self._extract_flexible_header(lines, None)
        
        return {
            'page_boundaries': page_analysis['page_boundaries'],
            'headers_found': page_analysis['headers_found'],
            'direct_header_extraction': header_result,
            'text_lines': lines[:10],  # First 10 lines for inspection
            'flexibility_test': {
                'found_tlf_type': header_result.get('tlf_type'),
                'found_output_number': header_result.get('output_number'),
                'found_title': header_result.get('title'),
                'found_population': header_result.get('population'),
                'document_context': header_result.get('document_context', {}),
                'confidence': header_result.get('confidence', 0)
            }
        }

    def _extract_flexible_header(self, lines: List[str], boundary_info: Dict = None) -> Dict[str, Any]:
        """
        ROBUST: Extract TLF header with flexible patterns for different sponsors/formats.
        
        Handles:
        - Different sponsor names and formats
        - Various document types
        - Output number/title on same line or separate lines
        - Different header arrangements
        """
        
        header_info = {
            'has_header_content': False,
            'tlf_type': None,
            'output_number': None,
            'title': None,
            'population': None,
            'confidence': 0.0,
            'header_lines': [],
            'document_context': {},
            'boundary_info': boundary_info
        }
        
        # Clean and filter lines
        clean_lines = [line.strip() for line in lines if line.strip()]
        
        if len(clean_lines) < 2:
            return header_info
        
        # Track what we find
        found_components = {
            'protocol_line': None,
            'tlf_line': None, 
            'title_lines': [],
            'population_line': None,
            'document_context': {}
        }
        
        # Scan all lines for header components
        for i, line in enumerate(clean_lines):
            line_lower = line.lower()
            line_normalized = ' '.join(line.split())  # Normalize whitespace
            
            # Skip obvious page headers/footers (but extract useful info)
            if self._is_page_header_footer(line_lower):
                self._extract_document_context(line_normalized, found_components['document_context'])
                continue
            
            # 1. Protocol identification (flexible)
            protocol_match = re.search(r'protocol\s+([a-zA-Z0-9\-_]{3,20})', line_lower)
            if protocol_match and not found_components['protocol_line']:
                found_components['protocol_line'] = i
                found_components['document_context']['protocol'] = protocol_match.group(1)
                header_info['has_header_content'] = True
                continue
            
            # 2. TLF identification (flexible - same line or separate)
            tlf_patterns = [
                # Standard format: "Table 9.1.1"
                r'(table|listing|figure)\s+(\d+(?:\.\d+){1,5})',
                # With title on same line: "Table 9.1.1: Summary of xxxxx"  
                r'(table|listing|figure)\s+(\d+(?:\.\d+){1,5})\s*[:\-]\s*(.+)',
                # Abbreviated: "T-9.1.1" or "L-14.2.1"
                r'([tlf])[\-\s](\d+(?:\.\d+){1,5})',
            ]
            
            for pattern in tlf_patterns:
                tlf_match = re.search(pattern, line_lower)
                if tlf_match:
                    found_components['tlf_line'] = i
                    
                    # Extract type and number
                    tlf_type = tlf_match.group(1)
                    if tlf_type in ['t', 'l', 'f']:
                        type_map = {'t': 'table', 'l': 'listing', 'f': 'figure'}
                        header_info['tlf_type'] = type_map[tlf_type]
                    else:
                        header_info['tlf_type'] = tlf_type
                    
                    header_info['output_number'] = tlf_match.group(2)
                    
                    # Check if title is on same line
                    if len(tlf_match.groups()) > 2 and tlf_match.group(3):
                        title_on_same_line = tlf_match.group(3).strip()
                        if len(title_on_same_line) > 3:  # Substantial title
                            found_components['title_lines'].append(title_on_same_line)
                    
                    header_info['has_header_content'] = True
                    header_info['header_lines'].append(line)
                    break
            
            # 3. Population identification (flexible)
            population_patterns = [
                r'^\s*\(\s*([^)]{5,50})\s*\)\s*$',  # Standard: (Safety Analysis Set)
                r'^\s*\[\s*([^\]]{5,50})\s*\]\s*$',  # Alternative: [ITT Population]
                # Population mentioned inline
                r'(?:population|analysis\s+set|participants?):\s*([a-z\s]{5,30})',
            ]
            
            for pattern in population_patterns:
                pop_match = re.search(pattern, line_lower)
                if pop_match:
                    found_components['population_line'] = i
                    pop_text = pop_match.group(1).strip()
                    header_info['population'] = self._standardize_population(pop_text)
                    header_info['header_lines'].append(line)
                    break
            
            # 4. Title lines (collect lines between TLF and population, or after TLF)
            if (found_components['tlf_line'] is not None and 
                i > found_components['tlf_line'] and
                (found_components['population_line'] is None or i < found_components['population_line'])):
                
                # Check if this looks like a title line
                if self._is_potential_title_line(line, line_lower):
                    found_components['title_lines'].append(line.strip())
                    header_info['header_lines'].append(line)
        
        # Construct final title
        if found_components['title_lines']:
            # Clean and join title parts
            title_parts = []
            for title_part in found_components['title_lines']:
                cleaned = re.sub(r'[:\-]\s*$', '', title_part.strip())  # Remove trailing colons/dashes
                if len(cleaned) > 2:
                    title_parts.append(cleaned)
            
            if title_parts:
                header_info['title'] = ' '.join(title_parts)
        
        # Store document context
        header_info['document_context'] = found_components['document_context']
        
        # Calculate confidence
        header_info['confidence'] = self._calculate_header_confidence(found_components, header_info)
        
        return header_info


    async def _llm_tlf_analysis(self, text: str) -> Dict[str, Any]:
        """Use LLM to analyze TLF content."""
        try:
            prompt = self._tlf_classification_prompt.format(text=text[:1500])
            response = await self._llm.acomplete(prompt)
            response_text = response.text
            
            # Parse structured response
            result = {}
            
            patterns = {
                "tlf_type": r'OUTPUT_TYPE:\s*([^\n]+)',
                "output_number": r'OUTPUT_NUMBER:\s*([^\n]+)',
                "title": r'TITLE:\s*([^\n]+)',
                "clinical_domain": r'CLINICAL_DOMAIN:\s*([^\n]+)',
                "population": r'POPULATION:\s*([^\n]+)',
                "treatment_groups": r'TREATMENT_GROUPS:\s*([^\n]+)',
                "confidence": r'CONFIDENCE:\s*([0-9.]+)'
            }
            
            for key, pattern in patterns.items():
                match = re.search(pattern, response_text, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    if key == "confidence":
                        result[key] = float(value) if value else 0.0
                    elif key == "treatment_groups":
                        result[key] = [g.strip() for g in value.split(';') if g.strip() and g.strip().lower() != "unknown"]
                    else:
                        result[key] = value if value.lower() != "unknown" else None
            
            result["method"] = "llm"
            return result
            
        except Exception as e:
            logging.error(f"LLM TLF analysis error: {e}")
            return {"method": "llm_error", "confidence": 0.0}

    def _determine_content_type(self, structure_result: Dict) -> str:
        """Determine the type of content."""
        if structure_result.get("is_header"):
            return "header"
        elif structure_result.get("is_data"):
            return "data"
        elif structure_result.get("is_footnote"):
            return "footnote"
        else:
            return "content"

    def _calculate_overall_confidence(self, pattern_result: Dict, structure_result: Dict, 
                                    domain_result: Dict, llm_result: Optional[Dict]) -> float:
        """Calculate overall confidence score."""
        pattern_conf = pattern_result.get("confidence", 0.0)
        structure_conf = structure_result.get("structure_confidence", 0.0)
        domain_conf = domain_result.get("domain_confidence", 0.0)
        
        # Base confidence from pattern and structure
        base_confidence = (pattern_conf * 0.5) + (structure_conf * 0.3) + (domain_conf * 0.2)
        
        # Boost if LLM agrees
        if llm_result and llm_result.get("confidence", 0) > 0.7:
            llm_conf = llm_result.get("confidence", 0.0)
            base_confidence = (base_confidence * 0.7) + (llm_conf * 0.3)
        
        return min(base_confidence, 1.0)

    def get_tlf_summary(self) -> Dict[str, Any]:
        """Get summary of detected TLF outputs."""
        tlf_types = defaultdict(int)
        domains = defaultdict(int)
        outputs = []
        
        for tlf_data, confidence, position in self._tlf_history:
            if tlf_data.get("tlf_type"):
                tlf_types[tlf_data["tlf_type"]] += 1
            if tlf_data.get("clinical_domain"):
                domains[tlf_data["clinical_domain"]] += 1
            
            outputs.append({
                "type": tlf_data.get("tlf_type"),
                "number": tlf_data.get("output_number"),
                "title": tlf_data.get("title"),
                "domain": tlf_data.get("clinical_domain"),
                "population": tlf_data.get("population"),
                "confidence": confidence,
                "position": position
            })
        
        return {
            "total_tlf_outputs": len(self._tlf_history),
            "tlf_type_distribution": dict(tlf_types),
            "clinical_domain_distribution": dict(domains),
            "detected_outputs": outputs,
            "current_context": self._current_tlf
        }

    # FIXED: Bundle optimization methods
    def _check_cache(self, text: str, node_index: int) -> Optional[Dict[str, Any]]:
        """Check if we've seen similar content before and can reuse metadata."""
        # Create a simple hash of the text for comparison
        text_hash = hash(text.strip()[:200])  # Use first 200 chars for hash
        
        # Check if this exact text was processed recently (within last 20 nodes)
        recent_range = max(0, node_index - 20)
        
        # This is a simple approach - in practice you might want more sophisticated caching
        return None  # For now, let the full processing happen

    def _should_skip_expensive_processing(self, structure_result: Dict, pattern_result: Dict) -> bool:
        """Determine if we can skip expensive processing for this node."""
        # Skip LLM and detailed domain analysis for:
        # 1. Clear headers that match previous headers
        # 2. Clear footnotes 
        # 3. Page headers/footers
        
        if structure_result.get("is_footnote"):
            return True
            
        # If it's a header and we've seen this TLF before, skip detailed analysis
        if (structure_result.get("is_header") and 
            pattern_result.get("output_number") and
            self._is_repeat_header(pattern_result)):
            return True
            
        return False

    def _is_repeat_header(self, pattern_result: Dict) -> bool:
        """Check if this header is a repeat of one we've seen."""
        output_key = (pattern_result.get("tlf_type"), pattern_result.get("output_number"))
        
        if output_key in self._header_cache:
            # We've seen this exact output before
            return True
            
        return False

    def _is_table_of_contents_strict(self, text: str) -> bool:
        """
        Much stricter TOC detection that avoids false positives with regular table content.
        """
        text_lower = text.lower().strip()
        
        # Must explicitly say "table of contents" or very similar
        explicit_indicators = [
            r'\btable\s+of\s+contents\b',
            r'\blist\s+of\s+tables\b', 
            r'\blist\s+of\s+figures\b',
            r'\blist\s+of\s+listings\b',
            r'\bindex\s+of\s+tables\b',
            r'\bindex\s+of\s+figures\b'
            r'\btoc\b'
        ]

        has_explicit = any(re.search(pattern, text_lower) for pattern in explicit_indicators)
        
        if not has_explicit:
            return False

            
        # ADDITIONAL EXCLUSIONS: If it has clinical content, it's NOT a TOC
        # Even if it mentions "table of contents" in a header/footer
        clinical_exclusions = [
            r'mean\s*\(\s*sd\s*\)',
            r'n\s*\(\s*%\s*\)',
            # r'analysis\s+set',
            r'\d+\s*\(\s*\d+\.\d+%\s*\)'  # Statistical data patterns
        ]

        has_clinical_content = any(re.search(pattern, text_lower) for pattern in clinical_exclusions)
    
        if has_clinical_content:
            return False  # Has TOC mention but also clinical content - not a pure TOC
            
        # Additional validation - should have TOC structure
        # Look for multiple entries with dots leading to page numbers
        lines = text.split('\n')
        toc_entry_count = 0
        
        for line in lines:
            # Classic TOC format: "Table 9.1.1 Something Something......Page 1"
            if re.search(r'(?:table|figure|listing)\s+\d+(?:\.\d+)*.*\.{3,}', line.lower()):
                toc_entry_count += 1
        
        # If has explicit TOC mention and no clinical content, it's probably TOC
        # Don't require TOC structure since some TOCs might be formatted differently
        return True

    def _create_optimized_metadata(self, pattern_result: Dict, structure_result: Dict, 
                                 node_index: int) -> Dict[str, Any]:
        """FIXED: Create metadata using cached information and minimal processing."""
        
        # For repeated headers, use cached data
        if structure_result.get("is_header"):
            output_key = (pattern_result.get("tlf_type"), pattern_result.get("output_number"))
            if output_key in self._header_cache:
                cached_metadata = self._header_cache[output_key].copy()
                cached_metadata.update({
                    "node_position": node_index,
                    "detection_method": "cached_header"
                })
                return cached_metadata
        
        # For footnotes, use minimal metadata
        if structure_result.get("is_footnote"):
            return {
                "tlf_type": self._current_tlf.get("tlf_type") if self._current_tlf else None,
                "output_number": self._current_tlf.get("output_number") if self._current_tlf else None,
                "title": self._current_tlf.get("title") if self._current_tlf else None,
                "population": self._current_tlf.get("population") if self._current_tlf else None,
                "treatment_groups": self._current_tlf.get("treatment_groups", []) if self._current_tlf else [],
                "clinical_domain": self._current_tlf.get("clinical_domain") if self._current_tlf else None,
                "domain_confidence": 0.0,
                "matched_keywords": [],
                "all_clinical_domains": {},
                "content_type": "footnote",
                "is_header": False,
                "is_data_content": False,
                "is_footnote": True,
                "page_info": structure_result.get("page_info", {}),
                "sponsor_info": structure_result.get("sponsor_info", {}),
                "detection_method": "optimized_footnote",
                "pattern_confidence": 0.8,
                "structure_confidence": 0.9,
                "overall_confidence": 0.8,
                "node_position": node_index,
                "current_tlf_context": self._current_tlf,
                "tlf_transitions": len(self._tlf_history)
            }
        
        # Fallback to basic inherited metadata
        return self._create_inherited_metadata(pattern_result, structure_result, node_index)

    def _create_inherited_metadata(self, current_metadata: Dict, text: str, node_index: int) -> Dict[str, Any]:
        """
        Create metadata by inheriting TLF context but preserving new domain classification.
        """
        
        # Start with current metadata 
        inherited_metadata = current_metadata.copy()
        
        # Inherit core TLF information from context if available
        if self._current_tlf:
            inherited_metadata.update({
                'tlf_type': inherited_metadata.get('tlf_type') or self._current_tlf.get('tlf_type'),
                'output_number': inherited_metadata.get('output_number') or self._current_tlf.get('output_number'),
                'population': inherited_metadata.get('population') or self._current_tlf.get('population'),
            })
            
            # Smart title inheritance - prefer newly found titles over old ones
            current_title = inherited_metadata.get('title')
            context_title = self._current_tlf.get('title')
            
            if context_title:
                # For inherited nodes, always use the context title (the true table title)
                inherited_metadata['title'] = context_title
            elif current_title:
                # Only use current title if no context exists
                inherited_metadata['title'] = current_title
            
            # Only inherit clinical domain if none was detected in current chunk
            if not inherited_metadata.get('clinical_domain'):
                inherited_metadata['clinical_domain'] = self._current_tlf.get('clinical_domain')
        
        # Update detection method to indicate inheritance
        original_method = inherited_metadata.get('detection_method', 'unknown')
        inherited_metadata['detection_method'] = f"{original_method}_inherited"        
        
        # Adjust confidence - boost if we found new title information
        base_confidence = inherited_metadata.get('overall_confidence', 0)
        if inherited_metadata.get('title') and (not self._current_tlf or not self._current_tlf.get('title')):
            # Found a title where context didn't have one - boost confidence
            base_confidence += 0.3
        
        inherited_metadata['overall_confidence'] = min(base_confidence + 0.2, 0.9)  # Cap at 0.9 for inherited
        
        return inherited_metadata

    def _update_cache(self, metadata: Dict, text: str):
        """Update the caches with processed metadata."""
        if metadata.get("is_header") and metadata.get("overall_confidence", 0) > 0.7:
            output_key = (metadata.get("tlf_type"), metadata.get("output_number"))
            if output_key[0] and output_key[1]:  # Both must be present
                self._header_cache[output_key] = {
                    k: v for k, v in metadata.items() 
                    if k not in ["node_position", "detection_method"]  # Exclude position-specific data
                }

    def reset_context(self):
        """Reset the extraction context (useful for processing new documents)."""
        print(f"Resetting TLF context. Previous context had {len(self._tlf_history)} transitions.")
        self._current_tlf = None
        self._tlf_confidence = 0.0
        self._tlf_history = []
        self._page_context = {}
        if self._enable_bundle_optimization:
            self._header_cache = {}
            self._footnote_cache = {}
            self._last_processed_header = None

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for bundle processing."""
        total_nodes = len(self._tlf_history) if hasattr(self, '_total_processed_nodes') else 0
        cached_headers = len(self._header_cache)
        
        return {
            "total_nodes_processed": total_nodes,
            "cached_headers": cached_headers,
            "optimization_enabled": self._enable_bundle_optimization,
            "cache_hit_potential": f"{cached_headers * 100 / max(total_nodes, 1):.1f}%" if total_nodes > 0 else "0%"
        }

        
    # Additional helper method for debugging
    def get_extraction_debug_info(self) -> Dict[str, Any]:
        """Get debug information about the extraction process."""
        return {
            "current_tlf_context": self._current_tlf,
            "tlf_history_count": len(self._tlf_history),
            "tlf_history": [
                {
                    "tlf_type": tlf.get("tlf_type"),
                    "output_number": tlf.get("output_number"), 
                    "title": tlf.get("title"),
                    "confidence": conf,
                    "node_index": node_idx
                }
                for tlf, conf, node_idx in self._tlf_history
            ],
            "header_cache_size": len(self._header_cache),
            "optimization_enabled": self._enable_bundle_optimization
        }

    def _create_toc_metadata(self, text: str, node_index: int) -> Dict[str, Any]:
        """Create clean TOC metadata with no TLF contamination."""
        return {
            'tlf_type': None,
            'output_number': None, 
            'title': 'Table of Contents',
            'population': None,
            'treatment_groups': [],
            'clinical_domain': 'table_of_contents',
            'domain_confidence': 0.95,
            'matched_keywords': ['table of contents'],
            'all_clinical_domains': {
                'table_of_contents': {
                    'confidence': 0.95,
                    'score': 100,
                    'matched_keywords': ['table of contents'],
                    'unique_matches': 1
                }
            },
            'content_type': 'table_of_contents',
            'is_header': True,
            'is_data_content': False,
            'is_footnote': False,
            'page_info': self._extract_page_info(text),
            'sponsor_info': self._extract_sponsor_info(text),
            'detection_method': 'strict_toc_detection',
            'pattern_confidence': 0.95,
            'structure_confidence': 0.95,
            'overall_confidence': 0.95,
            'node_position': node_index,
            'current_tlf_context': self._current_tlf.copy() if self._current_tlf else None,
            'tlf_transitions': len(self._tlf_history),
            'inheritance_decision': 'toc_special_case'
        }

    def debug_toc_detection(self, text: str) -> Dict:
        """Debug method to test TOC detection on specific text."""
        return {
            "is_toc": self._is_table_of_contents_strict(text),
            "extracted_output_number": self._extract_output_number(text),
            "extracted_title": self._extract_title(text),
            "text_preview": text[:200]
        }


    def debug_chunk_analysis(self, text: str, node_index: int) -> Dict:
        """Debug method to analyze how a specific chunk would be processed."""
        
        page_analysis = self._detect_page_boundary_and_headers(text)
        is_toc = self._is_table_of_contents_strict(text)
        pattern_result = self._detect_tlf_patterns(text)
        
        # Create preliminary metadata to test inheritance logic
        preliminary_metadata = {
            'tlf_type': pattern_result.get('tlf_type'),
            'output_number': pattern_result.get('output_number'),
            'title': pattern_result.get('title'),
            'overall_confidence': pattern_result.get('confidence', 0),
            'clinical_domain': 'test_domain'  # Placeholder
        }
        
        should_inherit = self._should_inherit_context(preliminary_metadata, text)
        
        return {
            'node_index': node_index,
            'is_toc': is_toc,
            'page_analysis': page_analysis,
            'pattern_result': pattern_result,
            'should_inherit': should_inherit,
            'current_context': self._current_tlf,
            'text_preview': text[:300]
        }

    def debug_flexible_header_extraction(self, text: str) -> Dict:
        """Debug method to test flexible header extraction."""
        
        lines = text.split('\n')
        page_analysis = self._detect_page_boundary_and_headers(text)
        
        # Test header extraction on entire text
        header_result = self._extract_flexible_header(lines, None)
        
        return {
            'page_boundaries': page_analysis['page_boundaries'],
            'headers_found': page_analysis['headers_found'],
            'direct_header_extraction': header_result,
            'text_lines': lines[:10],  # First 10 lines for inspection
            'flexibility_test': {
                'found_tlf_type': header_result.get('tlf_type'),
                'found_output_number': header_result.get('output_number'),
                'found_title': header_result.get('title'),
                'found_population': header_result.get('population'),
                'document_context': header_result.get('document_context', {}),
                'confidence': header_result.get('confidence', 0)
            }
        }
    def debug_title_extraction(self, text: str, node_index: int) -> Dict:
        """Debug why title extraction is failing."""
        
        lines = text.split('\n')
        clean_lines = [line.strip() for line in lines if line.strip()]
        
        # Test both the original and flexible title extraction
        original_title = self._extract_title(text)
        
        # Also test the flexible header extraction
        header_result = self._extract_flexible_header(clean_lines, None)
        flexible_title = header_result.get('title')
        
        # Analyze line by line
        line_analysis = []
        
        found_components = {
            'protocol_line': None,
            'tlf_line': None,
            'title_lines': [],
            'population_line': None
        }
        
        for i, line in enumerate(clean_lines[:15]):  # First 15 lines
            line_lower = line.lower()
            line_analysis_item = {
                'line_num': i,
                'text': line,
                'length': len(line),
                'word_count': len(line.split()),
                'is_potential_title': False,
                'skip_reasons': [],
                'line_type': 'unknown'
            }
            
            # Check what type of line this is
            if self._is_page_header_footer(line_lower):
                line_analysis_item['line_type'] = 'header_footer'
                line_analysis_item['skip_reasons'].append('page header/footer')
            
            # Check for protocol
            elif re.search(r'protocol\s+[a-zA-Z0-9\-_]{3,20}', line_lower):
                line_analysis_item['line_type'] = 'protocol'
                found_components['protocol_line'] = i
            
            # Check for TLF
            elif re.search(r'(table|listing|figure)\s+(\d+(?:\.\d+){1,5})', line_lower):
                line_analysis_item['line_type'] = 'tlf_identifier'
                found_components['tlf_line'] = i
            
            # Check for population
            elif re.search(r'^\s*\(\s*([^)]{5,50})\s*\)\s*$', line):
                line_analysis_item['line_type'] = 'population'
                found_components['population_line'] = i
            
            # Check if it could be a title
            else:
                is_title = self._is_potential_title_line(line, line_lower)
                line_analysis_item['is_potential_title'] = is_title
                
                if is_title:
                    line_analysis_item['line_type'] = 'potential_title'
                    # Check if it's in the right position for title
                    if (found_components['tlf_line'] is not None and 
                        i > found_components['tlf_line'] and
                        (found_components['population_line'] is None or i < found_components['population_line'])):
                        found_components['title_lines'].append(line.strip())
                        line_analysis_item['included_in_title'] = True
                    else:
                        line_analysis_item['included_in_title'] = False
                        line_analysis_item['skip_reasons'].append('wrong position for title')
                else:
                    # Why was it not considered a title?
                    if any(skip in line_lower for skip in [
                        'protocol', 'page ', 'confidential', 'cut-off',
                        'pharmaceuticals', 'inc.', 'ltd.', 'corp.'
                    ]):
                        line_analysis_item['skip_reasons'].append('contains excluded terms')
                    
                    words = line.split()
                    if len(words) < 2:
                        line_analysis_item['skip_reasons'].append('too few words')
                    elif len(words) > 15:
                        line_analysis_item['skip_reasons'].append('too many words')
                    
                    alpha_chars = sum(1 for c in line if c.isalpha())
                    if alpha_chars < len(line) * 0.5:
                        line_analysis_item['skip_reasons'].append('too many non-alpha characters')
                    
                    if re.search(r'\d+\s*\(\s*\d+', line_lower):
                        line_analysis_item['skip_reasons'].append('looks like data (n (%))')
            
            line_analysis.append(line_analysis_item)
        
        # Construct what the title should be
        constructed_title = None
        if found_components['title_lines']:
            title_parts = []
            for title_part in found_components['title_lines']:
                cleaned = re.sub(r'[:\-]\s*$', '', title_part.strip())
                if len(cleaned) > 2:
                    title_parts.append(cleaned)
            if title_parts:
                constructed_title = ' '.join(title_parts)
        
        return {
            'node_index': node_index,
            'original_title_method': original_title,
            'flexible_header_title': flexible_title,
            'constructed_title': constructed_title,
            'found_components': found_components,
            'line_analysis': line_analysis,
            'total_lines': len(clean_lines),
            'text_preview': text[:500]
        }

    def debug_specific_node_title(self, node_index: int, doc_nodes: List) -> Dict:
        """Debug title extraction for a specific node."""
        
        if node_index >= len(doc_nodes):
            return {'error': 'Node index out of range'}
        
        node = doc_nodes[node_index]
        text = node.text
        metadata = node.metadata
        
        title_debug = self.debug_title_extraction(text, node_index)
        
        return {
            'node_index': node_index,
            'current_metadata': {
                'tlf_type': metadata.get('tlf_type'),
                'output_number': metadata.get('output_number'),
                'title': metadata.get('title'),
                'population': metadata.get('population')
            },
            'title_debug': title_debug,
            'recommendations': []
        }

    def suggest_title_fixes(self, doc_nodes: List, node_indices: List[int] = None) -> Dict:
        """Suggest fixes for title extraction issues."""
        
        if node_indices is None:
            # Check first 20 nodes for title issues
            node_indices = list(range(min(20, len(doc_nodes))))
        
        results = {
            'nodes_analyzed': len(node_indices),
            'nodes_with_missing_titles': [],
            'common_issues': {},
            'suggested_fixes': []
        }
        
        for node_idx in node_indices:
            if node_idx >= len(doc_nodes):
                continue
                
            node = doc_nodes[node_idx]
            metadata = node.metadata
            
            # Skip TOC nodes
            if metadata.get('clinical_domain') == 'table_of_contents':
                continue
            
            # Check if title is missing
            title = metadata.get('title')
            if not title or title == 'No title':
                title_debug = self.debug_title_extraction(node.text, node_idx)
                
                results['nodes_with_missing_titles'].append({
                    'node_index': node_idx,
                    'tlf_type': metadata.get('tlf_type'),
                    'output_number': metadata.get('output_number'),
                    'debug_info': title_debug
                })
                
                # Analyze common issues
                for line_info in title_debug['line_analysis']:
                    if line_info['is_potential_title'] and not line_info.get('included_in_title', False):
                        for reason in line_info['skip_reasons']:
                            if reason not in results['common_issues']:
                                results['common_issues'][reason] = 0
                            results['common_issues'][reason] += 1
        
        # Generate suggestions based on common issues
        if 'wrong position for title' in results['common_issues']:
            results['suggested_fixes'].append(
                "Title lines are being found but in wrong position - check TLF line detection"
            )
        
        if 'too few words' in results['common_issues']:
            results['suggested_fixes'].append(
                "Many potential titles rejected for being too short - consider lowering word count threshold"
            )
        
        if 'contains excluded terms' in results['common_issues']:
            results['suggested_fixes'].append(
                "Potential titles contain excluded terms - review exclusion list"
            )
        
        return results
