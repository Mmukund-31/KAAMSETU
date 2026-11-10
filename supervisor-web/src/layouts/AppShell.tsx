import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  ClipboardCheck,
  ClipboardList,
  Cog,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  Repeat,
  Users,
  Wrench,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth, useCurrentUser } from "../auth/AuthContext";
import { cx } from "../components/ui";
import { dashboardApi } from "../services";
import { queryKeys } from "../lib/queryKeys";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  count?: number;
}

export function AppShell() {
  const user = useCurrentUser();
  const { logout } = useAuth();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const [lastPath, setLastPath] = useState(location.pathname);
  if (lastPath !== location.pathname) {
    // close the mobile drawer after navigating
    setLastPath(location.pathname);
    setOpen(false);
  }

  const overview = useQuery({ queryKey: queryKeys.overview, queryFn: dashboardApi.overview, refetchInterval: 15_000 });
  const pending = overview.data?.pending_approval;

  const icon = "h-4 w-4";
  const items: NavItem[] = [
    { to: "/", label: "Overview", icon: <LayoutDashboard className={icon} /> },
    { to: "/approvals", label: "Approvals", icon: <ClipboardCheck className={icon} />, count: pending },
    { to: "/work-orders", label: "Work orders", icon: <ClipboardList className={icon} /> },
    { to: "/equipment", label: "Equipment", icon: <Wrench className={icon} /> },
    { to: "/technicians", label: "Technicians", icon: <Users className={icon} /> },
    { to: "/handovers", label: "Handovers", icon: <Repeat className={icon} /> },
    { to: "/analytics", label: "Analytics", icon: <BarChart3 className={icon} /> },
    { to: "/audit", label: "Audit log", icon: <History className={icon} /> },
    { to: "/settings", label: "Settings", icon: <Cog className={icon} /> },
  ];

  const nav = (
    <nav aria-label="Main" className="flex-1 space-y-0.5 px-3 py-4">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/"}
          className={({ isActive }) =>
            cx(
              "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium",
              isActive ? "bg-primary-50 text-primary-800" : "text-ink-muted hover:bg-surface-sunken hover:text-ink",
            )
          }
        >
          {item.icon}
          <span className="flex-1">{item.label}</span>
          {!!item.count && (
            <span
              className="rounded-full bg-amber-100 px-1.5 text-xs font-semibold tabular-nums text-amber-900"
              aria-label={`${item.count} waiting`}
            >
              {item.count}
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  );

  const brand = (
    <div className="flex items-center gap-2 px-5 py-4">
      <img src="/favicon.svg" alt="" className="h-7 w-7" />
      <div>
        <p className="text-sm font-semibold tracking-wide text-ink">KAAMSETU</p>
        <p className="text-xs text-ink-muted">Supervisor console</p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-surface-subtle">
      {/* desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 hidden w-60 flex-col border-r border-line bg-white lg:flex">
        {brand}
        {nav}
      </aside>

      {/* mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-ink/40" onClick={() => setOpen(false)} aria-hidden />
          <aside className="relative flex h-full w-64 flex-col bg-white shadow-xl">
            <div className="flex items-center justify-between pr-3">
              {brand}
              <button
                className="rounded p-1.5 text-ink-muted hover:bg-surface-sunken"
                onClick={() => setOpen(false)}
                aria-label="Close menu"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            {nav}
          </aside>
        </div>
      )}

      <div className="lg:pl-60">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-line bg-white px-4 sm:px-6">
          <button
            className="rounded p-1.5 text-ink-muted hover:bg-surface-sunken lg:hidden"
            onClick={() => setOpen(true)}
            aria-label="Open menu"
          >
            <Menu className="h-5 w-5" />
          </button>
          <p className="hidden text-sm text-ink-muted sm:block">{user.site?.name ?? "All sites"}</p>
          <div className="ml-auto flex items-center gap-3">
            <div className="text-right">
              <p className="text-sm font-medium text-ink">{user.name}</p>
              <p className="text-xs capitalize text-ink-muted">{user.role}</p>
            </div>
            <button
              onClick={() => logout()}
              className="rounded-md p-2 text-ink-muted hover:bg-surface-sunken hover:text-ink"
              aria-label="Sign out"
              title="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
