"""
Embedding Generator using Google Gemini

Generates vector embeddings for:
- Documents (ship reports, port reports, anomaly alerts)
- Track history summaries
- Anomaly descriptions

Uses Gemini embedding-001 model (768 dimensions).
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
import os

import google.generativeai as genai
import asyncpg

from ..config import settings, get_google_api_key, get_postgres_url

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """
    Generate embeddings using Gemini and store in PostgreSQL.
    """

    def __init__(
        self,
        api_key: str = None,
        model_name: str = None,
        postgres_url: str = None,
    ):
        self.api_key = api_key or get_google_api_key()
        self.model_name = model_name or settings.embedding_model
        self.postgres_url = postgres_url or get_postgres_url()
        self.pg_pool: Optional[asyncpg.Pool] = None

        # Configure Gemini
        genai.configure(api_key=self.api_key)

    async def connect(self):
        """Initialize PostgreSQL connection pool."""
        self.pg_pool = await asyncpg.create_pool(
            self.postgres_url,
            min_size=2,
            max_size=10,
        )
        logger.info("EmbeddingGenerator connected to PostgreSQL")

    async def close(self):
        """Close connections."""
        if self.pg_pool:
            await self.pg_pool.close()

    def embed_text(self, text: str, task_type: str = "retrieval_document") -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed
            task_type: One of "retrieval_document", "retrieval_query", "semantic_similarity"

        Returns:
            List of 768 floats (embedding vector)
        """
        result = genai.embed_content(
            model=self.model_name,
            content=text,
            task_type=task_type,
        )
        return result["embedding"]

    def embed_texts(
        self,
        texts: List[str],
        task_type: str = "retrieval_document",
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts (batched).

        Args:
            texts: List of texts to embed
            task_type: Embedding task type

        Returns:
            List of embedding vectors
        """
        embeddings = []
        batch_size = settings.embedding_batch_size

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            for text in batch:
                try:
                    embedding = self.embed_text(text, task_type)
                    embeddings.append(embedding)
                except Exception as e:
                    logger.error(f"Failed to embed text: {e}")
                    # Return zero vector on failure
                    embeddings.append([0.0] * settings.embedding_dimensions)

        return embeddings

    async def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a search query.

        Uses "retrieval_query" task type for better search performance.
        """
        return self.embed_text(query, task_type="retrieval_query")

    async def store_document_embedding(
        self,
        content: str,
        document_type: str,
        metadata: Dict[str, Any] = None,
    ) -> str:
        """
        Generate embedding for a document and store in PostgreSQL.

        Args:
            content: Document text
            document_type: Type (ship_report, port_report, anomaly_alert, etc.)
            metadata: Optional metadata dict

        Returns:
            UUID of inserted record
        """
        embedding = self.embed_text(content)

        async with self.pg_pool.acquire() as conn:
            result = await conn.fetchval(
                """
                INSERT INTO document_embeddings (content, document_type, metadata, embedding)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                content,
                document_type,
                metadata or {},
                str(embedding),  # pgvector accepts string representation
            )

        logger.debug(f"Stored document embedding: {result}")
        return str(result)

    async def store_document_embeddings_batch(
        self,
        documents: List[Dict[str, Any]],
    ) -> int:
        """
        Store multiple document embeddings in batch.

        Args:
            documents: List of dicts with keys: content, document_type, metadata

        Returns:
            Number of documents stored
        """
        if not documents:
            return 0

        # Generate all embeddings
        texts = [doc["content"] for doc in documents]
        embeddings = self.embed_texts(texts)

        # Prepare records
        records = []
        for doc, embedding in zip(documents, embeddings):
            records.append((
                doc["content"],
                doc.get("document_type", "unknown"),
                doc.get("metadata", {}),
                str(embedding),
            ))

        # Batch insert
        async with self.pg_pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO document_embeddings (content, document_type, metadata, embedding)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT DO NOTHING
                """,
                records,
            )

        logger.info(f"Stored {len(records)} document embeddings")
        return len(records)

    async def store_track_history_embedding(
        self,
        track_id: str,
        description: str,
        window_start: str,
        window_end: str,
        metadata: Dict[str, Any] = None,
    ) -> str:
        """
        Store embedding for a track history segment.

        Args:
            track_id: Track identifier
            description: Text description of the track segment
            window_start: Start timestamp (ISO format)
            window_end: End timestamp (ISO format)
            metadata: Optional stats (avg_speed, sensors_used, etc.)

        Returns:
            UUID of inserted record
        """
        embedding = self.embed_text(description)

        async with self.pg_pool.acquire() as conn:
            result = await conn.fetchval(
                """
                INSERT INTO track_history_embeddings
                (track_id, description, window_start, window_end, metadata, embedding)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                track_id,
                description,
                window_start,
                window_end,
                metadata or {},
                str(embedding),
            )

        return str(result)

    async def store_anomaly_embedding(
        self,
        source_type: str,
        source_id: str,
        description: str,
        metadata: Dict[str, Any] = None,
    ) -> str:
        """
        Store embedding for an anomaly description.

        Args:
            source_type: Type of anomaly (dark_ship, speed_anomaly, etc.)
            source_id: ID of source record
            description: Text description of the anomaly
            metadata: Optional metadata

        Returns:
            UUID of inserted record
        """
        embedding = self.embed_text(description)

        async with self.pg_pool.acquire() as conn:
            result = await conn.fetchval(
                """
                INSERT INTO anomaly_embeddings
                (source_type, source_id, description, metadata, embedding)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                source_type,
                source_id,
                description,
                metadata or {},
                str(embedding),
            )

        return str(result)


async def seed_embeddings_from_json(json_path: str):
    """
    Seed document embeddings from maritime_documents.json.

    This is a one-time setup to populate initial embeddings.
    """
    import json

    # Load documents
    with open(json_path, "r") as f:
        documents = json.load(f)

    logger.info(f"Loading {len(documents)} documents from {json_path}")

    # Initialize generator
    generator = EmbeddingGenerator()
    await generator.connect()

    try:
        # Prepare documents for batch insert
        docs_to_embed = []
        for doc in documents:
            docs_to_embed.append({
                "content": doc["content"],
                "document_type": doc.get("metadata", {}).get("type", "unknown"),
                "metadata": doc.get("metadata", {}),
            })

        # Store embeddings
        count = await generator.store_document_embeddings_batch(docs_to_embed)
        logger.info(f"Seeded {count} document embeddings")

    finally:
        await generator.close()


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    # Default path to maritime_documents.json
    json_path = sys.argv[1] if len(sys.argv) > 1 else "maritime_documents.json"

    asyncio.run(seed_embeddings_from_json(json_path))
