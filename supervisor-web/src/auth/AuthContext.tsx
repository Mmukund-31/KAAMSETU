import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, getToken, onUnauthorized, setToken } from "../lib/api";
import { authApi } from "../services";
import type { User } from "../types/api";

/** The web app is the supervisor console; technicians use the mobile app. */
export const WEB_ROLES = new Set(["supervisor", "manager"]);

type AuthState =
  | { status: "loading"; user: null }
  | { status: "anonymous"; user: null; notice?: string }
  | { status: "authenticated"; user: User };

interface AuthContextValue {
  state: AuthState;
  login: (email: string, password: string) => Promise<void>;
  logout: (notice?: string) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<AuthState>(() =>
    getToken() ? { status: "loading", user: null } : { status: "anonymous", user: null },
  );

  const logout = useCallback(
    (notice?: string) => {
      setToken(null);
      queryClient.clear();
      setState({ status: "anonymous", user: null, notice });
    },
    [queryClient],
  );

  useEffect(() => {
    onUnauthorized(() => logout("Your session has ended. Please sign in again."));
    return () => onUnauthorized(null);
  }, [logout]);

  // Restore a saved session. The server re-reads the role, so a stale token for a deactivated user fails here.
  useEffect(() => {
    if (state.status !== "loading") return;
    let cancelled = false;
    authApi
      .me()
      .then((user) => {
        if (cancelled) return;
        if (!WEB_ROLES.has(user.role)) logout("The supervisor console is for supervisors and managers.");
        else setState({ status: "authenticated", user });
      })
      .catch(() => !cancelled && logout());
    return () => {
      cancelled = true;
    };
  }, [state.status, logout]);

  const login = useCallback(async (email: string, password: string) => {
    const result = await authApi.login(email, password);
    if (!WEB_ROLES.has(result.user.role)) {
      throw new ApiError(
        403,
        "web_role_not_permitted",
        "This console is for supervisors and managers. Technicians report work in the KAAMSETU mobile app.",
      );
    }
    setToken(result.access_token);
    setState({ status: "authenticated", user: result.user });
  }, []);

  const value = useMemo(() => ({ state, login, logout }), [state, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

/** The signed-in user. Only call inside routes guarded by RequireAuth. */
export function useCurrentUser(): User {
  const { state } = useAuth();
  if (state.status !== "authenticated") throw new Error("No authenticated user");
  return state.user;
}

export function useLogoutNotice(): string | undefined {
  const { state } = useAuth();
  return state.status === "anonymous" ? state.notice : undefined;
}

