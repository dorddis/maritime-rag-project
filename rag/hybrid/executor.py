"""
Hybrid Executor - Combines SQL, Vector, and Redis results.

Implements:
- Query routing based on classification
- Parallel execution of SQL and Vector search
- Result fusion using Reciprocal Rank Fusion (RRF)
- Real-time data from Redis
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

import redis.asyncio as redis

from ..config import settings, get_redis_url, get_postgres_url
from ..router.query_router import QueryRouter, QueryType, QueryRoute
from ..sql_agent.agent import SQLAgent
from ..vector.retriever import VectorRetriever

logger = logging.getLogger(__name__)


class HybridExecutor:
    """
    Executes queries using the appropriate RAG strategy.

    Combines:
    - SQL Agent for structured queries
    - Vector Retriever for semantic queries
    - Redis for real-time data
    """

    def __init__(
        self,
        postgres_url: str = None,
        redis_url: str = None,
    ):
        self.postgres_url = postgres_url or get_postgres_url()
        self.redis_url = redis_url or get_redis_url()

        # Components (lazy initialized)
        self._router: Optional[QueryRouter] = None
        self._sql_agent: Optional[SQLAgent] = None
        self._vector_retriever: Optional[VectorRetriever] = None
        self._redis: Optional[redis.Redis] = None

    @property
    def router(self) -> QueryRouter:
        if self._router is None:
            self._router = QueryRouter()
        return self._router

    @property
    def sql_agent(self) -> SQLAgent:
        if self._sql_agent is None:
            self._sql_agent = SQLAgent(database_url=self.postgres_url)
        return self._sql_agent

    @property
    def vector_retriever(self) -> VectorRetriever:
        if self._vector_retriever is None:
            self._vector_retriever = VectorRetriever(postgres_url=self.postgres_url)
        return self._vector_retriever

    async def get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def close(self):
        """Close all connections."""
        if self._redis:
            await self._redis.close()
        if self._vector_retriever and self._vector_retriever.pg_pool:
            await self._vector_retriever.close()

    async def execute(
        self,
        query: str,
        include_realtime: bool = True,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """
        Execute a query using the appropriate strategy.

        Args:
            query: Natural language query
            include_realtime: Whether to fetch real-time data from Redis
            max_results: Maximum results to return

        Returns:
            {
                "query": str,
                "query_type": str,
                "route": QueryRoute,
                "structured_results": list,
                "semantic_results": list,
                "realtime_results": list,
                "fused_results": list,
                "explanation": str,
                "execution_time_ms": float
            }
        """
        start_time = datetime.now(timezone.utc)

        # Route query
        route = await self.router.route(query)

        result = {
            "query": query,
            "query_type": route.query_type.value,
            "route": route.model_dump(),
            "structured_results": [],
            "semantic_results": [],
            "realtime_results": [],
            "fused_results": [],
            "explanation": "",
            "execution_time_ms": 0,
        }

        try:
            if route.query_type == QueryType.STRUCTURED:
                result = await self._execute_structured(query, route, result, max_results)

            elif route.query_type == QueryType.SEMANTIC:
                result = await self._execute_semantic(query, route, result, max_results)

            elif route.query_type == QueryType.HYBRID:
                result = await self._execute_hybrid(query, route, result, max_results)

            elif route.query_type == QueryType.TEMPORAL:
                result = await self._execute_temporal(query, route, result, max_results)

            elif route.query_type == QueryType.GENERAL:
                result = await self._execute_general(query, route, result)

            # Add real-time data if requested
            if include_realtime:
                realtime = await self._fetch_realtime_tracks(route.extracted_filters)
                result["realtime_results"] = realtime

            # Fuse all results
            result["fused_results"] = self._fuse_results(
                result["structured_results"],
                result["semantic_results"],
                result["realtime_results"],
            )

        except Exception as e:
            logger.error(f"Execution error: {e}")
            result["explanation"] = f"Error: {str(e)}"

        # Calculate execution time
        end_time = datetime.now(timezone.utc)
        result["execution_time_ms"] = (end_time - start_time).total_seconds() * 1000

        return result

    async def _execute_structured(
        self,
        query: str,
        route: QueryRoute,
        result: Dict,
        max_results: int,
    ) -> Dict:
        """Execute structured SQL query."""
        sql_response = await self.sql_agent.query(query, route.extracted_filters)

        result["structured_results"] = sql_response.get("results", [])
        result["explanation"] = sql_response.get("explanation", "")

        if sql_response.get("sql"):
            result["explanation"] = f"SQL: {sql_response['sql']}\n\n{result['explanation']}"

        return result

    async def _execute_semantic(
        self,
        query: str,
        route: QueryRoute,
        result: Dict,
        max_results: int,
    ) -> Dict:
        """Execute semantic vector search."""
        await self.vector_retriever.connect()

        # Search all embedding types
        search_results = await self.vector_retriever.search_all(
            query,
            limit_per_type=max_results // 3,
        )

        # Combine all semantic results
        semantic_results = []
        for source, items in search_results.items():
            for item in items:
                item["source"] = source
                semantic_results.append(item)

        # Sort by similarity
        semantic_results.sort(key=lambda x: x.get("similarity", 0), reverse=True)

        result["semantic_results"] = semantic_results[:max_results]
        result["explanation"] = f"Found {len(semantic_results)} semantically similar results"

        return result

    async def _execute_hybrid(
        self,
        query: str,
        route: QueryRoute,
        result: Dict,
        max_results: int,
    ) -> Dict:
        """Execute hybrid query combining structured and semantic."""
        # Run SQL and Vector searches in parallel
        await self.vector_retriever.connect()

        sql_task = asyncio.create_task(
            self.sql_agent.query(query, route.extracted_filters)
        )

        semantic_query = route.semantic_query or query
        vector_task = asyncio.create_task(
            self.vector_retriever.search_all(semantic_query, limit_per_type=max_results // 3)
        )

        # Wait for both
        sql_response, vector_response = await asyncio.gather(sql_task, vector_task)

        # Process structured results
        result["structured_results"] = sql_response.get("results", [])

        # Process semantic results
        semantic_results = []
        for source, items in vector_response.items():
            for item in items:
                item["source"] = source
                semantic_results.append(item)
        semantic_results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        result["semantic_results"] = semantic_results[:max_results]

        # Build explanation
        result["explanation"] = (
            f"Hybrid search:\n"
            f"- Structured: {len(result['structured_results'])} results\n"
            f"- Semantic: {len(result['semantic_results'])} results\n"
            f"SQL: {sql_response.get('sql', 'N/A')}"
        )

        return result

    async def _execute_temporal(
        self,
        query: str,
        route: QueryRoute,
        result: Dict,
        max_results: int,
    ) -> Dict:
        """Execute temporal query with time focus."""
        # Add time constraints to SQL query
        time_filter = self._build_time_filter(route.time_range)

        # Modify query to include time
        temporal_query = query
        if time_filter and "WHERE" not in query.upper():
            temporal_query = f"{query} (filter: {time_filter})"

        sql_response = await self.sql_agent.query(temporal_query, route.extracted_filters)

        result["structured_results"] = sql_response.get("results", [])
        result["explanation"] = f"Temporal query with filter: {time_filter}\n{sql_response.get('explanation', '')}"

        return result

    async def _execute_general(
        self,
        query: str,
        route: QueryRoute,
        result: Dict,
    ) -> Dict:
        """Execute general conversational query."""
        try:
            # Simple LLM call for conversational response
            prompt = f"""You are an intelligent maritime assistant for a ship tracking system.
The system tracks ships using AIS, Satellite, and Radar data.
It can detect anomalies like dark ships, speed violations, and zone entries.

User Query: {query}

Provide a helpful, concise, and professional response.
If the user asks what you can do, explain that you can track ships, find anomalies, and answer questions about the maritime domain.
"""
            response = await self.router.model.generate_content_async(prompt)
            result["explanation"] = response.text
            result["structured_results"] = []  # No data for general chat
            
            return result
        except Exception as e:
            logger.error(f"General query failed: {e}")
            result["explanation"] = "I'm sorry, I couldn't process that request."
            return result

    async def _fetch_realtime_tracks(
        self,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch latest tracks from Redis fusion layer."""
        try:
            redis_client = await self.get_redis()

            # Get active track IDs
            track_ids = await redis_client.smembers("fusion:active_tracks")

            if not track_ids:
                return []

            tracks = []
            for track_id in list(track_ids)[:50]:  # Limit to 50 tracks
                track_data = await redis_client.hgetall(f"fusion:track:{track_id}")

                if not track_data:
                    continue

                # Apply filters if provided
                if filters and not self._matches_filters(track_data, filters):
                    continue

                tracks.append({
                    "track_id": track_id,
                    "source": "realtime",
                    **track_data,
                })

            return tracks

        except Exception as e:
            logger.warning(f"Failed to fetch realtime tracks: {e}")
            return []

    def _matches_filters(self, track: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if track matches filter criteria."""
        for key, value in filters.items():
            if key == "vessel_type":
                track_type = track.get("vessel_type", "").upper().replace("_", " ")
                filter_type = value.upper().replace("_", " ")
                # Skip filter if track has no vessel type (common in realtime data)
                if not track_type:
                    continue
                # Match if filter type is contained in track type or vice versa
                if filter_type not in track_type and track_type not in filter_type:
                    return False
            elif key == "speed_gt":
                try:
                    if float(track.get("speed_knots", 0)) <= value:
                        return False
                except:
                    return False
            elif key == "speed_lt":
                try:
                    if float(track.get("speed_knots", 0)) >= value:
                        return False
                except:
                    return False
            elif key == "is_dark_ship":
                if str(track.get("is_dark_ship", "false")).lower() != str(value).lower():
                    return False
            elif key == "port":
                # Filter by proximity to known port coordinates
                if not self._is_near_port(track, value):
                    return False
            elif key == "limit":
                # Limit is handled elsewhere, skip here
                continue

        return True

    def _is_near_port(self, track: Dict[str, Any], port_name: str, radius_km: float = 100) -> bool:
        """Check if track is within radius of a known port."""
        try:
            track_lat = float(track.get("latitude", 0))
            track_lon = float(track.get("longitude", 0))

            port_coords = settings.known_ports.get(port_name.lower())
            if not port_coords:
                return True  # If port not known, don't filter

            port_lat, port_lon = port_coords

            # Simple distance calculation (Haversine approximation)
            import math
            lat1, lon1 = math.radians(track_lat), math.radians(track_lon)
            lat2, lon2 = math.radians(port_lat), math.radians(port_lon)

            dlat = lat2 - lat1
            dlon = lon2 - lon1

            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a))

            # Earth radius in km
            distance_km = 6371 * c

            return distance_km <= radius_km
        except (ValueError, TypeError):
            return True  # If can't calculate, don't filter

    def _build_time_filter(self, time_range: Optional[Dict[str, Any]]) -> str:
        """Build SQL time filter from time range."""
        if not time_range:
            return ""

        value = time_range.get("value", "")

        if "hour" in value:
            hours = int(value.split()[0]) if value[0].isdigit() else 1
            return f"updated_at >= NOW() - INTERVAL '{hours} hours'"
        elif value == "today":
            return "updated_at >= CURRENT_DATE"
        elif value == "yesterday":
            return "updated_at >= CURRENT_DATE - INTERVAL '1 day' AND updated_at < CURRENT_DATE"
        elif "day" in value:
            days = int(value.split()[0]) if value[0].isdigit() else 1
            return f"updated_at >= NOW() - INTERVAL '{days} days'"

        return ""

    def _fuse_results(
        self,
        structured: List[Dict],
        semantic: List[Dict],
        realtime: List[Dict],
    ) -> List[Dict[str, Any]]:
        """
        Fuse results using Reciprocal Rank Fusion (RRF).

        RRF formula: score(doc) = sum(1 / (k + rank_i)) for each ranking i
        """
        k = settings.rrf_k
        weights = settings.fusion_weights

        # Create score map
        scores: Dict[str, float] = {}
        items: Dict[str, Dict] = {}

        # Score structured results
        for rank, item in enumerate(structured):
            item_id = self._get_item_id(item)
            rrf_score = weights.get("structured", 1.0) * (1 / (k + rank))
            scores[item_id] = scores.get(item_id, 0) + rrf_score
            items[item_id] = item

        # Score semantic results
        for rank, item in enumerate(semantic):
            item_id = self._get_item_id(item)
            rrf_score = weights.get("semantic", 0.8) * (1 / (k + rank))
            scores[item_id] = scores.get(item_id, 0) + rrf_score
            if item_id not in items:
                items[item_id] = item

        # Score realtime results
        for rank, item in enumerate(realtime):
            item_id = self._get_item_id(item)
            rrf_score = weights.get("realtime", 1.2) * (1 / (k + rank))
            scores[item_id] = scores.get(item_id, 0) + rrf_score
            if item_id not in items:
                items[item_id] = item

        # Sort by fused score
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        # Build final list
        fused = []
        for item_id in sorted_ids:
            item = items[item_id].copy()
            item["fusion_score"] = scores[item_id]
            fused.append(item)

        return fused

    def _get_item_id(self, item: Dict) -> str:
        """Get unique ID for an item (for deduplication)."""
        # Try various ID fields
        for field in ["track_id", "id", "mmsi", "ship_name"]:
            if field in item and item[field]:
                return str(item[field])

        # Fallback to hash of content
        return str(hash(str(sorted(item.items()))))


# Convenience function
async def hybrid_query(query: str) -> Dict[str, Any]:
    """
    Simple interface to execute a hybrid query.

    Example:
        result = await hybrid_query("Tankers near Mumbai with suspicious behavior")
    """
    executor = HybridExecutor()
    try:
        return await executor.execute(query)
    finally:
        await executor.close()
