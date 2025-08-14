# backend/app/core/config.py
import os
from typing import Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    """Application configuration."""
    
    # AWS Settings
    aws_region: str = "us-west-2"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    
    # Bedrock Settings
    llm_model_id: str = "arn:aws:bedrock:us-west-2:912115013020:inference-profile/us.anthropic.claude-3-7-sonnet-20250219-v1:0"
    embedding_model_id: str = "amazon.titan-embed-text-v1"
    temperature: float = 0.2
    max_tokens: int = 4096
    
    # Application Settings
    development_mode: bool = True
    log_level: str = "INFO"
    max_file_size_mb: int = 50
    base_storage_path: str = "\\datastore\BU\RD\Restricted\DS\AIGAS\source_docs\study"
    
    # Processing Settings
    chunk_size: int = 512
    chunk_overlap: int = 50
    confidence_threshold: float = 0.7
    
    # Extractor configuration flags
    enable_keyword_extraction: bool = False
    enable_question_extraction: bool = False
    enable_summary_extraction: bool = False
        

    use_vector_store: bool = True
    
    def get_aws_config(self) -> Dict[str, Any]:
        """Get AWS configuration dictionary."""
        return {
            "region": self.aws_region,
            "llm_model_id": self.llm_model_id,
            "embedding_model_id": self.embedding_model_id,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
    
    def is_development_mode(self) -> bool:
        """Check if running in development mode."""
        return self.development_mode


def get_config() -> Config:
    """Get application configuration from environment variables."""
    
    return Config(
        # AWS Settings
        aws_region=os.getenv("AWS_REGION", "us-west-2"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        
        # Bedrock Settings
        llm_model_id=os.getenv("LLM_MODEL_ID", "arn:aws:bedrock:us-west-2:912115013020:inference-profile/us.anthropic.claude-3-7-sonnet-20250219-v1:0"),
        embedding_model_id=os.getenv("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v1"),
        temperature=float(os.getenv("TEMPERATURE", "0.2")),
        max_tokens=int(os.getenv("MAX_TOKENS", "4096")),
        
        # Application Settings
        development_mode=os.getenv("DEVELOPMENT_MODE", "true").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        max_file_size_mb=int(os.getenv("MAX_FILE_SIZE_MB", "50")),
        base_storage_path=Path(os.getenv("BASE_STORAGE_PATH", "//datastore/BU/RD/Restricted/DS/AIGAS/source_docs/study")),

        # Processing Settings
        chunk_size=int(os.getenv("CHUNK_SIZE", "512")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "50")),
        confidence_threshold=float(os.getenv("CONFIDENCE_THRESHOLD", "0.7")),

        use_vector_store = True
    )
