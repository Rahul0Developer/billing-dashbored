// ---- Design-system primitives: Button, Input, Badge, Card, Modal, Toast, Skeleton, EmptyState ----
import React, { createContext, useCallback, useContext, useState } from "react";

type BtnVariant = "primary" | "secondary" | "danger" | "ghost" | "success";
export function Button({
  variant = "secondary", size = "md", className = "", loading = false, children, ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: "sm" | "md" | "lg"; loading?: boolean }) {
  return (
    <button
      className={`btn btn-${variant} btn-${size} ${loading ? "is-loading" : ""} ${className}`}
      disabled={loading || rest.disabled}
      {...rest}
    >
      {loading && <span className="spinner" aria-hidden="true" />}
      {children}
    </button>
  );
}

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  function Input(props, ref) {
    return <input ref={ref} className="field" {...props} />;
  },
);

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className="field" {...props} />;
}

const TONE_CLASS: Record<string, string> = {
  neutral: "badge-neutral", success: "badge-success", warning: "badge-warning",
  danger: "badge-danger", info: "badge-info", gold: "badge-gold",
};
export function Badge({ tone = "neutral", children }: { tone?: keyof typeof TONE_CLASS; children: React.ReactNode }) {
  return <span className={`badge ${TONE_CLASS[tone]}`}>{children}</span>;
}

export function statusTone(status: string): keyof typeof TONE_CLASS {
  switch (status) {
    case "COMPLETED": return "success";
    case "VOIDED": return "danger";
    case "RETURNED": return "warning";
    case "PARTIALLY_RETURNED": return "info";
    default: return "neutral";
  }
}

export function Card({ title, actions, children, className = "" }: {
  title?: React.ReactNode; actions?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          <h3>{title}</h3>
          <div className="card-actions">{actions}</div>
        </header>
      )}
      <div className="card-body">{children}</div>
    </section>
  );
}

export function Modal({ open, onClose, title, children, width = 560 }: {
  open: boolean; onClose: () => void; title: React.ReactNode; children: React.ReactNode; width?: number;
}) {
  if (!open) return null;
  return (
    <div className="modal-overlay" onClick={onClose} role="presentation">
      <div className="modal" style={{ maxWidth: width }} role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : "Dialog"}
        onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Close dialog">✕</button>
        </header>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

// ---- Toast system ----
interface Toast { id: number; kind: "success" | "error" | "info"; text: string }
const ToastCtx = createContext<{ push: (kind: Toast["kind"], text: string) => void }>({ push: () => undefined });
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((kind: Toast["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);
  return (
    <ToastCtx.Provider value={{ push }}>
      {children}
      <div className="toast-stack" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`}>{t.text}</div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

// ---- Loading skeleton ----
export function Skeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="skeleton-stack" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton" />)}
    </div>
  );
}

// ---- Empty state with recovery action ----
export function EmptyState({ icon = "📦", title, hint, action }: {
  icon?: string; title: string; hint?: string; action?: React.ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon" aria-hidden="true">{icon}</div>
      <h4>{title}</h4>
      {hint && <p>{hint}</p>}
      {action}
    </div>
  );
}

// ---- Error state with retry ----
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="empty-state error">
      <div className="empty-icon" aria-hidden="true">⚠️</div>
      <h4>Something went wrong</h4>
      <p>{message}</p>
      {onRetry && <Button variant="primary" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

// ---- KPI card with optional sparkline ----
export function KpiCard({ label, value, delta, tone = "info", spark }: {
  label: string; value: string; delta?: string; tone?: keyof typeof TONE_CLASS; spark?: number[];
}) {
  const points = spark && spark.length > 1
    ? spark.map((v, i) => `${(i / (spark.length - 1)) * 100},${30 - ((v - Math.min(...spark)) / (Math.max(...spark) - Math.min(...spark) || 1)) * 28}`).join(" ")
    : undefined;
  return (
    <div className={`kpi-card kpi-${tone}`}>
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span>
      {delta && <span className="kpi-delta">{delta}</span>}
      {points && (
        <svg className="sparkline" viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true">
          <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" />
        </svg>
      )}
    </div>
  );
}
