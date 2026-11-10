# supervisor-web

Supervisor command centre (React + TypeScript + Vite + Tailwind).
Initialised in **Phase 5**. Planned layout:

```
src/
  pages/        Login, Overview, WorkOrders, WorkOrderDetail, Approvals, Equipment,
                EquipmentDetail, Technicians, Handovers, HandoverDetail, Analytics, Settings
  layouts/      AppShell (sidebar + topbar)
  components/   DataTable, FilterBar, StatusBadge, PriorityBadge, StatCard,
                EmptyState, ErrorState, Skeleton, ConfirmDialog, Drawer, Timeline
  hooks/        useAuth, useWorkOrders, useDashboard, ...
  services/     api.ts (axios), per-domain typed clients
  types/        mirrors backend Pydantic schemas
  lib/          formatting, constants
```
