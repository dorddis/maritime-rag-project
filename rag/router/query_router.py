"""
Query Router - Classifies user queries into execution strategies.

Uses Gemini 2.5 Flash to determine:
- STRUCTURED: SQL queries (filters, aggregations, exact lookups)
- SEMANTIC: Vector search (anomaly patterns, suspicious behavior)
- HYBRID: Combination of both
- TEMPORAL: Time-based queries with recency focus
"""

import json
import logging
import re
from enum import Enum
from typing import Dict, Any, Optional, List

from pydantic import BaseModel
import google.generativeai as genai

from ..config import settings, get_google_api_key

logger = logging.getLogger(__name__)


class QueryType(str, Enum):
    """Query classification types."""
    STRUCTURED = "structured"  # Use SQL agent
    SEMANTIC = "semantic"      # Use vector retriever
    HYBRID = "hybrid"          # Use both
    TEMPORAL = "temporal"      # Time-aware queries


class QueryRoute(BaseModel):
    """Query routing result."""
    query_type: QueryType
    confidence: float
    reasoning: str
    extracted_filters: Optional[Dict[str, Any]] = None
    time_range: Optional[Dict[str, Any]] = None
    semantic_query: Optional[str] = None  # For hybrid, the semantic component


class QueryRouter:
    """
    Routes user queries to appropriate RAG strategy.

    Uses Gemini to classify queries and extract filters.
    """

    def __init__(
        self,
        model_name: str = None,
        api_key: str = None,
    ):
        self.model_name = model_name or settings.gemini_model
        self.api_key = api_key or get_google_api_key()

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(self.model_name)

    def _build_routing_prompt(self, query: str) -> str:
        """Build the classification prompt."""
        return f"""You are a query classifier for a maritime ship tracking system.

Classify the following query into ONE of these types:

1. STRUCTURED: Queries requiring exact filters, aggregations, or database lookups
   - Has specific values: vessel type, speed numbers, ship names, port names
   - Asks for counts, lists, or specific data points
   - Examples: "Tankers near Mumbai", "Ships faster than 15 knots", "Count cargo ships"

2. SEMANTIC: Queries requiring semantic understanding or pattern matching
   - Uses vague/descriptive terms: suspicious, unusual, anomalous, similar
   - Asks about behavior or patterns without specific values
   - Examples: "Ships with suspicious behavior", "Unusual vessel patterns", "Anomalies like X"

3. HYBRID: Queries with BOTH structured filters AND semantic components
   - Has specific filters (type, location) AND vague/descriptive terms
   - Examples: "Tankers with unusual behavior near Mumbai", "Dark ships with suspicious patterns"

4. TEMPORAL: Queries with explicit time constraints as the primary focus
   - Time is the main filter: "last hour", "today", "yesterday", "recent"
   - Examples: "Ships detected in the last hour", "Recent dark ship events"

For the query, also extract:
- extracted_filters: Specific values mentioned (vessel_type, speed, port, mmsi, ship_name)
- time_range: Time constraints if any (e.g., "last_hour", "today", "last_24h")
- semantic_query: For HYBRID queries, the semantic/descriptive part

Query: "{query}"

Respond with valid JSON only:
{{
    "query_type": "structured|semantic|hybrid|temporal",
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation",
    "extracted_filters": {{"vessel_type": "...", "speed_gt": 15, "port": "Mumbai", ...}} or null,
    "time_range": {{"type": "relative", "value": "1 hour"}} or null,
    "semantic_query": "the descriptive/semantic part" or null
}}"""

    async def route(self, query: str) -> QueryRoute:
        """
        Classify query and determine routing strategy.

        Args:
            query: User's natural language query

        Returns:
            QueryRoute with classification and extracted info
        """
        prompt = self._build_routing_prompt(query)

        try:
            response = await self.model.generate_content_async(
                prompt,
                generation_config={
                    "temperature": 0.1,
                    "response_mime_type": "application/json",
                },
            )

            result = json.loads(response.text)

            return QueryRoute(
                query_type=QueryType(result.get("query_type", "structured")),
                confidence=float(result.get("confidence", 0.8)),
                reasoning=result.get("reasoning", ""),
                extracted_filters=result.get("extracted_filters"),
                time_range=result.get("time_range"),
                semantic_query=result.get("semantic_query"),
            )

        except Exception as e:
            logger.error(f"Query routing failed: {e}")
            # Fall back to rule-based routing
            return self._rule_based_route(query)

    def route_sync(self, query: str) -> QueryRoute:
        """Synchronous version of route()."""
        prompt = self._build_routing_prompt(query)

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.1,
                    "response_mime_type": "application/json",
                },
            )

            result = json.loads(response.text)

            return QueryRoute(
                query_type=QueryType(result.get("query_type", "structured")),
                confidence=float(result.get("confidence", 0.8)),
                reasoning=result.get("reasoning", ""),
                extracted_filters=result.get("extracted_filters"),
                time_range=result.get("time_range"),
                semantic_query=result.get("semantic_query"),
            )

        except Exception as e:
            logger.error(f"Query routing failed: {e}")
            return self._rule_based_route(query)

    def _rule_based_route(self, query: str) -> QueryRoute:
        """
        Fallback rule-based routing when LLM fails.

        Uses keyword matching to classify queries.
        """
        query_lower = query.lower()

        # Semantic keywords
        semantic_keywords = [
            "suspicious", "unusual", "anomaly", "anomalous", "pattern",
            "behavior", "similar", "like", "strange", "odd", "irregular"
        ]

        # Structured keywords (specific values)
        structured_keywords = [
            "tanker", "cargo", "container", "passenger", "fishing",
            "knots", "speed", "faster", "slower", "count", "how many",
            "near", "port", "mumbai", "chennai", "singapore", "dubai"
        ]

        # Temporal keywords
        temporal_keywords = [
            "last hour", "last day", "today", "yesterday", "recent",
            "in the past", "24 hours", "this week"
        ]

        has_semantic = any(kw in query_lower for kw in semantic_keywords)
        has_structured = any(kw in query_lower for kw in structured_keywords)
        has_temporal = any(kw in query_lower for kw in temporal_keywords)

        # Extract basic filters
        filters = self._extract_filters_rule_based(query)
        time_range = self._extract_time_range(query)

        # Determine type
        if has_semantic and has_structured:
            query_type = QueryType.HYBRID
            reasoning = "Query has both specific filters and semantic/descriptive terms"
        elif has_semantic:
            query_type = QueryType.SEMANTIC
            reasoning = "Query uses descriptive/semantic terms"
        elif has_temporal and not has_structured:
            query_type = QueryType.TEMPORAL
            reasoning = "Query focuses on time constraints"
        else:
            query_type = QueryType.STRUCTURED
            reasoning = "Query has specific filters or asks for structured data"

        return QueryRoute(
            query_type=query_type,
            confidence=0.7,  # Lower confidence for rule-based
            reasoning=reasoning,
            extracted_filters=filters if filters else None,
            time_range=time_range,
            semantic_query=query if has_semantic else None,
        )

    def _extract_filters_rule_based(self, query: str) -> Dict[str, Any]:
        """Extract filters using regex patterns."""
        query_lower = query.lower()
        filters = {}

        # Vessel types
        vessel_types = ["tanker", "cargo", "container", "passenger", "fishing", "bulk"]
        for vt in vessel_types:
            if vt in query_lower:
                filters["vessel_type"] = vt.upper()
                break

        # Speed patterns
        speed_match = re.search(r"(\d+)\s*knots?", query_lower)
        if speed_match:
            speed = int(speed_match.group(1))
            if "faster" in query_lower or "greater" in query_lower or ">" in query:
                filters["speed_gt"] = speed
            elif "slower" in query_lower or "less" in query_lower or "<" in query:
                filters["speed_lt"] = speed
            else:
                filters["speed"] = speed

        # Ports
        ports = ["mumbai", "chennai", "kochi", "singapore", "dubai", "colombo", "kandla"]
        for port in ports:
            if port in query_lower:
                filters["port"] = port.capitalize()
                break

        # Dark ship
        if "dark ship" in query_lower or "dark_ship" in query_lower:
            filters["is_dark_ship"] = True

        return filters

    def _extract_time_range(self, query: str) -> Optional[Dict[str, Any]]:
        """Extract time range from query."""
        query_lower = query.lower()

        if "last hour" in query_lower or "past hour" in query_lower:
            return {"type": "relative", "value": "1 hour"}
        elif "last 2 hour" in query_lower:
            return {"type": "relative", "value": "2 hours"}
        elif "today" in query_lower:
            return {"type": "relative", "value": "today"}
        elif "yesterday" in query_lower:
            return {"type": "relative", "value": "yesterday"}
        elif "24 hour" in query_lower or "last day" in query_lower:
            return {"type": "relative", "value": "24 hours"}
        elif "this week" in query_lower or "last week" in query_lower:
            return {"type": "relative", "value": "7 days"}

        return None


# Convenience function
async def classify_query(query: str) -> QueryRoute:
    """Quick interface to classify a query."""
    router = QueryRouter()
    return await router.route(query)
