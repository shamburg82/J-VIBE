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


# Only apply nest_asyncio if not using uvloop
try:
    loop = asyncio.get_event_loop()
    if not isinstance(loop, type(asyncio.new_event_loop())):
        # We're using a different loop (like uvloop), don't patch
        logger = logging.getLogger(__name__)
        logger.info("Using alternative event loop, skipping nest_asyncio.apply()")
    else:
        nest_asyncio.apply()
except Exception as e:
    # If we can't determine loop type safely, skip patching
    logger = logging.getLogger(__name__)
    logger.warning(f"Could not determine event loop type, skipping nest_asyncio: {e}")

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
            
        llm_model_arn = aws_config.get("llm_model_arn", "arn:aws:bedrock:us-west-2:912115013020:inference-profile/us.anthropic.claude-3-7-sonnet-20250219-v1:0")  # ARN for LlamaIndex
        llm_model_id = aws_config.get("llm_model_id", "anthropic.claude-3-7-sonnet-20250219-v1:0") # This model ID for direct calls
        region = aws_config.get("region", "us-west-2")
        temperature = aws_config.get("temperature", 0.2)
        max_tokens = aws_config.get("max_tokens", 4096)
        embedding_model_id = aws_config.get("embedding_model_id", "amazon.titan-embed-text-v1")

        logger.info(f"🔧 Configuring Bedrock with proper model separation:")
        logger.info(f"   LLM ARN (for LlamaIndex): {llm_model_arn}")
        logger.info(f"   LLM Model ID (backup): {llm_model_id}")
        logger.info(f"   Embedding Model: {embedding_model_id}")
        logger.info(f"   Region: {region}")

        # Create Bedrock LLM
        logger.info("🚀 Creating BedrockConverse with inference profile ARN...")
        llm = BedrockConverse(
            model=llm_model_arn,
            region_name=region,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=3
        )
        
        # Create Bedrock Embedding Model with explicit configuration
        logger.info("🔤 Creating BedrockEmbedding with explicit model configuration...")

        test_embedding_success = await _test_embedding_model(embedding_model_id, region)
        
        if not test_embedding_success:
            logger.error("❌ Embedding model test failed, trying alternatives...")
            embedding_model_id = await _find_working_embedding_model(region)
            if not embedding_model_id:
                logger.error("❌ No working embedding model found!")
                return None
        
        embed_model = BedrockEmbedding(
            model_name=embedding_model_id,
            region_name=region,
            # Explicit parameters to ensure it uses the right model
            embed_batch_size=10,  # Smaller batch size to avoid timeouts
        )
        
        # Set LlamaIndex global settings
        Settings.llm = llm
        Settings.embed_model = embed_model
        
        logger.info("✅ Both LLM and embedding models configured successfully")
        
        # Test the LLM with a simple call
        logger.info("🧪 Testing LLM...")
        try:
            test_response = await llm.acomplete("Hello")
            logger.info(f"✅ LLM test successful!")
        except Exception as test_error:
            logger.warning(f"⚠️  LLM test failed: {test_error}")
            return await _try_alternative_model_config(config)
        
        # Test embedding model
        logger.info("🧪 Testing embedding model...")
        try:
            test_embedding = await embed_model.aget_text_embedding("test")
            logger.info(f"✅ Embedding test successful! Dimension: {len(test_embedding)}")
        except Exception as embed_error:
            logger.error(f"❌ Embedding test failed: {embed_error}")
            return None
        
        if config.is_development_mode():
            logger.info(f"✅ All Bedrock models configured and tested successfully")
        
        return llm
        
    except Exception as e:
        logger.error(f"❌ Failed to configure Bedrock: {e}")
        logger.exception("Bedrock configuration error details:")
        return None


async def _test_embedding_model(model_id: str, region: str) -> bool:
    """Test if the embedding model works."""
    
    try:
        logger.info(f"🧪 Testing embedding model: {model_id}")
        
        # Create a temporary embedding model to test
        test_embed = BedrockEmbedding(
            model_name=model_id,
            region_name=region
        )
        
        # Try to get an embedding
        embedding = await test_embed.aget_text_embedding("test")
        
        if embedding and len(embedding) > 0:
            logger.info(f"✅ Embedding model {model_id} works! Dimension: {len(embedding)}")
            return True
        else:
            logger.warning(f"⚠️  Embedding model {model_id} returned empty embedding")
            return False
            
    except Exception as e:
        logger.warning(f"⚠️  Embedding model {model_id} test failed: {e}")
        return False


async def _find_working_embedding_model(region: str) -> Optional[str]:
    """Find a working embedding model."""
    
    # Try different embedding models
    embedding_models = [
        "amazon.titan-embed-text-v1",
        "amazon.titan-embed-text-v1",
        "cohere.embed-english-v3",
        "cohere.embed-multilingual-v3"
    ]
    
    for model_id in embedding_models:
        if await _test_embedding_model(model_id, region):
            logger.info(f"✅ Found working embedding model: {model_id}")
            return model_id
    
    logger.error("❌ No working embedding model found!")
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
