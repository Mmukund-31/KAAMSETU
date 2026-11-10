# supervisor-web

The KAAMSETU supervisor console (React 18, TypeScript, Vite 6, Tailwind 3, TanStack Query 5, Recharts 3).
For supervisors and managers only. Technicians use the mobile app, and the console refuses technician sign-ins.

## Run

```powershell
# backend first (port 8001), see the root README
cd supervisor-web
npm install
npm run dev          # http://localhost:5173
```

In development the app calls `/api/...` on its own origin, and Vite forwards it to `http://localhost:8001`.
No CORS setup is needed. To point at another backend, set `VITE_PROXY_TARGET` (see `.env.example`). Set
`VITE_API_BASE_URL` only when the built app is served from a different origin than the API; then add that origin
to the backend's `CORS_ORIGINS`.

| Command | What it does |
|---|---|
| `npm run dev` | dev server with the API proxy |
| `npm test` | Vitest + Testing Library (fetch mocked with backend-shaped fixtures) |
| `npm run typecheck` | `tsc --noEmit`, strict mode |
| `npm run build` | typecheck, then production build to `dist/` |
| `npm run preview` | serve `dist/` on 4173 with the same proxy |

Demo sign-in: `supervisor@kaamsetu.demo` or `manager@kaamsetu.demo`, password `Kaamsetu@2026` (synthetic seed data).

## Docker

`docker compose up -d --build` (repository root) builds this app with Node, serves it with nginx on
http://localhost:8080 and forwards `/api` to the backend container, so the console and the API share one origin.
See `Dockerfile` and `nginx.conf`, which set security headers, the SPA fallback and an 11 MB body limit.

## Pages

| Route | Purpose | Data |
|---|---|---|
| `/login` | sign in, supervisors and managers only | `POST /auth/login` |
| `/` | overview tiles, "needs a decision" and overdue lists; polls every 15 s | `/dashboard/overview`, `/work-orders` |
| `/approvals` | new reports (reported, under review, escalated) and completion review, priority order | `/work-orders?status=...&sort=priority` |
| `/work-orders` | search, status and priority chips, overdue, safety, sort, pagination; filters live in the URL | `/work-orders` |
| `/work-orders/:id` | transcript next to the structured order, actions, assignment, SOP checklist, history | `/work-orders/{id}` and its actions |
| `/equipment`, `/equipment/:id` | register (with "register equipment"), fault history, recent orders | `/equipment` |
| `/technicians` | workload per technician, add account | `/dashboard/technician-workload`, `POST /auth/register` |
| `/handovers`, `/handovers/:id` | handover list, notes plus record-based summary, review with pending actions | `/handovers` |
| `/analytics` | trends, priority, status, category, symptoms, workload, recurring equipment; each chart has a table view | `/dashboard/*` |
| `/audit` | append-only audit log | `/audit-logs` |
| `/settings` | account, SOP checklist templates (publish a version, deactivate) | `/checklists/templates` |

## How it stays honest

- **The server decides what is allowed.** Action buttons come from `allowed_actions` in the work-order detail.
  Guarded actions are shown disabled with the reason, for example "Mandatory checklist steps are still open".
  Assignment uses `can_assign`. The client never works out lifecycle rules itself.
- **Every number comes from the API.** Tiles and charts show `/dashboard/*` fields directly, with no client-side
  recounting.
- **Evidence stays as recorded.** The original transcript is shown verbatim and labelled as immutable evidence.
  Edits go to the work order, and the server audits them.
- **Errors are shown, never hidden.** Every page has loading, empty and error states. Dialogs show the backend's
  error message, such as `409 already approved`. A 401 anywhere ends the session.

## Layout

```
src/
  lib/          api.ts (fetch wrapper, ApiError, token), format.ts (labels, dates), queryKeys.ts
  types/        api.ts, which mirrors backend/app/schemas
  services/     index.ts, typed client per domain (one function per endpoint)
  auth/         AuthContext (session restore, role gate, sign out on 401)
  layouts/      AppShell (sidebar, mobile drawer, top bar)
  components/   ui (Button, Card, StatCard, Modal, fields, Table, states), badges, Timeline,
                WorkOrderTable, WorkOrderActions (action bar, approve/reject/escalate/status, assign, edit)
  pages/        one file per route
  test/         harness (fetch mock, fixtures), api, format, auth, workOrders, management tests
```

Charts use the dataviz reference palette (categorical slots 1–4, validated on the light surface). Slots 3 and 4
are below 3:1 contrast, so every chart has a "Show table" view. The UI is light-theme only.
