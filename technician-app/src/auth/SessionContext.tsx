import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { stopPlayback } from "../audio/player";
import { ApiError, onUnauthorized, setAuthToken } from "../lib/api";
import { translate, type StringKey } from "../lib/i18n";
import { KEYS, storage } from "../lib/storage";
import { authApi } from "../services";
import type { Language, User } from "../types/api";

type Status = "loading" | "signed_out" | "signed_in";

interface SessionValue {
  status: Status;
  user: User | null;
  /** The language the technician speaks and reads; null until chosen on this device. */
  language: Language | null;
  notice: StringKey | null;
  login: (email: string, password: string) => Promise<void>;
  logout: (notice?: StringKey) => Promise<void>;
  setLanguage: (language: Language) => Promise<void>;
  t: (key: StringKey, vars?: Record<string, string | number>) => string;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [language, setLanguageState] = useState<Language | null>(null);
  const [notice, setNotice] = useState<StringKey | null>(null);

  const logout = useCallback(
    async (reason?: StringKey) => {
      stopPlayback();
      setAuthToken(null);
      await storage.set(KEYS.token, null);
      queryClient.clear();
      setUser(null);
      setNotice(reason ?? null);
      setStatus("signed_out");
    },
    [queryClient],
  );

  useEffect(() => {
    onUnauthorized(() => void logout("err_session"));
    return () => onUnauthorized(null);
  }, [logout]);

  // Restore the saved session and language. The server re-checks the token and the role.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [token, savedLanguage] = await Promise.all([storage.get(KEYS.token), storage.get(KEYS.language)]);
      if (savedLanguage) setLanguageState(savedLanguage as Language);
      if (!token) {
        if (!cancelled) setStatus("signed_out");
        return;
      }
      setAuthToken(token);
      try {
        const me = await authApi.me();
        if (cancelled) return;
        if (me.role !== "technician") return void logout("technicianOnly");
        setUser(me);
        setStatus("signed_in");
      } catch (err) {
        // A 401 has already signed out through onUnauthorized with the "session ended" notice; keep it.
        if (!cancelled && !(err instanceof ApiError && err.status === 401)) await logout();
      }
    })();
    return () => {
      cancelled = true;
    };
    // run once on start
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await authApi.login(email, password);
    if (result.user.role !== "technician") {
      throw new ApiError(403, "technician_only", "This app is for technicians.");
    }
    setAuthToken(result.access_token);
    await storage.set(KEYS.token, result.access_token);
    setNotice(null);
    setUser(result.user);
    setStatus("signed_in");
  }, []);

  const setLanguage = useCallback(async (value: Language) => {
    setLanguageState(value);
    await storage.set(KEYS.language, value);
  }, []);

  // Before a language is chosen, show the account's preferred language (or English on the sign-in screen).
  const uiLanguage: Language = language ?? user?.preferred_language ?? "en";
  const t = useCallback(
    (key: StringKey, vars?: Record<string, string | number>) => translate(uiLanguage, key, vars),
    [uiLanguage],
  );

  const value = useMemo(
    () => ({ status, user, language, notice, login, logout, setLanguage, t }),
    [status, user, language, notice, login, logout, setLanguage, t],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside SessionProvider");
  return ctx;
}

/** The technician's language once chosen (screens after the language step can rely on it). */
export function useLanguage(): Language {
  const { language, user } = useSession();
  return language ?? user?.preferred_language ?? "en";
}
