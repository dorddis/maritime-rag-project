# RAG Architecture Research for Maritime Ship Tracking System

## Executive Summary

This document evaluates 6 different RAG (Retrieval-Augmented Generation) architectures for a maritime ship tracking system with multi-sensor data (AIS, radar, satellite, drone). The system uses Redis Streams for real-time data pipeline and needs to answer queries about vessel positions, metadata, and temporal patterns.

**Recommended Implementation Strategy:**
1. **Start with Hybrid RAG** (Quick wins, moderate complexity)
2. **Add Temporal RAG** (Essential for time-series ship tracking)
3. **Optionally implement Agentic RAG** (Advanced multi-step queries)

---

## System Context

**Data Sources:**
- AIS (Automatic Identification System) transponders - ship-to-ship/shore communication
- Radar detection
- Satellite S-AIS (ORBCOMM, HawkEye 360)
- Drone visual/sensor data

**Data Pipeline:**
- Redis Streams for real-time ingestion
- Time-series ship position data with metadata (vessel name, type, speed, heading, course)
- Need to support both real-time and historical queries

**Example Queries:**
- "Which ships are near Mumbai port?"
- "Show me tankers heading north"
- "What's the status of vessel MARITIME PRIDE?"
- "Find ships that were near each other in the last hour"

---

## 1. Basic/Naive RAG

### How It Works
Simple RAG follows a chain of **indexing → retrieval → generation**. The system:
1. Converts ship position records and metadata into vector embeddings
2. Stores embeddings in a vector database (Redis Vector Search)
3. For queries, embeds the question and performs cosine similarity search
4. Returns top-k most similar records to LLM for answer generation

### Architecture
```
User Query → Embedding Model → Vector Search (Redis) → Top-K Results → LLM → Answer
```

### Pros for Maritime Use Case
- **Simple to implement** - straightforward pipeline, minimal moving parts
- **Fast retrieval** - Redis vector search is highly optimized
- **Good for factual lookups** - "What is the current position of MARITIME PRIDE?"
- **Works well with static data** - vessel specifications, historical records

### Cons for Maritime Use Case
- **Poor temporal awareness** - doesn't understand "last hour" or "yesterday"
- **No structured filtering** - hard to filter by vessel type, speed ranges, proximity
- **Misses exact matches** - purely semantic, might miss exact vessel name lookups
- **Stale data issues** - without recency weighting, returns outdated positions

### Implementation Approach with Redis
```python
# 1. Create vector index in Redis
from redis import Redis
from redis.commands.search.field import VectorField, TagField, NumericField

redis_client = Redis(host='localhost', port=6379)

# Create schema with vector + metadata fields
schema = (
    VectorField("embedding", "HNSW", {"TYPE": "FLOAT32", "DIM": 768, "DISTANCE_METRIC": "COSINE"}),
    TagField("vessel_name"),
    TagField("vessel_type"),
    NumericField("speed"),
    NumericField("latitude"),
    NumericField("longitude"),
    NumericField("timestamp")
)

# 2. Index ship positions
import openai
ship_data = {
    "vessel_name": "MARITIME PRIDE",
    "vessel_type": "TANKER",
    "speed": 12.5,
    "heading": 45,
    "latitude": 18.9388,
    "longitude": 72.8354
}

# Create embedding
text = f"{ship_data['vessel_name']} {ship_data['vessel_type']} speed {ship_data['speed']} heading {ship_data['heading']}"
embedding = openai.Embedding.create(input=text, model="text-embedding-3-small")['data'][0]['embedding']

# Store in Redis
redis_client.hset("ship:001", mapping={
    "embedding": embedding,
    "vessel_name": ship_data['vessel_name'],
    "vessel_type": ship_data['vessel_type'],
    "speed": ship_data['speed']
})

# 3. Query
query_embedding = openai.Embedding.create(input="tankers near Mumbai", model="text-embedding-3-small")['data'][0]['embedding']
results = redis_client.ft().search(query_embedding, {"K": 10})
```

### Suitability Score: 2/5
**Rationale:** Too simplistic for maritime domain. Lacks temporal awareness and structured filtering critical for ship tracking.

### Implementation Complexity: Low
**Timeline:** 1-2 days

### Key Libraries/Tools
- `redis-py` (Redis Python client)
- `openai` or `sentence-transformers` (embeddings)
- `langchain` (optional orchestration)

### Example Query It Handles Well
- "What type of vessel is MARITIME PRIDE?" (factual lookup)
- "Tell me about container ships" (semantic understanding)

### Example Query It Struggles With
- "Ships near Mumbai in the last hour" (temporal + geospatial)
- "Tankers going faster than 15 knots" (structured filtering)

---

## 2. Hybrid RAG

### How It Works
Combines **vector similarity search** (semantic understanding) with **keyword/structured search** (exact matches, filters). The system decides whether to:
- Use vector search for semantic queries ("ships heading north")
- Use structured queries for exact matches ("vessel_name = MARITIME PRIDE")
- Combine both for complex queries ("tankers near Mumbai")

According to research, hybrid RAG systems can reduce response times by 40% in customer support systems.

### Architecture
```
                    ┌──────────────┐
User Query ────────►│Query Analyzer│
                    └──────┬───────┘
                           │
            ┌──────────────┴──────────────┐
            ▼                             ▼
    ┌───────────────┐           ┌─────────────────┐
    │Vector Search  │           │Structured Filter│
    │(Semantic)     │           │(Tags, Ranges)   │
    └───────┬───────┘           └────────┬────────┘
            │                            │
            └────────────┬───────────────┘
                         ▼
                   ┌──────────┐
                   │ Merger   │
                   └────┬─────┘
                        ▼
                      LLM
```

### When to Use Vector vs Structured
- **Vector Search:** "ships heading north", "vessels going fast", "tankers near port"
- **Structured Search:** vessel_type="TANKER", speed>15, latitude/longitude ranges
- **Combined:** "tankers (type filter) heading north (vector) near Mumbai (geo filter)"

### How to Combine Results
1. **Pre-filtering:** Apply structured filters first, then vector search on subset
2. **Post-filtering:** Vector search first, then apply filters to results
3. **Hybrid scoring:** Combine vector similarity score + metadata match score
4. **Reciprocal Rank Fusion (RRF):** Merge ranked results from both methods

```python
# RRF formula
score(doc) = sum(1 / (k + rank_i)) for each ranking i
# where k is a constant (typically 60)
```

### Pros for Maritime Use Case
- **Best of both worlds** - semantic understanding + precise filtering
- **Handle diverse queries** - "tankers" (type filter) "heading north" (semantic/heading filter)
- **Exact match vessel names** - full-text search prevents embedding errors
- **Geospatial filtering** - Redis native geo queries for proximity
- **Speed/heading ranges** - numeric filters for operational parameters

### Cons for Maritime Use Case
- **Still limited temporal awareness** - needs explicit time filters
- **Complex query parsing** - need to split query into vector/structured parts
- **Score combination complexity** - balancing semantic vs exact match weights

### Implementation Approach with Redis
```python
from redis.commands.search.query import Query

# Create index with vector + full-text + numeric fields
schema = (
    VectorField("embedding", "HNSW", {"TYPE": "FLOAT32", "DIM": 768}),
    TextField("vessel_name"),  # Full-text search
    TagField("vessel_type"),
    NumericField("speed"),
    NumericField("heading"),
    GeoField("position")  # Lat/lon
)

# Hybrid query: "tankers near Mumbai going faster than 15 knots"
# 1. Parse query components
filters = {
    "vessel_type": "TANKER",
    "speed": ">15",
    "position": "near Mumbai (18.9388, 72.8354, 50km)"
}

# 2. Build hybrid query
query = Query("(@vessel_type:{TANKER}) (@speed:[15 +inf]) @position:[18.9388 72.8354 50 km]")
vector_query = embed("tankers heading north")

# 3. Combine vector similarity with filters
hybrid_query = query.add_vector_param("embedding", vector_query, "COSINE", K=10)

# 4. Execute
results = redis_client.ft().search(hybrid_query)
```

### Suitability Score: 4/5
**Rationale:** Excellent fit for maritime queries requiring both semantic understanding and precise filtering. Missing temporal features prevents 5/5.

### Implementation Complexity: Medium
**Timeline:** 3-5 days

### Key Libraries/Tools
- `redis-py` with RediSearch module
- `openai` or `sentence-transformers`
- `langchain` or custom query parser
- Redis GeoSpatial commands for proximity

### Example Queries It Handles Well
- "Tankers near Mumbai port" (type + geo filters)
- "Ships heading north faster than 20 knots" (heading semantic + speed filter)
- "Find vessel MARITIME PRIDE" (exact text match)
- "Container ships in the Arabian Sea" (type + region)

### Example Queries It Struggles With
- "Ships that were near each other yesterday" (temporal reasoning)
- "Vessels that changed course in the last hour" (event detection)

---

## 3. Graph RAG

### How It Works
Builds a **knowledge graph** of entities (ships, ports, routes) and relationships (proximity, same route, port visits). Combines:
- **Vector search** for semantic retrieval
- **Graph traversal** for relationship queries
- **Entity extraction** from ship data

Neo4j research shows GraphRAG can improve multi-hop QA recall by 6.4 points and reduce hallucinations by 18% in biomedical tasks.

### Architecture
```
Ship Position Data
       ↓
Entity Extraction → Knowledge Graph (Neo4j/Redis Graph)
       ↓
   ┌────────────────────────┐
   │   Nodes:               │
   │   - Vessels            │
   │   - Ports              │
   │   - Routes             │
   │   - Events (detections)│
   └────────────────────────┘
           ↓
   ┌────────────────────────┐
   │   Edges:               │
   │   - NEAR (proximity)   │
   │   - VISITED_PORT       │
   │   - SAME_ROUTE         │
   │   - DETECTED_BY (sensor)│
   └────────────────────────┘
           ↓
   Query → Graph Traversal + Vector Search → LLM
```

### How to Model Ship Relationships
```cypher
// Neo4j schema examples

// Nodes
CREATE (v:Vessel {name: "MARITIME PRIDE", type: "TANKER", imo: "9234567"})
CREATE (p:Port {name: "Mumbai Port", lat: 18.9388, lon: 72.8354})
CREATE (r:Route {name: "Mumbai-Dubai-Route", distance_km: 1900})

// Relationships
CREATE (v1:Vessel)-[:NEAR {distance_km: 5, timestamp: 1735123456}]->(v2:Vessel)
CREATE (v:Vessel)-[:VISITED_PORT {arrival: datetime(), departure: datetime()}]->(p:Port)
CREATE (v:Vessel)-[:FOLLOWS_ROUTE]->(r:Route)
CREATE (v:Vessel)-[:DETECTED_BY {timestamp: 1735123456, confidence: 0.95}]->(s:Sensor {type: "AIS"})
CREATE (v:Vessel)-[:POSITION_AT {timestamp: 1735123456, lat: 18.9388, lon: 72.8354, speed: 12.5, heading: 45}]->(l:Location)
```

### Benefits for Maritime Domain
- **Multi-hop reasoning:** "Ships that visited same ports as MARITIME PRIDE"
- **Relationship queries:** "Vessels that were near each other multiple times"
- **Proximity events:** Track when ships come within X km
- **Route analysis:** "Ships following Mumbai-Dubai route"
- **Sensor correlation:** "Ships detected by multiple sensor types"
- **Temporal patterns:** "Vessels that frequently visit Mumbai"

### Neo4j vs Redis Graph Options

| Feature | Neo4j | Redis Graph |
|---------|-------|-------------|
| **Maturity** | Industry standard | Experimental (deprecated in Redis 7.2) |
| **Query Language** | Cypher (powerful) | OpenCypher subset |
| **Performance** | Optimized for complex graphs | Fast for simple graphs |
| **Integration** | Separate DB, need sync | Native Redis, same pipeline |
| **Scalability** | Excellent for large graphs | Limited |
| **Vector Support** | Via plugins | Native Redis Vector |
| **Recommendation** | Use for production | Avoid (deprecated) |

**Best Approach:** Neo4j for graph + Redis for vector/time-series, sync periodically.

### Pros for Maritime Use Case
- **Powerful relationship queries** - proximity events, route patterns
- **Multi-hop reasoning** - "ships that visited same ports"
- **Event detection** - identify recurring proximity (potential meetings)
- **Contextual retrieval** - understand ship behavior patterns
- **Explainable results** - show graph path in answer

### Cons for Maritime Use Case
- **High complexity** - need entity extraction, graph maintenance
- **Dual database** - Neo4j + Redis, sync overhead
- **Slower for simple queries** - overkill for "find ship X"
- **Graph maintenance** - constantly updating edges for moving ships
- **Limited temporal support** - graphs are snapshots, not time-series

### Implementation Approach
```python
# 1. Entity Extraction from Redis Streams
from neo4j import GraphDatabase
import redis

redis_client = redis.Redis()
neo4j_driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))

# 2. Build graph from ship positions
def create_vessel_graph(ship_data):
    with neo4j_driver.session() as session:
        # Create vessel node
        session.run("""
            MERGE (v:Vessel {name: $name})
            SET v.type = $type, v.imo = $imo
        """, name=ship_data['vessel_name'], type=ship_data['vessel_type'], imo=ship_data['imo'])

        # Create position relationship
        session.run("""
            MATCH (v:Vessel {name: $name})
            CREATE (l:Location {lat: $lat, lon: $lon, timestamp: $ts})
            CREATE (v)-[:POSITION_AT {speed: $speed, heading: $heading}]->(l)
        """, name=ship_data['vessel_name'], lat=ship_data['lat'], lon=ship_data['lon'],
            ts=ship_data['timestamp'], speed=ship_data['speed'], heading=ship_data['heading'])

# 3. Detect proximity events (run periodically)
def detect_proximity_events(distance_km=10):
    with neo4j_driver.session() as session:
        session.run("""
            MATCH (v1:Vessel)-[:POSITION_AT]->(l1:Location)
            MATCH (v2:Vessel)-[:POSITION_AT]->(l2:Location)
            WHERE v1 <> v2
              AND abs(l1.timestamp - l2.timestamp) < 3600  // Within 1 hour
              AND point.distance(
                point({latitude: l1.lat, longitude: l1.lon}),
                point({latitude: l2.lat, longitude: l2.lon})
              ) < $distance * 1000
            MERGE (v1)-[:NEAR {distance_km: point.distance(...)/1000, timestamp: l1.timestamp}]->(v2)
        """, distance=distance_km)

# 4. Query graph
def find_ships_on_same_route(vessel_name):
    with neo4j_driver.session() as session:
        result = session.run("""
            MATCH (v1:Vessel {name: $name})-[:VISITED_PORT]->(p:Port)<-[:VISITED_PORT]-(v2:Vessel)
            WHERE v1 <> v2
            RETURN DISTINCT v2.name as vessel, count(p) as common_ports
            ORDER BY common_ports DESC
        """, name=vessel_name)
        return [record for record in result]
```

### Suitability Score: 3/5
**Rationale:** Powerful for relationship queries but high complexity and maintenance overhead. Overkill for basic position tracking. Valuable for advanced analytics (route patterns, vessel behavior).

### Implementation Complexity: High
**Timeline:** 1-2 weeks

### Key Libraries/Tools
- `neo4j` (Python driver)
- `py2neo` (alternative Neo4j library)
- `redis-py` (for Redis integration)
- `langchain` with Neo4j graph chains
- Cypher query language

### Example Queries It Handles Well
- "Ships that visited the same ports as MARITIME PRIDE" (multi-hop)
- "Vessels that were near each other multiple times" (relationship patterns)
- "Show me the route history of tanker ABC" (path traversal)
- "Ships detected by both AIS and radar" (sensor correlation)

### Example Queries It Struggles With
- "Ships near Mumbai right now" (real-time, better with Redis)
- "Fastest ship in the last hour" (time-series aggregation)

---

## 4. Agentic RAG

### How It Works
Uses AI agents that **plan, reason, and execute** multi-step retrieval tasks. Agents can:
- Break complex queries into sub-queries
- Use tools (database queries, calculations, map APIs)
- Self-reflect and retry with different approaches
- Combine results from multiple sources

According to research, Agentic RAG "doesn't just answer questions—it tackles complex, multi-step information retrieval tasks."

### Architecture (LangGraph)
```
User Query
    ↓
┌─────────────────┐
│ Routing Agent   │ ← Decides which tools/sources to use
└────────┬────────┘
         ↓
┌─────────────────┐
│ Planning Agent  │ ← Breaks query into sub-steps
└────────┬────────┘
         ↓
    ┌────┴────┐
    ↓         ↓
[Tool 1]  [Tool 2]  [Tool N]
  ↓         ↓         ↓
Redis   Geo API   Calculator
Vector   Lookup   (distance)
Search
    ↓         ↓         ↓
    └────┬────┴─────────┘
         ↓
┌─────────────────┐
│ Synthesis Agent │ ← Combines results
└────────┬────────┘
         ↓
    Final Answer
```

### Breaking Complex Queries Into Sub-Queries
**Example Query:** "Find ships that were near each other in the last hour and are both heading to Mumbai port"

**Agent Breakdown:**
1. **Sub-query 1:** Get all ships with positions in last hour (Redis time filter)
2. **Sub-query 2:** Calculate pairwise distances (custom distance tool)
3. **Sub-query 3:** Filter pairs within proximity threshold (e.g., <10km)
4. **Sub-query 4:** For each ship, predict destination using heading/speed (calculation tool)
5. **Sub-query 5:** Filter ships heading toward Mumbai coordinates (geo tool)
6. **Synthesis:** Combine results and generate natural language answer

### Using Tools
```python
from langchain.agents import Tool
from langchain_community.utilities import GoogleMapsAPIWrapper

# Define tools for maritime queries
tools = [
    Tool(
        name="RedisVectorSearch",
        func=lambda query: redis_vector_search(query),
        description="Search ship positions using semantic similarity"
    ),
    Tool(
        name="RedisTimeFilter",
        func=lambda hours: get_ships_last_n_hours(hours),
        description="Get ships detected in last N hours"
    ),
    Tool(
        name="CalculateDistance",
        func=lambda pos1, pos2: haversine_distance(pos1, pos2),
        description="Calculate distance between two lat/lon positions in km"
    ),
    Tool(
        name="PredictDestination",
        func=lambda ship_data: predict_destination(ship_data),
        description="Predict ship destination based on heading, speed, current position"
    ),
    Tool(
        name="PortLookup",
        func=lambda port_name: get_port_coordinates(port_name),
        description="Get coordinates for a named port"
    )
]

# Agent with ReAct pattern (Reasoning + Acting)
from langchain.agents import initialize_agent, AgentType
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4", temperature=0)
agent = initialize_agent(
    tools=tools,
    llm=llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True
)

# Execute complex query
result = agent.run("Find ships that were near each other in the last hour and are heading to Mumbai")
```

### Agent Types in Agentic RAG

1. **Routing Agent:** Decides which data source/tool to use
   - Vector search vs structured query?
   - Redis vs external API?

2. **Query Planning Agent:** Breaks complex queries into steps
   - "Find A, then calculate B, then filter by C"

3. **ReAct Agent (Reasoning + Acting):** Iterative reasoning
   - Try approach → Check result → Adjust approach

4. **Self-Reflective Agent:** Evaluates its own outputs
   - "Are these results relevant?"
   - "Should I retrieve more data?"

### Pros for Maritime Use Case
- **Handle complex multi-step queries** - proximity + destination prediction
- **Tool integration** - combine Redis + external APIs + calculations
- **Adaptive retrieval** - retry with different approaches if first fails
- **Reasoning transparency** - show step-by-step logic
- **Extensible** - easy to add new tools (weather API, route planning)

### Cons for Maritime Use Case
- **High latency** - multiple LLM calls per query
- **Cost** - GPT-4 calls for planning/reasoning expensive
- **Unpredictable** - agent might take unexpected paths
- **Overkill for simple queries** - "find ship X" doesn't need agents
- **Debugging complexity** - hard to trace failures in multi-step chains

### Implementation Approach
```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, List

# Define state
class MaritimeQueryState(TypedDict):
    query: str
    sub_queries: List[str]
    ship_data: List[dict]
    proximity_pairs: List[tuple]
    destinations: List[str]
    final_answer: str

# Define nodes (agents)
def route_query(state):
    # Decide which path to take based on query type
    if "near each other" in state["query"]:
        return "proximity_agent"
    elif "heading to" in state["query"]:
        return "destination_agent"
    else:
        return "simple_search"

def proximity_agent(state):
    # Get ships, calculate distances, find nearby pairs
    ships = get_recent_ships(hours=1)
    pairs = []
    for i, s1 in enumerate(ships):
        for s2 in ships[i+1:]:
            dist = haversine_distance(s1['position'], s2['position'])
            if dist < 10:  # Within 10km
                pairs.append((s1, s2))
    state["proximity_pairs"] = pairs
    return state

def destination_agent(state):
    # Predict destinations for ships
    destinations = []
    for ship in state["ship_data"]:
        dest = predict_destination(ship)
        destinations.append(dest)
    state["destinations"] = destinations
    return state

def synthesize(state):
    # Combine results and generate answer
    llm = ChatOpenAI(model="gpt-4")
    prompt = f"Based on proximity pairs {state['proximity_pairs']} and destinations {state['destinations']}, answer: {state['query']}"
    state["final_answer"] = llm.invoke(prompt)
    return state

# Build graph
workflow = StateGraph(MaritimeQueryState)
workflow.add_node("router", route_query)
workflow.add_node("proximity_agent", proximity_agent)
workflow.add_node("destination_agent", destination_agent)
workflow.add_node("synthesize", synthesize)

workflow.add_edge("router", "proximity_agent")
workflow.add_edge("proximity_agent", "destination_agent")
workflow.add_edge("destination_agent", "synthesize")
workflow.add_edge("synthesize", END)

app = workflow.compile()

# Execute
result = app.invoke({"query": "Find ships near each other in the last hour heading to Mumbai"})
print(result["final_answer"])
```

### Suitability Score: 4/5
**Rationale:** Excellent for complex maritime intelligence queries requiring multi-step reasoning. High value for showcase project demonstrating advanced AI capabilities. Deducted 1 point for cost/latency concerns.

### Implementation Complexity: High
**Timeline:** 1-2 weeks

### Key Libraries/Tools
- `langgraph` (LangChain's graph-based agent framework)
- `langchain` (agent orchestration)
- `openai` or `anthropic` (LLM for reasoning)
- Custom tools (Redis queries, distance calculations, geo APIs)

### Example Queries It Handles Well
- "Find ships that were near each other in the last hour" (multi-step: retrieve → calculate → filter)
- "Which tankers are heading toward Mumbai and traveling faster than 15 knots?" (multiple filters + prediction)
- "Show me vessels detected by multiple sensors in the last 24 hours" (cross-source correlation)
- "What's the most unusual ship behavior in the last hour?" (anomaly detection reasoning)

### Example Queries It Struggles With
- "Where is MARITIME PRIDE?" (too simple, agent overhead not needed)
- Requires well-designed tools and clear task decomposition

---

## 5. Temporal RAG

### How It Works
Adds **time-awareness** to retrieval through:
1. **Recency weighting** - newer data scores higher
2. **Time-based decay** - older data gradually de-prioritized
3. **Temporal query parsing** - understand "last hour", "yesterday", "last week"
4. **Time-series indexing** - efficient queries over time windows

Research shows a "simple recency prior achieved an accuracy of 1.00 on freshness tasks" while basic clustering heuristics failed (0.08 F1-score).

### Architecture
```
User Query → Temporal Parser → Time Window Extraction
                                      ↓
                            ┌─────────┴──────────┐
                            ↓                    ↓
                    [Recency-Weighted      [Time-Series
                     Vector Search]         Filter]
                            ↓                    ↓
                    Redis Vector + Decay   Redis Sorted Set
                            ↓                    ↓
                            └─────────┬──────────┘
                                      ↓
                            Merge + Rank by Time
                                      ↓
                                    LLM
```

### Recency Weighting Formula
```python
# Exponential decay
def time_decay_score(similarity_score, timestamp, current_time, half_life_hours=24):
    """
    similarity_score: 0-1 from vector search
    timestamp: document timestamp
    current_time: current time
    half_life_hours: time for score to decay to 50%
    """
    age_hours = (current_time - timestamp) / 3600
    decay_factor = 0.5 ** (age_hours / half_life_hours)
    return similarity_score * decay_factor

# Daily decay (simpler)
def daily_decay_score(similarity_score, days_old):
    """Today=1.0, yesterday=0.98, 2 days ago=0.96, etc."""
    decay_factor = 0.98 ** days_old
    return similarity_score * decay_factor
```

### Handling Time-Series Data with Redis
```python
# Use Redis Sorted Sets for time-series indexing
import redis
import time

redis_client = redis.Redis()

# Store ship positions with timestamp as score
def store_ship_position(vessel_name, position_data):
    key = f"ship:positions:{vessel_name}"
    timestamp = time.time()

    # Sorted set: timestamp as score, JSON data as value
    redis_client.zadd(key, {json.dumps(position_data): timestamp})

# Query positions in time range
def get_positions_in_range(vessel_name, start_time, end_time):
    key = f"ship:positions:{vessel_name}"
    # ZRANGEBYSCORE returns items with score in [start, end]
    results = redis_client.zrangebyscore(key, start_time, end_time)
    return [json.loads(r) for r in results]

# Get last N hours
def get_recent_positions(vessel_name, hours=1):
    current_time = time.time()
    start_time = current_time - (hours * 3600)
    return get_positions_in_range(vessel_name, start_time, current_time)

# Recency-weighted vector search
def temporal_vector_search(query_embedding, current_time, k=10, half_life_hours=24):
    # Get all candidates from vector search
    candidates = redis_client.ft().search(query_embedding, {"K": k * 3})  # Get 3x more candidates

    # Re-rank with time decay
    scored_results = []
    for doc in candidates:
        similarity = doc['similarity_score']
        timestamp = doc['timestamp']
        temporal_score = time_decay_score(similarity, timestamp, current_time, half_life_hours)
        scored_results.append((doc, temporal_score))

    # Sort by temporal score and return top K
    scored_results.sort(key=lambda x: x[1], reverse=True)
    return [doc for doc, score in scored_results[:k]]
```

### Temporal Query Parsing
```python
import re
from datetime import datetime, timedelta

def parse_temporal_query(query):
    """
    Extract time constraints from natural language query
    Returns: (cleaned_query, start_time, end_time)
    """
    current_time = datetime.now()

    # Patterns
    patterns = {
        r'last (\d+) hour': lambda m: timedelta(hours=int(m.group(1))),
        r'last hour': lambda m: timedelta(hours=1),
        r'last (\d+) day': lambda m: timedelta(days=int(m.group(1))),
        r'yesterday': lambda m: timedelta(days=1),
        r'last week': lambda m: timedelta(weeks=1),
        r'in the past (\d+) minutes': lambda m: timedelta(minutes=int(m.group(1)))
    }

    time_delta = None
    for pattern, delta_func in patterns.items():
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            time_delta = delta_func(match)
            query = re.sub(pattern, '', query, flags=re.IGNORECASE).strip()
            break

    if time_delta:
        start_time = current_time - time_delta
        end_time = current_time
    else:
        start_time = None
        end_time = None

    return query, start_time, end_time

# Example usage
query = "Show me tankers near Mumbai in the last 2 hours"
cleaned_query, start_time, end_time = parse_temporal_query(query)
# cleaned_query: "Show me tankers near Mumbai"
# start_time: 2 hours ago
# end_time: now
```

### Historical vs Real-Time Queries
```python
def route_temporal_query(query, start_time, end_time):
    """
    Route to appropriate data source based on time range
    """
    if end_time == datetime.now() and (datetime.now() - start_time).total_seconds() < 3600:
        # Last hour → Redis Streams (real-time data)
        return query_redis_streams(query, start_time, end_time)

    elif (datetime.now() - start_time).days < 7:
        # Last week → Redis Sorted Sets (recent time-series)
        return query_redis_timeseries(query, start_time, end_time)

    else:
        # Older data → Archive database or Redis with longer TTL
        return query_archive(query, start_time, end_time)
```

### Pros for Maritime Use Case
- **Essential for ship tracking** - ships move continuously, position freshness critical
- **Natural time queries** - "last hour", "yesterday" common in maritime ops
- **Recency weighting** - prioritize latest positions over stale data
- **Time-series aggregation** - analyze ship behavior over time windows
- **Efficient time filtering** - Redis Sorted Sets optimized for range queries

### Cons for Maritime Use Case
- **Decay tuning complexity** - choosing right half-life for different query types
- **Storage overhead** - maintaining multiple time indexes
- **Query parsing errors** - "last hour" vs "past hour" ambiguity
- **Limited relationship reasoning** - doesn't handle "ships that met yesterday"

### Implementation Approach
See code examples above. Key components:
1. Redis Sorted Sets for time-series indexing
2. Recency weighting function (exponential decay)
3. Temporal query parser (regex-based)
4. Hybrid approach: time filter + recency-weighted vector search

### Suitability Score: 5/5
**Rationale:** CRITICAL for maritime ship tracking. Ships are constantly moving, making temporal awareness essential. Every position query implicitly needs recency consideration.

### Implementation Complexity: Medium
**Timeline:** 3-5 days

### Key Libraries/Tools
- `redis-py` (Sorted Sets, Time Series module)
- `dateparser` or `dateutil` (natural language time parsing)
- `pandas` (time-series analysis)
- `arrow` (better datetime library)

### Example Queries It Handles Well
- "Ships detected in the last hour" (time window)
- "Where was MARITIME PRIDE yesterday at 3pm?" (historical point-in-time)
- "Show me recent tanker positions near Mumbai" (recency + filters)
- "Vessels that changed speed in the last 2 hours" (time-series analysis)

### Example Queries It Struggles With
- "Ships that were near each other yesterday" (needs proximity calculation, not just time filter)
- "Most frequent port visitor this month" (needs aggregation logic)

---

## 6. Multi-Modal RAG (Optional)

### How It Works
Combines retrieval from **multiple data modalities**:
- **Structured data:** Ship metadata from databases (vessel specs, owner, registration)
- **Unstructured text:** Incident reports, maritime news, captain logs
- **Sensor data:** AIS signals, radar returns, satellite imagery
- **Visual data:** Drone footage, satellite photos (ship identification)

Research shows MAHA (Modality-Aware Hybrid Architecture) achieved ROUGE-L score of 0.486 with complete modality coverage.

### Architecture
```
User Query
    ↓
┌─────────────────────────────────────┐
│      Modality Router                │
└────┬─────────┬──────────┬──────────┘
     ↓         ↓          ↓
[Structured] [Text]  [Sensor]  [Visual]
   Redis DB   Docs     Redis    Images
     ↓         ↓          ↓         ↓
  SQL/Tag   Vector   Time-Series  Vision
  Filter    Search   Query        Model
     ↓         ↓          ↓         ↓
     └─────────┴──────────┴─────────┘
               ↓
        Knowledge Graph
      (Cross-Modal Links)
               ↓
             LLM
```

### Data Types in Maritime System

1. **Structured Sensor Data (AIS/Radar)**
   - Format: JSON, time-series
   - Fields: lat, lon, speed, heading, timestamp
   - Storage: Redis Streams, Sorted Sets
   - Retrieval: Time filters, geo queries

2. **Unstructured Reports**
   - Format: Text (incident reports, weather advisories)
   - Content: "Vessel MARITIME PRIDE reported engine trouble at 18.93N, 72.83E"
   - Storage: Vector database (embeddings)
   - Retrieval: Semantic search

3. **Visual Data (Satellite/Drone)**
   - Format: Images, video
   - Content: Ship imagery for visual identification
   - Storage: Object storage (S3) + metadata in Redis
   - Retrieval: Vision model → ship detection → link to vessel ID

4. **Metadata (Vessel Registry)**
   - Format: Structured database
   - Fields: vessel_name, imo_number, owner, flag, built_year, gross_tonnage
   - Storage: Redis Hashes or PostgreSQL
   - Retrieval: Exact match queries

### Combining Data Types
```python
# Multi-modal query: "What happened to MARITIME PRIDE yesterday?"

# 1. Structured data: Get position history
positions = get_positions_in_range("MARITIME PRIDE", yesterday_start, yesterday_end)

# 2. Unstructured text: Search incident reports
reports = vector_search_documents("MARITIME PRIDE incident")

# 3. Visual data: Find satellite images near position
images = find_images_near_position(positions[0], time_range=yesterday)

# 4. Combine in context
context = f"""
Position History: {positions}
Incident Reports: {reports}
Satellite Images: {images}
"""

# 5. LLM synthesizes multi-modal answer
answer = llm.invoke(f"Based on this data, what happened to MARITIME PRIDE yesterday?\n{context}")
```

### Cross-Modal Knowledge Graph
```cypher
// Link different data modalities

// Vessel node (structured metadata)
CREATE (v:Vessel {name: "MARITIME PRIDE", imo: "9234567", type: "TANKER"})

// Position data (sensor)
CREATE (p:Position {lat: 18.93, lon: 72.83, timestamp: 1735123456, source: "AIS"})
CREATE (v)-[:POSITION_AT]->(p)

// Incident report (unstructured text)
CREATE (r:Report {text: "Engine trouble reported", timestamp: 1735123456, doc_id: "INC-001"})
CREATE (v)-[:MENTIONED_IN]->(r)

// Satellite image (visual)
CREATE (i:Image {url: "s3://images/sat-001.jpg", timestamp: 1735123456, lat: 18.93, lon: 72.83})
CREATE (v)-[:VISIBLE_IN]->(i)
CREATE (i)-[:CAPTURED_AT]->(p)

// Now can query: "Find all data about vessel X at time Y"
MATCH (v:Vessel {name: "MARITIME PRIDE"})-[*1..2]-(data)
WHERE data.timestamp BETWEEN $start AND $end
RETURN data
```

### Pros for Maritime Use Case
- **Rich context** - combine position data + reports + imagery
- **Incident investigation** - correlate sensor data with reports
- **Visual verification** - satellite images confirm AIS data
- **Comprehensive answers** - "what happened" requires multiple sources

### Cons for Maritime Use Case
- **Very high complexity** - managing 4+ data types
- **Vision model costs** - satellite image processing expensive
- **May be overkill** - if system only has AIS/radar, not multi-modal
- **Sync challenges** - keeping modalities aligned
- **Storage costs** - images/video consume significant storage

### Implementation Approach
```python
from langchain.retrievers import MultiModalRetriever
from PIL import Image
import openai

# 1. Multi-modal embeddings (CLIP for images + text)
def create_multimodal_embedding(data, modality):
    if modality == "text":
        return openai.Embedding.create(input=data, model="text-embedding-3-small")['data'][0]['embedding']
    elif modality == "image":
        # Use CLIP or similar
        return clip_model.encode_image(Image.open(data))
    elif modality == "structured":
        # Convert to text description
        text = f"{data['vessel_name']} {data['vessel_type']} at position {data['lat']}, {data['lon']}"
        return openai.Embedding.create(input=text, model="text-embedding-3-small")['data'][0]['embedding']

# 2. Store in unified vector space
def store_multimodal_data(data, modality):
    embedding = create_multimodal_embedding(data, modality)
    redis_client.hset(f"{modality}:{data['id']}", mapping={
        "embedding": embedding,
        "modality": modality,
        "data": json.dumps(data)
    })

# 3. Retrieve across modalities
def multimodal_search(query, modalities=["text", "structured", "image"]):
    query_embedding = create_multimodal_embedding(query, "text")
    results = {}
    for modality in modalities:
        # Search within each modality
        results[modality] = redis_vector_search(query_embedding, filter=f"@modality:{modality}")
    return results

# 4. Synthesize with vision-language model
from openai import OpenAI
client = OpenAI()

def answer_multimodal_query(query, multimodal_results):
    # Prepare context with images + text
    messages = [
        {"role": "system", "content": "You are a maritime intelligence assistant."},
        {"role": "user", "content": [
            {"type": "text", "text": f"Query: {query}\n\nStructured data: {multimodal_results['structured']}"},
            {"type": "text", "text": f"Reports: {multimodal_results['text']}"},
            {"type": "image_url", "image_url": {"url": multimodal_results['image'][0]['url']}}
        ]}
    ]
    response = client.chat.completions.create(model="gpt-4o", messages=messages)
    return response.choices[0].message.content
```

### Suitability Score: 2/5 (for current system)
**Rationale:** System description mentions only sensor data (AIS, radar, satellite, drone), not unstructured reports or images requiring multi-modal RAG. Score would be 4/5 if drone footage or incident reports are included.

**IMPORTANT:** If your "drone" data source includes visual imagery (not just structured sensor readings), increase score to 4/5 and prioritize this approach.

### Implementation Complexity: High
**Timeline:** 2-3 weeks

### Key Libraries/Tools
- `openai` (GPT-4 Vision, CLIP embeddings)
- `transformers` (CLIP, BLIP for vision-language)
- `Pillow` (image processing)
- `langchain` (multi-modal chains)
- Object storage (S3, MinIO)

### Example Queries It Handles Well
- "What happened to vessel X yesterday?" (position + reports + images)
- "Show me all data about the incident at coordinates Y" (cross-modal correlation)
- "Verify AIS data with satellite imagery" (visual confirmation)

### Example Queries It Struggles With
- "Which ship is fastest?" (simple query, no multi-modal data needed)

---

## Comparative Analysis

| Approach | Suitability | Complexity | Timeline | Best For |
|----------|-------------|------------|----------|----------|
| **Naive RAG** | 2/5 | Low | 1-2 days | Quick POC, simple factual lookups |
| **Hybrid RAG** | 4/5 | Medium | 3-5 days | **Production ready**, filtering + semantic |
| **Graph RAG** | 3/5 | High | 1-2 weeks | Relationship queries, route analysis |
| **Agentic RAG** | 4/5 | High | 1-2 weeks | **Showcase project**, complex reasoning |
| **Temporal RAG** | 5/5 | Medium | 3-5 days | **ESSENTIAL**, time-aware ship tracking |
| **Multi-Modal RAG** | 2/5* | High | 2-3 weeks | If visual data available (*then 4/5) |

*Score increases to 4/5 if drone imagery or incident reports are part of the system.

---

## Recommended Implementation Roadmap

### Phase 1: MVP (Week 1) - Hybrid + Temporal RAG
**Goal:** Production-ready system handling 80% of queries

**Components:**
1. **Hybrid RAG** for filtering + semantic search
   - Redis Vector Search (embeddings)
   - Full-text search (vessel names)
   - Tag/numeric filters (type, speed)
   - Geo queries (proximity to ports)

2. **Temporal RAG** for time-awareness
   - Redis Sorted Sets (time-series positions)
   - Recency weighting (exponential decay)
   - Temporal query parser ("last hour", "yesterday")

**Deliverables:**
- Handle queries: "Tankers near Mumbai in the last hour"
- Real-time position updates from Redis Streams
- Time-filtered historical queries

**Tech Stack:**
- Redis Stack (Vector + Sorted Sets + Streams)
- `redis-py`, `openai`, `langchain`
- Simple Flask/FastAPI endpoint

### Phase 2: Advanced (Week 2) - Agentic RAG
**Goal:** Showcase advanced AI capabilities for portfolio

**Components:**
1. **Agentic RAG** with LangGraph
   - Multi-step query decomposition
   - Tools: distance calculator, destination predictor, port lookup
   - Self-reflective routing

**Deliverables:**
- Handle complex queries: "Ships near each other heading to same port"
- Show reasoning steps in UI (transparency)
- Integrate with external APIs (weather, port schedules)

**Tech Stack:**
- `langgraph`, `langchain`
- OpenAI GPT-4 (for reasoning)
- Custom tools (Python functions)

### Phase 3: Optional (Week 3+) - Graph RAG or Multi-Modal
**Goal:** Differentiate project for specific use cases

**Option A: Graph RAG** (if emphasizing analytics)
- Neo4j integration
- Relationship queries (route patterns, vessel meetings)
- Proximity event detection

**Option B: Multi-Modal RAG** (if drone imagery available)
- Vision model integration
- Satellite image correlation
- Incident report synthesis

**Choose based on:** Data availability and portfolio positioning (AI reasoning vs. data analytics)

---

## Implementation Examples by Query Type

| Query | Recommended Approach | Reason |
|-------|---------------------|--------|
| "Where is MARITIME PRIDE?" | Hybrid RAG (text match) | Exact vessel name lookup |
| "Tankers near Mumbai" | Hybrid RAG (tag + geo) | Type filter + proximity |
| "Ships in the last hour" | Temporal RAG | Time window critical |
| "Ships heading north" | Hybrid RAG (vector + heading) | Semantic + numeric filter |
| "Ships near each other yesterday" | Agentic RAG | Multi-step: time filter → distance calc → filter |
| "Vessels on same route as X" | Graph RAG | Relationship traversal |
| "What happened to vessel X?" | Multi-Modal RAG | Combine position + reports + images |
| "Fastest ship right now" | Temporal RAG + Structured | Recency + speed aggregation |

---

## Redis-Specific Implementation Tips

### 1. Schema Design
```python
# Unified document with all fields
{
    "vessel_name": "MARITIME PRIDE",
    "vessel_type": "TANKER",
    "imo": "9234567",
    "position": "18.9388,72.8354",  # Geo field
    "speed": 12.5,
    "heading": 45,
    "timestamp": 1735123456,
    "embedding": [0.1, 0.2, ...],  # 768-dim vector
    "source": "AIS"  # Sensor type
}
```

### 2. Index Creation
```python
from redis.commands.search.field import VectorField, TagField, NumericField, GeoField, TextField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType

schema = (
    VectorField("embedding", "HNSW", {
        "TYPE": "FLOAT32",
        "DIM": 768,
        "DISTANCE_METRIC": "COSINE",
        "INITIAL_CAP": 10000
    }),
    TextField("vessel_name", weight=2.0),  # Full-text, higher weight
    TagField("vessel_type"),
    TagField("source"),
    NumericField("speed", sortable=True),
    NumericField("heading"),
    NumericField("timestamp", sortable=True),
    GeoField("position")
)

definition = IndexDefinition(prefix=["ship:"], index_type=IndexType.HASH)
redis_client.ft().create_index(schema, definition=definition)
```

### 3. Hybrid Query Examples
```python
from redis.commands.search.query import Query

# Example 1: Tankers near Mumbai, last hour, speed > 10 knots
current_time = time.time()
one_hour_ago = current_time - 3600

query = Query(
    "(@vessel_type:{TANKER}) "
    "(@timestamp:[{} {}]) "
    "(@speed:[10 +inf]) "
    "@position:[18.9388 72.8354 50 km]"
    .format(one_hour_ago, current_time)
).sort_by("timestamp", asc=False).paging(0, 10)

results = redis_client.ft().search(query)

# Example 2: Vector similarity + filters
vector_query = embed_query("ships heading north")
hybrid_query = Query(
    "(@vessel_type:{TANKER|CARGO}) "
    "(@timestamp:[{} {}]) "
    "=>[KNN 10 @embedding $vector AS score]"
    .format(one_hour_ago, current_time)
).sort_by("score").return_fields("vessel_name", "position", "speed", "score").dialect(2)

results = redis_client.ft().search(hybrid_query, query_params={"vector": vector_query})
```

### 4. Time-Series Patterns
```python
# Pattern 1: Sorted Set for position history
def track_vessel_history(vessel_name, position_data):
    key = f"history:{vessel_name}"
    timestamp = time.time()
    redis_client.zadd(key, {json.dumps(position_data): timestamp})
    # Set TTL to 30 days
    redis_client.expire(key, 30 * 24 * 3600)

# Pattern 2: Redis Streams for real-time ingestion
def ingest_from_sensor(sensor_type, data):
    stream_key = f"sensor:{sensor_type}"
    redis_client.xadd(stream_key, data, maxlen=10000)  # Keep last 10K entries

# Pattern 3: Combine streams into unified index
def consume_and_index():
    # Read from all sensor streams
    streams = {
        "sensor:AIS": "0",
        "sensor:radar": "0",
        "sensor:satellite": "0",
        "sensor:drone": "0"
    }

    while True:
        results = redis_client.xread(streams, block=1000, count=100)
        for stream, messages in results:
            for msg_id, data in messages:
                # Index in vector DB + sorted set
                index_ship_position(data)
                track_vessel_history(data['vessel_name'], data)
                streams[stream] = msg_id
```

---

## Cost & Performance Estimates

### Embedding Costs (OpenAI text-embedding-3-small)
- **$0.02 per 1M tokens**
- Average ship record: ~50 tokens → $0.000001 per record
- 1M ship positions: $1 in embedding costs

### LLM Costs (GPT-4 for generation)
- **Input:** $2.50/1M tokens, **Output:** $10/1M tokens
- Hybrid RAG query: ~500 input tokens + 200 output → $0.003 per query
- 1000 queries/day: $3/day = $90/month

### Agentic RAG Costs (Multiple LLM calls)
- Planning (GPT-4): 300 tokens
- Tool calls: 3 × 200 tokens
- Synthesis (GPT-4): 400 tokens
- Total: ~1500 tokens → $0.015 per query
- 1000 queries/day: $15/day = $450/month

**Cost Optimization:**
- Use GPT-4o-mini for routing/planning ($0.15/1M in, $0.60/1M out)
- Cache embeddings (don't re-embed same ships)
- Use Gemini 2.5 Flash for agentic reasoning ($0.30/1M in, $2.50/1M out)

### Redis Performance
- **Vector search:** <10ms for 1M vectors (HNSW index)
- **Geo queries:** <5ms for radius search
- **Sorted set range:** <2ms for time windows
- **Throughput:** 10,000+ queries/sec on single instance

---

## References & Further Reading

### Research Papers
- [Solving Freshness in RAG: A Simple Recency Prior](https://arxiv.org/html/2509.19376) - Temporal RAG with recency weighting
- [Multimodal RAG for Unstructured Data](https://arxiv.org/pdf/2510.14592) - MAHA architecture
- [Agentic Retrieval-Augmented Generation for Time Series](https://arxiv.org/abs/2408.14484) - Time-series specific RAG

### Technical Guides
- [Neo4j Knowledge Graph RAG Tutorial](https://neo4j.com/blog/developer/knowledge-graph-rag-application/)
- [LangGraph Agentic RAG Guide](https://qdrant.tech/documentation/agentic-rag-langgraph/)
- [Redis Vector Search Documentation](https://redis.io/docs/stack/search/reference/vectors/)

### Industry Examples
- [MarineTraffic](https://www.marinetraffic.com/) - Global AIS ship tracking
- [VesselFinder](https://www.vesselfinder.com/) - Real-time vessel positions
- [ORBCOMM Satellite AIS](https://www.orbcomm.com/) - S-AIS network

---

## Sources

- [The 2025 Guide to Retrieval-Augmented Generation (RAG)](https://www.edenai.co/post/the-2025-guide-to-retrieval-augmented-generation-rag)
- [8 Retrieval Augmented Generation (RAG) Architectures You Should Know in 2025](https://humanloop.com/blog/rag-architectures)
- [RAG Architecture Explained: A Comprehensive Guide [2025]](https://orq.ai/blog/rag-architecture)
- [Neo4j Knowledge Graph RAG Application Tutorial](https://neo4j.com/blog/developer/knowledge-graph-rag-application/)
- [Setting Up and Running GraphRAG with Neo4j](https://www.analyticsvidhya.com/blog/2024/11/graphrag-with-neo4j/)
- [How to Build GraphRAG Systems](https://ragaboutit.com/how-to-build-graphrag-systems-connecting-knowledge-graphs-with-retrieval-augmented-generation/)
- [Enhancing RAG Reasoning with Knowledge Graphs - Hugging Face](https://huggingface.co/learn/cookbook/en/rag_with_knowledge_graphs_neo4j)
- [Agentic RAG With LangGraph - Qdrant](https://qdrant.tech/documentation/agentic-rag-langgraph/)
- [A Comprehensive Guide to Building Agentic RAG Systems with LangGraph](https://www.analyticsvidhya.com/blog/2024/07/building-agentic-rag-systems-with-langgraph/)
- [Build a custom RAG agent with LangGraph - LangChain Docs](https://docs.langchain.com/oss/python/langgraph/agentic-rag)
- [Self-Reflective RAG with LangGraph](https://blog.langchain.com/agentic-rag-with-langgraph/)
- [What is Agentic RAG? | IBM](https://www.ibm.com/think/topics/agentic-rag)
- [Solving Freshness in RAG: A Simple Recency Prior](https://arxiv.org/html/2509.19376)
- [Retrieval Augmented Time Series Forecasting](https://arxiv.org/abs/2411.08249)
- [Agentic Retrieval-Augmented Generation for Time Series Analysis](https://arxiv.org/abs/2408.14484)
- [Beyond Basic RAG: Retrieval Weighting](https://blog.langflow.org/beyond-basic-rag-retrieval-weighting/)
- [Multimodal RAG for Unstructured Data](https://arxiv.org/pdf/2510.14592)
- [Building data pipelines for RAG use cases - IBM](https://www.ibm.com/new/announcements/building-data-pipelines-that-ingest-preprocess-transform-unstructured-data-enable-rag-use-cases)
- [Physical AI: Building the Next Foundation in Autonomous Intelligence - AWS](https://aws.amazon.com/blogs/spatial/physical-ai-building-the-next-foundation-in-autonomous-intelligence/)
- [Automatic Identification System (AIS) - Wikipedia](https://en.wikipedia.org/wiki/Automatic_identification_system)
- [MarineTraffic: Global Ship Tracking Intelligence](https://www.marinetraffic.com/en/ais/home/)
- [VesselFinder - Free AIS Vessel Tracking](https://www.vesselfinder.com/)

---

## Conclusion

For your maritime ship tracking portfolio project, I recommend implementing:

1. **Start: Hybrid RAG + Temporal RAG** (Week 1)
   - Cover 80% of use cases
   - Production-ready approach
   - Showcase Redis expertise

2. **Enhance: Agentic RAG** (Week 2)
   - Differentiate your project
   - Demonstrate advanced AI capabilities
   - Great for job interviews

3. **Optional: Graph RAG** (if time permits)
   - Add relationship analytics
   - Show systems thinking
   - Valuable for data engineering roles

**Skip Multi-Modal RAG** unless your drone data includes actual imagery (not just sensor readings).

This combination provides **breadth** (multiple RAG approaches), **depth** (production-quality implementations), and **novelty** (agentic reasoning) - perfect for a standout portfolio project targeting 18-24 LPA AI Engineer roles.
