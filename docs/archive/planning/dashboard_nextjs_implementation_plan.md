# Maritime Dashboard - Next.js + shadcn/ui Implementation Plan

## Goal
Build a professional React dashboard for controlling 4 maritime data ingesters with real-time log streaming, configuration panels, and WebSocket updates.

## Tech Stack
- **Frontend**: Next.js 14 (App Router) + TypeScript
- **UI**: shadcn/ui + Tailwind CSS
- **State**: React Query (server state) + Zustand (logs)
- **Real-time**: WebSocket
- **Backend**: Existing FastAPI (port 8000)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    NEXT.JS DASHBOARD (:3000)                    │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐   │
│  │ AIS Card        │ │ Radar Card      │ │ Satellite Card  │   │
│  │ ● RUNNING       │ │ ○ STOPPED       │ │ ● RUNNING       │   │
│  │ Ships: [===]100 │ │ Tracks: [==]50  │ │ Rate: [=]0.1Hz  │   │
│  │ Rate: [===]1Hz  │ │ Rate: [===]1Hz  │ │                 │   │
│  │ ─────────────── │ │ ─────────────── │ │ ─────────────── │   │
│  │ > Parsed MMSI.. │ │ > Waiting...    │ │ > 24 detections │   │
│  │ > Position at.. │ │                 │ │ > 5 dark ships  │   │
│  │ [Stop]          │ │ [Start]         │ │ [Stop]          │   │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ STREAM STATS  ais: 1,234 │ radar: 0 │ sat: 567 │ drone: │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                    WebSocket + REST API
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FASTAPI BACKEND (:8000)                      │
│  GET  /api/ingesters         POST /api/ingesters/{name}/start   │
│  GET  /api/streams/stats     POST /api/ingesters/{name}/stop    │
│  WS   /ws/dashboard          (real-time logs + status)          │
└─────────────────────────────────────────────────────────────────┘
```

## File Structure

```
maritime-rag-project/
├── dashboard/                       # NEW - Next.js app
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.ts
│   ├── components.json              # shadcn/ui config
│   ├── .env.local                   # NEXT_PUBLIC_API_URL
│   │
│   ├── app/
│   │   ├── layout.tsx               # Dark theme layout
│   │   ├── page.tsx                 # Main dashboard
│   │   ├── globals.css              # Tailwind + maritime theme
│   │   └── providers.tsx            # React Query + WebSocket
│   │
│   ├── components/
│   │   ├── ui/                      # shadcn/ui components
│   │   │   ├── button.tsx
│   │   │   ├── card.tsx
│   │   │   ├── badge.tsx
│   │   │   ├── slider.tsx
│   │   │   ├── scroll-area.tsx
│   │   │   └── collapsible.tsx
│   │   │
│   │   ├── ingester/
│   │   │   ├── ingester-card.tsx    # Main card component
│   │   │   ├── config-panel.tsx     # Sliders for rate, ships, etc.
│   │   │   └── log-window.tsx       # Terminal-style log viewer
│   │   │
│   │   └── dashboard/
│   │       ├── header.tsx
│   │       ├── ingester-grid.tsx
│   │       └── stream-stats.tsx
│   │
│   ├── lib/
│   │   ├── api.ts                   # REST API client
│   │   ├── types.ts                 # TypeScript interfaces
│   │   └── utils.ts                 # cn() helper
│   │
│   ├── hooks/
│   │   ├── use-ingesters.ts         # React Query hooks
│   │   ├── use-stream-stats.ts
│   │   └── use-websocket.ts         # WebSocket connection
│   │
│   └── stores/
│       └── log-store.ts             # Zustand for log buffers
│
├── admin/
│   ├── server.py                    # MODIFY - Add WebSocket endpoint
│   └── ingester_manager.py          # MODIFY - Fix Windows stdout
```

## Implementation Phases

### Phase 1: Backend WebSocket (30 min)
**Files to modify:**
- `admin/server.py` - Add `/ws/dashboard` endpoint
- `admin/ingester_manager.py` - Fix Windows stdout reading

**Key changes:**
```python
# admin/server.py - Add WebSocket endpoint
@app.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    await websocket.accept()
    while True:
        status = manager.get_all_status()
        logs = read_all_ingester_logs()
        await websocket.send_json({"status": status, "logs": logs})
        await asyncio.sleep(0.1)
```

### Phase 2: Next.js Setup (30 min)
```bash
cd maritime-rag-project
npx create-next-app@latest dashboard --typescript --tailwind --eslint --app
cd dashboard
npx shadcn-ui@latest init
npx shadcn-ui@latest add button card badge slider scroll-area collapsible
npm install @tanstack/react-query zustand lucide-react
```

### Phase 3: Core Infrastructure (45 min)
1. `lib/types.ts` - TypeScript interfaces
2. `lib/api.ts` - REST API client
3. `stores/log-store.ts` - Zustand log buffer (100 lines per ingester)
4. `hooks/use-websocket.ts` - WebSocket with auto-reconnect
5. `hooks/use-ingesters.ts` - React Query hooks

### Phase 4: UI Components (1 hour)
1. `app/layout.tsx` - Dark maritime theme
2. `app/page.tsx` - Dashboard grid layout
3. `components/ingester/ingester-card.tsx` - Status, config, logs, controls
4. `components/ingester/config-panel.tsx` - Sliders per ingester type
5. `components/ingester/log-window.tsx` - Auto-scroll terminal
6. `components/dashboard/stream-stats.tsx` - Redis counters

### Phase 5: Polish (30 min)
1. Loading states and error handling
2. Toast notifications for start/stop
3. Connection status indicator
4. Test on Windows

## Key Component: Ingester Card

Each card displays:
- **Header**: Name (AIS/RADAR/etc) + Format tag (NMEA 0183) + Status badge
- **Config Panel** (collapsible):
  - AIS: Ships slider (1-500), Rate slider (0.1-10 Hz)
  - Radar: Tracks slider (1-200), Rate slider
  - Satellite: Rate slider (0.01-1 Hz), Watch dir input
  - Drone: Rate slider, Watch dir input
- **Log Window**: Terminal-style, 100 lines max, color-coded levels
- **Controls**: Start/Stop button with loading state

## Color Scheme (Maritime Dark)
```css
--background: #1a1a2e     /* Deep navy */
--card: #16213e           /* Panel background */
--border: #0f3460         /* Borders */
--accent: #00d9ff         /* Cyan accent */
--destructive: #ff5252    /* Red for errors/stop */
--success: #00c853        /* Green for running */
```

## Ingester-Specific Colors
- AIS: `#00d9ff` (Cyan)
- Radar: `#ff6b6b` (Red)
- Satellite: `#feca57` (Yellow)
- Drone: `#1dd1a1` (Green)

## Config Sliders Per Ingester

| Ingester | Control | Range | Default |
|----------|---------|-------|---------|
| AIS | Ships | 1-500 | 100 |
| AIS | Rate (Hz) | 0.1-10 | 1.0 |
| Radar | Tracks | 1-200 | 50 |
| Radar | Rate (Hz) | 0.1-10 | 1.0 |
| Satellite | Rate (Hz) | 0.01-1 | 0.1 |
| Drone | Rate (Hz) | 0.1-5 | 0.5 |

## Windows Compatibility

The current `ingester_manager.py` uses `select.select()` which doesn't work on Windows. Fix:

```python
# Use asyncio subprocess for cross-platform stdout reading
process = await asyncio.create_subprocess_exec(
    *cmd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.STDOUT
)
```

## Success Criteria

- [ ] Next.js dashboard runs on port 3000
- [ ] 4 ingester cards with working start/stop
- [ ] Config sliders update ingester args
- [ ] Real-time log streaming via WebSocket
- [ ] Redis stream stats refresh every 2 seconds
- [ ] Professional dark maritime theme
- [ ] Works on Windows

## Commands to Run

```bash
# Terminal 1: Start FastAPI backend
cd maritime-rag-project
python -m uvicorn admin.server:app --reload --port 8000

# Terminal 2: Start Next.js dashboard
cd maritime-rag-project/dashboard
npm run dev
```

Dashboard at: http://localhost:3000
API at: http://localhost:8000
