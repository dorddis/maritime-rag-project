"""
RAG System Configuration

All settings loaded from environment variables with sensible defaults.
"""

import os
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Dict


class RAGSettings(BaseSettings):
    """RAG system configuration."""

    # Database URLs
    postgres_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/maritime",
        description="PostgreSQL connection URL"
    )
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL"
    )

    # Google/Gemini API
    google_api_key: str = Field(
        default="",
        description="Google API key for Gemini"
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model for LLM tasks (per project policy: always 2.5)"
    )
    embedding_model: str = Field(
        default="models/embedding-001",
        description="Gemini embedding model (768 dimensions)"
    )
    embedding_dimensions: int = Field(
        default=768,
        description="Embedding vector dimensions"
    )

    # SQL Agent Settings
    sql_agent_max_iterations: int = Field(
        default=5,
        description="Max iterations for SQL agent"
    )
    sql_agent_temperature: float = Field(
        default=0.0,
        description="Temperature for SQL generation (0 = deterministic)"
    )

    # Vector Search Settings
    vector_search_limit: int = Field(
        default=10,
        description="Default number of results for vector search"
    )
    similarity_threshold: float = Field(
        default=0.5,
        description="Minimum cosine similarity for vector matches"
    )

    # Sync Service Settings
    sync_rate_hz: float = Field(
        default=2.0,
        description="Rate to sync Redis → PostgreSQL (Hz)"
    )
    sync_batch_size: int = Field(
        default=100,
        description="Batch size for sync operations"
    )

    # Embedding Generation Settings
    embedding_batch_size: int = Field(
        default=50,
        description="Batch size for embedding generation"
    )

    # Hybrid Fusion Settings
    rrf_k: int = Field(
        default=60,
        description="Reciprocal Rank Fusion constant"
    )
    fusion_weights: Dict[str, float] = Field(
        default={"structured": 1.0, "semantic": 0.8, "realtime": 1.2},
        description="Weights for result fusion"
    )

    # Query Router Settings
    router_model: str = Field(
        default="gemini-2.5-pro",
        description="Gemini model for query routing (pro for better accuracy)"
    )
    router_confidence_threshold: float = Field(
        default=0.7,
        description="Minimum confidence for query routing"
    )

    # Known Port Coordinates (for geo queries)
    known_ports: Dict[str, tuple] = Field(
        default={
            "mumbai": (18.9388, 72.8354),
            "chennai": (13.0827, 80.2707),
            "kochi": (9.9312, 76.2673),
            "visakhapatnam": (17.6868, 83.2185),
            "kandla": (23.0333, 70.2167),
            "colombo": (6.9271, 79.8612),
            "singapore": (1.3521, 103.8198),
            "dubai": (25.2048, 55.2708),
        },
        description="Known port coordinates for geo queries"
    )

    class Config:
        env_file = ".env"
        env_prefix = "RAG_"
        extra = "ignore"


# Global settings instance
settings = RAGSettings()


def get_postgres_url() -> str:
    """Get PostgreSQL URL, preferring env var."""
    return os.getenv("DATABASE_URL", os.getenv("POSTGRES_URL", settings.postgres_url))


def get_redis_url() -> str:
    """Get Redis URL, preferring env var."""
    return os.getenv("REDIS_URL", settings.redis_url)


def get_google_api_key() -> str:
    """Get Google API key."""
    return os.getenv("GOOGLE_API_KEY", settings.google_api_key)
