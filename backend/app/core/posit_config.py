# backend/posit_config.py
"""
Posit Connect specific configuration.
"""
import os
from pathlib import Path

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
        self.base_storage_path = Path("//datastore/BU/RD/Restricted/DS/AIGAS/source_docs/study")
        
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

        # Environment-specific limits
        if self.is_posit_connect:
            # Production limits
            self.max_file_size_mb = int(os.getenv("MAX_FILE_SIZE_MB", "100"))
            self.max_concurrent_uploads = int(os.getenv("MAX_CONCURRENT_UPLOADS", "10"))
            self.log_level = "INFO"
        else:
            # Development limits (Workbench)
            self.max_file_size_mb = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
            self.max_concurrent_uploads = int(os.getenv("MAX_CONCURRENT_UPLOADS", "5"))
            self.log_level = "DEBUG"
        
        print(f"🏗️  Posit Config - Environment: {'Connect' if self.is_posit_connect else 'Workbench' if self.is_posit_workbench else 'Other'}")
        print(f"📁 Storage: {self.base_storage_path}")
        print(f"🔧 Dev Mode: {self.development_mode}")

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


def get_posit_config() -> PositConfig:
    """Get Posit Connect/Workbench configuration."""
    return PositConfig()
