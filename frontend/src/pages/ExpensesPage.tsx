// Expenses Tracker — categories, add form, monthly summary.
import React, { useCallback, useEffect, useState } from "react";
import * as api from "../api/client";
import type { Expense } from "../api/types";
import { useApp, hasRole } from "../store/appStore";
import { Button, Card, EmptyState, ErrorState, Input, KpiCard, Select, Skeleton, useToast } from "../components/ui";
import { inr } from "../lib/format";

const CATEGORIES = ["RENT", "SALARY", "UTILITIES", "MAINTENANCE", "MARKETING", "LOGISTICS", "OTHER"];

export function ExpensesPage() {
  const app = useApp();
  const { push } = useToast();
  const [rows, setRows] = useState<Expense[] | null>(null);
  const [summary, setSummary] = useState<Record<string, number> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cat, setCat] = useState(CATEGORIES[0]);
  const [amt, setAmt] = useState("");
  const [desc, setDesc] = useState("");
  const canManage = hasRole(app.user, "STORE_MANAGER");

  const load = useCallback(async () => {
    setError(null);
    try {
      const [list, sum] = await Promise.all([api.listExpenses(), api.expenseSummary()]);
      setRows(list); setSummary(sum);
    } catch (e) { setError(e instanceof Error ? e.message : "Failed to load expenses"); }
  }, []);
  useEffect(() => { if (canManage) void load(); }, [canManage, load]);

  if (!canManage) return <EmptyState icon="🔒" title="Expenses are manager-only" />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (rows === null) return <Skeleton rows={6} />;

  const total = Object.values(summary ?? {}).reduce((a, b) => a + b, 0);

  return (
    <div className="page-stack">
      <div className="kpi-grid">
        <KpiCard label="Total Expenses (30d)" value={inr(total, { compact: true })} tone="danger" />
        {Object.entries(summary ?? {}).slice(0, 5).map(([k, v]) => (
          <KpiCard key={k} label={k} value={inr(v, { compact: true })} tone="neutral" />
        ))}
      </div>

      <Card title="Record Expense">
        <div className="inline-form">
          <Select value={cat} onChange={(e) => setCat(e.target.value)} aria-label="Category">
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </Select>
          <Input placeholder="Amount ₹" type="number" min={1} value={amt} onChange={(e) => setAmt(e.target.value)} aria-label="Amount" />
          <Input placeholder="Description / voucher no." value={desc} onChange={(e) => setDesc(e.target.value)} aria-label="Description" />
          <Button variant="primary" disabled={!amt} onClick={async () => {
            try { await api.addExpense(cat, Number(amt), desc || cat); push("success", "Expense recorded"); setAmt(""); setDesc(""); void load(); }
            catch (e) { push("error", e instanceof Error ? e.message : "Failed"); }
          }}>Add</Button>
        </div>
      </Card>

      <Card title={`Entries (${rows.length})`}>
        {rows.length === 0 ? <EmptyState icon="💸" title="No expenses logged this period" /> : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Date</th><th>Category</th><th>Description</th><th className="num">Amount</th><th /></tr></thead>
              <tbody>
                {rows.slice(0, 60).map((x) => (
                  <tr key={x.id}>
                    <td>{new Date(x.date).toLocaleDateString("en-IN")}</td>
                    <td><Badge2>{x.category}</Badge2></td>
                    <td>{x.description}</td>
                    <td className="num bad">{inr(x.amount)}</td>
                    <td><Button size="sm" variant="ghost" onClick={async () => {
                      try { await api.deleteExpense(x.id); push("success", "Deleted"); void load(); }
                      catch (e) { push("error", e instanceof Error ? e.message : "Delete failed"); }
                    }}>✕</Button></td>
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
function Badge2({ children }: { children: React.ReactNode }) { return <span className="badge badge-neutral">{children}</span>; }
