# RAG Pipeline & UI Refactoring Plan

**Goal:** Correctly handle and visualize "General/Conversational" queries in the RAG pipeline, preventing the UI from displaying unnecessary technical steps (SQL/Vector) for non-data queries.

---

## 1. Backend Verification (Completed)
- [x] **Update `QueryRouter`:** Added `GENERAL` category to `QueryType` enum and LLM prompt.
- [x] **Update `HybridExecutor`:** Added `_execute_general` method to bypass SQL/Vector agents and return direct LLM response.

## 2. Frontend Type Definitions
**File:** `dashboard/src/lib/chat-types.ts`
- [ ] **Action:** Update `QueryType` type alias to include `'general'`.
- [ ] **Action:** Add configuration to `QUERY_TYPE_INFO` for the 'general' type (Label: "GENERAL", Color: Grey).

## 3. Frontend State Management
**File:** `dashboard/src/hooks/use-sse-chat.ts`
- [ ] **Action:** Modify the `routing` event handler.
- [ ] **Logic:**
    - When `routing` status is `complete`:
    - Check if `data.query_type === 'general'`.
    - **If General:** Do NOT initialize `sql`, `vector`, `realtime`, or `fusion` steps to `pending`. Leave them undefined.
    - **If Data Query:** Continue initializing them to `pending` (existing behavior).

## 4. Frontend Visualization
**File:** `dashboard/src/components/chat/pipeline-visualization.tsx`
- [ ] **Action:** Wrap the rendering of downstream steps (SQL, Vector, Realtime, Fusion) in a conditional block.
- [ ] **Logic:** `if (pipeline.routing?.queryType !== 'general') { render_steps }`
- [ ] **Outcome:** General queries will only show the "Query Analysis" step (to confirm the system understood the intent), while data queries show the full pipeline.

## 5. Verification
- [ ] **Test Case 1 (General):** User types "Hello".
    - *Expectation:* UI shows "Query Analysis" (General) -> Green checkmark -> Direct text response. No "SQL Query" or "Vector Search" boxes appear.
- [ ] **Test Case 2 (Structured):** User types "Tankers near Mumbai".
    - *Expectation:* UI shows full pipeline: Query Analysis (Structured) -> SQL Query -> Realtime -> Fusion -> Answer.
- [ ] **Test Case 3 (Hybrid):** User types "Suspicious tankers near Mumbai".
    - *Expectation:* UI shows full pipeline: Query Analysis (Hybrid) -> SQL + Vector -> Fusion -> Answer.
