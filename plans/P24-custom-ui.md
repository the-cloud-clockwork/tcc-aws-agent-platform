# P24 — QITP Dashboard (Custom UI)

## Objective
Build a web dashboard for the QITP platform — real-time portfolio monitoring, strategy performance, manual controls, and 2FA approval via web. Built with Next.js 15 + React 19 + Recharts + TailwindCSS. Deployed as a Docker container behind Cognito authentication.

## Plane Tickets
ROOT-70

## Target Repo
`~/dev/tccw-qitp-dashboard` (NEW)

## Dependencies
P14 (ibkr-mcp — portfolio data), P16 (risk engine — risk state), P18 (observability — pipeline data), P06 (artifacts-mcp — artifact store)

## Repo Structure
```
tccw-qitp-dashboard/
├── src/
│   ├── app/
│   │   ├── layout.tsx             # Root layout with sidebar nav
│   │   ├── page.tsx               # Dashboard home (overview)
│   │   ├── globals.css            # Tailwind + theme variables
│   │   ├── portfolio/
│   │   │   └── page.tsx           # Portfolio view: positions, P&L, allocation
│   │   ├── strategies/
│   │   │   └── page.tsx           # Strategy performance comparison
│   │   ├── pipeline/
│   │   │   └── page.tsx           # Pipeline runs: status, timing, logs
│   │   ├── risk/
│   │   │   └── page.tsx           # Risk dashboard: circuit breakers, limits
│   │   ├── watchlist/
│   │   │   └── page.tsx           # Watchlist management (add/remove symbols)
│   │   ├── approvals/
│   │   │   └── page.tsx           # 2FA web approval interface
│   │   └── settings/
│   │       └── page.tsx           # Settings: execution mode, alert config
│   ├── components/
│   │   ├── charts/
│   │   │   ├── EquityCurve.tsx
│   │   │   ├── PositionTable.tsx
│   │   │   ├── AllocationPie.tsx
│   │   │   ├── PnlBar.tsx
│   │   │   ├── RiskGauge.tsx
│   │   │   └── PipelineTimeline.tsx
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx
│   │   │   ├── Header.tsx
│   │   │   └── StatusBar.tsx
│   │   └── ui/
│   │       ├── Card.tsx
│   │       ├── Badge.tsx
│   │       └── Modal.tsx
│   ├── lib/
│   │   ├── api.ts                 # API client (fetch from backend)
│   │   ├── websocket.ts           # WebSocket for real-time updates
│   │   └── types.ts               # TypeScript types matching backend schemas
│   └── hooks/
│       ├── usePortfolio.ts
│       ├── usePipeline.ts
│       └── useWebSocket.ts
├── api/
│   ├── routes/
│   │   ├── portfolio.ts           # /api/portfolio — proxy to IBKR MCP
│   │   ├── strategies.ts          # /api/strategies — read from DynamoDB
│   │   ├── pipeline.ts            # /api/pipeline — SFN execution status
│   │   ├── risk.ts                # /api/risk — risk state from DynamoDB
│   │   ├── watchlist.ts           # /api/watchlist — CRUD watchlist
│   │   └── approvals.ts           # /api/approvals — 2FA web approval
│   └── middleware.ts              # Auth middleware (Cognito JWT)
├── public/
│   └── favicon.ico
├── tailwind.config.ts
├── tsconfig.json
├── next.config.ts
├── package.json
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── .github/
│   └── workflows/
│       └── ci.yml
├── CLAUDE.md
└── tests/
    ├── components/
    │   ├── EquityCurve.test.tsx
    │   └── PositionTable.test.tsx
    └── api/
        └── portfolio.test.ts
```

## Pages

| Page | Route | Data Source | Key Widgets |
|------|-------|-------------|-------------|
| Dashboard Home | `/` | IBKR MCP, DynamoDB | NAV card, daily P&L, positions count, next run, circuit breakers |
| Portfolio | `/portfolio` | IBKR MCP | Positions table, equity curve, allocation pie |
| Strategies | `/strategies` | DynamoDB, artifacts-mcp | Strategy comparison table, Sharpe/return/win-rate bars |
| Pipeline | `/pipeline` | Step Functions API | Run history, stage timeline, log viewer, manual trigger |
| Risk | `/risk` | DynamoDB `qitp_risk_state` | Circuit breaker status, rule thresholds, violation history, gauge |
| Watchlist | `/watchlist` | DynamoDB `qitp_watchlist` | Symbol CRUD, sector tags, gap threshold config |
| Approvals | `/approvals` | DynamoDB `qitp_2fa_events` | Pending orders, Approve/Reject, audit trail |
| Settings | `/settings` | Environment + DynamoDB | Execution mode switch, alert prefs, theme toggle |

## Libraries

| Library | Version | Purpose |
|---------|---------|---------|
| Next.js | 15.x | App Router, server components, API routes |
| React | 19.x | UI framework |
| Recharts | 2.x | Charts (line, bar, pie, radial) |
| TailwindCSS | 4.x | Utility-first CSS |
| @aws-sdk/client-dynamodb | 3.x | DynamoDB access |
| @aws-sdk/lib-dynamodb | 3.x | DynamoDB document client |
| @aws-sdk/client-sfn | 3.x | Step Functions status |
| jose | 5.x | Cognito JWT verification |
| lucide-react | latest | Icons |
| clsx | 2.x | Conditional classnames |

## Key Design Decisions

1. **Server Components by default** — Only mark `"use client"` for interactive charts and forms.
2. **API routes as backend proxy** — All AWS SDK calls happen server-side via Next.js Route Handlers. No AWS credentials in browser.
3. **WebSocket via API Gateway WebSocket API** — Real-time portfolio updates pushed from Lambda on position change events.
4. **Cognito JWT auth** — Middleware validates token on every request. No session cookies.
5. **Execution mode badge** — Always visible in header. Color-coded: green=backtest, yellow=paper, red=live.
6. **Dark theme default** — Trading dashboards are always dark. Light theme available via toggle.

---

## Implementation

### package.json

```json
{
  "name": "qitp-dashboard",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "test": "jest --passWithNoTests",
    "test:watch": "jest --watch",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "next": "^15.1.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "recharts": "^2.15.0",
    "@aws-sdk/client-dynamodb": "^3.700.0",
    "@aws-sdk/lib-dynamodb": "^3.700.0",
    "@aws-sdk/client-sfn": "^3.700.0",
    "@aws-sdk/client-s3": "^3.700.0",
    "jose": "^5.9.0",
    "lucide-react": "^0.468.0",
    "clsx": "^2.1.1"
  },
  "devDependencies": {
    "@types/node": "^22.10.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "typescript": "^5.7.0",
    "tailwindcss": "^4.0.0",
    "@tailwindcss/postcss": "^4.0.0",
    "postcss": "^8.4.0",
    "eslint": "^9.0.0",
    "eslint-config-next": "^15.1.0",
    "@testing-library/react": "^16.1.0",
    "@testing-library/jest-dom": "^6.6.0",
    "jest": "^29.7.0",
    "jest-environment-jsdom": "^29.7.0",
    "ts-jest": "^29.2.0",
    "@testing-library/user-event": "^14.5.0"
  }
}
```

### tsconfig.json

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": {
      "@/*": ["./src/*"],
      "@api/*": ["./api/*"]
    },
    "types": ["jest", "@testing-library/jest-dom"]
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

### next.config.ts

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  serverExternalPackages: [
    "@aws-sdk/client-dynamodb",
    "@aws-sdk/lib-dynamodb",
    "@aws-sdk/client-sfn",
    "@aws-sdk/client-s3",
  ],
  env: {
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8080",
    NEXT_PUBLIC_EXECUTION_MODE: process.env.EXECUTION_MODE || "backtest",
  },
};

export default nextConfig;
```

### tailwind.config.ts

```typescript
import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef2ff",
          100: "#e0e7ff",
          200: "#c7d2fe",
          300: "#a5b4fc",
          400: "#818cf8",
          500: "#6366f1",
          600: "#4f46e5",
          700: "#4338ca",
          800: "#3730a3",
          900: "#312e81",
          950: "#1e1b4b",
        },
        profit: "#22c55e",
        loss: "#ef4444",
        warning: "#f59e0b",
        surface: {
          DEFAULT: "#1e1e2e",
          light: "#ffffff",
          card: "#2a2a3e",
          "card-light": "#f8fafc",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
```

### postcss.config.mjs

```javascript
/** @type {import('postcss-load-config').Config} */
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
```

### .env.example

```bash
# AWS Configuration
AWS_REGION=eu-west-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=

# Cognito
COGNITO_USER_POOL_ID=eu-west-1_XXXXXXXXX
COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
COGNITO_ISSUER=https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_XXXXXXXXX

# QITP Backend
IBKR_MCP_URL=http://localhost:8001
MARKET_DATA_MCP_URL=http://localhost:8002
ARTIFACTS_MCP_URL=http://localhost:8004

# Execution Mode
EXECUTION_MODE=backtest

# WebSocket
NEXT_PUBLIC_WS_URL=ws://localhost:8080

# DynamoDB Table Names
DYNAMODB_WATCHLIST_TABLE=qitp_watchlist
DYNAMODB_RISK_STATE_TABLE=qitp_risk_state
DYNAMODB_AUDIT_LOG_TABLE=qitp_audit_log
DYNAMODB_STRATEGY_REGISTRY_TABLE=qitp_strategy_registry
DYNAMODB_2FA_EVENTS_TABLE=qitp_2fa_events
DYNAMODB_RUN_HISTORY_TABLE=qitp_run_history

# Step Functions
SFN_STATE_MACHINE_ARN=arn:aws:states:eu-west-1:835618032093:stateMachine:qitp-weekly-analysis
```

### .gitignore

```
node_modules/
.next/
out/
build/
dist/
.env
.env.local
.env.production
*.tsbuildinfo
next-env.d.ts
coverage/
.DS_Store
```

### CLAUDE.md

```markdown
# tccw-qitp-dashboard

QITP web dashboard — portfolio monitoring, strategy performance, pipeline status, risk management, and 2FA approval.

## Stack
- Next.js 15 (App Router, server components)
- React 19 + Recharts + TailwindCSS 4
- AWS SDK v3 (DynamoDB, SFN, S3)
- Cognito JWT auth

## Commands
- `npm run dev` — local dev server on :3000
- `npm run build` — production build
- `npm test` — run Jest tests
- `npm run typecheck` — TypeScript check
- `docker compose up` — run with Docker

## Architecture
- All AWS calls happen server-side in Route Handlers (`src/app/api/`)
- Client components marked with `"use client"` only for interactivity
- WebSocket for real-time portfolio updates
- Execution mode from `EXECUTION_MODE` env var — displayed in header

## Parent Specs
All architecture decisions live in `~/tccw-strand-package/CLAUDE.md`.
```

---

### src/app/globals.css

```css
@import "tailwindcss";

:root {
  --color-background: #0a0a1a;
  --color-foreground: #e2e8f0;
  --color-surface: #1e1e2e;
  --color-surface-card: #2a2a3e;
  --color-border: #3f3f5e;
  --color-muted: #94a3b8;
}

.light {
  --color-background: #f8fafc;
  --color-foreground: #0f172a;
  --color-surface: #ffffff;
  --color-surface-card: #f1f5f9;
  --color-border: #e2e8f0;
  --color-muted: #64748b;
}

body {
  background: var(--color-background);
  color: var(--color-foreground);
  font-family: system-ui, -apple-system, sans-serif;
}

/* Scrollbar styling */
::-webkit-scrollbar {
  width: 6px;
}
::-webkit-scrollbar-track {
  background: var(--color-surface);
}
::-webkit-scrollbar-thumb {
  background: var(--color-border);
  border-radius: 3px;
}

/* Recharts tooltip override */
.recharts-tooltip-wrapper {
  outline: none !important;
}
```

### src/lib/types.ts

```typescript
/**
 * TypeScript types matching QITP backend schemas.
 * Keep in sync with agent-core Pydantic models.
 */

// --- Portfolio ---

export interface Position {
  symbol: string;
  quantity: number;
  avg_entry_price: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  sector: string;
  trailing_stop_pct: number;
  trailing_stop_price: number;
  opened_at: string; // ISO datetime
}

export interface PortfolioSummary {
  nav: number;
  daily_pnl: number;
  daily_pnl_pct: number;
  total_pnl: number;
  total_pnl_pct: number;
  open_positions: number;
  buying_power: number;
  cash: number;
  margin_used: number;
  last_updated: string;
}

export interface EquityPoint {
  date: string;
  nav: number;
  benchmark: number;
}

export interface AllocationSlice {
  sector: string;
  value: number;
  pct: number;
  color: string;
}

// --- Strategies ---

export interface StrategyPerformance {
  strategy_id: string;
  name: string;
  sharpe_ratio: number;
  total_return_pct: number;
  annualized_return_pct: number;
  max_drawdown_pct: number;
  win_rate_pct: number;
  total_trades: number;
  profit_factor: number;
  last_backtest: string;
  status: "active" | "paused" | "draft";
}

// --- Pipeline ---

export type PipelineStatus = "RUNNING" | "SUCCEEDED" | "FAILED" | "TIMED_OUT" | "ABORTED";

export interface PipelineRun {
  execution_id: string;
  name: string;
  status: PipelineStatus;
  started_at: string;
  stopped_at?: string;
  duration_seconds?: number;
  stages: PipelineStage[];
}

export interface PipelineStage {
  name: string;
  status: PipelineStatus;
  started_at?: string;
  stopped_at?: string;
  duration_seconds?: number;
  output_key?: string; // S3 claim-check key
  error?: string;
}

// --- Risk ---

export type CircuitBreakerStatus = "OK" | "TRIGGERED" | "MANUAL_OVERRIDE";

export interface RiskRule {
  rule_id: string;
  name: string;
  threshold: number;
  current_value: number;
  unit: string;
  status: CircuitBreakerStatus;
  triggered_at?: string;
  resumes_at?: string;
}

export interface RiskState {
  rules: RiskRule[];
  overall_status: CircuitBreakerStatus;
  last_checked: string;
  daily_loss_pct: number;
  drawdown_from_peak_pct: number;
}

// --- Watchlist ---

export interface WatchlistItem {
  symbol: string;
  name: string;
  sector: string;
  gap_threshold_pct: number;
  enabled: boolean;
  added_at: string;
  notes?: string;
}

// --- Approvals (2FA) ---

export type ApprovalStatus = "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED";

export interface ApprovalRequest {
  request_id: string;
  task_token: string;
  order_type: string;
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  price?: number;
  strategy_id: string;
  rationale: string;
  risk_check_result: "PASS" | "FAIL";
  status: ApprovalStatus;
  created_at: string;
  expires_at: string;
  decided_at?: string;
  decided_by?: string;
}

// --- Settings ---

export type ExecutionMode = "backtest" | "paper" | "live";

export interface DashboardSettings {
  execution_mode: ExecutionMode;
  theme: "dark" | "light";
  alert_telegram: boolean;
  alert_email: boolean;
  auto_refresh_seconds: number;
}

// --- WebSocket ---

export type WSMessageType =
  | "portfolio_update"
  | "position_change"
  | "circuit_breaker"
  | "pipeline_status"
  | "approval_request"
  | "heartbeat";

export interface WSMessage {
  type: WSMessageType;
  payload: unknown;
  timestamp: string;
}
```

### src/lib/api.ts

```typescript
/**
 * API client for QITP dashboard backend routes.
 * All calls go to Next.js Route Handlers which proxy to AWS services.
 */

import type {
  PortfolioSummary,
  Position,
  EquityPoint,
  AllocationSlice,
  StrategyPerformance,
  PipelineRun,
  RiskState,
  WatchlistItem,
  ApprovalRequest,
  DashboardSettings,
} from "./types";

const BASE = "/api";

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

// --- Portfolio ---

export async function getPortfolioSummary(): Promise<PortfolioSummary> {
  return fetchJson<PortfolioSummary>("/portfolio/summary");
}

export async function getPositions(): Promise<Position[]> {
  return fetchJson<Position[]>("/portfolio/positions");
}

export async function getEquityCurve(days?: number): Promise<EquityPoint[]> {
  const params = days ? `?days=${days}` : "";
  return fetchJson<EquityPoint[]>(`/portfolio/equity${params}`);
}

export async function getAllocation(): Promise<AllocationSlice[]> {
  return fetchJson<AllocationSlice[]>("/portfolio/allocation");
}

// --- Strategies ---

export async function getStrategies(): Promise<StrategyPerformance[]> {
  return fetchJson<StrategyPerformance[]>("/strategies");
}

// --- Pipeline ---

export async function getPipelineRuns(limit?: number): Promise<PipelineRun[]> {
  const params = limit ? `?limit=${limit}` : "";
  return fetchJson<PipelineRun[]>(`/pipeline${params}`);
}

export async function triggerPipeline(): Promise<{ execution_id: string }> {
  return fetchJson<{ execution_id: string }>("/pipeline/trigger", {
    method: "POST",
  });
}

// --- Risk ---

export async function getRiskState(): Promise<RiskState> {
  return fetchJson<RiskState>("/risk");
}

// --- Watchlist ---

export async function getWatchlist(): Promise<WatchlistItem[]> {
  return fetchJson<WatchlistItem[]>("/watchlist");
}

export async function addToWatchlist(
  item: Omit<WatchlistItem, "added_at">
): Promise<WatchlistItem> {
  return fetchJson<WatchlistItem>("/watchlist", {
    method: "POST",
    body: JSON.stringify(item),
  });
}

export async function removeFromWatchlist(symbol: string): Promise<void> {
  await fetch(`${BASE}/watchlist/${symbol}`, { method: "DELETE" });
}

export async function updateWatchlistItem(
  symbol: string,
  updates: Partial<WatchlistItem>
): Promise<WatchlistItem> {
  return fetchJson<WatchlistItem>(`/watchlist/${symbol}`, {
    method: "PATCH",
    body: JSON.stringify(updates),
  });
}

// --- Approvals ---

export async function getPendingApprovals(): Promise<ApprovalRequest[]> {
  return fetchJson<ApprovalRequest[]>("/approvals?status=PENDING");
}

export async function getApprovalHistory(): Promise<ApprovalRequest[]> {
  return fetchJson<ApprovalRequest[]>("/approvals?status=ALL");
}

export async function approveOrder(requestId: string): Promise<void> {
  await fetchJson("/approvals/decide", {
    method: "POST",
    body: JSON.stringify({ request_id: requestId, decision: "APPROVED" }),
  });
}

export async function rejectOrder(
  requestId: string,
  reason: string
): Promise<void> {
  await fetchJson("/approvals/decide", {
    method: "POST",
    body: JSON.stringify({
      request_id: requestId,
      decision: "REJECTED",
      reason,
    }),
  });
}

// --- Settings ---

export async function getSettings(): Promise<DashboardSettings> {
  return fetchJson<DashboardSettings>("/settings");
}

export async function updateSettings(
  updates: Partial<DashboardSettings>
): Promise<DashboardSettings> {
  return fetchJson<DashboardSettings>("/settings", {
    method: "PATCH",
    body: JSON.stringify(updates),
  });
}
```

### src/lib/websocket.ts

```typescript
/**
 * WebSocket client for real-time QITP updates.
 * Connects to API Gateway WebSocket API.
 * Auto-reconnects with exponential backoff.
 */

import type { WSMessage, WSMessageType } from "./types";

type Listener = (msg: WSMessage) => void;

export class QitpWebSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private listeners: Map<WSMessageType | "*", Set<Listener>> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private _connected = false;

  constructor(url: string) {
    this.url = url;
  }

  get connected(): boolean {
    return this._connected;
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this._connected = true;
        this.reconnectAttempts = 0;
        this.emit({
          type: "heartbeat",
          payload: { status: "connected" },
          timestamp: new Date().toISOString(),
        });
      };

      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as WSMessage;
          this.emit(msg);
        } catch {
          console.error("Failed to parse WS message:", event.data);
        }
      };

      this.ws.onclose = () => {
        this._connected = false;
        this.scheduleReconnect();
      };

      this.ws.onerror = () => {
        this._connected = false;
        this.ws?.close();
      };
    } catch {
      this.scheduleReconnect();
    }
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.reconnectAttempts = this.maxReconnectAttempts;
    this.ws?.close();
    this._connected = false;
  }

  on(type: WSMessageType | "*", listener: Listener): () => void {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set());
    }
    this.listeners.get(type)!.add(listener);
    return () => this.listeners.get(type)?.delete(listener);
  }

  private emit(msg: WSMessage): void {
    this.listeners.get(msg.type)?.forEach((fn) => fn(msg));
    this.listeners.get("*")?.forEach((fn) => fn(msg));
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return;
    const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 30000);
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }
}
```

### src/hooks/useWebSocket.ts

```typescript
"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { QitpWebSocket } from "@/lib/websocket";
import type { WSMessage, WSMessageType } from "@/lib/types";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8080";

let sharedWs: QitpWebSocket | null = null;

function getSharedWs(): QitpWebSocket {
  if (!sharedWs) {
    sharedWs = new QitpWebSocket(WS_URL);
    sharedWs.connect();
  }
  return sharedWs;
}

export function useWebSocket(
  type: WSMessageType | "*",
  handler: (msg: WSMessage) => void
): { connected: boolean } {
  const ws = useRef<QitpWebSocket>(getSharedWs());
  const [connected, setConnected] = useState(false);
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    const unsubType = ws.current.on(type, (msg) => handlerRef.current(msg));
    const unsubHeartbeat = ws.current.on("heartbeat", () => {
      setConnected(ws.current.connected);
    });
    setConnected(ws.current.connected);

    return () => {
      unsubType();
      unsubHeartbeat();
    };
  }, [type]);

  return { connected };
}

export function useWebSocketCallback<T>(
  type: WSMessageType,
  transform: (payload: unknown) => T
): { data: T | null; connected: boolean } {
  const [data, setData] = useState<T | null>(null);
  const transformRef = useRef(transform);
  transformRef.current = transform;

  const handler = useCallback((msg: WSMessage) => {
    setData(transformRef.current(msg.payload));
  }, []);

  const { connected } = useWebSocket(type, handler);
  return { data, connected };
}
```

### src/hooks/usePortfolio.ts

```typescript
"use client";

import { useState, useEffect, useCallback } from "react";
import type { PortfolioSummary, Position } from "@/lib/types";
import { getPortfolioSummary, getPositions } from "@/lib/api";
import { useWebSocket } from "./useWebSocket";

export function usePortfolio(refreshInterval = 30000) {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [s, p] = await Promise.all([
        getPortfolioSummary(),
        getPositions(),
      ]);
      setSummary(s);
      setPositions(p);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch portfolio");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, refreshInterval);
    return () => clearInterval(interval);
  }, [refresh, refreshInterval]);

  // Real-time updates override polling
  useWebSocket("portfolio_update", (msg) => {
    const payload = msg.payload as Partial<PortfolioSummary>;
    setSummary((prev) => (prev ? { ...prev, ...payload } : null));
  });

  useWebSocket("position_change", (msg) => {
    const updated = msg.payload as Position;
    setPositions((prev) =>
      prev.map((p) => (p.symbol === updated.symbol ? updated : p))
    );
  });

  return { summary, positions, loading, error, refresh };
}
```

### src/hooks/usePipeline.ts

```typescript
"use client";

import { useState, useEffect, useCallback } from "react";
import type { PipelineRun } from "@/lib/types";
import { getPipelineRuns, triggerPipeline } from "@/lib/api";
import { useWebSocket } from "./useWebSocket";

export function usePipeline(limit = 10) {
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await getPipelineRuns(limit);
      setRuns(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch pipeline");
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useWebSocket("pipeline_status", (msg) => {
    const update = msg.payload as PipelineRun;
    setRuns((prev) => {
      const idx = prev.findIndex((r) => r.execution_id === update.execution_id);
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = update;
        return next;
      }
      return [update, ...prev].slice(0, limit);
    });
  });

  const trigger = useCallback(async () => {
    setTriggering(true);
    try {
      await triggerPipeline();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to trigger pipeline");
    } finally {
      setTriggering(false);
    }
  }, [refresh]);

  return { runs, loading, triggering, error, refresh, trigger };
}
```

---

### src/components/ui/Card.tsx

```typescript
import { clsx } from "clsx";
import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  title?: string;
  subtitle?: string;
  action?: ReactNode;
}

export function Card({ children, className, title, subtitle, action }: CardProps) {
  return (
    <div
      className={clsx(
        "rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-card)] p-6",
        className
      )}
    >
      {(title || action) && (
        <div className="mb-4 flex items-center justify-between">
          <div>
            {title && (
              <h3 className="text-lg font-semibold text-[var(--color-foreground)]">
                {title}
              </h3>
            )}
            {subtitle && (
              <p className="text-sm text-[var(--color-muted)]">{subtitle}</p>
            )}
          </div>
          {action}
        </div>
      )}
      {children}
    </div>
  );
}
```

### src/components/ui/Badge.tsx

```typescript
import { clsx } from "clsx";

type BadgeVariant = "success" | "danger" | "warning" | "info" | "neutral";

interface BadgeProps {
  label: string;
  variant?: BadgeVariant;
  pulse?: boolean;
}

const variantStyles: Record<BadgeVariant, string> = {
  success: "bg-green-500/20 text-green-400 border-green-500/30",
  danger: "bg-red-500/20 text-red-400 border-red-500/30",
  warning: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  info: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  neutral: "bg-gray-500/20 text-gray-400 border-gray-500/30",
};

export function Badge({ label, variant = "neutral", pulse }: BadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        variantStyles[variant]
      )}
    >
      {pulse && (
        <span className="relative flex h-2 w-2">
          <span
            className={clsx(
              "absolute inline-flex h-full w-full animate-ping rounded-full opacity-75",
              variant === "success" && "bg-green-400",
              variant === "danger" && "bg-red-400",
              variant === "warning" && "bg-yellow-400"
            )}
          />
          <span
            className={clsx(
              "relative inline-flex h-2 w-2 rounded-full",
              variant === "success" && "bg-green-500",
              variant === "danger" && "bg-red-500",
              variant === "warning" && "bg-yellow-500"
            )}
          />
        </span>
      )}
      {label}
    </span>
  );
}
```

### src/components/ui/Modal.tsx

```typescript
"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}

export function Modal({ open, onClose, title, children }: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open) {
      dialog.showModal();
    } else {
      dialog.close();
    }
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      className="w-full max-w-lg rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-0 text-[var(--color-foreground)] backdrop:bg-black/60"
      onClose={onClose}
    >
      <div className="flex items-center justify-between border-b border-[var(--color-border)] px-6 py-4">
        <h2 className="text-lg font-semibold">{title}</h2>
        <button
          onClick={onClose}
          className="rounded-lg p-1 hover:bg-[var(--color-surface-card)]"
        >
          <X className="h-5 w-5" />
        </button>
      </div>
      <div className="p-6">{children}</div>
    </dialog>
  );
}
```

---

### src/components/layout/Sidebar.tsx

```typescript
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import {
  LayoutDashboard,
  Briefcase,
  TrendingUp,
  Play,
  ShieldAlert,
  List,
  CheckCircle,
  Settings,
} from "lucide-react";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/portfolio", label: "Portfolio", icon: Briefcase },
  { href: "/strategies", label: "Strategies", icon: TrendingUp },
  { href: "/pipeline", label: "Pipeline", icon: Play },
  { href: "/risk", label: "Risk", icon: ShieldAlert },
  { href: "/watchlist", label: "Watchlist", icon: List },
  { href: "/approvals", label: "Approvals", icon: CheckCircle },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-screen w-64 flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)]">
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 border-b border-[var(--color-border)] px-6">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 font-bold text-white text-sm">
          Q
        </div>
        <span className="text-lg font-bold tracking-tight">QITP</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <ul className="space-y-1">
          {navItems.map((item) => {
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={clsx(
                    "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                    active
                      ? "bg-brand-600/20 text-brand-400"
                      : "text-[var(--color-muted)] hover:bg-[var(--color-surface-card)] hover:text-[var(--color-foreground)]"
                  )}
                >
                  <Icon className="h-5 w-5 shrink-0" />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Version */}
      <div className="border-t border-[var(--color-border)] px-6 py-3">
        <p className="text-xs text-[var(--color-muted)]">QITP Dashboard v0.1.0</p>
      </div>
    </aside>
  );
}
```

### src/components/layout/Header.tsx

```typescript
"use client";

import { Badge } from "@/components/ui/Badge";
import { Bell, Moon, Sun } from "lucide-react";
import { useState } from "react";
import type { ExecutionMode } from "@/lib/types";

const modeConfig: Record<ExecutionMode, { label: string; variant: "success" | "warning" | "danger" }> = {
  backtest: { label: "BACKTEST", variant: "success" },
  paper: { label: "PAPER", variant: "warning" },
  live: { label: "LIVE", variant: "danger" },
};

export function Header() {
  const mode = (process.env.NEXT_PUBLIC_EXECUTION_MODE || "backtest") as ExecutionMode;
  const config = modeConfig[mode];
  const [dark, setDark] = useState(true);

  const toggleTheme = () => {
    setDark(!dark);
    document.documentElement.classList.toggle("light");
  };

  return (
    <header className="flex h-16 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] px-6">
      <div className="flex items-center gap-4">
        <h1 className="text-sm font-medium text-[var(--color-muted)]">
          Quantitative Intelligence Trading Platform
        </h1>
      </div>
      <div className="flex items-center gap-4">
        <Badge label={config.label} variant={config.variant} pulse={mode === "live"} />
        <button
          onClick={toggleTheme}
          className="rounded-lg p-2 text-[var(--color-muted)] hover:bg-[var(--color-surface-card)]"
          title="Toggle theme"
        >
          {dark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </button>
        <button
          className="relative rounded-lg p-2 text-[var(--color-muted)] hover:bg-[var(--color-surface-card)]"
          title="Notifications"
        >
          <Bell className="h-5 w-5" />
          <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-red-500" />
        </button>
      </div>
    </header>
  );
}
```

### src/components/layout/StatusBar.tsx

```typescript
"use client";

import { Badge } from "@/components/ui/Badge";
import { useWebSocket } from "@/hooks/useWebSocket";
import { Wifi, WifiOff } from "lucide-react";
import { useState, useCallback } from "react";

export function StatusBar() {
  const [wsConnected, setWsConnected] = useState(false);

  useWebSocket("heartbeat", useCallback(() => {
    setWsConnected(true);
  }, []));

  return (
    <div className="flex h-8 items-center justify-between border-t border-[var(--color-border)] bg-[var(--color-surface)] px-4 text-xs text-[var(--color-muted)]">
      <div className="flex items-center gap-3">
        {wsConnected ? (
          <span className="flex items-center gap-1 text-green-400">
            <Wifi className="h-3 w-3" /> Connected
          </span>
        ) : (
          <span className="flex items-center gap-1 text-red-400">
            <WifiOff className="h-3 w-3" /> Disconnected
          </span>
        )}
      </div>
      <div className="flex items-center gap-3">
        <span>Region: eu-west-1</span>
        <Badge label="v0.1.0" variant="neutral" />
      </div>
    </div>
  );
}
```

---

### src/components/charts/EquityCurve.tsx

```typescript
"use client";

import { Card } from "@/components/ui/Card";
import type { EquityPoint } from "@/lib/types";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from "recharts";

interface EquityCurveProps {
  data: EquityPoint[];
  title?: string;
}

export function EquityCurve({ data, title = "Equity Curve" }: EquityCurveProps) {
  return (
    <Card title={title}>
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis
              dataKey="date"
              tick={{ fill: "var(--color-muted)", fontSize: 11 }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: "var(--color-muted)", fontSize: 11 }}
              tickLine={false}
              tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: 8,
                color: "var(--color-foreground)",
              }}
              formatter={(value: number) => [`$${value.toLocaleString()}`, ""]}
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="nav"
              name="Portfolio NAV"
              stroke="#6366f1"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
            <Line
              type="monotone"
              dataKey="benchmark"
              name="Benchmark (SPY)"
              stroke="#94a3b8"
              strokeWidth={1.5}
              strokeDasharray="5 5"
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
```

### src/components/charts/PositionTable.tsx

```typescript
"use client";

import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { Position } from "@/lib/types";
import { clsx } from "clsx";

interface PositionTableProps {
  positions: Position[];
}

function formatCurrency(val: number): string {
  return val.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function formatPct(val: number): string {
  const sign = val >= 0 ? "+" : "";
  return `${sign}${val.toFixed(2)}%`;
}

export function PositionTable({ positions }: PositionTableProps) {
  return (
    <Card title="Open Positions" subtitle={`${positions.length} positions`}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--color-border)] text-left text-xs font-medium uppercase tracking-wider text-[var(--color-muted)]">
              <th className="px-3 py-3">Symbol</th>
              <th className="px-3 py-3">Qty</th>
              <th className="px-3 py-3 text-right">Entry</th>
              <th className="px-3 py-3 text-right">Current</th>
              <th className="px-3 py-3 text-right">P&L</th>
              <th className="px-3 py-3 text-right">P&L %</th>
              <th className="px-3 py-3 text-right">Market Value</th>
              <th className="px-3 py-3 text-right">Trail Stop</th>
              <th className="px-3 py-3">Sector</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border)]">
            {positions.map((pos) => (
              <tr
                key={pos.symbol}
                className="transition-colors hover:bg-[var(--color-surface-card)]/50"
              >
                <td className="px-3 py-3 font-mono font-semibold">{pos.symbol}</td>
                <td className="px-3 py-3">{pos.quantity}</td>
                <td className="px-3 py-3 text-right font-mono">
                  {formatCurrency(pos.avg_entry_price)}
                </td>
                <td className="px-3 py-3 text-right font-mono">
                  {formatCurrency(pos.current_price)}
                </td>
                <td
                  className={clsx(
                    "px-3 py-3 text-right font-mono",
                    pos.unrealized_pnl >= 0 ? "text-profit" : "text-loss"
                  )}
                >
                  {formatCurrency(pos.unrealized_pnl)}
                </td>
                <td
                  className={clsx(
                    "px-3 py-3 text-right font-mono",
                    pos.unrealized_pnl_pct >= 0 ? "text-profit" : "text-loss"
                  )}
                >
                  {formatPct(pos.unrealized_pnl_pct)}
                </td>
                <td className="px-3 py-3 text-right font-mono">
                  {formatCurrency(pos.market_value)}
                </td>
                <td className="px-3 py-3 text-right font-mono">
                  {formatCurrency(pos.trailing_stop_price)}
                  <span className="ml-1 text-xs text-[var(--color-muted)]">
                    ({pos.trailing_stop_pct}%)
                  </span>
                </td>
                <td className="px-3 py-3">
                  <Badge label={pos.sector} variant="info" />
                </td>
              </tr>
            ))}
            {positions.length === 0 && (
              <tr>
                <td
                  colSpan={9}
                  className="px-3 py-8 text-center text-[var(--color-muted)]"
                >
                  No open positions
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
```

### src/components/charts/AllocationPie.tsx

```typescript
"use client";

import { Card } from "@/components/ui/Card";
import type { AllocationSlice } from "@/lib/types";
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
} from "recharts";

interface AllocationPieProps {
  data: AllocationSlice[];
}

const SECTOR_COLORS = [
  "#6366f1", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6",
  "#06b6d4", "#ec4899", "#14b8a6", "#f97316", "#64748b",
];

export function AllocationPie({ data }: AllocationPieProps) {
  return (
    <Card title="Sector Allocation">
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="pct"
              nameKey="sector"
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={100}
              paddingAngle={2}
              label={({ sector, pct }) => `${sector} ${pct.toFixed(1)}%`}
              labelLine={false}
            >
              {data.map((_, idx) => (
                <Cell
                  key={idx}
                  fill={SECTOR_COLORS[idx % SECTOR_COLORS.length]}
                />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                backgroundColor: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: 8,
                color: "var(--color-foreground)",
              }}
              formatter={(value: number) => [`${value.toFixed(1)}%`, "Allocation"]}
            />
            <Legend
              wrapperStyle={{ fontSize: 12, color: "var(--color-muted)" }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
```

### src/components/charts/PnlBar.tsx

```typescript
"use client";

import { Card } from "@/components/ui/Card";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
} from "recharts";

interface PnlBarProps {
  data: Array<{ date: string; pnl: number }>;
  title?: string;
}

export function PnlBar({ data, title = "Daily P&L" }: PnlBarProps) {
  return (
    <Card title={title}>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis
              dataKey="date"
              tick={{ fill: "var(--color-muted)", fontSize: 11 }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: "var(--color-muted)", fontSize: 11 }}
              tickLine={false}
              tickFormatter={(v: number) => `$${v.toLocaleString()}`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: 8,
                color: "var(--color-foreground)",
              }}
              formatter={(value: number) => [`$${value.toLocaleString()}`, "P&L"]}
            />
            <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
              {data.map((entry, idx) => (
                <Cell
                  key={idx}
                  fill={entry.pnl >= 0 ? "#22c55e" : "#ef4444"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
```

### src/components/charts/RiskGauge.tsx

```typescript
"use client";

import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { RiskRule, CircuitBreakerStatus } from "@/lib/types";
import { clsx } from "clsx";

interface RiskGaugeProps {
  rules: RiskRule[];
  overallStatus: CircuitBreakerStatus;
}

function statusVariant(status: CircuitBreakerStatus) {
  switch (status) {
    case "OK":
      return "success" as const;
    case "TRIGGERED":
      return "danger" as const;
    case "MANUAL_OVERRIDE":
      return "warning" as const;
  }
}

function progressPct(current: number, threshold: number): number {
  return Math.min((Math.abs(current) / Math.abs(threshold)) * 100, 100);
}

export function RiskGauge({ rules, overallStatus }: RiskGaugeProps) {
  return (
    <Card
      title="Risk Monitor"
      action={<Badge label={overallStatus} variant={statusVariant(overallStatus)} pulse={overallStatus === "TRIGGERED"} />}
    >
      <div className="space-y-4">
        {rules.map((rule) => {
          const pct = progressPct(rule.current_value, rule.threshold);
          const danger = pct > 80;
          const warning = pct > 60 && pct <= 80;
          return (
            <div key={rule.rule_id}>
              <div className="mb-1 flex items-center justify-between text-sm">
                <span className="font-medium">{rule.name}</span>
                <span className="font-mono text-xs text-[var(--color-muted)]">
                  {rule.current_value.toFixed(1)} / {rule.threshold} {rule.unit}
                </span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-[var(--color-border)]">
                <div
                  className={clsx(
                    "h-full rounded-full transition-all duration-500",
                    danger ? "bg-red-500" : warning ? "bg-yellow-500" : "bg-green-500"
                  )}
                  style={{ width: `${pct}%` }}
                />
              </div>
              {rule.status === "TRIGGERED" && rule.resumes_at && (
                <p className="mt-1 text-xs text-red-400">
                  Circuit breaker active. Resumes: {new Date(rule.resumes_at).toLocaleString()}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
```

### src/components/charts/PipelineTimeline.tsx

```typescript
"use client";

import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { PipelineRun, PipelineStatus } from "@/lib/types";
import { clsx } from "clsx";
import { Clock, CheckCircle2, XCircle, Loader2 } from "lucide-react";

interface PipelineTimelineProps {
  runs: PipelineRun[];
}

function statusIcon(status: PipelineStatus) {
  switch (status) {
    case "RUNNING":
      return <Loader2 className="h-4 w-4 animate-spin text-blue-400" />;
    case "SUCCEEDED":
      return <CheckCircle2 className="h-4 w-4 text-green-400" />;
    case "FAILED":
      return <XCircle className="h-4 w-4 text-red-400" />;
    default:
      return <Clock className="h-4 w-4 text-yellow-400" />;
  }
}

function statusVariant(status: PipelineStatus) {
  switch (status) {
    case "RUNNING":
      return "info" as const;
    case "SUCCEEDED":
      return "success" as const;
    case "FAILED":
      return "danger" as const;
    default:
      return "warning" as const;
  }
}

function formatDuration(seconds?: number): string {
  if (!seconds) return "--";
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

export function PipelineTimeline({ runs }: PipelineTimelineProps) {
  return (
    <Card title="Pipeline Runs">
      <div className="space-y-3">
        {runs.map((run) => (
          <div
            key={run.execution_id}
            className="rounded-lg border border-[var(--color-border)] p-4"
          >
            {/* Run header */}
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                {statusIcon(run.status)}
                <span className="font-mono text-sm font-medium">
                  {run.name || run.execution_id.slice(0, 12)}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Badge label={run.status} variant={statusVariant(run.status)} />
                <span className="text-xs text-[var(--color-muted)]">
                  {formatDuration(run.duration_seconds)}
                </span>
              </div>
            </div>
            {/* Stages */}
            <div className="flex gap-1">
              {run.stages.map((stage, idx) => {
                const pct = run.stages.length > 0 ? 100 / run.stages.length : 100;
                return (
                  <div
                    key={idx}
                    className="group relative"
                    style={{ width: `${pct}%` }}
                  >
                    <div
                      className={clsx(
                        "h-6 rounded transition-colors",
                        stage.status === "SUCCEEDED" && "bg-green-500/60",
                        stage.status === "RUNNING" && "bg-blue-500/60 animate-pulse",
                        stage.status === "FAILED" && "bg-red-500/60",
                        !stage.status && "bg-gray-500/20"
                      )}
                    />
                    {/* Tooltip on hover */}
                    <div className="invisible absolute bottom-full left-1/2 z-10 mb-2 -translate-x-1/2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-xs shadow-lg group-hover:visible">
                      <p className="font-medium">{stage.name}</p>
                      <p className="text-[var(--color-muted)]">
                        {formatDuration(stage.duration_seconds)}
                      </p>
                      {stage.error && (
                        <p className="mt-1 text-red-400">{stage.error}</p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="mt-1 text-xs text-[var(--color-muted)]">
              Started: {new Date(run.started_at).toLocaleString()}
            </div>
          </div>
        ))}
        {runs.length === 0 && (
          <p className="py-8 text-center text-[var(--color-muted)]">
            No pipeline runs found
          </p>
        )}
      </div>
    </Card>
  );
}
```

---

### src/app/layout.tsx

```typescript
import type { Metadata } from "next";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { StatusBar } from "@/components/layout/StatusBar";
import "./globals.css";

export const metadata: Metadata = {
  title: "QITP Dashboard",
  description: "Quantitative Intelligence Trading Platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="flex h-screen overflow-hidden">
        <Sidebar />
        <div className="flex flex-1 flex-col overflow-hidden">
          <Header />
          <main className="flex-1 overflow-y-auto p-6">{children}</main>
          <StatusBar />
        </div>
      </body>
    </html>
  );
}
```

### src/app/page.tsx

```typescript
"use client";

import { usePortfolio } from "@/hooks/usePortfolio";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { clsx } from "clsx";
import {
  DollarSign,
  TrendingUp,
  TrendingDown,
  Briefcase,
  Clock,
  ShieldAlert,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { RiskState, PipelineRun } from "@/lib/types";
import { getRiskState, getPipelineRuns } from "@/lib/api";

function formatCurrency(val: number): string {
  return val.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function formatPct(val: number): string {
  const sign = val >= 0 ? "+" : "";
  return `${sign}${val.toFixed(2)}%`;
}

interface MetricCardProps {
  label: string;
  value: string;
  subValue?: string;
  icon: React.ReactNode;
  trend?: "up" | "down" | "neutral";
}

function MetricCard({ label, value, subValue, icon, trend }: MetricCardProps) {
  return (
    <Card>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-[var(--color-muted)]">{label}</p>
          <p className="mt-1 text-2xl font-bold">{value}</p>
          {subValue && (
            <p
              className={clsx(
                "mt-1 text-sm font-medium",
                trend === "up" && "text-profit",
                trend === "down" && "text-loss",
                trend === "neutral" && "text-[var(--color-muted)]"
              )}
            >
              {subValue}
            </p>
          )}
        </div>
        <div className="rounded-lg bg-brand-600/20 p-2.5 text-brand-400">
          {icon}
        </div>
      </div>
    </Card>
  );
}

export default function DashboardPage() {
  const { summary, positions, loading } = usePortfolio();
  const [riskState, setRiskState] = useState<RiskState | null>(null);
  const [latestRun, setLatestRun] = useState<PipelineRun | null>(null);

  useEffect(() => {
    getRiskState().then(setRiskState).catch(() => {});
    getPipelineRuns(1).then((runs) => setLatestRun(runs[0] ?? null)).catch(() => {});
  }, []);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-[var(--color-muted)]">
        Loading dashboard...
      </div>
    );
  }

  const triggeredBreakers = riskState?.rules.filter((r) => r.status === "TRIGGERED") ?? [];

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Dashboard</h2>

      {/* Metric cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Net Asset Value"
          value={summary ? formatCurrency(summary.nav) : "--"}
          subValue={summary ? formatPct(summary.total_pnl_pct) : undefined}
          icon={<DollarSign className="h-5 w-5" />}
          trend={summary && summary.total_pnl >= 0 ? "up" : "down"}
        />
        <MetricCard
          label="Daily P&L"
          value={summary ? formatCurrency(summary.daily_pnl) : "--"}
          subValue={summary ? formatPct(summary.daily_pnl_pct) : undefined}
          icon={
            summary && summary.daily_pnl >= 0 ? (
              <TrendingUp className="h-5 w-5" />
            ) : (
              <TrendingDown className="h-5 w-5" />
            )
          }
          trend={summary && summary.daily_pnl >= 0 ? "up" : "down"}
        />
        <MetricCard
          label="Open Positions"
          value={positions.length.toString()}
          subValue={`of 5 max`}
          icon={<Briefcase className="h-5 w-5" />}
          trend="neutral"
        />
        <MetricCard
          label="Next Pipeline Run"
          value={latestRun ? latestRun.status : "No runs"}
          subValue={
            latestRun?.started_at
              ? new Date(latestRun.started_at).toLocaleString()
              : undefined
          }
          icon={<Clock className="h-5 w-5" />}
          trend="neutral"
        />
      </div>

      {/* Circuit breaker alerts */}
      {triggeredBreakers.length > 0 && (
        <Card className="border-red-500/50">
          <div className="flex items-center gap-3">
            <ShieldAlert className="h-6 w-6 text-red-500" />
            <div>
              <p className="font-semibold text-red-400">
                {triggeredBreakers.length} Circuit Breaker{triggeredBreakers.length > 1 ? "s" : ""} Active
              </p>
              <ul className="mt-1 space-y-1 text-sm text-[var(--color-muted)]">
                {triggeredBreakers.map((r) => (
                  <li key={r.rule_id}>
                    {r.name}: {r.current_value.toFixed(1)}{r.unit} (limit: {r.threshold}{r.unit})
                    {r.resumes_at && (
                      <span className="ml-2 text-xs">
                        Resumes: {new Date(r.resumes_at).toLocaleString()}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Card>
      )}

      {/* Quick position summary */}
      {positions.length > 0 && (
        <Card title="Position Summary">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {positions.map((pos) => (
              <div
                key={pos.symbol}
                className="flex items-center justify-between rounded-lg border border-[var(--color-border)] p-3"
              >
                <div>
                  <p className="font-mono font-semibold">{pos.symbol}</p>
                  <p className="text-xs text-[var(--color-muted)]">{pos.sector}</p>
                </div>
                <div className="text-right">
                  <p
                    className={clsx(
                      "font-mono text-sm font-medium",
                      pos.unrealized_pnl >= 0 ? "text-profit" : "text-loss"
                    )}
                  >
                    {formatCurrency(pos.unrealized_pnl)}
                  </p>
                  <p
                    className={clsx(
                      "text-xs",
                      pos.unrealized_pnl_pct >= 0 ? "text-profit" : "text-loss"
                    )}
                  >
                    {formatPct(pos.unrealized_pnl_pct)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
```

### src/app/portfolio/page.tsx

```typescript
"use client";

import { usePortfolio } from "@/hooks/usePortfolio";
import { EquityCurve } from "@/components/charts/EquityCurve";
import { PositionTable } from "@/components/charts/PositionTable";
import { AllocationPie } from "@/components/charts/AllocationPie";
import { PnlBar } from "@/components/charts/PnlBar";
import { useEffect, useState } from "react";
import type { EquityPoint, AllocationSlice } from "@/lib/types";
import { getEquityCurve, getAllocation } from "@/lib/api";

export default function PortfolioPage() {
  const { positions, summary, loading } = usePortfolio();
  const [equityData, setEquityData] = useState<EquityPoint[]>([]);
  const [allocation, setAllocation] = useState<AllocationSlice[]>([]);

  useEffect(() => {
    getEquityCurve(90).then(setEquityData).catch(() => {});
    getAllocation().then(setAllocation).catch(() => {});
  }, []);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-[var(--color-muted)]">
        Loading portfolio...
      </div>
    );
  }

  // Derive daily P&L from equity curve
  const dailyPnl = equityData.slice(1).map((point, idx) => ({
    date: point.date,
    pnl: point.nav - equityData[idx].nav,
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Portfolio</h2>
        {summary && (
          <div className="text-right">
            <p className="text-sm text-[var(--color-muted)]">Net Asset Value</p>
            <p className="text-xl font-bold">
              ${summary.nav.toLocaleString()}
            </p>
          </div>
        )}
      </div>

      <EquityCurve data={equityData} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <AllocationPie data={allocation} />
        <PnlBar data={dailyPnl} />
      </div>

      <PositionTable positions={positions} />
    </div>
  );
}
```

### src/app/strategies/page.tsx

```typescript
"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { StrategyPerformance } from "@/lib/types";
import { getStrategies } from "@/lib/api";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<StrategyPerformance[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getStrategies()
      .then(setStrategies)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-[var(--color-muted)]">
        Loading strategies...
      </div>
    );
  }

  const sharpeData = strategies.map((s) => ({
    name: s.name,
    sharpe: s.sharpe_ratio,
  }));

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Strategy Performance</h2>

      {/* Sharpe ratio comparison */}
      <Card title="Sharpe Ratio Comparison">
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={sharpeData} margin={{ top: 5, right: 20, bottom: 5, left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis
                dataKey="name"
                tick={{ fill: "var(--color-muted)", fontSize: 11 }}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: "var(--color-muted)", fontSize: 11 }}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "var(--color-surface)",
                  border: "1px solid var(--color-border)",
                  borderRadius: 8,
                  color: "var(--color-foreground)",
                }}
              />
              <Bar dataKey="sharpe" fill="#6366f1" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Strategy detail table */}
      <Card title="Strategy Details">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-xs font-medium uppercase tracking-wider text-[var(--color-muted)]">
                <th className="px-3 py-3">Strategy</th>
                <th className="px-3 py-3">Status</th>
                <th className="px-3 py-3 text-right">Sharpe</th>
                <th className="px-3 py-3 text-right">Return</th>
                <th className="px-3 py-3 text-right">Max DD</th>
                <th className="px-3 py-3 text-right">Win Rate</th>
                <th className="px-3 py-3 text-right">Trades</th>
                <th className="px-3 py-3 text-right">Profit Factor</th>
                <th className="px-3 py-3">Last Backtest</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {strategies.map((s) => (
                <tr key={s.strategy_id} className="hover:bg-[var(--color-surface-card)]/50">
                  <td className="px-3 py-3 font-medium">{s.name}</td>
                  <td className="px-3 py-3">
                    <Badge
                      label={s.status}
                      variant={
                        s.status === "active"
                          ? "success"
                          : s.status === "paused"
                            ? "warning"
                            : "neutral"
                      }
                    />
                  </td>
                  <td className="px-3 py-3 text-right font-mono">
                    {s.sharpe_ratio.toFixed(2)}
                  </td>
                  <td className="px-3 py-3 text-right font-mono">
                    {s.total_return_pct.toFixed(1)}%
                  </td>
                  <td className="px-3 py-3 text-right font-mono text-loss">
                    {s.max_drawdown_pct.toFixed(1)}%
                  </td>
                  <td className="px-3 py-3 text-right font-mono">
                    {s.win_rate_pct.toFixed(1)}%
                  </td>
                  <td className="px-3 py-3 text-right font-mono">{s.total_trades}</td>
                  <td className="px-3 py-3 text-right font-mono">
                    {s.profit_factor.toFixed(2)}
                  </td>
                  <td className="px-3 py-3 text-xs text-[var(--color-muted)]">
                    {new Date(s.last_backtest).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
```

### src/app/pipeline/page.tsx

```typescript
"use client";

import { usePipeline } from "@/hooks/usePipeline";
import { PipelineTimeline } from "@/components/charts/PipelineTimeline";
import { Card } from "@/components/ui/Card";
import { Play, RefreshCw } from "lucide-react";

export default function PipelinePage() {
  const { runs, loading, triggering, trigger, refresh } = usePipeline(20);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Pipeline</h2>
        <div className="flex gap-2">
          <button
            onClick={refresh}
            className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm font-medium text-[var(--color-foreground)] transition-colors hover:bg-[var(--color-surface-card)]"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
          <button
            onClick={trigger}
            disabled={triggering}
            className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-700 disabled:opacity-50"
          >
            <Play className="h-4 w-4" />
            {triggering ? "Triggering..." : "Trigger Run"}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex h-64 items-center justify-center text-[var(--color-muted)]">
          Loading pipeline runs...
        </div>
      ) : (
        <>
          {/* Summary stats */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Card>
              <p className="text-sm text-[var(--color-muted)]">Total Runs</p>
              <p className="mt-1 text-2xl font-bold">{runs.length}</p>
            </Card>
            <Card>
              <p className="text-sm text-[var(--color-muted)]">Succeeded</p>
              <p className="mt-1 text-2xl font-bold text-profit">
                {runs.filter((r) => r.status === "SUCCEEDED").length}
              </p>
            </Card>
            <Card>
              <p className="text-sm text-[var(--color-muted)]">Failed</p>
              <p className="mt-1 text-2xl font-bold text-loss">
                {runs.filter((r) => r.status === "FAILED").length}
              </p>
            </Card>
          </div>

          <PipelineTimeline runs={runs} />
        </>
      )}
    </div>
  );
}
```

### src/app/risk/page.tsx

```typescript
"use client";

import { useEffect, useState } from "react";
import { RiskGauge } from "@/components/charts/RiskGauge";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { RiskState } from "@/lib/types";
import { getRiskState } from "@/lib/api";
import { useWebSocket } from "@/hooks/useWebSocket";
import { ShieldCheck, ShieldAlert } from "lucide-react";

export default function RiskPage() {
  const [riskState, setRiskState] = useState<RiskState | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getRiskState()
      .then(setRiskState)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useWebSocket("circuit_breaker", (msg) => {
    const update = msg.payload as RiskState;
    setRiskState(update);
  });

  if (loading || !riskState) {
    return (
      <div className="flex h-64 items-center justify-center text-[var(--color-muted)]">
        Loading risk state...
      </div>
    );
  }

  const triggeredCount = riskState.rules.filter((r) => r.status === "TRIGGERED").length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Risk Management</h2>
        <Badge
          label={riskState.overall_status}
          variant={riskState.overall_status === "OK" ? "success" : "danger"}
          pulse={riskState.overall_status === "TRIGGERED"}
        />
      </div>

      {/* Status banner */}
      <Card
        className={
          riskState.overall_status === "OK"
            ? "border-green-500/30"
            : "border-red-500/30"
        }
      >
        <div className="flex items-center gap-4">
          {riskState.overall_status === "OK" ? (
            <ShieldCheck className="h-8 w-8 text-green-500" />
          ) : (
            <ShieldAlert className="h-8 w-8 text-red-500" />
          )}
          <div>
            <p className="text-lg font-semibold">
              {riskState.overall_status === "OK"
                ? "All Risk Checks Passing"
                : `${triggeredCount} Circuit Breaker${triggeredCount > 1 ? "s" : ""} Active`}
            </p>
            <p className="text-sm text-[var(--color-muted)]">
              Last checked: {new Date(riskState.last_checked).toLocaleString()}
            </p>
          </div>
        </div>
      </Card>

      {/* Key metrics */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card title="Daily Loss">
          <p className="text-3xl font-bold text-loss">
            {riskState.daily_loss_pct.toFixed(2)}%
          </p>
          <p className="text-sm text-[var(--color-muted)]">Limit: -3.00%</p>
        </Card>
        <Card title="Drawdown from Peak">
          <p className="text-3xl font-bold text-loss">
            {riskState.drawdown_from_peak_pct.toFixed(2)}%
          </p>
          <p className="text-sm text-[var(--color-muted)]">Limit: -10.00%</p>
        </Card>
      </div>

      <RiskGauge rules={riskState.rules} overallStatus={riskState.overall_status} />
    </div>
  );
}
```

### src/app/watchlist/page.tsx

```typescript
"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import type { WatchlistItem } from "@/lib/types";
import { getWatchlist, addToWatchlist, removeFromWatchlist } from "@/lib/api";
import { Plus, Trash2 } from "lucide-react";

export default function WatchlistPage() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);

  // Add form state
  const [newSymbol, setNewSymbol] = useState("");
  const [newName, setNewName] = useState("");
  const [newSector, setNewSector] = useState("");
  const [newThreshold, setNewThreshold] = useState("2.0");

  const refresh = () => {
    getWatchlist()
      .then(setItems)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    refresh();
  }, []);

  const handleAdd = async () => {
    if (!newSymbol || !newSector) return;
    await addToWatchlist({
      symbol: newSymbol.toUpperCase(),
      name: newName,
      sector: newSector,
      gap_threshold_pct: parseFloat(newThreshold),
      enabled: true,
      notes: "",
    });
    setShowAdd(false);
    setNewSymbol("");
    setNewName("");
    setNewSector("");
    setNewThreshold("2.0");
    refresh();
  };

  const handleRemove = async (symbol: string) => {
    if (!confirm(`Remove ${symbol} from watchlist?`)) return;
    await removeFromWatchlist(symbol);
    refresh();
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-[var(--color-muted)]">
        Loading watchlist...
      </div>
    );
  }

  const sectors = [...new Set(items.map((i) => i.sector))];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Watchlist</h2>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-700"
        >
          <Plus className="h-4 w-4" />
          Add Symbol
        </button>
      </div>

      {/* Summary by sector */}
      <div className="flex flex-wrap gap-2">
        {sectors.map((sector) => (
          <Badge
            key={sector}
            label={`${sector}: ${items.filter((i) => i.sector === sector).length}`}
            variant="info"
          />
        ))}
        <Badge label={`Total: ${items.length}`} variant="neutral" />
      </div>

      {/* Watchlist table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-xs font-medium uppercase tracking-wider text-[var(--color-muted)]">
                <th className="px-3 py-3">Symbol</th>
                <th className="px-3 py-3">Name</th>
                <th className="px-3 py-3">Sector</th>
                <th className="px-3 py-3 text-right">Gap Threshold</th>
                <th className="px-3 py-3">Status</th>
                <th className="px-3 py-3">Added</th>
                <th className="px-3 py-3">Notes</th>
                <th className="px-3 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {items.map((item) => (
                <tr key={item.symbol} className="hover:bg-[var(--color-surface-card)]/50">
                  <td className="px-3 py-3 font-mono font-semibold">{item.symbol}</td>
                  <td className="px-3 py-3">{item.name}</td>
                  <td className="px-3 py-3">
                    <Badge label={item.sector} variant="info" />
                  </td>
                  <td className="px-3 py-3 text-right font-mono">
                    {item.gap_threshold_pct}%
                  </td>
                  <td className="px-3 py-3">
                    <Badge
                      label={item.enabled ? "Enabled" : "Disabled"}
                      variant={item.enabled ? "success" : "neutral"}
                    />
                  </td>
                  <td className="px-3 py-3 text-xs text-[var(--color-muted)]">
                    {new Date(item.added_at).toLocaleDateString()}
                  </td>
                  <td className="px-3 py-3 text-xs text-[var(--color-muted)]">
                    {item.notes || "--"}
                  </td>
                  <td className="px-3 py-3">
                    <button
                      onClick={() => handleRemove(item.symbol)}
                      className="rounded p-1 text-red-400 hover:bg-red-500/20"
                      title="Remove"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Add symbol modal */}
      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="Add Symbol to Watchlist">
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Symbol</label>
            <input
              type="text"
              value={newSymbol}
              onChange={(e) => setNewSymbol(e.target.value)}
              placeholder="AAPL"
              className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Name</label>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Apple Inc."
              className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Sector</label>
            <input
              type="text"
              value={newSector}
              onChange={(e) => setNewSector(e.target.value)}
              placeholder="Technology"
              className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Gap Threshold (%)</label>
            <input
              type="number"
              value={newThreshold}
              onChange={(e) => setNewThreshold(e.target.value)}
              step="0.1"
              className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm"
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setShowAdd(false)}
              className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm"
            >
              Cancel
            </button>
            <button
              onClick={handleAdd}
              disabled={!newSymbol || !newSector}
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              Add
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
```

### src/app/approvals/page.tsx

```typescript
"use client";

import { useEffect, useState, useCallback } from "react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import type { ApprovalRequest, ApprovalStatus } from "@/lib/types";
import {
  getPendingApprovals,
  getApprovalHistory,
  approveOrder,
  rejectOrder,
} from "@/lib/api";
import { useWebSocket } from "@/hooks/useWebSocket";
import { CheckCircle, XCircle, AlertTriangle } from "lucide-react";

function statusVariant(status: ApprovalStatus) {
  switch (status) {
    case "PENDING":
      return "warning" as const;
    case "APPROVED":
      return "success" as const;
    case "REJECTED":
      return "danger" as const;
    case "EXPIRED":
      return "neutral" as const;
  }
}

export default function ApprovalsPage() {
  const [pending, setPending] = useState<ApprovalRequest[]>([]);
  const [history, setHistory] = useState<ApprovalRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [rejectModal, setRejectModal] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const refresh = useCallback(() => {
    Promise.all([getPendingApprovals(), getApprovalHistory()])
      .then(([p, h]) => {
        setPending(p);
        setHistory(h.filter((r) => r.status !== "PENDING"));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Real-time new approval requests
  useWebSocket("approval_request", useCallback(() => {
    refresh();
  }, [refresh]));

  const handleApprove = async (requestId: string) => {
    await approveOrder(requestId);
    refresh();
  };

  const handleReject = async () => {
    if (!rejectModal) return;
    await rejectOrder(rejectModal, rejectReason);
    setRejectModal(null);
    setRejectReason("");
    refresh();
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-[var(--color-muted)]">
        Loading approvals...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Order Approvals (2FA)</h2>

      {/* Pending approvals */}
      <Card
        title="Pending Approvals"
        subtitle={`${pending.length} order${pending.length !== 1 ? "s" : ""} awaiting decision`}
      >
        {pending.length === 0 ? (
          <p className="py-8 text-center text-[var(--color-muted)]">
            No pending approvals
          </p>
        ) : (
          <div className="space-y-4">
            {pending.map((req) => (
              <div
                key={req.request_id}
                className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="h-5 w-5 text-yellow-400" />
                      <span className="font-mono text-lg font-bold">
                        {req.side} {req.quantity} {req.symbol}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-[var(--color-muted)]">
                      {req.order_type} | Strategy: {req.strategy_id}
                    </p>
                    {req.price && (
                      <p className="text-sm text-[var(--color-muted)]">
                        Price: ${req.price.toLocaleString()}
                      </p>
                    )}
                    <p className="mt-2 text-sm">{req.rationale}</p>
                    <div className="mt-2 flex gap-2">
                      <Badge
                        label={`Risk: ${req.risk_check_result}`}
                        variant={req.risk_check_result === "PASS" ? "success" : "danger"}
                      />
                      <span className="text-xs text-[var(--color-muted)]">
                        Expires: {new Date(req.expires_at).toLocaleString()}
                      </span>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleApprove(req.request_id)}
                      className="flex items-center gap-1 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700"
                    >
                      <CheckCircle className="h-4 w-4" />
                      Approve
                    </button>
                    <button
                      onClick={() => setRejectModal(req.request_id)}
                      className="flex items-center gap-1 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
                    >
                      <XCircle className="h-4 w-4" />
                      Reject
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* History */}
      <Card title="Decision History">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-xs font-medium uppercase tracking-wider text-[var(--color-muted)]">
                <th className="px-3 py-3">Time</th>
                <th className="px-3 py-3">Order</th>
                <th className="px-3 py-3">Strategy</th>
                <th className="px-3 py-3">Decision</th>
                <th className="px-3 py-3">Decided By</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {history.slice(0, 20).map((req) => (
                <tr key={req.request_id}>
                  <td className="px-3 py-3 text-xs text-[var(--color-muted)]">
                    {req.decided_at ? new Date(req.decided_at).toLocaleString() : "--"}
                  </td>
                  <td className="px-3 py-3 font-mono">
                    {req.side} {req.quantity} {req.symbol}
                  </td>
                  <td className="px-3 py-3">{req.strategy_id}</td>
                  <td className="px-3 py-3">
                    <Badge label={req.status} variant={statusVariant(req.status)} />
                  </td>
                  <td className="px-3 py-3 text-xs text-[var(--color-muted)]">
                    {req.decided_by || "--"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Reject modal */}
      <Modal
        open={rejectModal !== null}
        onClose={() => setRejectModal(null)}
        title="Reject Order"
      >
        <div className="space-y-4">
          <p className="text-sm text-[var(--color-muted)]">
            Provide a reason for rejecting this order.
          </p>
          <textarea
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            rows={3}
            placeholder="Reason for rejection..."
            className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm"
          />
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setRejectModal(null)}
              className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm"
            >
              Cancel
            </button>
            <button
              onClick={handleReject}
              disabled={!rejectReason}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              Reject Order
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
```

### src/app/settings/page.tsx

```typescript
"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { DashboardSettings, ExecutionMode } from "@/lib/types";
import { getSettings, updateSettings } from "@/lib/api";
import { Save, AlertTriangle } from "lucide-react";

export default function SettingsPage() {
  const [settings, setSettings] = useState<DashboardSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showLiveWarning, setShowLiveWarning] = useState(false);

  useEffect(() => {
    getSettings()
      .then(setSettings)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleModeChange = (mode: ExecutionMode) => {
    if (mode === "live") {
      setShowLiveWarning(true);
      return;
    }
    setSettings((prev) => (prev ? { ...prev, execution_mode: mode } : null));
  };

  const confirmLiveMode = () => {
    setSettings((prev) => (prev ? { ...prev, execution_mode: "live" } : null));
    setShowLiveWarning(false);
  };

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      const updated = await updateSettings(settings);
      setSettings(updated);
    } catch {
      // Error handling
    } finally {
      setSaving(false);
    }
  };

  if (loading || !settings) {
    return (
      <div className="flex h-64 items-center justify-center text-[var(--color-muted)]">
        Loading settings...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Settings</h2>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          <Save className="h-4 w-4" />
          {saving ? "Saving..." : "Save Changes"}
        </button>
      </div>

      {/* Execution Mode */}
      <Card title="Execution Mode" subtitle="Controls data source and order routing">
        <div className="grid grid-cols-3 gap-3">
          {(["backtest", "paper", "live"] as const).map((mode) => {
            const active = settings.execution_mode === mode;
            const colors = {
              backtest: "border-green-500 bg-green-500/10",
              paper: "border-yellow-500 bg-yellow-500/10",
              live: "border-red-500 bg-red-500/10",
            };
            return (
              <button
                key={mode}
                onClick={() => handleModeChange(mode)}
                className={`rounded-lg border-2 p-4 text-left transition-colors ${
                  active ? colors[mode] : "border-[var(--color-border)]"
                }`}
              >
                <p className="font-semibold uppercase">{mode}</p>
                <p className="mt-1 text-xs text-[var(--color-muted)]">
                  {mode === "backtest" && "Historical data, simulation engine"}
                  {mode === "paper" && "Live data, paper account"}
                  {mode === "live" && "Live data, real orders, 2FA required"}
                </p>
                {active && (
                  <Badge
                    label="Active"
                    variant={
                      mode === "backtest"
                        ? "success"
                        : mode === "paper"
                          ? "warning"
                          : "danger"
                    }
                  />
                )}
              </button>
            );
          })}
        </div>
      </Card>

      {/* Live mode warning */}
      {showLiveWarning && (
        <Card className="border-red-500/50">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-6 w-6 shrink-0 text-red-500" />
            <div>
              <p className="font-semibold text-red-400">
                Switching to LIVE mode will enable real money trading.
              </p>
              <p className="mt-1 text-sm text-[var(--color-muted)]">
                All orders will be routed to your Interactive Brokers live account.
                2FA approval will be required for every order.
              </p>
              <div className="mt-3 flex gap-2">
                <button
                  onClick={() => setShowLiveWarning(false)}
                  className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm"
                >
                  Cancel
                </button>
                <button
                  onClick={confirmLiveMode}
                  className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white"
                >
                  Confirm LIVE Mode
                </button>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Alert Preferences */}
      <Card title="Alert Preferences">
        <div className="space-y-4">
          <label className="flex items-center justify-between">
            <span className="text-sm">Telegram notifications</span>
            <input
              type="checkbox"
              checked={settings.alert_telegram}
              onChange={(e) =>
                setSettings({ ...settings, alert_telegram: e.target.checked })
              }
              className="h-5 w-5 rounded border-gray-300"
            />
          </label>
          <label className="flex items-center justify-between">
            <span className="text-sm">Email notifications</span>
            <input
              type="checkbox"
              checked={settings.alert_email}
              onChange={(e) =>
                setSettings({ ...settings, alert_email: e.target.checked })
              }
              className="h-5 w-5 rounded border-gray-300"
            />
          </label>
          <div>
            <label className="mb-1 block text-sm">Auto-refresh interval (seconds)</label>
            <input
              type="number"
              value={settings.auto_refresh_seconds}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  auto_refresh_seconds: parseInt(e.target.value) || 30,
                })
              }
              min={5}
              max={300}
              className="w-32 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm"
            />
          </div>
        </div>
      </Card>

      {/* Theme */}
      <Card title="Appearance">
        <div className="flex gap-3">
          <button
            onClick={() => {
              setSettings({ ...settings, theme: "dark" });
              document.documentElement.classList.remove("light");
            }}
            className={`rounded-lg border-2 px-6 py-3 ${
              settings.theme === "dark"
                ? "border-brand-500 bg-brand-500/10"
                : "border-[var(--color-border)]"
            }`}
          >
            Dark
          </button>
          <button
            onClick={() => {
              setSettings({ ...settings, theme: "light" });
              document.documentElement.classList.add("light");
            }}
            className={`rounded-lg border-2 px-6 py-3 ${
              settings.theme === "light"
                ? "border-brand-500 bg-brand-500/10"
                : "border-[var(--color-border)]"
            }`}
          >
            Light
          </button>
        </div>
      </Card>
    </div>
  );
}
```

---

### API Route Handlers

### api/middleware.ts

```typescript
/**
 * Cognito JWT verification middleware for API routes.
 * Validates the Authorization: Bearer <token> header.
 */

import { NextRequest, NextResponse } from "next/server";
import * as jose from "jose";

const COGNITO_ISSUER = process.env.COGNITO_ISSUER!;
const COGNITO_CLIENT_ID = process.env.COGNITO_CLIENT_ID!;

let jwks: jose.JWTVerifyGetKey | null = null;

function getJwks(): jose.JWTVerifyGetKey {
  if (!jwks) {
    const jwksUrl = new URL("/.well-known/jwks.json", COGNITO_ISSUER);
    jwks = jose.createRemoteJWKSet(jwksUrl);
  }
  return jwks;
}

export interface AuthUser {
  sub: string;
  email: string;
  groups: string[];
}

export async function verifyAuth(req: NextRequest): Promise<AuthUser | NextResponse> {
  // Skip auth in development
  if (process.env.NODE_ENV === "development" && !process.env.COGNITO_ISSUER) {
    return {
      sub: "dev-user",
      email: "dev@qitp.local",
      groups: ["admin"],
    };
  }

  const authHeader = req.headers.get("authorization");
  if (!authHeader?.startsWith("Bearer ")) {
    return NextResponse.json({ error: "Missing authorization header" }, { status: 401 });
  }

  const token = authHeader.slice(7);

  try {
    const { payload } = await jose.jwtVerify(token, getJwks(), {
      issuer: COGNITO_ISSUER,
      audience: COGNITO_CLIENT_ID,
    });

    return {
      sub: payload.sub as string,
      email: (payload.email as string) || "",
      groups: (payload["cognito:groups"] as string[]) || [],
    };
  } catch {
    return NextResponse.json({ error: "Invalid or expired token" }, { status: 401 });
  }
}
```

### api/routes/portfolio.ts

```typescript
/**
 * /api/portfolio/* — Portfolio data from IBKR MCP.
 * Proxies requests to the IBKR MCP server for positions, NAV, equity curve.
 */

import { NextRequest, NextResponse } from "next/server";
import { verifyAuth } from "../middleware";
import type { PortfolioSummary, Position, EquityPoint, AllocationSlice } from "@/lib/types";

const IBKR_MCP_URL = process.env.IBKR_MCP_URL || "http://localhost:8001";

async function callMcp<T>(tool: string, params: Record<string, unknown> = {}): Promise<T> {
  const res = await fetch(`${IBKR_MCP_URL}/mcp/v1/tools/${tool}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ params }),
  });
  if (!res.ok) {
    throw new Error(`MCP ${tool} failed: ${res.status}`);
  }
  const data = await res.json();
  return data.result as T;
}

// GET /api/portfolio/summary
export async function getSummary(req: NextRequest): Promise<NextResponse> {
  const auth = await verifyAuth(req);
  if (auth instanceof NextResponse) return auth;

  try {
    const summary = await callMcp<PortfolioSummary>("get_account_summary");
    return NextResponse.json(summary);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 502 }
    );
  }
}

// GET /api/portfolio/positions
export async function getPositionsRoute(req: NextRequest): Promise<NextResponse> {
  const auth = await verifyAuth(req);
  if (auth instanceof NextResponse) return auth;

  try {
    const positions = await callMcp<Position[]>("get_positions");
    return NextResponse.json(positions);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 502 }
    );
  }
}

// GET /api/portfolio/equity?days=90
export async function getEquity(req: NextRequest): Promise<NextResponse> {
  const auth = await verifyAuth(req);
  if (auth instanceof NextResponse) return auth;

  const days = parseInt(req.nextUrl.searchParams.get("days") || "90");

  try {
    const equity = await callMcp<EquityPoint[]>("get_equity_curve", { days });
    return NextResponse.json(equity);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 502 }
    );
  }
}

// GET /api/portfolio/allocation
export async function getAllocationRoute(req: NextRequest): Promise<NextResponse> {
  const auth = await verifyAuth(req);
  if (auth instanceof NextResponse) return auth;

  try {
    const allocation = await callMcp<AllocationSlice[]>("get_allocation");
    return NextResponse.json(allocation);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 502 }
    );
  }
}
```

### api/routes/strategies.ts

```typescript
/**
 * /api/strategies — Strategy performance from DynamoDB.
 */

import { NextRequest, NextResponse } from "next/server";
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, ScanCommand } from "@aws-sdk/lib-dynamodb";
import { verifyAuth } from "../middleware";
import type { StrategyPerformance } from "@/lib/types";

const client = new DynamoDBClient({ region: process.env.AWS_REGION || "eu-west-1" });
const docClient = DynamoDBDocumentClient.from(client);
const TABLE = process.env.DYNAMODB_STRATEGY_REGISTRY_TABLE || "qitp_strategy_registry";

// GET /api/strategies
export async function listStrategies(req: NextRequest): Promise<NextResponse> {
  const auth = await verifyAuth(req);
  if (auth instanceof NextResponse) return auth;

  try {
    const result = await docClient.send(
      new ScanCommand({ TableName: TABLE })
    );
    const strategies = (result.Items || []) as unknown as StrategyPerformance[];
    return NextResponse.json(strategies);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 }
    );
  }
}
```

### api/routes/pipeline.ts

```typescript
/**
 * /api/pipeline — Step Functions execution status.
 */

import { NextRequest, NextResponse } from "next/server";
import {
  SFNClient,
  ListExecutionsCommand,
  DescribeExecutionCommand,
  StartExecutionCommand,
} from "@aws-sdk/client-sfn";
import { verifyAuth } from "../middleware";
import type { PipelineRun, PipelineStage } from "@/lib/types";

const sfnClient = new SFNClient({ region: process.env.AWS_REGION || "eu-west-1" });
const STATE_MACHINE_ARN = process.env.SFN_STATE_MACHINE_ARN || "";

// GET /api/pipeline?limit=10
export async function listRuns(req: NextRequest): Promise<NextResponse> {
  const auth = await verifyAuth(req);
  if (auth instanceof NextResponse) return auth;

  const limit = parseInt(req.nextUrl.searchParams.get("limit") || "10");

  try {
    const result = await sfnClient.send(
      new ListExecutionsCommand({
        stateMachineArn: STATE_MACHINE_ARN,
        maxResults: limit,
      })
    );

    const runs: PipelineRun[] = (result.executions || []).map((exec) => ({
      execution_id: exec.executionArn?.split(":").pop() || "",
      name: exec.name || "",
      status: (exec.status as PipelineRun["status"]) || "RUNNING",
      started_at: exec.startDate?.toISOString() || "",
      stopped_at: exec.stopDate?.toISOString(),
      duration_seconds: exec.startDate && exec.stopDate
        ? Math.round((exec.stopDate.getTime() - exec.startDate.getTime()) / 1000)
        : undefined,
      stages: [], // Populated on detail view
    }));

    return NextResponse.json(runs);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 }
    );
  }
}

// POST /api/pipeline/trigger
export async function triggerRun(req: NextRequest): Promise<NextResponse> {
  const auth = await verifyAuth(req);
  if (auth instanceof NextResponse) return auth;

  try {
    const name = `manual-${Date.now()}`;
    const result = await sfnClient.send(
      new StartExecutionCommand({
        stateMachineArn: STATE_MACHINE_ARN,
        name,
        input: JSON.stringify({
          trigger: "manual",
          triggered_by: "sub" in auth ? auth.sub : "unknown",
          timestamp: new Date().toISOString(),
        }),
      })
    );

    return NextResponse.json({
      execution_id: result.executionArn?.split(":").pop() || "",
    });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 }
    );
  }
}
```

### api/routes/risk.ts

```typescript
/**
 * /api/risk — Risk state from DynamoDB.
 */

import { NextRequest, NextResponse } from "next/server";
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, GetCommand } from "@aws-sdk/lib-dynamodb";
import { verifyAuth } from "../middleware";
import type { RiskState } from "@/lib/types";

const client = new DynamoDBClient({ region: process.env.AWS_REGION || "eu-west-1" });
const docClient = DynamoDBDocumentClient.from(client);
const TABLE = process.env.DYNAMODB_RISK_STATE_TABLE || "qitp_risk_state";

// GET /api/risk
export async function getRisk(req: NextRequest): Promise<NextResponse> {
  const auth = await verifyAuth(req);
  if (auth instanceof NextResponse) return auth;

  try {
    const result = await docClient.send(
      new GetCommand({
        TableName: TABLE,
        Key: { pk: "RISK_STATE", sk: "CURRENT" },
      })
    );

    if (!result.Item) {
      // Return default risk state if none exists
      const defaultState: RiskState = {
        rules: [
          { rule_id: "max_positions", name: "Max Open Positions", threshold: 5, current_value: 0, unit: "positions", status: "OK" },
          { rule_id: "max_position_size", name: "Max Single Position Size", threshold: 20, current_value: 0, unit: "% NAV", status: "OK" },
          { rule_id: "max_sector", name: "Max Sector Concentration", threshold: 40, current_value: 0, unit: "%", status: "OK" },
          { rule_id: "daily_loss", name: "Daily Loss Breaker", threshold: 3, current_value: 0, unit: "%", status: "OK" },
          { rule_id: "drawdown", name: "Drawdown Breaker", threshold: 10, current_value: 0, unit: "%", status: "OK" },
        ],
        overall_status: "OK",
        last_checked: new Date().toISOString(),
        daily_loss_pct: 0,
        drawdown_from_peak_pct: 0,
      };
      return NextResponse.json(defaultState);
    }

    return NextResponse.json(result.Item as unknown as RiskState);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 }
    );
  }
}
```

### api/routes/watchlist.ts

```typescript
/**
 * /api/watchlist — CRUD operations on DynamoDB watchlist.
 */

import { NextRequest, NextResponse } from "next/server";
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
  DynamoDBDocumentClient,
  ScanCommand,
  PutCommand,
  DeleteCommand,
  UpdateCommand,
} from "@aws-sdk/lib-dynamodb";
import { verifyAuth } from "../middleware";
import type { WatchlistItem } from "@/lib/types";

const client = new DynamoDBClient({ region: process.env.AWS_REGION || "eu-west-1" });
const docClient = DynamoDBDocumentClient.from(client);
const TABLE = process.env.DYNAMODB_WATCHLIST_TABLE || "qitp_watchlist";

// GET /api/watchlist
export async function listWatchlist(req: NextRequest): Promise<NextResponse> {
  const auth = await verifyAuth(req);
  if (auth instanceof NextResponse) return auth;

  try {
    const result = await docClient.send(new ScanCommand({ TableName: TABLE }));
    return NextResponse.json(result.Items || []);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 }
    );
  }
}

// POST /api/watchlist
export async function addWatchlistItem(req: NextRequest): Promise<NextResponse> {
  const auth = await verifyAuth(req);
  if (auth instanceof NextResponse) return auth;

  const body = await req.json();
  const item: WatchlistItem = {
    ...body,
    added_at: new Date().toISOString(),
  };

  try {
    await docClient.send(
      new PutCommand({
        TableName: TABLE,
        Item: { pk: item.symbol, ...item },
        ConditionExpression: "attribute_not_exists(pk)",
      })
    );
    return NextResponse.json(item, { status: 201 });
  } catch (err: unknown) {
    if (err && typeof err === "object" && "name" in err && err.name === "ConditionalCheckFailedException") {
      return NextResponse.json({ error: "Symbol already in watchlist" }, { status: 409 });
    }
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 }
    );
  }
}

// DELETE /api/watchlist/:symbol
export async function removeWatchlistItem(
  req: NextRequest,
  symbol: string
): Promise<NextResponse> {
  const auth = await verifyAuth(req);
  if (auth instanceof NextResponse) return auth;

  try {
    await docClient.send(
      new DeleteCommand({
        TableName: TABLE,
        Key: { pk: symbol },
      })
    );
    return new NextResponse(null, { status: 204 });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 }
    );
  }
}

// PATCH /api/watchlist/:symbol
export async function updateWatchlistItemRoute(
  req: NextRequest,
  symbol: string
): Promise<NextResponse> {
  const auth = await verifyAuth(req);
  if (auth instanceof NextResponse) return auth;

  const updates = await req.json();
  const expressions: string[] = [];
  const names: Record<string, string> = {};
  const values: Record<string, unknown> = {};

  Object.entries(updates).forEach(([key, value]) => {
    if (key === "symbol") return; // Cannot change PK
    const attr = `#${key}`;
    const val = `:${key}`;
    expressions.push(`${attr} = ${val}`);
    names[attr] = key;
    values[val] = value;
  });

  if (expressions.length === 0) {
    return NextResponse.json({ error: "No fields to update" }, { status: 400 });
  }

  try {
    const result = await docClient.send(
      new UpdateCommand({
        TableName: TABLE,
        Key: { pk: symbol },
        UpdateExpression: `SET ${expressions.join(", ")}`,
        ExpressionAttributeNames: names,
        ExpressionAttributeValues: values,
        ReturnValues: "ALL_NEW",
      })
    );
    return NextResponse.json(result.Attributes);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 }
    );
  }
}
```

### api/routes/approvals.ts

```typescript
/**
 * /api/approvals — 2FA web approval interface.
 * Reads pending approval requests from DynamoDB.
 * Sends approval/rejection via SFN SendTaskSuccess/SendTaskFailure.
 */

import { NextRequest, NextResponse } from "next/server";
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
  DynamoDBDocumentClient,
  QueryCommand,
  ScanCommand,
  UpdateCommand,
} from "@aws-sdk/lib-dynamodb";
import {
  SFNClient,
  SendTaskSuccessCommand,
  SendTaskFailureCommand,
} from "@aws-sdk/client-sfn";
import { verifyAuth } from "../middleware";

const dynamoClient = new DynamoDBClient({ region: process.env.AWS_REGION || "eu-west-1" });
const docClient = DynamoDBDocumentClient.from(dynamoClient);
const sfnClient = new SFNClient({ region: process.env.AWS_REGION || "eu-west-1" });
const TABLE = process.env.DYNAMODB_2FA_EVENTS_TABLE || "qitp_2fa_events";

// GET /api/approvals?status=PENDING|ALL
export async function listApprovals(req: NextRequest): Promise<NextResponse> {
  const auth = await verifyAuth(req);
  if (auth instanceof NextResponse) return auth;

  const statusFilter = req.nextUrl.searchParams.get("status") || "PENDING";

  try {
    let result;
    if (statusFilter === "ALL") {
      result = await docClient.send(new ScanCommand({ TableName: TABLE }));
    } else {
      result = await docClient.send(
        new QueryCommand({
          TableName: TABLE,
          IndexName: "status-index",
          KeyConditionExpression: "#s = :status",
          ExpressionAttributeNames: { "#s": "status" },
          ExpressionAttributeValues: { ":status": statusFilter },
          ScanIndexForward: false,
        })
      );
    }

    return NextResponse.json(result.Items || []);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 }
    );
  }
}

// POST /api/approvals/decide
export async function decide(req: NextRequest): Promise<NextResponse> {
  const auth = await verifyAuth(req);
  if (auth instanceof NextResponse) return auth;

  const { request_id, decision, reason } = await req.json();

  if (!request_id || !decision) {
    return NextResponse.json(
      { error: "request_id and decision are required" },
      { status: 400 }
    );
  }

  if (!["APPROVED", "REJECTED"].includes(decision)) {
    return NextResponse.json(
      { error: "decision must be APPROVED or REJECTED" },
      { status: 400 }
    );
  }

  try {
    // Get the task token from DynamoDB
    const getResult = await docClient.send(
      new QueryCommand({
        TableName: TABLE,
        KeyConditionExpression: "pk = :pk",
        ExpressionAttributeValues: { ":pk": request_id },
        Limit: 1,
      })
    );

    const item = getResult.Items?.[0];
    if (!item) {
      return NextResponse.json({ error: "Approval request not found" }, { status: 404 });
    }

    if (item.status !== "PENDING") {
      return NextResponse.json({ error: "Request already decided" }, { status: 409 });
    }

    const taskToken = item.task_token as string;
    const decidedBy = "sub" in auth ? auth.sub : "unknown";

    if (decision === "APPROVED") {
      await sfnClient.send(
        new SendTaskSuccessCommand({
          taskToken,
          output: JSON.stringify({
            decision: "APPROVED",
            decided_by: decidedBy,
            decided_at: new Date().toISOString(),
            channel: "web",
          }),
        })
      );
    } else {
      await sfnClient.send(
        new SendTaskFailureCommand({
          taskToken,
          error: "OrderRejected",
          cause: reason || "Rejected via web dashboard",
        })
      );
    }

    // Update DynamoDB record
    await docClient.send(
      new UpdateCommand({
        TableName: TABLE,
        Key: { pk: request_id, sk: item.sk },
        UpdateExpression: "SET #s = :status, decided_at = :da, decided_by = :db",
        ExpressionAttributeNames: { "#s": "status" },
        ExpressionAttributeValues: {
          ":status": decision,
          ":da": new Date().toISOString(),
          ":db": decidedBy,
        },
      })
    );

    return NextResponse.json({ success: true });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 }
    );
  }
}
```

---

### Dockerfile

```dockerfile
# --- Build stage ---
FROM node:22-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# --- Production stage ---
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV HOSTNAME="0.0.0.0"
ENV PORT=3000

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
```

### docker-compose.yml

```yaml
version: "3.9"

services:
  dashboard:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
      - AWS_REGION=eu-west-1
      - EXECUTION_MODE=backtest
      - IBKR_MCP_URL=http://ibkr-mcp:8001
      - MARKET_DATA_MCP_URL=http://market-data-mcp:8002
      - ARTIFACTS_MCP_URL=http://artifacts-mcp:8004
      - DYNAMODB_WATCHLIST_TABLE=qitp_watchlist
      - DYNAMODB_RISK_STATE_TABLE=qitp_risk_state
      - DYNAMODB_AUDIT_LOG_TABLE=qitp_audit_log
      - DYNAMODB_STRATEGY_REGISTRY_TABLE=qitp_strategy_registry
      - DYNAMODB_2FA_EVENTS_TABLE=qitp_2fa_events
      - DYNAMODB_RUN_HISTORY_TABLE=qitp_run_history
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:3000"]
      interval: 30s
      timeout: 5s
      retries: 3

  # Development only — local DynamoDB
  dynamodb-local:
    image: amazon/dynamodb-local:latest
    ports:
      - "8000:8000"
    command: ["-jar", "DynamoDBLocal.jar", "-inMemory"]
    profiles:
      - dev
```

### .github/workflows/ci.yml

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: "npm"

      - run: npm ci

      - name: Type check
        run: npm run typecheck

      - name: Lint
        run: npm run lint

      - name: Test
        run: npm test -- --coverage

      - name: Build
        run: npm run build

  docker:
    runs-on: ubuntu-latest
    needs: build-and-test
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t qitp-dashboard:${{ github.sha }} .
```

---

### Tests

### jest.config.ts

```typescript
import type { Config } from "jest";
import nextJest from "next/jest";

const createJestConfig = nextJest({ dir: "./" });

const config: Config = {
  testEnvironment: "jsdom",
  setupFilesAfterSetup: ["<rootDir>/tests/setup.ts"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
    "^@api/(.*)$": "<rootDir>/api/$1",
  },
  testPathPattern: "tests/.*\\.test\\.tsx?$",
};

export default createJestConfig(config);
```

### tests/setup.ts

```typescript
import "@testing-library/jest-dom";
```

### tests/components/EquityCurve.test.tsx

```typescript
import { render, screen } from "@testing-library/react";
import { EquityCurve } from "@/components/charts/EquityCurve";
import type { EquityPoint } from "@/lib/types";

// Mock Recharts — it doesn't render well in jsdom
jest.mock("recharts", () => {
  const MockedResponsiveContainer = ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  );
  const MockedLineChart = ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  );
  const MockedLine = (props: Record<string, unknown>) => (
    <div data-testid={`line-${props.dataKey}`} />
  );
  return {
    ResponsiveContainer: MockedResponsiveContainer,
    LineChart: MockedLineChart,
    Line: MockedLine,
    XAxis: () => null,
    YAxis: () => null,
    Tooltip: () => null,
    Legend: () => null,
    CartesianGrid: () => null,
  };
});

describe("EquityCurve", () => {
  const sampleData: EquityPoint[] = [
    { date: "2024-01-01", nav: 100000, benchmark: 100000 },
    { date: "2024-01-02", nav: 101000, benchmark: 100500 },
    { date: "2024-01-03", nav: 99500, benchmark: 99800 },
  ];

  it("renders the card with default title", () => {
    render(<EquityCurve data={sampleData} />);
    expect(screen.getByText("Equity Curve")).toBeInTheDocument();
  });

  it("renders with custom title", () => {
    render(<EquityCurve data={sampleData} title="My Portfolio" />);
    expect(screen.getByText("My Portfolio")).toBeInTheDocument();
  });

  it("renders the chart container", () => {
    render(<EquityCurve data={sampleData} />);
    expect(screen.getByTestId("responsive-container")).toBeInTheDocument();
    expect(screen.getByTestId("line-chart")).toBeInTheDocument();
  });

  it("renders both nav and benchmark lines", () => {
    render(<EquityCurve data={sampleData} />);
    expect(screen.getByTestId("line-nav")).toBeInTheDocument();
    expect(screen.getByTestId("line-benchmark")).toBeInTheDocument();
  });
});
```

### tests/components/PositionTable.test.tsx

```typescript
import { render, screen } from "@testing-library/react";
import { PositionTable } from "@/components/charts/PositionTable";
import type { Position } from "@/lib/types";

describe("PositionTable", () => {
  const samplePositions: Position[] = [
    {
      symbol: "AAPL",
      quantity: 100,
      avg_entry_price: 150.0,
      current_price: 160.0,
      market_value: 16000,
      unrealized_pnl: 1000,
      unrealized_pnl_pct: 6.67,
      sector: "Technology",
      trailing_stop_pct: 5,
      trailing_stop_price: 152.0,
      opened_at: "2024-01-15T10:00:00Z",
    },
    {
      symbol: "JPM",
      quantity: 50,
      avg_entry_price: 180.0,
      current_price: 175.0,
      market_value: 8750,
      unrealized_pnl: -250,
      unrealized_pnl_pct: -2.78,
      sector: "Financials",
      trailing_stop_pct: 5,
      trailing_stop_price: 171.0,
      opened_at: "2024-01-20T14:00:00Z",
    },
  ];

  it("renders the positions count", () => {
    render(<PositionTable positions={samplePositions} />);
    expect(screen.getByText("2 positions")).toBeInTheDocument();
  });

  it("renders all symbols", () => {
    render(<PositionTable positions={samplePositions} />);
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("JPM")).toBeInTheDocument();
  });

  it("renders sector badges", () => {
    render(<PositionTable positions={samplePositions} />);
    expect(screen.getByText("Technology")).toBeInTheDocument();
    expect(screen.getByText("Financials")).toBeInTheDocument();
  });

  it("shows empty state when no positions", () => {
    render(<PositionTable positions={[]} />);
    expect(screen.getByText("No open positions")).toBeInTheDocument();
    expect(screen.getByText("0 positions")).toBeInTheDocument();
  });

  it("renders table headers", () => {
    render(<PositionTable positions={samplePositions} />);
    expect(screen.getByText("Symbol")).toBeInTheDocument();
    expect(screen.getByText("Qty")).toBeInTheDocument();
    expect(screen.getByText("Entry")).toBeInTheDocument();
    expect(screen.getByText("Current")).toBeInTheDocument();
    expect(screen.getByText("P&L")).toBeInTheDocument();
    expect(screen.getByText("P&L %")).toBeInTheDocument();
  });

  it("formats positive P&L with green styling", () => {
    const { container } = render(<PositionTable positions={samplePositions} />);
    const profitCells = container.querySelectorAll(".text-profit");
    expect(profitCells.length).toBeGreaterThan(0);
  });

  it("formats negative P&L with red styling", () => {
    const { container } = render(<PositionTable positions={samplePositions} />);
    const lossCells = container.querySelectorAll(".text-loss");
    expect(lossCells.length).toBeGreaterThan(0);
  });
});
```

### tests/api/portfolio.test.ts

```typescript
/**
 * Tests for portfolio API route handlers.
 * Mocks the MCP server calls and Cognito auth.
 */

import { NextRequest } from "next/server";

// Mock jose before importing routes
jest.mock("jose", () => ({
  createRemoteJWKSet: jest.fn(),
  jwtVerify: jest.fn(),
}));

// Mock fetch for MCP calls
const mockFetch = jest.fn();
global.fetch = mockFetch;

// Set env for dev mode auth bypass
process.env.NODE_ENV = "development";

describe("Portfolio API Routes", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("returns portfolio summary from MCP", async () => {
    const mockSummary = {
      nav: 100000,
      daily_pnl: 1500,
      daily_pnl_pct: 1.5,
      total_pnl: 5000,
      total_pnl_pct: 5.0,
      open_positions: 3,
      buying_power: 50000,
      cash: 40000,
      margin_used: 10000,
      last_updated: "2024-01-15T16:00:00Z",
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ result: mockSummary }),
    });

    // Import dynamically to pick up mocks
    const { getSummary } = await import("@api/routes/portfolio");

    const req = new NextRequest("http://localhost:3000/api/portfolio/summary");
    const res = await getSummary(req);
    const data = await res.json();

    expect(res.status).toBe(200);
    expect(data.nav).toBe(100000);
    expect(data.daily_pnl).toBe(1500);
  });

  it("returns 502 when MCP is unavailable", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 503,
    });

    const { getSummary } = await import("@api/routes/portfolio");

    const req = new NextRequest("http://localhost:3000/api/portfolio/summary");
    const res = await getSummary(req);

    expect(res.status).toBe(502);
  });

  it("returns positions from MCP", async () => {
    const mockPositions = [
      {
        symbol: "AAPL",
        quantity: 100,
        avg_entry_price: 150,
        current_price: 160,
        market_value: 16000,
        unrealized_pnl: 1000,
        unrealized_pnl_pct: 6.67,
        sector: "Technology",
        trailing_stop_pct: 5,
        trailing_stop_price: 152,
        opened_at: "2024-01-15T10:00:00Z",
      },
    ];

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ result: mockPositions }),
    });

    const { getPositionsRoute } = await import("@api/routes/portfolio");

    const req = new NextRequest("http://localhost:3000/api/portfolio/positions");
    const res = await getPositionsRoute(req);
    const data = await res.json();

    expect(res.status).toBe(200);
    expect(data).toHaveLength(1);
    expect(data[0].symbol).toBe("AAPL");
  });
});
```

---

## Acceptance Criteria

1. **Dashboard renders** — `npm run dev` starts on :3000, all 8 pages load without errors
2. **Type-safe** — `npm run typecheck` passes with zero errors
3. **Linting** — `npm run lint` passes
4. **Tests pass** — `npm test` passes all component and API route tests
5. **Docker builds** — `docker build .` produces a runnable standalone image
6. **Auth enforced** — API routes return 401 without valid Cognito JWT (skipped in dev mode)
7. **Execution mode visible** — Header shows colored badge matching `EXECUTION_MODE` env var
8. **Live mode warning** — Switching to LIVE mode in settings shows confirmation dialog
9. **2FA web approval** — Approvals page shows pending orders with Approve/Reject that calls SFN SendTaskSuccess/SendTaskFailure
10. **Real-time updates** — WebSocket hook connects and updates portfolio data without page refresh
11. **Responsive** — All pages work on 1024px+ viewports (no mobile requirement for trading dashboard)
12. **Dark theme default** — Dashboard loads in dark theme; light toggle works

## Notes

- This is a Phase 2 deliverable. All backend services (MCPs, DynamoDB tables, SFN state machine) must exist before the dashboard can show real data.
- For local development, the API routes fall back to mock data when MCP servers are unreachable.
- The WebSocket integration requires an API Gateway WebSocket API deployed via CDK in P11.
- Cognito user pool and app client must be provisioned in P11 (infra).
