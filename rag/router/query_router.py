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
    GENERAL = "general"        # General knowledge/conversation


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
        # Use router-specific model (gemini-2.5-pro) for better classification accuracy
        self.model_name = model_name or settings.router_model
        self.api_key = api_key or get_google_api_key()

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(self.model_name)

    def _build_routing_prompt(self, query: str) -> str:
        """Build the classification prompt with full schema context."""
        return f"""You are a query classifier for a maritime ship tracking system.

## SYSTEM CONTEXT

You have access to a ship tracking database with the following data:

### Available Fields for Filtering:
| Field | Type | Valid Values | Description |
|-------|------|--------------|-------------|
| vessel_type | string | TANKER, CARGO, CONTAINER, PASSENGER, FISHING, BULK_CARRIER | Type of vessel |
| is_dark_ship | boolean | true, false | Ship with AIS transponder disabled (not broadcasting location) |
| speed_knots | number | 0-50 | Current speed in nautical knots |
| port | string | Mumbai, Chennai, Kochi, Singapore, Dubai, Colombo, Kandla, Visakhapatnam | Nearest port |
| ship_name | string | any | Vessel name (e.g., "ARABIAN STAR") |
| mmsi | string | 9-digit number | Maritime Mobile Service Identity |
| limit | number | 1-100 | Maximum results to return |

### Domain Terminology Mapping:
- "dark ship" / "dark vessel" / "AIS off" / "stealth" → is_dark_ship: true
- "tanker" / "oil tanker" → vessel_type: "TANKER"
- "cargo" / "cargo ship" / "freighter" → vessel_type: "CARGO"
- "container" / "container ship" → vessel_type: "CONTAINER"
- "fishing" / "fishing boat" / "trawler" → vessel_type: "FISHING"
- "bulk" / "bulk carrier" → vessel_type: "BULK_CARRIER"
- "faster than X knots" / "speed > X" / "speeding" → speed_gt: X
- "slower than X knots" / "speed < X" → speed_lt: X
- "near Mumbai" / "at Mumbai port" / "Mumbai area" → port: "Mumbai"
- "show 5" / "top 5" / "5 ships" / "limit 5" → limit: 5
- "recently" / "latest" / "last hour" / "just detected" → time_range with value

## QUERY TYPES

Classify into ONE of these types:

### 1. STRUCTURED
Database queries with specific, exact filters. No vague or descriptive terms.
- User wants specific data points, counts, or filtered lists
- All filters have concrete values

Examples with EXACT JSON output:

Query: "Show me tankers near Mumbai"
{{"query_type": "structured", "confidence": 0.95, "reasoning": "Specific vessel type and port filter", "extracted_filters": {{"vessel_type": "TANKER", "port": "Mumbai"}}, "time_range": null, "semantic_query": null}}

Query: "List 5 dark ships"
{{"query_type": "structured", "confidence": 0.95, "reasoning": "Specific filter for dark ships with limit", "extracted_filters": {{"is_dark_ship": true, "limit": 5}}, "time_range": null, "semantic_query": null}}

Query: "Ships faster than 20 knots"
{{"query_type": "structured", "confidence": 0.95, "reasoning": "Speed threshold filter", "extracted_filters": {{"speed_gt": 20}}, "time_range": null, "semantic_query": null}}

Query: "Find cargo ships at Chennai port"
{{"query_type": "structured", "confidence": 0.95, "reasoning": "Vessel type and port filter", "extracted_filters": {{"vessel_type": "CARGO", "port": "Chennai"}}, "time_range": null, "semantic_query": null}}

### 2. SEMANTIC
Pattern matching queries using vague, descriptive, or behavioral terms. No specific filter values.
- User describes behavior or patterns without exact criteria
- Uses words like: suspicious, unusual, anomalous, erratic, strange, similar, like

Examples:
- "Ships with suspicious behavior" → SEMANTIC, semantic_query: "suspicious behavior patterns"
- "Any unusual vessel movements?" → SEMANTIC, semantic_query: "unusual vessel movements"
- "Anomalies in shipping patterns" → SEMANTIC, semantic_query: "shipping pattern anomalies"
- "Erratic navigation patterns" → SEMANTIC, semantic_query: "erratic navigation"

### 3. HYBRID
Queries combining BOTH specific filters AND semantic/descriptive components.
- Has concrete filter values (type, port, speed) AND vague behavioral terms

Examples:
- "Tankers with suspicious behavior near Mumbai" → HYBRID, filters: {{vessel_type: "TANKER", port: "Mumbai"}}, semantic_query: "suspicious behavior"
- "Dark ships acting erratically" → HYBRID, filters: {{is_dark_ship: true}}, semantic_query: "erratic behavior"
- "Cargo ships with unusual speed patterns" → HYBRID, filters: {{vessel_type: "CARGO"}}, semantic_query: "unusual speed patterns"

### 4. TEMPORAL
Queries where TIME is the primary focus. Often combined with other filters.
- Explicit time words: recently, latest, last hour, today, yesterday, past X hours
- Recency is the main constraint

Examples with EXACT JSON output:

Query: "Recently detected dark ships"
{{"query_type": "temporal", "confidence": 0.95, "reasoning": "Time-focused query with dark ship filter", "extracted_filters": {{"is_dark_ship": true}}, "time_range": {{"type": "relative", "value": "recent"}}, "semantic_query": null}}

Query: "Ships detected in the last hour"
{{"query_type": "temporal", "confidence": 0.95, "reasoning": "Explicit time constraint", "extracted_filters": null, "time_range": {{"type": "relative", "value": "1 hour"}}, "semantic_query": null}}

Query: "Show me recently detected 5 dark ships"
{{"query_type": "temporal", "confidence": 0.95, "reasoning": "Time-focused with dark ship filter and limit", "extracted_filters": {{"is_dark_ship": true, "limit": 5}}, "time_range": {{"type": "relative", "value": "recent"}}, "semantic_query": null}}

Query: "Today's tanker movements"
{{"query_type": "temporal", "confidence": 0.95, "reasoning": "Time-focused with vessel type filter", "extracted_filters": {{"vessel_type": "TANKER"}}, "time_range": {{"type": "relative", "value": "today"}}, "semantic_query": null}}

### 5. GENERAL
Conversational queries NOT requiring database access.
- Greetings, help requests, explanations, meta-questions about the system
- Questions about concepts (what is AIS, what is a dark ship)
- No data lookup needed

Examples:
- "Hello" → GENERAL
- "What can you do?" → GENERAL
- "What is a dark ship?" → GENERAL
- "Explain AIS tracking" → GENERAL
- "How does this system work?" → GENERAL
- "Thank you" → GENERAL

## YOUR TASK

Classify this query: "{query}"

Respond with valid JSON:
{{
    "query_type": "structured|semantic|hybrid|temporal|general",
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation of classification",
    "extracted_filters": {{"field": "value", ...}} or null,
    "time_range": {{"type": "relative", "value": "1 hour|today|recent|..."}} or null,
    "semantic_query": "the vague/descriptive part for semantic search" or null
}}

## CRITICAL RULES - MUST FOLLOW

1. FIELD NAMES - Use ONLY these exact field names in extracted_filters:
   - is_dark_ship (NOT: status, dark_ship, dark, is_dark)
   - vessel_type (NOT: type, ship_type, vessel)
   - speed_gt, speed_lt (NOT: speed, velocity)
   - port (NOT: location, area, near)
   - limit (NOT: count, top, max)

2. FIELD VALUES:
   - is_dark_ship: must be boolean true or false (NOT string "true" or "dark_ship")
   - vessel_type: must be uppercase "TANKER", "CARGO", "CONTAINER", etc.
   - port: must be capitalized "Mumbai", "Chennai", etc.
   - limit: must be a number

3. DARK SHIP QUERIES:
   When user mentions "dark ship", "dark ships", "dark vessel", "AIS off":
   CORRECT: {{"is_dark_ship": true}}
   WRONG: {{"status": "dark_ship"}} or {{"status": "dark"}} or {{"dark_ship": true}}

4. For TEMPORAL queries, always include time_range
5. For HYBRID queries, include both extracted_filters AND semantic_query"""

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

            # Normalize query_type to lowercase (LLM sometimes returns uppercase)
            query_type_str = result.get("query_type", "general").lower()

            return QueryRoute(
                query_type=QueryType(query_type_str),
                confidence=float(result.get("confidence", 0.8)),
                reasoning=result.get("reasoning", ""),
                extracted_filters=result.get("extracted_filters"),
                time_range=result.get("time_range"),
                semantic_query=result.get("semantic_query"),
            )

        except Exception as e:
            logger.error(f"Query routing failed: {e}")
            # Fall back to rule-based routing
            return self._fallback_route(query)

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

            # Normalize query_type to lowercase (LLM sometimes returns uppercase)
            query_type_str = result.get("query_type", "general").lower()

            return QueryRoute(
                query_type=QueryType(query_type_str),
                confidence=float(result.get("confidence", 0.8)),
                reasoning=result.get("reasoning", ""),
                extracted_filters=result.get("extracted_filters"),
                time_range=result.get("time_range"),
                semantic_query=result.get("semantic_query"),
            )

        except Exception as e:
            logger.error(f"Query routing failed: {e}")
            return self._fallback_route(query)

    def _fallback_route(self, query: str) -> QueryRoute:
        """
        Safe fallback when LLM classification fails.

        Returns GENERAL type - safest default that won't trigger unnecessary pipeline.
        """
        logger.warning(f"LLM classification failed, defaulting to GENERAL for: {query[:50]}...")
        return QueryRoute(
            query_type=QueryType.GENERAL,
            confidence=0.5,
            reasoning="LLM classification failed, defaulting to conversational mode",
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
