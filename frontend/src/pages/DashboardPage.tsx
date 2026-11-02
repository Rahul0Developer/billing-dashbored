// Executive Dashboard & BI — 6 pillars: P&L, restock queue, dead stock, trends.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import * as api from "../api/client";
import type { BIReport, DashboardData, OrderSummary } from "../api/types";
import { useApp } from "../store/appStore";
import { Badge, Button, Card, ErrorState, KpiCard, Skeleton, useToast } from "../components/ui";
import { inr } from "../lib/format";

type Period = "TODAY" | "WEEK" | "MONTH" | "YEAR";
const DAYS: Record<Period, number> = { TODAY: 1, WEEK: 7, MONTH: 30, YEAR: 365 };

export function DashboardPage() {
  const app = useApp();
  const { push } = useToast();
  const [dash, setDash] = useState<DashboardData | null>(null);
  const [bi, setBi] = useState<BIReport | null>(null);
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState<Period>("WEEK");

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [d, b, o] = await Promise.all([api.getDashboard(), api.getBI(), api.listOrders().catch(() => [])]);
      setDash(d); setBi(b); setOrders(o);
    } catch (e) { setError(e instanceof Error ? e.message : "Failed to load dashboard"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const periodStats = useMemo(() => {
    const cutoff = Date.now() - DAYS[period] * 864e5;
    const inRange = orders.filter((o) => new Date(o.date).getTime() >= cutoff && o.status === "COMPLETED");
    const revenue = inRange.reduce((a, o) => a + o.grand_total, 0);
    const byDay = new Map<string, number>();
    inRange.forEach((o) => {
      const k = new Date(o.date).toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
      byDay.set(k, (byDay.get(k) ?? 0) + o.grand_total);
    });
    return { revenue, bills: inRange.length, spark: Array.from(byDay.values()).slice(-14) };
  }, [orders, period]);

  if (loading) return <Skeleton rows={10} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const marginPct = bi?.revenue ? ((bi.gross_margin ?? 0) / bi.revenue) * 100 : 0;

  return (
    <div className="page-stack">
      <div className="toolbar">
        <div className="segmented" role="tablist" aria-label="Period">
          {(Object.keys(DAYS) as Period[]).map((p) => (
            <button key={p} role="tab" aria-selected={period === p}
              className={`chip ${period === p ? "chip-active" : ""}`} onClick={() => setPeriod(p)}>{p}</button>
          ))}
        </div>
        <span className="spacer" />
        <Button size="sm" onClick={() => void load()}>Refresh</Button>
      </div>

      <div className="kpi-grid">
        <KpiCard label={`Revenue · ${period.toLowerCase()}`} value={inr(periodStats.revenue, { compact: true })} delta={`${periodStats.bills} bills`} tone="success" spark={periodStats.spark} />
        <KpiCard label="Today Revenue" value={inr(dash?.today_revenue ?? 0)} delta={`${dash?.today_bills ?? 0} bills`} tone="info" />
        <KpiCard label="Gross Margin" value={inr(bi?.gross_margin ?? 0, { compact: true })} delta={`${marginPct.toFixed(1)}% of revenue`} tone="gold" />
        <KpiCard label="Net Profit" value={inr(bi?.net_profit ?? 0, { compact: true })} tone={(bi?.net_profit ?? 0) >= 0 ? "success" : "danger"} />
        <KpiCard label="Low Stock SKUs" value={String(dash?.low_stock_count ?? 0)} tone="warning" />
        <KpiCard label="Active Members" value={String(dash?.active_customers ?? 0)} tone="info" />
      </div>

      <div className="two-col">
        <Card title="P&L Snapshot (30 days)">
          <table className="mini-table">
            <tbody>
              <tr><td>Revenue</td><td className="num">{inr(bi?.revenue ?? 0)}</td></tr>
              <tr><td>COGS</td><td className="num bad">− {inr(bi?.cogs ?? 0)}</td></tr>
              <tr><td><strong>Gross Margin</strong></td><td className="num"><strong>{inr(bi?.gross_margin ?? 0)}</strong></td></tr>
              <tr><td>Operating Expenses</td><td className="num bad">− {inr(bi?.expenses ?? 0)}</td></tr>
              <tr className="row-total"><td><strong>Net Profit</strong></td><td className="num"><strong className={(bi?.net_profit ?? 0) >= 0 ? "good" : "bad"}>{inr(bi?.net_profit ?? 0)}</strong></td></tr>
            </tbody>
          </table>
        </Card>

        <Card title="Restock Priority Queue">
          {(bi?.restock_queue ?? []).length === 0 ? <p className="muted">All shelves healthy 🎉</p> : (
            <ul className="queue-list">
              {(bi?.restock_queue ?? []).slice(0, 8).map((r) => (
                <li key={r.barcode}>
                  <span className="queue-name">{r.name}</span>
                  <Badge tone={r.stock <= 0 ? "danger" : r.urgency > 5 ? "warning" : "info"}>
                    {r.stock <= 0 ? "OUT" : `${r.stock} left`}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Dead Stock — recommend markdown or inter-branch transfer">
        {(bi?.dead_stock ?? []).length === 0 ? <p className="muted">No dead stock detected.</p> : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Product</th><th>Barcode</th><th className="num">Days Unsold</th><th className="num">Locked Value</th><th>Action</th></tr></thead>
              <tbody>
                {(bi?.dead_stock ?? []).slice(0, 12).map((d) => (
                  <tr key={d.barcode}>
                    <td>{d.name}</td><td className="mono">{d.barcode}</td>
                    <td className="num bad">{d.days_since_sale}d</td>
                    <td className="num">{inr(d.value)}</td>
                    <td><Button size="sm" onClick={() => { app.setPage("inventory"); push("info", `Search ${d.barcode} in Inventory to adjust or transfer.`); }}>Take action</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
