# backend/app/core/bedrock_setup.py
import nest_asyncio
import logging
from typing import Optional
import os

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from llama_index.llms.bedrock_converse import BedrockConverse
from llama_index.embeddings.bedrock import BedrockEmbedding
from llama_index.core import Settings

from .config import get_config

nest_asyncio.apply()
logger = logging.getLogger(__name__)


async def configure_bedrock_llm() -> Optional[BedrockConverse]:
    """Configure Bedrock LLM using config settings."""
    try:
        config = get_config()
        
        # Get AWS configuration
        aws_config = config.get_aws_config()

        # # Validate AWS credentials first
        # if not _validate_aws_credentials():
        #     logger.error("AWS credentials not properly configured for Posit Connect")
        #     return None
        
        llm_model_id = aws_config.get("llm_model_id", "anthropic.claude-3-7-sonnet-20250219-v1:0")
        region = aws_config.get("region", "us-west-2")
        temperature = aws_config.get("temperature", 0.2)
        max_tokens = aws_config.get("max_tokens", 4096)
        embedding_model_id = aws_config.get("embedding_model_id", "amazon.titan-embed-text-v1")

        # Create Bedrock LLM
        llm = BedrockConverse(
            model=llm_model_id,
            region_name=region,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        # Create Bedrock Embedding Model
        embed_model = BedrockEmbedding(
            model_name=embedding_model_id,
            region_name=region
        )
        
        # Set LlamaIndex global settings
        Settings.llm = llm
        Settings.embed_model = embed_model
        
        # Test the LLM with a simple call
        test_response = await llm.acomplete("Hello")
        logger.info(f"LLM Test response preview: {str(test_response)[:200]}")
        
        if config.is_development_mode():
            logger.info(f"✓ Configured Bedrock LLM: {llm_model_id} in {region}")
        
        return llm
        
    except Exception as e:
        logger.error(f"❌ Failed to configure Bedrock LLM: {e}")
        return None


def _validate_aws_credentials() -> bool:
    """Validate AWS credentials are available."""
    
    try:
        # Try to create a boto3 session
        session = boto3.Session(
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION", "us-west-2")
        )
        
        # Test with STS get-caller-identity (lightweight call)
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        
        logger.info(f"AWS credentials validated - Account: {identity.get('Account')}")
        return True
        
    except (ClientError, NoCredentialsError) as e:
        logger.error(f"AWS credentials validation failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error validating AWS credentials: {e}")
        return False

