import React, { useEffect, useMemo, useState } from "react";
import { useApp, hasRole } from "../store/appStore";
import type { PageKey } from "../store/appStore";
import { useI18n } from "../i18n";
import { Badge } from "./ui";

interface NavItem { key: PageKey; icon: string; labelKey: string; minRole?: "STORE_MANAGER" | "INVENTORY_MANAGER" }

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "OPERATIONS",
    items: [
      { key: "pos", icon: "🧾", labelKey: "nav.pos" },
      { key: "sales", icon: "📄", labelKey: "nav.sales" },
      { key: "shifts", icon: "🗄️", labelKey: "nav.shifts" },
    ],
  },
  {
    section: "MANAGEMENT",
    items: [
      { key: "dashboard", icon: "📈", labelKey: "nav.dashboard", minRole: "STORE_MANAGER" },
      { key: "branches", icon: "🌐", labelKey: "nav.branches" },
      { key: "inventory", icon: "📦", labelKey: "nav.inventory" },
      { key: "customers", icon: "👥", labelKey: "nav.customers" },
      { key: "expenses", icon: "💸", labelKey: "nav.expenses", minRole: "STORE_MANAGER" },
      { key: "reports", icon: "📤", labelKey: "nav.reports", minRole: "STORE_MANAGER" },
      { key: "users", icon: "🛡️", labelKey: "nav.users", minRole: "STORE_MANAGER" },
    ],
  },
];

function Clock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => { const id = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(id); }, []);
  return <span className="topbar-clock" aria-label="Current time">{now.toLocaleTimeString("en-IN", { hour12: true })}</span>;
}

export function Layout({ children }: { children: React.ReactNode }) {
  const app = useApp();
  const { t, lang, setLang } = useI18n();
  const [collapsed, setCollapsed] = useState(false);

  const visibleNav = useMemo(
    () =>
      NAV.map((sec) => ({
        ...sec,
        items: sec.items.filter((it) => !it.minRole || hasRole(app.user, it.minRole)),
      })).filter((sec) => sec.items.length > 0),
    [app.user],
  );

  const branchName = app.branches.find((b) => b.branch_id === app.activeBranchId)?.name
    ?? app.profile?.name ?? "Apex Store";

  return (
    <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
      <aside className="app-sidebar" aria-label="Primary navigation">
        <div className="sidebar-brand">
          <div className="brand-logo-circle">🛒</div>
          {!collapsed && (
            <div className="brand-text">
              <h2>APEX RETAIL</h2>
              <span className="store-badge-tag">ENTERPRISE POS</span>
            </div>
          )}
        </div>
        <div className="store-location-info" title={app.activeBranchId}>
          🏬
          {!collapsed && (
            <div>
              <strong>{branchName}</strong>
              <small>Branch ID: {app.activeBranchId}</small>
            </div>
          )}
        </div>
        <nav className="sidebar-nav">
          {visibleNav.map((sec) => (
            <React.Fragment key={sec.section}>
              {!collapsed && <div className="nav-section-label">{sec.section}</div>}
              {sec.items.map((it) => (
                <button key={it.key}
                  className={`nav-item ${app.page === it.key ? "active" : ""}`}
                  onClick={() => app.setPage(it.key)}
                  aria-current={app.page === it.key ? "page" : undefined}
                  title={t(it.labelKey)}>
                  <span className="nav-icon" aria-hidden="true">{it.icon}</span>
                  {!collapsed && <span>{t(it.labelKey)}</span>}
                </button>
              ))}
            </React.Fragment>
          ))}
        </nav>
        <div className="sidebar-footer">
          <button className="nav-item" onClick={() => setCollapsed((c) => !c)} aria-label="Toggle sidebar">
            <span className="nav-icon">{collapsed ? "⏩" : "⏪"}</span>
            {!collapsed && <span>Collapse</span>}
          </button>
        </div>
      </aside>

      <div className="app-main">
        <header className="app-topbar">
          <div className="topbar-left">
            <h1 className="topbar-title">{t(`nav.${app.page}`)}</h1>
            {app.branches.length > 1 && hasRole(app.user, "STORE_MANAGER") && (
              <select className="field field-sm" value={app.activeBranchId}
                onChange={(e) => app.setActiveBranchId(e.target.value)} aria-label="Switch branch">
                {app.branches.map((b) => <option key={b.branch_id} value={b.branch_id}>{b.name}</option>)}
              </select>
            )}
          </div>
          <div className="topbar-right">
            <span className={`conn-pill ${app.online ? "conn-online" : "conn-offline"}`} role="status">
              {app.online ? "● Online" : "○ Offline"}
              {app.queuedCount > 0 && <span className="queue-badge" title="Queued offline sales">⇅ {app.queuedCount}</span>}
            </span>
            <Clock />
            <button className="icon-btn" title="Language" onClick={() => setLang(lang === "en" ? "hi" : "en")}>
              {lang === "en" ? "अ" : "EN"}
            </button>
            <button className="icon-btn" title="Theme (light/dark/high-contrast)" onClick={app.cycleTheme}>
              {app.theme === "light" ? "🌙" : app.theme === "dark" ? "◐" : "☀️"}
            </button>
            <Badge tone={app.user?.role === "ADMIN" ? "danger" : app.user?.role === "STORE_MANAGER" ? "gold" : "info"}>
              {app.user?.name} · {app.user?.role}
            </Badge>
            <button className="btn btn-ghost btn-sm" onClick={() => void app.signOut()}>Sign out</button>
          </div>
        </header>
        <main className="app-content" role="main">
          {children}
        </main>
      </div>
    </div>
  );
}
