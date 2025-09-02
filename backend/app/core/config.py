# backend/app/core/config.py
import os
from typing import Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path

# Load environment variables from .env files
try:
    from dotenv import load_dotenv
    
    # Try to load .env from multiple locations
    env_paths = [
        Path(".env"),                    # Project root
        Path("backend/.env"),           # Backend directory
        Path(__file__).parent / ".env", # Same directory as this file
        Path(__file__).parent.parent.parent / ".env"  # Project root from backend/app/core/
    ]
    
    env_loaded = False
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path, override=False)  # Don't override existing env vars
            print(f"✅ Loaded environment from: {env_path}")
            env_loaded = True
            break
    
    if not env_loaded:
        print("⚠️  No .env file found, using system environment variables only")
        
except ImportError:
    print("⚠️  python-dotenv not installed, using system environment variables only")


@dataclass
class Config:
    """Application configuration."""
    
    # AWS Settings
    aws_region: str = "us-west-2"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    
    # Bedrock Settings
    llm_model_id: str = "arn:aws:bedrock:us-west-2:912115013020:inference-profile/us.anthropic.claude-3-7-sonnet-20250219-v1:0"
    embedding_model_id: str = "amazon.titan-embed-text-v2"
    temperature: float = 0.2
    max_tokens: int = 4096
    
    # Application Settings
    development_mode: bool = True
    log_level: str = "INFO"
    max_file_size_mb: int = 50
    base_storage_path: str = "//datastore/BU/RD/Restricted/DS/JazzVIBE/source_docs/study"
    
    # Processing Settings
    chunk_size: int = 512
    chunk_overlap: int = 50
    confidence_threshold: float = 0.7
    
    # Extractor configuration flags
    enable_keyword_extraction: bool = False
    enable_question_extraction: bool = False
    enable_summary_extraction: bool = False
        
    
    # Vector Store Settings
    use_vector_store: bool = True
    vector_store_type: str = "mongodb"  # Options: "memory", "mongodb"
    
    # MongoDB Settings
    mongodb_connection_string: Optional[str] = None
    mongodb_database_name: str = "jazzvibe"
    mongodb_collection_name: str = "vector_store"
    mongodb_host: str = "na2-dsejazzvibe01-pl-0.os021j.mongodb.net"
    mongodb_username: Optional[str] = None
    mongodb_password: Optional[str] = None

    
    def get_aws_config(self) -> Dict[str, Any]:
        """Get AWS configuration dictionary."""
        return {
            "region": self.aws_region,
            "llm_model_id": self.llm_model_id,
            "embedding_model_id": self.embedding_model_id,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
    
    def get_mongodb_config(self) -> Dict[str, Any]:
        """Get MongoDB configuration dictionary."""
        return {
            "connection_string": self.mongodb_connection_string,
            "database_name": self.mongodb_database_name,
            "collection_name": self.mongodb_collection_name,
            "host": self.mongodb_host,
            "username": self.mongodb_username,
            "password": self.mongodb_password
        }
    
    def is_mongodb_enabled(self) -> bool:
        """Check if MongoDB vector store is enabled."""
        return self.use_vector_store and self.vector_store_type.lower() == "mongodb"
    
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
        base_storage_path=Path(os.getenv("BASE_STORAGE_PATH", "//datastore/BU/RD/Restricted/DS/JazzVIBE/source_docs/study")),

        # Processing Settings
        chunk_size=int(os.getenv("CHUNK_SIZE", "512")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "50")),
        confidence_threshold=float(os.getenv("CONFIDENCE_THRESHOLD", "0.7")),

        # Vector Store Settings
        use_vector_store=os.getenv("USE_VECTOR_STORE", "true").lower() == "true",
        vector_store_type=os.getenv("VECTOR_STORE_TYPE", "mongodb"),
        
        # MongoDB Settings
        mongodb_connection_string=os.getenv("MONGODB_CONNECTION_STRING") or os.getenv("MONGODB_URI"),
        mongodb_database_name=os.getenv("MONGODB_DATABASE_NAME", "jazzvibe"),
        mongodb_collection_name=os.getenv("MONGODB_COLLECTION_NAME", "vector_store"),
        mongodb_host=os.getenv("MONGODB_HOST", "na2-dsejazzvibe01-pl-0.os021j.mongodb.net"),
        mongodb_username=os.getenv("MONGODB_USERNAME"),
        mongodb_password=os.getenv("MONGODB_PASSWORD")
    )
