"""
RAG Chat API Endpoints with SSE Streaming

FastAPI router for streaming chat interface:
- POST /api/rag/chat/stream - SSE streaming endpoint for pipeline visualization
- POST /api/rag/chat/query - Non-streaming query (fallback)

Streams events for each pipeline step:
- routing: Query classification result
- sql_start/sql_complete: SQL generation and execution
- vector_start/vector_complete: Semantic search
- realtime: Redis real-time data
- fusion: RRF result fusion
- answer: Final natural language response
- done: Stream complete
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any, AsyncGenerator
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from rag.hybrid.executor import HybridExecutor
from rag.router.query_router import QueryRouter, QueryType, QueryRoute
from rag.sql_agent.agent import SQLAgent
from rag.vector.retriever import VectorRetriever
from rag.config import settings

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/rag/chat", tags=["Chat"])

# Lazy-initialized components (shared with rag_endpoints)
_executor: Optional[HybridExecutor] = None
_router: Optional[QueryRouter] = None
_sql_agent: Optional[SQLAgent] = None
_vector_retriever: Optional[VectorRetriever] = None


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


def get_sql_agent() -> SQLAgent:
    """Get or create SQL agent."""
    global _sql_agent
    if _sql_agent is None:
        _sql_agent = SQLAgent()
    return _sql_agent


def get_vector_retriever() -> VectorRetriever:
    """Get or create vector retriever."""
    global _vector_retriever
    if _vector_retriever is None:
        _vector_retriever = VectorRetriever()
    return _vector_retriever


# ============ Request/Response Models ============

class ChatRequest(BaseModel):
    """Request model for chat query."""
    query: str = Field(..., description="Natural language query", min_length=3)
    include_realtime: bool = Field(default=True, description="Include real-time Redis data")
    max_results: int = Field(default=10, ge=1, le=100, description="Maximum results per source")


# ============ SSE Event Helpers ============

def format_sse_event(event: str, data: Dict[str, Any]) -> str:
    """Format data as Server-Sent Event."""
    json_data = json.dumps(data, default=str)
    return f"event: {event}\ndata: {json_data}\n\n"


# ============ Streaming Pipeline Executor ============

async def stream_pipeline(
    query: str,
    include_realtime: bool = True,
    max_results: int = 10,
) -> AsyncGenerator[str, None]:
    """
    Generator that yields SSE events for each pipeline step.

    Wraps HybridExecutor to emit events as each step completes.
    """
    start_time = datetime.now(timezone.utc)
    step_times: Dict[str, float] = {}

    try:
        # ============ Step 1: Route Query ============
        routing_start = datetime.now(timezone.utc)
        yield format_sse_event("routing", {
            "status": "start",
            "timestamp": routing_start.isoformat(),
        })

        router_instance = get_query_router()
        route = await router_instance.route(query)

        routing_time = (datetime.now(timezone.utc) - routing_start).total_seconds() * 1000
        step_times["routing"] = routing_time

        yield format_sse_event("routing", {
            "status": "complete",
            "query_type": route.query_type.value,
            "confidence": route.confidence,
            "reasoning": route.reasoning,
            "extracted_filters": route.extracted_filters,
            "time_range": route.time_range,
            "semantic_query": route.semantic_query,
            "execution_time_ms": routing_time,
        })

        # Initialize result containers
        structured_results = []
        semantic_results = []
        realtime_results = []
        sql_query = None
        explanation = ""

        # ============ Step 2: Execute based on query type ============

        if route.query_type in [QueryType.STRUCTURED, QueryType.TEMPORAL, QueryType.HYBRID]:
            # SQL Query
            sql_start = datetime.now(timezone.utc)
            yield format_sse_event("sql_start", {
                "status": "start",
                "timestamp": sql_start.isoformat(),
            })

            try:
                sql_agent = get_sql_agent()
                sql_response = await sql_agent.query(query, route.extracted_filters)

                sql_time = (datetime.now(timezone.utc) - sql_start).total_seconds() * 1000
                step_times["sql"] = sql_time

                structured_results = sql_response.get("results", [])
                sql_query = sql_response.get("sql")
                explanation = sql_response.get("explanation", "")

                yield format_sse_event("sql_complete", {
                    "status": "complete",
                    "sql": sql_query,
                    "row_count": sql_response.get("row_count", len(structured_results)),
                    "results": structured_results[:5],  # Send first 5 for preview
                    "total_results": len(structured_results),
                    "explanation": explanation[:500] if explanation else None,
                    "execution_time_ms": sql_time,
                    "error": sql_response.get("error"),
                })
            except Exception as e:
                logger.error(f"SQL execution error: {e}")
                yield format_sse_event("sql_complete", {
                    "status": "error",
                    "error": str(e),
                    "execution_time_ms": (datetime.now(timezone.utc) - sql_start).total_seconds() * 1000,
                })

        if route.query_type in [QueryType.SEMANTIC, QueryType.HYBRID]:
            # Vector Search
            vector_start = datetime.now(timezone.utc)
            semantic_query = route.semantic_query or query

            yield format_sse_event("vector_start", {
                "status": "start",
                "query": semantic_query,
                "timestamp": vector_start.isoformat(),
            })

            try:
                retriever = get_vector_retriever()
                await retriever.connect()

                search_results = await retriever.search_all(
                    semantic_query,
                    limit_per_type=max_results // 3,
                )

                vector_time = (datetime.now(timezone.utc) - vector_start).total_seconds() * 1000
                step_times["vector"] = vector_time

                # Process semantic results
                for source, items in search_results.items():
                    for item in items:
                        item["source"] = source
                        semantic_results.append(item)

                # Sort by similarity
                semantic_results.sort(key=lambda x: x.get("similarity", 0), reverse=True)

                # Get top similarities for display
                top_similarities = [r.get("similarity", 0) for r in semantic_results[:5]]
                sources = list(set(r.get("source", "unknown") for r in semantic_results))

                yield format_sse_event("vector_complete", {
                    "status": "complete",
                    "query": semantic_query,
                    "result_count": len(semantic_results),
                    "top_similarities": top_similarities,
                    "sources": sources,
                    "results": semantic_results[:5],  # Send first 5 for preview
                    "execution_time_ms": vector_time,
                })
            except Exception as e:
                logger.error(f"Vector search error: {e}")
                yield format_sse_event("vector_complete", {
                    "status": "error",
                    "error": str(e),
                    "execution_time_ms": (datetime.now(timezone.utc) - vector_start).total_seconds() * 1000,
                })

        # ============ Step 3: Real-time Data ============
        if include_realtime:
            realtime_start = datetime.now(timezone.utc)

            try:
                executor = get_executor()
                realtime_results = await executor._fetch_realtime_tracks(route.extracted_filters)

                realtime_time = (datetime.now(timezone.utc) - realtime_start).total_seconds() * 1000
                step_times["realtime"] = realtime_time

                yield format_sse_event("realtime", {
                    "status": "complete",
                    "track_count": len(realtime_results),
                    "filters_applied": route.extracted_filters,
                    "results": realtime_results[:5],  # Send first 5 for preview
                    "execution_time_ms": realtime_time,
                })
            except Exception as e:
                logger.error(f"Realtime fetch error: {e}")
                yield format_sse_event("realtime", {
                    "status": "error",
                    "error": str(e),
                    "track_count": 0,
                })

        # ============ Step 4: Result Fusion ============
        fusion_start = datetime.now(timezone.utc)

        executor = get_executor()
        fused_results = executor._fuse_results(
            structured_results,
            semantic_results,
            realtime_results,
        )

        fusion_time = (datetime.now(timezone.utc) - fusion_start).total_seconds() * 1000
        step_times["fusion"] = fusion_time

        # Calculate breakdown
        breakdown = {
            "structured": len(structured_results),
            "semantic": len(semantic_results),
            "realtime": len(realtime_results),
        }

        yield format_sse_event("fusion", {
            "status": "complete",
            "method": "RRF",
            "rrf_k": settings.rrf_k,
            "weights": settings.fusion_weights,
            "total_results": len(fused_results),
            "breakdown": breakdown,
            "results": fused_results[:max_results],  # Send top results
            "execution_time_ms": fusion_time,
        })

        # ============ Step 5: Generate Answer ============
        answer_start = datetime.now(timezone.utc)

        # Build answer summary
        answer = _build_answer_summary(
            query=query,
            route=route,
            structured_count=len(structured_results),
            semantic_count=len(semantic_results),
            realtime_count=len(realtime_results),
            fused_count=len(fused_results),
            sql_query=sql_query,
            explanation=explanation,
        )

        answer_time = (datetime.now(timezone.utc) - answer_start).total_seconds() * 1000
        step_times["answer"] = answer_time

        yield format_sse_event("answer", {
            "status": "complete",
            "content": answer,
            "execution_time_ms": answer_time,
        })

        # ============ Done ============
        total_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

        yield format_sse_event("done", {
            "status": "complete",
            "total_time_ms": total_time,
            "step_times": step_times,
            "result_count": len(fused_results),
        })

    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        yield format_sse_event("error", {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


def _build_answer_summary(
    query: str,
    route: QueryRoute,
    structured_count: int,
    semantic_count: int,
    realtime_count: int,
    fused_count: int,
    sql_query: Optional[str],
    explanation: str,
) -> str:
    """Build a natural language answer summary."""
    parts = []

    # Query type explanation
    type_explanations = {
        QueryType.STRUCTURED: "database query",
        QueryType.SEMANTIC: "semantic search",
        QueryType.HYBRID: "combined database and semantic search",
        QueryType.TEMPORAL: "time-based query",
    }

    parts.append(f"Query classified as **{route.query_type.value}** ({type_explanations.get(route.query_type, 'unknown')}).")

    # Results summary
    if fused_count > 0:
        parts.append(f"Found **{fused_count} results** after fusion:")
        if structured_count > 0:
            parts.append(f"- {structured_count} from database")
        if semantic_count > 0:
            parts.append(f"- {semantic_count} from semantic search")
        if realtime_count > 0:
            parts.append(f"- {realtime_count} from real-time tracking")
    else:
        parts.append("No results found matching your query.")

    # Add filters if extracted
    if route.extracted_filters:
        filter_str = ", ".join(f"{k}={v}" for k, v in route.extracted_filters.items())
        parts.append(f"\nFilters applied: {filter_str}")

    return "\n".join(parts)


# ============ API Endpoints ============

@router.post("/stream")
async def chat_stream(request: ChatRequest, req: Request):
    """
    SSE streaming endpoint for chat queries.

    Streams pipeline execution events as each step completes:
    - routing: Query classification
    - sql_start/sql_complete: SQL execution
    - vector_start/vector_complete: Vector search
    - realtime: Real-time Redis data
    - fusion: RRF result fusion
    - answer: Final response
    - done: Stream complete

    Example usage with curl:
        curl -N -X POST http://localhost:8000/api/rag/chat/stream \\
            -H "Content-Type: application/json" \\
            -d '{"query": "Show tankers near Mumbai"}'
    """
    async def event_generator():
        async for event in stream_pipeline(
            query=request.query,
            include_realtime=request.include_realtime,
            max_results=request.max_results,
        ):
            # Check if client disconnected
            if await req.is_disconnected():
                logger.info("Client disconnected, stopping stream")
                break
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/query")
async def chat_query(request: ChatRequest):
    """
    Non-streaming chat query endpoint (fallback).

    Returns the complete result without streaming.
    Use /stream for real-time pipeline visualization.
    """
    try:
        executor = get_executor()
        result = await executor.execute(
            query=request.query,
            include_realtime=request.include_realtime,
            max_results=request.max_results,
        )

        # Add answer summary
        route = QueryRoute(
            query_type=QueryType(result["query_type"]),
            confidence=result["route"].get("confidence", 0),
            reasoning=result["route"].get("reasoning", ""),
            extracted_filters=result["route"].get("extracted_filters"),
            time_range=result["route"].get("time_range"),
            semantic_query=result["route"].get("semantic_query"),
        )

        result["answer"] = _build_answer_summary(
            query=request.query,
            route=route,
            structured_count=len(result.get("structured_results", [])),
            semantic_count=len(result.get("semantic_results", [])),
            realtime_count=len(result.get("realtime_results", [])),
            fused_count=len(result.get("fused_results", [])),
            sql_query=result.get("explanation", "").split("SQL:")[-1].split("\n")[0] if "SQL:" in result.get("explanation", "") else None,
            explanation=result.get("explanation", ""),
        )

        return result
    except Exception as e:
        logger.error(f"Chat query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def chat_health():
    """Health check for chat endpoints."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "streaming_enabled": True,
    }
