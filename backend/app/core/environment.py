"""
Environment variable validation for production deployments.
Validates critical environment variables on application startup.
"""
import os
import logging
import secrets
from typing import List, Tuple

logger = logging.getLogger(__name__)


def validate_required_env_vars() -> Tuple[bool, List[str]]:
    """
    Validate that all required environment variables are set.
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # Required environment variables
    required_vars = {
        "DATABASE_URL": os.getenv("DATABASE_URL"),
        "SECRET_KEY": os.getenv("SECRET_KEY"),
        "LLM_PROVIDER": os.getenv("LLM_PROVIDER", "openai"),
    }
    
    # Check required vars
    for var_name, var_value in required_vars.items():
        if not var_value:
            errors.append(f"Required environment variable {var_name} is not set")
    
    # Validate SECRET_KEY
    secret_key = os.getenv("SECRET_KEY", "")
    if secret_key:
        if len(secret_key) < 32:
            errors.append("SECRET_KEY must be at least 32 characters long")
        if secret_key in ["dev-secret-key-change-in-production", "change-me-in-production"]:
            errors.append("SECRET_KEY must be changed from default value in production")
    
    # Validate LLM configuration based on provider
    llm_provider = os.getenv("LLM_PROVIDER", "openai").lower()
    
    if llm_provider == "openai":
        openai_key = os.getenv("OPENAI_API_KEY") or os.getenv("RUNPOD_API_KEY")
        if not openai_key:
            errors.append("OPENAI_API_KEY or RUNPOD_API_KEY must be set when LLM_PROVIDER=openai")
    elif llm_provider == "anthropic":
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if not anthropic_key:
            errors.append("ANTHROPIC_API_KEY must be set when LLM_PROVIDER=anthropic")
    
    # Validate MODEL_NAME
    model_name = os.getenv("MODEL_NAME")
    if not model_name:
        errors.append("MODEL_NAME must be set")
    
    # Validate DATABASE_URL format
    database_url = os.getenv("DATABASE_URL", "")
    if database_url and not database_url.startswith(("postgresql://", "postgresql+psycopg2://")):
        errors.append("DATABASE_URL must be a valid PostgreSQL connection string")
    
    # Validate environment-specific settings
    environment = os.getenv("ENVIRONMENT", "development").lower()
    if environment == "production":
        # In production, ensure CORS_ORIGINS is set
        cors_origins = os.getenv("CORS_ORIGINS", "")
        if not cors_origins:
            errors.append("CORS_ORIGINS must be set in production environment")
        
        # Ensure database password is not default
        if "postgres:postgres@" in database_url:
            errors.append("Default database password detected. Change POSTGRES_PASSWORD in production")
    
    return len(errors) == 0, errors


def generate_secret_key() -> str:
    """Generate a secure random secret key."""
    return secrets.token_urlsafe(32)


def print_env_summary():
    """Print a summary of environment configuration (safe for logs)."""
    environment = os.getenv("ENVIRONMENT", "development")
    llm_provider = os.getenv("LLM_PROVIDER", "openai")
    model_name = os.getenv("MODEL_NAME", "not set")
    database_url = os.getenv("DATABASE_URL", "")
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    
    # Mask sensitive values
    if database_url:
        # Mask password in database URL
        if "@" in database_url:
            parts = database_url.split("@")
            if ":" in parts[0]:
                user_pass = parts[0].split(":")
                masked_url = f"{user_pass[0]}:****@{parts[1]}"
            else:
                masked_url = database_url
        else:
            masked_url = database_url
    else:
        masked_url = "not set"
    
    logger.info("=" * 60)
    logger.info("Environment Configuration Summary")
    logger.info("=" * 60)
    logger.info(f"Environment: {environment}")
    logger.info(f"LLM Provider: {llm_provider}")
    logger.info(f"Model Name: {model_name}")
    logger.info(f"Database URL: {masked_url}")
    logger.info(f"Qdrant URL: {qdrant_url}")
    logger.info(f"SECRET_KEY: {'*' * 32} (hidden)")
    logger.info("=" * 60)


def validate_on_startup():
    """
    Validate environment variables on application startup.
    Raises ValueError if validation fails.
    """
    is_valid, errors = validate_required_env_vars()
    
    if not is_valid:
        error_message = "Environment validation failed:\n" + "\n".join(f"  - {error}" for error in errors)
        logger.error(error_message)
        logger.error("\nTo generate a secure SECRET_KEY, run:")
        logger.error(f"  python -c 'import secrets; print(secrets.token_urlsafe(32))'")
        raise ValueError(error_message)
    
    logger.info("Environment validation passed")
    print_env_summary()