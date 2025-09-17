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


# FIXED: Only apply nest_asyncio if not using uvloop
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


async def configure_bedrock_for_posit() -> Optional[BedrockConverse]:
    """Configure Bedrock LLM specifically for Posit Connect/Workbench."""
    try:
        # Get Posit-specific configuration
        config = get_posit_config()
        
        # Log environment details
        env_info = config.get_posit_environment_info()
        logger.info(f"🏗️  Configuring Bedrock for {env_info['environment_type']}")
        logger.info(f"🗄️  Vector Store: {env_info['vector_store_type'] or 'disabled'}")
        
        if env_info['mongodb_enabled']:
            logger.info(f"📊 MongoDB Database: {env_info['mongodb_database']}")
        
        # Get AWS configuration from Posit config
        aws_config = config.get_aws_config()
        
        # Validate AWS credentials
        if not _validate_aws_credentials_posit(config):
            logger.error("❌ AWS credentials not properly configured for Posit environment")
            if config.is_posit_connect:
                logger.error("💡 Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY as environment variables in Posit Connect")
            else:
                logger.error("💡 Set AWS credentials in your development environment")
            return None
        
        # Create Bedrock LLM with environment-specific settings
        llm = BedrockConverse(
            model=aws_config.get("llm_model_arn"),
            region_name=aws_config.get("region"),
            temperature=aws_config.get("temperature"),
            max_tokens=aws_config.get("max_tokens"),
            # Add timeout settings based on environment
            timeout=30.0 if config.is_posit_connect else 60.0  # Shorter timeout for production
        )
        
        # Create Bedrock Embedding Model
        embed_model = BedrockEmbedding(
            model_name=aws_config.get("embedding_model_id"),
            region_name=aws_config.get("region")
        )
        
        # Set LlamaIndex global settings
        Settings.llm = llm
        Settings.embed_model = embed_model
        
        # Test the LLM with a simple call
        test_response = await llm.acomplete("Hello")
        logger.info(f"LLM Test response preview: {str(test_response)[:200]}")
        
        # Log configuration summary
        performance_config = config.get_performance_config()
        logger.info(f"⚙️  Performance Config:")
        logger.info(f"   - Chunk size: {performance_config['chunk_size']}")
        logger.info(f"   - Max file size: {performance_config['max_file_size_mb']}MB")
        logger.info(f"   - Extractors: {sum(performance_config['extractors'].values())}/3 enabled")
        
        if performance_config['mongodb_pool_settings']:
            mongo_settings = performance_config['mongodb_pool_settings']
            logger.info(f"   - MongoDB pool: {mongo_settings['min_pool_size']}-{mongo_settings['max_pool_size']}")
        
        logger.info(f"✅ Bedrock configured for {config.get_environment_name()}")
        
        return llm
        
    except Exception as e:
        logger.error(f"❌ Failed to configure Bedrock for Posit: {e}")
        logger.exception("Bedrock configuration error details:")
        return None


def _validate_aws_credentials_posit(config) -> bool:
    """Validate AWS credentials in Posit environments."""
    
    try:
        # Check if credentials are available
        # if not config.aws_access_key_id or not config.aws_secret_access_key:
        #     logger.error("❌ AWS credentials not found in environment variables")
        #     return False
        
        # Create a session with explicit credentials
        session = boto3.Session(
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key,
            region_name=config.aws_region
        )
        
        # Test with STS get-caller-identity (lightweight call)
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        
        logger.info(f"✅ AWS credentials validated - Account: {identity.get('Account')}")
        logger.info(f"🔐 IAM User/Role: {identity.get('Arn', 'Unknown')}")
        
        # Additional check: Verify Bedrock access
        try:
            bedrock = session.client('bedrock', region_name=config.aws_region)
            # List models to test Bedrock access
            models = bedrock.list_foundation_models(byProvider='anthropic')
            model_count = len(models.get('modelSummaries', []))
            logger.info(f"✅ Bedrock access verified - {model_count} Anthropic models available")
            
        except ClientError as bedrock_error:
            error_code = bedrock_error.response['Error']['Code']
            if error_code == 'AccessDeniedException':
                logger.warning("⚠️  Limited Bedrock access - check IAM permissions")
                logger.warning("💡 Ensure IAM role has bedrock:ListFoundationModels and bedrock:InvokeModel permissions")
            else:
                logger.warning(f"⚠️  Bedrock access check failed: {bedrock_error}")
            # Don't fail validation for Bedrock permission issues
        
        return True
        
    except (ClientError, NoCredentialsError) as e:
        logger.error(f"❌ AWS credentials validation failed: {e}")
        
        # Provide environment-specific guidance
        config = get_posit_config()  # Re-get config to ensure it's available
        if config.is_posit_connect:
            logger.error("💡 For Posit Connect:")
            logger.error("   1. Set AWS_ACCESS_KEY_ID environment variable")
            logger.error("   2. Set AWS_SECRET_ACCESS_KEY environment variable")
            logger.error("   3. Optionally set AWS_REGION (defaults to us-west-2)")
            logger.error("   4. Restart your app after setting variables")
        else:
            logger.error("💡 For Posit Workbench:")
            logger.error("   1. Set AWS credentials in your .env file")
            logger.error("   2. Or configure AWS CLI: aws configure")
            logger.error("   3. Or use AWS IAM roles if running on EC2")
        
        return False
        
    except Exception as e:
        logger.error(f"❌ Unexpected error validating AWS credentials: {e}")
        return False


def get_bedrock_model_info(config) -> dict:
    """Get information about available Bedrock models for the current configuration."""
    
    try:
        session = boto3.Session(
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key,
            region_name=config.aws_region
        )
        
        bedrock = session.client('bedrock', region_name=config.aws_region)
        
        # Get available models
        anthropic_models = bedrock.list_foundation_models(byProvider='anthropic')
        amazon_models = bedrock.list_foundation_models(byProvider='amazon')
        
        return {
            "current_llm_model": config.llm_model_arn,
            "current_embedding_model": config.embedding_model_id,
            "available_anthropic_models": len(anthropic_models.get('modelSummaries', [])),
            "available_amazon_models": len(amazon_models.get('modelSummaries', [])),
            "region": config.aws_region
        }
        
    except Exception as e:
        logger.warning(f"Could not retrieve Bedrock model info: {e}")
        return {
            "current_llm_model": config.llm_model_arn,
            "current_embedding_model": config.embedding_model_id,
            "error": str(e)
        }


async def test_posit_mongodb_integration(config) -> dict:
    """Test MongoDB integration in Posit environments."""
    
    if not config.is_mongodb_enabled():
        return {
            "mongodb_enabled": False,
            "message": "MongoDB vector store is disabled"
        }
    
    try:
        import pymongo
        from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
        
        mongodb_config = config.get_mongodb_config()
        connection_string = mongodb_config.get('connection_string')
        
        if not connection_string:
            return {
                "mongodb_enabled": True,
                "connected": False,
                "error": "No MongoDB connection string configured"
            }
        
        # Test connection with environment-appropriate timeout
        timeout_ms = 5000 if config.is_posit_connect else 10000
        
        client = pymongo.MongoClient(
            connection_string,
            serverSelectionTimeoutMS=timeout_ms,
            maxPoolSize=mongodb_config.get('max_pool_size', 20),
            minPoolSize=mongodb_config.get('min_pool_size', 1)
        )
        
        # Test the connection
        client.admin.command('ping')
        
        # Get database stats
        db = client[config.mongodb_database_name]
        collection = db[config.mongodb_collection_name]
        
        doc_count = collection.count_documents({})
        
        client.close()
        
        return {
            "mongodb_enabled": True,
            "connected": True,
            "database": config.mongodb_database_name,
            "collection": config.mongodb_collection_name,
            "document_count": doc_count,
            "connection_pool_size": f"{mongodb_config.get('min_pool_size', 1)}-{mongodb_config.get('max_pool_size', 20)}"
        }
        
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        return {
            "mongodb_enabled": True,
            "connected": False,
            "error": f"Connection failed: {str(e)}",
            "suggestion": "Check MongoDB connection string and network access"
        }
    except ImportError:
        return {
            "mongodb_enabled": True,
            "connected": False,
            "error": "pymongo package not installed"
        }
    except Exception as e:
        return {
            "mongodb_enabled": True,
            "connected": False,
            "error": f"Unexpected error: {str(e)}"
        }
