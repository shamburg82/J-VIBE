# backend/app/core/posit_bedrock_setup.py
import nest_asyncio
import logging
import os
from typing import Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from llama_index.llms.bedrock_converse import BedrockConverse
from llama_index.embeddings.bedrock import BedrockEmbedding
from llama_index.core import Settings

from .posit_config import get_posit_config

nest_asyncio.apply()
logger = logging.getLogger(__name__)


async def configure_bedrock_for_posit() -> Optional[BedrockConverse]:
    """Configure Bedrock LLM specifically for Posit Connect/Workbench."""
    try:
        # Get Posit-specific configuration
        config = get_posit_config()
        
        # Get AWS configuration from Posit config
        aws_config = config.get_aws_config()
        
        llm_model_id = aws_config.get("llm_model_id", "anthropic.claude-3-7-sonnet-20250219-v1:0")
        region = aws_config.get("region", "us-west-2")
        temperature = aws_config.get("temperature", 0.2)
        max_tokens = aws_config.get("max_tokens", 4096)
        embedding_model_id = aws_config.get("embedding_model_id", "amazon.titan-embed-text-v1")

        # For Posit Connect, AWS credentials should be set as environment variables
        logger.info(f"🔧 Configuring Bedrock for {config.get_environment_name()}")
        
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
        
        logger.info(f"✅ Configured Bedrock LLM for Posit: {llm_model_id} in {region}")
        logger.info(f"📁 Storage configured: {config.get_storage_path()}")
        
        return llm
        
    except Exception as e:
        logger.error(f"❌ Failed to configure Bedrock LLM for Posit: {e}")
        return None
