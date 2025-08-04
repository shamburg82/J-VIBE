# backend/app/utils/helpers.py
import hashlib
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
import json


def generate_document_id() -> str:
    """Generate a unique document ID."""
    return str(uuid.uuid4())


def generate_file_hash(content: bytes) -> str:
    """Generate SHA-256 hash of file content."""
    return hashlib.sha256(content).hexdigest()


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage."""
    # Remove or replace unsafe characters
    unsafe_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    safe_filename = filename
    
    for char in unsafe_chars:
        safe_filename = safe_filename.replace(char, '_')
    
    return safe_filename


def format_processing_time(seconds: float) -> str:
    """Format processing time in human-readable format."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def safe_json_serialize(obj: Any) -> str:
    """Safely serialize object to JSON."""
    try:
        return json.dumps(obj, default=str, ensure_ascii=False)
    except Exception:
        return json.dumps({"error": "Unable to serialize object"})


def extract_study_id_from_filename(filename: str) -> Optional[str]:
    """Extract study ID from filename using common patterns."""
    import re
    
    # Common study ID patterns
    patterns = [
        r'([A-Z]{2,4}[-_]?\d{2,4}[-_]?\d{2,4})',  # ABC-123-001 or ABC123001
        r'(study[-_]?\d+)',  # study-123 or study123
        r'(protocol[-_]?[A-Z0-9]+)',  # protocol-ABC123
    ]
    
    filename_upper = filename.upper()
    
    for pattern in patterns:
        match = re.search(pattern, filename_upper)
        if match:
            return match.group(1)
    
    return None
