"""
Vector Retriever using pgvector

Semantic search over:
- Document embeddings (ship reports, port reports, anomaly alerts)
- Track history embeddings
- Anomaly embeddings

Uses cosine similarity for ranking.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

import asyncpg

from ..config import settings, get_postgres_url
from .embeddings import EmbeddingGenerator

logger = logging.getLogger(__name__)


class VectorRetriever:
    """
    Semantic search using pgvector.
    """

    def __init__(
        self,
        postgres_url: str = None,
        embedding_generator: EmbeddingGenerator = None,
    ):
        self.postgres_url = postgres_url or get_postgres_url()
        self.embedding_generator = embedding_generator or EmbeddingGenerator()
        self.pg_pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Initialize connections."""
        self.pg_pool = await asyncpg.create_pool(
            self.postgres_url,
            min_size=2,
            max_size=10,
        )
        logger.info("VectorRetriever connected to PostgreSQL")

    async def close(self):
        """Close connections."""
        if self.pg_pool:
            await self.pg_pool.close()

    async def search_documents(
        self,
        query: str,
        document_type: str = None,
        limit: int = None,
        similarity_threshold: float = None,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search over document embeddings.

        Args:
            query: Natural language search query
            document_type: Filter by type (ship_report, port_report, anomaly_alert)
            limit: Max results to return
            similarity_threshold: Minimum cosine similarity (0-1)

        Returns:
            List of matching documents with similarity scores
        """
        limit = limit or settings.vector_search_limit
        similarity_threshold = similarity_threshold or settings.similarity_threshold

        # Generate query embedding
        query_embedding = self.embedding_generator.embed_text(
            query, task_type="retrieval_query"
        )

        async with self.pg_pool.acquire() as conn:
            if document_type:
                results = await conn.fetch(
                    """
                    SELECT
                        id,
                        content,
                        document_type,
                        metadata,
                        1 - (embedding <=> $1::vector) AS similarity
                    FROM document_embeddings
                    WHERE document_type = $2
                      AND 1 - (embedding <=> $1::vector) >= $3
                    ORDER BY embedding <=> $1::vector
                    LIMIT $4
                    """,
                    str(query_embedding),
                    document_type,
                    similarity_threshold,
                    limit,
                )
            else:
                results = await conn.fetch(
                    """
                    SELECT
                        id,
                        content,
                        document_type,
                        metadata,
                        1 - (embedding <=> $1::vector) AS similarity
                    FROM document_embeddings
                    WHERE 1 - (embedding <=> $1::vector) >= $2
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                    """,
                    str(query_embedding),
                    similarity_threshold,
                    limit,
                )

        return [
            {
                "id": str(row["id"]),
                "content": row["content"],
                "document_type": row["document_type"],
                "metadata": row["metadata"],
                "similarity": float(row["similarity"]),
            }
            for row in results
        ]

    async def search_track_history(
        self,
        query: str,
        time_start: datetime = None,
        time_end: datetime = None,
        limit: int = None,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search over track history descriptions.

        Args:
            query: Natural language query (e.g., "vessels that went dark")
            time_start: Filter by window start time
            time_end: Filter by window end time
            limit: Max results

        Returns:
            List of matching track history segments
        """
        limit = limit or settings.vector_search_limit

        query_embedding = self.embedding_generator.embed_text(
            query, task_type="retrieval_query"
        )

        async with self.pg_pool.acquire() as conn:
            if time_start and time_end:
                results = await conn.fetch(
                    """
                    SELECT
                        id,
                        track_id,
                        description,
                        window_start,
                        window_end,
                        metadata,
                        1 - (embedding <=> $1::vector) AS similarity
                    FROM track_history_embeddings
                    WHERE window_start >= $2 AND window_end <= $3
                    ORDER BY embedding <=> $1::vector
                    LIMIT $4
                    """,
                    str(query_embedding),
                    time_start,
                    time_end,
                    limit,
                )
            else:
                results = await conn.fetch(
                    """
                    SELECT
                        id,
                        track_id,
                        description,
                        window_start,
                        window_end,
                        metadata,
                        1 - (embedding <=> $1::vector) AS similarity
                    FROM track_history_embeddings
                    ORDER BY embedding <=> $1::vector
                    LIMIT $2
                    """,
                    str(query_embedding),
                    limit,
                )

        return [
            {
                "id": str(row["id"]),
                "track_id": row["track_id"],
                "description": row["description"],
                "window_start": row["window_start"].isoformat() if row["window_start"] else None,
                "window_end": row["window_end"].isoformat() if row["window_end"] else None,
                "metadata": row["metadata"],
                "similarity": float(row["similarity"]),
            }
            for row in results
        ]

    async def search_anomalies(
        self,
        query: str,
        source_type: str = None,
        limit: int = None,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search over anomaly descriptions.

        Args:
            query: Natural language query (e.g., "AIS gaps near Mumbai")
            source_type: Filter by anomaly type (dark_ship, speed_anomaly, etc.)
            limit: Max results

        Returns:
            List of matching anomalies
        """
        limit = limit or settings.vector_search_limit

        query_embedding = self.embedding_generator.embed_text(
            query, task_type="retrieval_query"
        )

        async with self.pg_pool.acquire() as conn:
            if source_type:
                results = await conn.fetch(
                    """
                    SELECT
                        id,
                        source_type,
                        source_id,
                        description,
                        metadata,
                        1 - (embedding <=> $1::vector) AS similarity
                    FROM anomaly_embeddings
                    WHERE source_type = $2
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                    """,
                    str(query_embedding),
                    source_type,
                    limit,
                )
            else:
                results = await conn.fetch(
                    """
                    SELECT
                        id,
                        source_type,
                        source_id,
                        description,
                        metadata,
                        1 - (embedding <=> $1::vector) AS similarity
                    FROM anomaly_embeddings
                    ORDER BY embedding <=> $1::vector
                    LIMIT $2
                    """,
                    str(query_embedding),
                    limit,
                )

        return [
            {
                "id": str(row["id"]),
                "source_type": row["source_type"],
                "source_id": row["source_id"],
                "description": row["description"],
                "metadata": row["metadata"],
                "similarity": float(row["similarity"]),
            }
            for row in results
        ]

    async def search_all(
        self,
        query: str,
        limit_per_type: int = 3,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search across all embedding types.

        Returns results from documents, track history, and anomalies.
        """
        documents = await self.search_documents(query, limit=limit_per_type)
        track_history = await self.search_track_history(query, limit=limit_per_type)
        anomalies = await self.search_anomalies(query, limit=limit_per_type)

        return {
            "documents": documents,
            "track_history": track_history,
            "anomalies": anomalies,
        }
