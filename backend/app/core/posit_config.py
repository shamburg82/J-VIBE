# backend/posit_config.py
"""
Posit Connect specific configuration.
"""
import os
from pathlib import Path
from typing import Dict, Any, Optional

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


# Import base config - adjust import based on where this file is
try:
    from .config import Config
except ImportError:
    from config import Config


class PositConfig(Config):
    """Posit Connect specific configuration."""
    
    def __init__(self):
        super().__init__()
        
        # Environment detection
        self.is_posit_connect = bool(os.getenv("RSTUDIO_CONNECT_URL"))
        self.is_posit_workbench = bool(os.getenv("RS_SERVER_URL")) and not self.is_posit_connect
        
        # Development mode: Workbench = dev, Connect = production
        self.development_mode = self.is_posit_workbench
        
        # Use your original datastore path for both environments
        self.base_storage_path = Path("//datastore/BU/RD/Restricted/DS/JazzVIBE/source_docs/study")
        
        # Ensure storage directory exists
        try:
            self.base_storage_path.mkdir(parents=True, exist_ok=True)
            print(f"✅ Storage path configured: {self.base_storage_path}")
        except Exception as e:
            print(f"⚠️  Storage path warning: {e}")
        
        # AWS credentials handling for Posit Connect
        # These should be set as environment variables in Posit Connect
        self.aws_region = os.getenv("AWS_REGION", "us-west-2")
        self.aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        
        # Bedrock settings
        self.llm_model_id = os.getenv("LLM_MODEL_ID", "arn:aws:bedrock:us-west-2:912115013020:inference-profile/us.anthropic.claude-3-7-sonnet-20250219-v1:0")
        self.embedding_model_id = os.getenv("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v1")
        self.temperature = float(os.getenv("TEMPERATURE", "0.2"))
        self.max_tokens = int(os.getenv("MAX_TOKENS", "4096"))
        
        # Vector Store Configuration
        self.use_vector_store = os.getenv("USE_VECTOR_STORE", "true").lower() == "true"
        self.vector_store_type = os.getenv("VECTOR_STORE_TYPE", "mongodb")
        
        # MongoDB Atlas Configuration
        # Primary connection string (preferred method)
        self.mongodb_connection_string = os.getenv("MONGODB_CONNECTION_STRING") or os.getenv("MONGODB_URI")
        
        # Individual MongoDB components (fallback)
        self.mongodb_host = os.getenv("MONGODB_HOST", "na2-dsejazzvibe01-pl-0.os021j.mongodb.net")
        self.mongodb_username = os.getenv("MONGODB_USERNAME")
        self.mongodb_password = os.getenv("MONGODB_PASSWORD")
        
        # MongoDB database and collection settings
        self.mongodb_database_name = os.getenv("MONGODB_DATABASE_NAME", "jazzvibe")
        self.mongodb_collection_name = os.getenv("MONGODB_COLLECTION_NAME", "vector_store")
        

        # Environment-specific limits
        if self.is_posit_connect:
            # Production limits
            self.max_file_size_mb = int(os.getenv("MAX_FILE_SIZE_MB", "100"))
            self.max_concurrent_uploads = int(os.getenv("MAX_CONCURRENT_UPLOADS", "10"))
            self.log_level = "INFO"
            
            # Production MongoDB settings
            self.mongodb_max_pool_size = int(os.getenv("MONGODB_MAX_POOL_SIZE", "50"))
            self.mongodb_min_pool_size = int(os.getenv("MONGODB_MIN_POOL_SIZE", "5"))
            self.mongodb_server_selection_timeout_ms = int(os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "30000"))
            
            # Production processing settings
            self.chunk_size = int(os.getenv("CHUNK_SIZE", "512"))
            self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "50"))
            self.confidence_threshold = float(os.getenv("CONFIDENCE_THRESHOLD", "0.7"))
            
            # Disable expensive extractors in production by default
            self.enable_keyword_extraction = os.getenv("ENABLE_KEYWORD_EXTRACTION", "false").lower() == "true"
            self.enable_question_extraction = os.getenv("ENABLE_QUESTION_EXTRACTION", "false").lower() == "true"
            self.enable_summary_extraction = os.getenv("ENABLE_SUMMARY_EXTRACTION", "false").lower() == "true"
            
        else:
            # Development settings (Workbench)
            self.max_file_size_mb = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
            self.max_concurrent_uploads = int(os.getenv("MAX_CONCURRENT_UPLOADS", "5"))
            self.log_level = "DEBUG"
            
            # Development MongoDB settings - more relaxed
            self.mongodb_max_pool_size = int(os.getenv("MONGODB_MAX_POOL_SIZE", "20"))
            self.mongodb_min_pool_size = int(os.getenv("MONGODB_MIN_POOL_SIZE", "1"))
            self.mongodb_server_selection_timeout_ms = int(os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "10000"))
            
            # Development processing settings - smaller for faster testing
            self.chunk_size = int(os.getenv("CHUNK_SIZE", "256"))
            self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "25"))
            self.confidence_threshold = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))
            
            # Enable extractors in development for testing
            self.enable_keyword_extraction = os.getenv("ENABLE_KEYWORD_EXTRACTION", "true").lower() == "true"
            self.enable_question_extraction = os.getenv("ENABLE_QUESTION_EXTRACTION", "false").lower() == "true"
            self.enable_summary_extraction = os.getenv("ENABLE_SUMMARY_EXTRACTION", "false").lower() == "true"
        
        print(f"🏗️  Posit Config - Environment: {self.get_environment_name()}")
        print(f"📁 File Storage: {self.base_storage_path}")
        print(f"🗄️  Vector Store: {'MongoDB Atlas' if self.is_mongodb_enabled() else 'In-Memory'}")
        print(f"🔧 Dev Mode: {self.development_mode}")
        
        # MongoDB connection validation
        if self.is_mongodb_enabled():
            self._validate_mongodb_config_posit()
    
    def _validate_mongodb_config_posit(self):
        """Validate MongoDB configuration for Posit environments."""
        
        if not self.mongodb_connection_string:
            if self.mongodb_username and self.mongodb_password and self.mongodb_host:
                # Build connection string from components
                self.mongodb_connection_string = f"mongodb+srv://{self.mongodb_username}:{self.mongodb_password}@{self.mongodb_host}/?retryWrites=true&w=majority&appName=JazzVIBE"
                print(f"✅ Built MongoDB connection string from components")
            else:
                print(f"⚠️  MongoDB configuration incomplete for {self.get_environment_name()}")
                print(f"    Required: MONGODB_CONNECTION_STRING or (MONGODB_USERNAME + MONGODB_PASSWORD)")
                if self.is_posit_connect:
                    print(f"    💡 Set these as environment variables in Posit Connect")
                else:
                    print(f"    💡 Set these in your development environment or .env file")
        else:
            print(f"✅ MongoDB connection string configured")
    
    def get_mongodb_config(self) -> Dict[str, Any]:
        """Get MongoDB configuration dictionary with Posit-specific settings."""
        base_config = super().get_mongodb_config()
        
        # Add Posit-specific MongoDB settings
        base_config.update({
            "max_pool_size": getattr(self, 'mongodb_max_pool_size', 20),
            "min_pool_size": getattr(self, 'mongodb_min_pool_size', 1),
            "server_selection_timeout_ms": getattr(self, 'mongodb_server_selection_timeout_ms', 30000),
            "socket_timeout_ms": int(os.getenv("MONGODB_SOCKET_TIMEOUT_MS", "20000")),
            "connect_timeout_ms": int(os.getenv("MONGODB_CONNECT_TIMEOUT_MS", "20000")),
            "max_idle_time_ms": int(os.getenv("MONGODB_MAX_IDLE_TIME_MS", "30000")),
            "app_name": "JazzVIBE-Posit"
        })
        
        return base_config

    def get_storage_path(self) -> Path:
        """Get the base storage path."""
        return self.base_storage_path

    def get_environment_name(self) -> str:
        """Get descriptive environment name."""
        if self.is_posit_connect:
            return "Posit Connect (Production)"
        elif self.is_posit_workbench:
            return "Posit Workbench (Development)"
        else:
            return "Other Environment"
    
    def is_mongodb_enabled(self) -> bool:
        """Check if MongoDB vector store is enabled."""
        return self.use_vector_store and self.vector_store_type.lower() == "mongodb"
    
    def get_posit_environment_info(self) -> Dict[str, Any]:
        """Get comprehensive environment information for Posit deployments."""
        
        return {
            "environment_type": self.get_environment_name(),
            "is_production": self.is_posit_connect,
            "is_development": self.is_posit_workbench,
            "storage_path": str(self.base_storage_path),
            "vector_store_enabled": self.use_vector_store,
            "vector_store_type": self.vector_store_type if self.use_vector_store else None,
            "mongodb_enabled": self.is_mongodb_enabled(),
            "mongodb_database": self.mongodb_database_name if self.is_mongodb_enabled() else None,
            "mongodb_collection": self.mongodb_collection_name if self.is_mongodb_enabled() else None,
            "max_file_size_mb": self.max_file_size_mb,
            "chunk_size": self.chunk_size,
            "extractors_enabled": {
                "keyword": self.enable_keyword_extraction,
                "question": self.enable_question_extraction,
                "summary": self.enable_summary_extraction
            },
            "aws_region": self.aws_region,
            "llm_model": self.llm_model_id.split('/')[-1] if '/' in self.llm_model_id else self.llm_model_id
        }
    
    def get_performance_config(self) -> Dict[str, Any]:
        """Get performance-related configuration for the current environment."""
        
        return {
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "confidence_threshold": self.confidence_threshold,
            "max_file_size_mb": self.max_file_size_mb,
            "max_concurrent_uploads": self.max_concurrent_uploads,
            "mongodb_pool_settings": {
                "max_pool_size": getattr(self, 'mongodb_max_pool_size', 20),
                "min_pool_size": getattr(self, 'mongodb_min_pool_size', 1),
                "timeout_ms": getattr(self, 'mongodb_server_selection_timeout_ms', 30000)
            } if self.is_mongodb_enabled() else None,
            "extractors": {
                "keyword_enabled": self.enable_keyword_extraction,
                "question_enabled": self.enable_question_extraction,
                "summary_enabled": self.enable_summary_extraction
            }
        }

def get_posit_config() -> PositConfig:
    """Get Posit Connect/Workbench configuration."""
    return PositConfig()
