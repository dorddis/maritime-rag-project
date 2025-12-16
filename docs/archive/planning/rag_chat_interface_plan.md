# RAG Chat Interface with Pipeline Visualization

## Overview

Add a dedicated `/chat` page to the maritime dashboard that visualizes the RAG pipeline execution step-by-step using Server-Sent Events (SSE) streaming.

**User Requirements:**
- Dedicated `/chat` page (not sidebar/modal)
- SSE streaming for real-time updates
- Session-only history (Zustand, no persistence)
- Full pipeline visualization (routing, SQL, vector, fusion steps)

---

## Architecture

```
User Query
    |
    v
[Frontend: /chat page]
    |
    | POST /api/rag/chat/stream
    v
[Backend: SSE Endpoint]
    |
    | Streams events as each step completes
    v
[Frontend: Updates UI in real-time]
    |
    v
[Collapsible pipeline steps + Final answer]
```

---

## Files to Create

### Backend (Python)

| File | Purpose |
|------|---------|
| `api/chat_endpoints.py` | FastAPI SSE streaming endpoint |

### Frontend (TypeScript/React)

| File | Purpose |
|------|---------|
| `dashboard/src/app/chat/page.tsx` | Chat page route |
| `dashboard/src/components/chat/chat-container.tsx` | Main layout with history + input |
| `dashboard/src/components/chat/chat-input.tsx` | Query input with send button |
| `dashboard/src/components/chat/chat-message.tsx` | User/assistant message wrapper |
| `dashboard/src/components/chat/chat-history.tsx` | Scrollable message list |
| `dashboard/src/components/chat/pipeline-visualization.tsx` | Pipeline steps container |
| `dashboard/src/components/chat/pipeline-step.tsx` | Single collapsible step |
| `dashboard/src/components/chat/ship-result-card.tsx` | Ship result display |
| `dashboard/src/lib/chat-types.ts` | TypeScript interfaces |
| `dashboard/src/stores/chat-store.ts` | Zustand store for chat state |
| `dashboard/src/hooks/use-sse-chat.ts` | SSE connection hook |

### Files to Modify

| File | Change |
|------|--------|
| `admin/server.py` | Add `app.include_router(chat_router)` |
| `dashboard/src/components/dashboard/header.tsx` | Add nav link to /chat |

---

## SSE Event Protocol

```
Event: routing
Data: { status, query_type, confidence, reasoning, extracted_filters, time_range }

Event: sql_start
Data: { status: "start" }

Event: sql_complete
Data: { sql, row_count, results, execution_time_ms }

Event: vector_start
Data: { status: "start", query }

Event: vector_complete
Data: { results, count, top_similarities, execution_time_ms }

Event: realtime
Data: { track_count, filters_applied, execution_time_ms }

Event: fusion
Data: { method: "RRF", total_results, breakdown, execution_time_ms }

Event: answer
Data: { content }

Event: done
Data: { total_time_ms }
```

---

## Key Type Definitions

```typescript
// lib/chat-types.ts

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  pipeline?: PipelineState;
  results?: ShipResult[];
  isStreaming?: boolean;
}

interface PipelineState {
  routing?: RoutingStep;
  sql?: SQLStep;
  vector?: VectorStep;
  realtime?: RealtimeStep;
  fusion?: FusionStep;
}

type StepStatus = "pending" | "running" | "complete" | "error" | "skipped";
```

---

## Zustand Store Structure

```typescript
// stores/chat-store.ts (follows log-store.ts pattern)

interface ChatStore {
  messages: ChatMessage[];
  currentMessageId: string | null;
  isStreaming: boolean;

  addUserMessage: (content: string) => string;
  addAssistantMessage: () => string;
  updatePipelineStep: (messageId: string, step: string, status: StepStatus, data?: any) => void;
  setAnswer: (messageId: string, content: string) => void;
  setStreaming: (streaming: boolean) => void;
  clearHistory: () => void;
}
```

---

## UI Component Pattern

Pipeline steps follow `ingester-card.tsx` collapsible pattern:

```tsx
<Collapsible open={isOpen} onOpenChange={setIsOpen}>
  <CollapsibleTrigger asChild>
    <Button variant="ghost" className="w-full justify-between">
      <span className="flex items-center gap-2">
        <Icon className="h-4 w-4" />
        {stepName}
      </span>
      <span className="flex items-center gap-2">
        {status === "running" && <Loader2 className="animate-spin" />}
        <Badge>{status}</Badge>
        <span className="text-xs">{executionTimeMs}ms</span>
        {isOpen ? <ChevronUp /> : <ChevronDown />}
      </span>
    </Button>
  </CollapsibleTrigger>
  <CollapsibleContent>
    <div className="rounded-md border border-slate-700 bg-slate-900/50 p-3 mt-2">
      {/* Step-specific content */}
    </div>
  </CollapsibleContent>
</Collapsible>
```

---

## Implementation Order

### Phase 1: Backend SSE Endpoint
1. Create `api/chat_endpoints.py`
2. Implement `StreamingHybridExecutor` that yields events at each step
3. Add SSE endpoint `POST /api/rag/chat/stream`
4. Register router in `admin/server.py`
5. Test with curl: `curl -N -X POST http://localhost:8000/api/rag/chat/stream -d '{"query":"test"}'`

### Phase 2: Frontend Foundation
1. Create `lib/chat-types.ts` with all interfaces
2. Create `stores/chat-store.ts` following log-store pattern
3. Create `hooks/use-sse-chat.ts` for EventSource/fetch streaming

### Phase 3: Basic Chat UI
1. Create `app/chat/page.tsx`
2. Create `chat-container.tsx` with layout
3. Create `chat-input.tsx` with textarea + send button
4. Create `chat-history.tsx` with ScrollArea
5. Create `chat-message.tsx` for user/assistant bubbles

### Phase 4: Pipeline Visualization
1. Create `pipeline-visualization.tsx` container
2. Create `pipeline-step.tsx` with collapsible pattern
3. Add step-specific content renderers:
   - Query Analysis (type badge, confidence bar, filters)
   - SQL Query (syntax highlighted code block)
   - Vector Search (query + similarity scores)
   - Real-time Data (track count)
   - Result Fusion (RRF breakdown)

### Phase 5: Results Display
1. Create `ship-result-card.tsx` for final results
2. Add dark ship indicator badge
3. Add source indicator (structured/semantic/realtime)
4. Add fusion score display

### Phase 6: Integration
1. Add navigation link in `dashboard/header.tsx`
2. End-to-end testing
3. Error handling and edge cases

---

## Dependencies

### Backend
```bash
pip install sse-starlette
```

### Frontend
All dependencies already installed (shadcn/ui, zustand, react-query, lucide-react)

---

## Critical Files Reference

| File | Purpose |
|------|---------|
| `rag/hybrid/executor.py` | Core pipeline logic to wrap for streaming |
| `rag/router/query_router.py` | Query classification (STRUCTURED/SEMANTIC/HYBRID/TEMPORAL) |
| `api/rag_endpoints.py` | Existing endpoint patterns to follow |
| `stores/log-store.ts` | Zustand store pattern to follow |
| `components/ingester/ingester-card.tsx` | Collapsible UI pattern to follow |
| `lib/types.ts` | Type definition patterns |
| `hooks/use-websocket.ts` | Real-time connection pattern |

---

## Estimated Effort

- Phase 1 (Backend): 2-3 hours
- Phase 2 (Foundation): 1-2 hours
- Phase 3 (Basic UI): 2-3 hours
- Phase 4 (Pipeline Viz): 3-4 hours
- Phase 5 (Results): 1-2 hours
- Phase 6 (Integration): 1 hour

**Total: ~12-15 hours of implementation**
