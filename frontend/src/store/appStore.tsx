// ---- Global app state (React context; Zustand-style API surface) ----
import React, { createContext, useContext, useState, useCallback, useMemo, useEffect } from "react";
import type { SessionUser, StoreProfile, Branch, Customer, UserRole } from "../api/types";
import * as api from "../api/client";
import { LoginForm } from "../components/LoginForm";

export type Theme = "light" | "dark" | "contrast";
export type PageKey =
  | "pos" | "sales" | "shifts" | "dashboard" | "branches"
  | "inventory" | "customers" | "expenses" | "reports" | "users";

interface AppState {
  user: SessionUser | null;
  setUser: (u: SessionUser | null) => void;
  loginWith: (username: string, pin: string) => Promise<SessionUser>;
  signOut: () => Promise<void>;
  profile: StoreProfile | null;
  branches: Branch[];
  activeBranchId: string;
  setActiveBranchId: (id: string) => void;
  theme: Theme;
  cycleTheme: () => void;
  page: PageKey;
  setPage: (p: PageKey) => void;
  online: boolean;
  queuedCount: number;
  refreshQueue: () => void;
  customer: Customer | null;
  setCustomer: (c: Customer | null) => void;
}

const Ctx = createContext<AppState | null>(null);

const ROLE_RANK: Record<UserRole, number> = { CASHIER: 1, INVENTORY_MANAGER: 2, STORE_MANAGER: 3, ADMIN: 4 };
export const hasRole = (user: SessionUser | null, min: UserRole) =>
  !!user && ROLE_RANK[user.role] >= ROLE_RANK[min];

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [profile, setProfile] = useState<StoreProfile | null>(null);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [activeBranchId, setActiveBranchId] = useState<string>("BR-DEL-01");
  const [theme, setTheme] = useState<Theme>((localStorage.getItem("apex_theme") as Theme) || "light");
  const [page, setPage] = useState<PageKey>("pos");
  const [online, setOnline] = useState<boolean>(navigator.onLine);
  const [queuedCount, setQueuedCount] = useState<number>(api.getQueuedSales().length);
  const [customer, setCustomer] = useState<Customer | null>(null);

  const bootstrap = useCallback(async () => {
    try {
      const p = await api.getStoreProfile();
      setProfile(p);
      try {
        const bs = await api.listBranches();
        setBranches(bs);
      } catch { /* manager-only endpoint; cashiers skip */ }
    } catch { /* offline or unauthorized */ }
  }, []);

  // Restore session on boot when a token exists.
  useEffect(() => {
    if (api.auth.token) void bootstrap();
  }, [bootstrap]);

  const loginWith = useCallback(async (username: string, pin: string) => {
    const res = await api.login(username, pin);
    api.auth.token = res.token;
    setUser(res.user);
    setActiveBranchId(res.user.branch_id || "BR-DEL-01");
    await bootstrap();
    return res.user;
  }, [bootstrap]);

  const signOut = useCallback(async () => {
    await api.logout();
    api.auth.token = null;
    setUser(null);
    setCustomer(null);
  }, []);

  const applyTheme = useCallback((th: Theme) => {
    localStorage.setItem("apex_theme", th);
    document.documentElement.setAttribute("data-theme", th === "contrast" ? "dark" : th);
    document.documentElement.setAttribute("data-contrast", th === "contrast" ? "on" : "off");
    setTheme(th);
  }, []);

  const cycleTheme = useCallback(() => {
    applyTheme(theme === "light" ? "dark" : theme === "dark" ? "contrast" : "light");
  }, [theme, applyTheme]);

  // Apply persisted theme once on mount.
  useEffect(() => { applyTheme(theme); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshQueue = useCallback(() => setQueuedCount(api.getQueuedSales().length), []);

  // Connectivity awareness + offline queue drain.
  useEffect(() => {
    const goOnline = () => { setOnline(true); void api.drainOfflineQueue().then(refreshQueue); };
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    const id = setInterval(() => { if (navigator.onLine) void api.drainOfflineQueue().then(refreshQueue); }, 30000);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
      clearInterval(id);
    };
  }, [refreshQueue]);

  const value = useMemo<AppState>(() => ({
    user, setUser, loginWith, signOut, profile, branches, activeBranchId, setActiveBranchId,
    theme, cycleTheme, page, setPage, online, queuedCount, refreshQueue,
    customer, setCustomer,
  }), [user, loginWith, signOut, profile, branches, activeBranchId, theme, page, online, queuedCount, customer, cycleTheme, refreshQueue]);

  return (
    <Ctx.Provider value={value}>
      <LoginGate>{children}</LoginGate>
    </Ctx.Provider>
  );
}

// Renders the login screen when there is no session.
function LoginGate({ children }: { children: React.ReactNode }) {
  const s = useContext(Ctx)!;
  if (s.user) return <>{children}</>;
  return <LoginForm onLogin={s.loginWith} />;
}

export function useApp(): AppState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useApp must be used inside AppProvider");
  return ctx;
}
