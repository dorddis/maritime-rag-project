"""
RAG API Endpoints

FastAPI router for hybrid RAG queries:
- POST /api/rag/query - Main hybrid query endpoint
- GET /api/rag/documents/search - Direct vector search
- POST /api/rag/sql - Direct SQL agent query
- GET /api/rag/health - Health check
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from rag.hybrid.executor import HybridExecutor
from rag.router.query_router import QueryRouter, QueryType
from rag.vector.retriever import VectorRetriever
from rag.sql_agent.agent import SQLAgent
from rag.config import settings

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/rag", tags=["RAG"])

# Lazy-initialized components
_executor: Optional[HybridExecutor] = None
_router: Optional[QueryRouter] = None
_vector_retriever: Optional[VectorRetriever] = None
_sql_agent: Optional[SQLAgent] = None


def get_executor() -> HybridExecutor:
    """Get or create hybrid executor."""
    global _executor
    if _executor is None:
        _executor = HybridExecutor()
    return _executor


def get_query_router() -> QueryRouter:
    """Get or create query router."""
    global _router
    if _router is None:
        _router = QueryRouter()
    return _router


def get_vector_retriever() -> VectorRetriever:
    """Get or create vector retriever."""
    global _vector_retriever
    if _vector_retriever is None:
        _vector_retriever = VectorRetriever()
    return _vector_retriever


def get_sql_agent() -> SQLAgent:
    """Get or create SQL agent."""
    global _sql_agent
    if _sql_agent is None:
        _sql_agent = SQLAgent()
    return _sql_agent


# ============ Request/Response Models ============

class QueryRequest(BaseModel):
    """Request model for hybrid query."""
    query: str = Field(..., description="Natural language query", min_length=3)
    include_realtime: bool = Field(default=True, description="Include real-time Redis data")
    max_results: int = Field(default=10, ge=1, le=100, description="Maximum results per source")


class QueryResponse(BaseModel):
    """Response model for hybrid query."""
    query: str
    query_type: str
    route: Dict[str, Any]
    structured_results: List[Dict[str, Any]]
    semantic_results: List[Dict[str, Any]]
    realtime_results: List[Dict[str, Any]]
    fused_results: List[Dict[str, Any]]
    explanation: str
    execution_time_ms: float


class DocumentSearchRequest(BaseModel):
    """Request model for document search."""
    query: str = Field(..., description="Search query", min_length=2)
    document_type: Optional[str] = Field(default=None, description="Filter by document type")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum results")
    similarity_threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="Minimum similarity")


class SQLQueryRequest(BaseModel):
    """Request model for SQL query."""
    question: str = Field(..., description="Natural language question", min_length=3)
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Pre-extracted filters")


class RouteRequest(BaseModel):
    """Request model for query routing."""
    query: str = Field(..., description="Query to classify", min_length=3)


class RouteResponse(BaseModel):
    """Response model for query routing."""
    query_type: str
    confidence: float
    reasoning: str
    extracted_filters: Optional[Dict[str, Any]]
    time_range: Optional[Dict[str, Any]]
    semantic_query: Optional[str]


# ============ API Endpoints ============

@router.get("/health")
async def health_check():
    """Health check endpoint for RAG system."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "config": {
            "postgres_configured": bool(settings.postgres_url),
            "redis_configured": bool(settings.redis_url),
            "gemini_model": settings.gemini_model,
            "embedding_model": settings.embedding_model,
        }
    }


@router.post("/query", response_model=QueryResponse)
async def hybrid_query(request: QueryRequest):
    """
    Execute a hybrid RAG query.

    Routes the query to appropriate strategy (SQL, Vector, or Both)
    and returns fused results from all sources.

    Examples:
    - "Tankers near Mumbai faster than 15 knots" -> SQL query
    - "Ships with suspicious behavior" -> Vector search
    - "Dark ships with unusual patterns near Chennai" -> Hybrid
    """
    try:
        executor = get_executor()
        result = await executor.execute(
            query=request.query,
            include_realtime=request.include_realtime,
            max_results=request.max_results,
        )
        return result
    except Exception as e:
        logger.error(f"Hybrid query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/route", response_model=RouteResponse)
async def route_query(request: RouteRequest):
    """
    Classify a query without executing it.

    Returns the query type, confidence, and extracted information.
    Useful for debugging or understanding query routing.
    """
    try:
        router_instance = get_query_router()
        route = await router_instance.route(request.query)
        return RouteResponse(
            query_type=route.query_type.value,
            confidence=route.confidence,
            reasoning=route.reasoning,
            extracted_filters=route.extracted_filters,
            time_range=route.time_range,
            semantic_query=route.semantic_query,
        )
    except Exception as e:
        logger.error(f"Query routing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/search")
async def search_documents(request: DocumentSearchRequest):
    """
    Direct semantic search over document embeddings.

    Bypasses query routing - always uses vector search.
    Useful for pure semantic similarity queries.
    """
    try:
        retriever = get_vector_retriever()
        await retriever.connect()

        results = await retriever.search_documents(
            query=request.query,
            document_type=request.document_type,
            limit=request.limit,
            similarity_threshold=request.similarity_threshold,
        )

        return {
            "query": request.query,
            "document_type": request.document_type,
            "results": results,
            "count": len(results),
        }
    except Exception as e:
        logger.error(f"Document search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/search")
async def search_documents_get(
    query: str = Query(..., min_length=2, description="Search query"),
    document_type: Optional[str] = Query(default=None, description="Filter by type"),
    limit: int = Query(default=10, ge=1, le=50, description="Max results"),
):
    """GET version of document search for easier testing."""
    return await search_documents(DocumentSearchRequest(
        query=query,
        document_type=document_type,
        limit=limit,
    ))


@router.post("/sql")
async def sql_query(request: SQLQueryRequest):
    """
    Direct SQL agent query.

    Converts natural language to SQL and executes against PostgreSQL.
    Bypasses query routing - always uses SQL agent.
    """
    try:
        agent = get_sql_agent()
        result = await agent.query(
            question=request.question,
            filters=request.filters,
        )
        return result
    except Exception as e:
        logger.error(f"SQL query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/anomalies/search")
async def search_anomalies(
    query: str = Query(..., min_length=2, description="Search query"),
    source_type: Optional[str] = Query(default=None, description="Anomaly source type"),
    limit: int = Query(default=10, ge=1, le=50, description="Max results"),
):
    """
    Search anomaly embeddings.

    Find similar anomaly patterns based on semantic similarity.
    """
    try:
        retriever = get_vector_retriever()
        await retriever.connect()

        results = await retriever.search_anomalies(
            query=query,
            source_type=source_type,
            limit=limit,
        )

        return {
            "query": query,
            "source_type": source_type,
            "results": results,
            "count": len(results),
        }
    except Exception as e:
        logger.error(f"Anomaly search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tracks/search")
async def search_track_history(
    query: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(default=10, ge=1, le=50, description="Max results"),
):
    """
    Search track history embeddings.

    Find track segments matching semantic description.
    Example: "vessels that went dark near Mumbai"
    """
    try:
        retriever = get_vector_retriever()
        await retriever.connect()

        results = await retriever.search_track_history(
            query=query,
            limit=limit,
        )

        return {
            "query": query,
            "results": results,
            "count": len(results),
        }
    except Exception as e:
        logger.error(f"Track history search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schema")
async def get_database_schema():
    """
    Get database schema information.

    Returns table info for debugging SQL generation.
    """
    try:
        agent = get_sql_agent()
        return {
            "tables": agent.get_usable_tables(),
            "table_info": agent.get_table_info(),
        }
    except Exception as e:
        logger.error(f"Schema fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ Cleanup ============

async def cleanup_rag():
    """Cleanup RAG resources on shutdown."""
    global _executor, _vector_retriever

    if _executor:
        await _executor.close()
        _executor = None

    if _vector_retriever:
        await _vector_retriever.close()
        _vector_retriever = None

    logger.info("RAG resources cleaned up")
