// Customer Footfall & Loyalty — searchable members, profile drawer w/ history + digital card.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import * as api from "../api/client";
import type { Customer, OrderSummary } from "../api/types";
import { Badge, Button, Card, EmptyState, ErrorState, Input, Modal, Skeleton, useToast } from "../components/ui";
import { inr, TIER_COLORS } from "../lib/format";

export function CustomersPage() {
  const { push } = useToast();
  const [customers, setCustomers] = useState<Customer[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Customer | null>(null);
  const [history, setHistory] = useState<OrderSummary[] | null>(null);
  const [adjustPts, setAdjustPts] = useState("");

  const load = useCallback(async () => {
    setError(null);
    try { setCustomers(await api.listCustomers()); }
    catch (e) { setError(e instanceof Error ? e.message : "Failed to load customers"); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const filtered = useMemo(() => {
    if (!customers) return [];
    const lower = q.toLowerCase();
    return customers.filter((c) => !lower || c.name.toLowerCase().includes(lower) || c.phone.includes(lower));
  }, [customers, q]);

  const openProfile = async (c: Customer) => {
    setSelected(c); setHistory(null); setAdjustPts("");
    try { setHistory(await api.customerHistory(c.phone)); } catch { setHistory([]); }
  };

  return (
    <div className="page-stack">
      <div className="toolbar">
        <Input placeholder="Search by name or phone…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search customers" />
        <Button onClick={() => void load()}>Refresh</Button>
      </div>

      {error ? <ErrorState message={error} onRetry={load} />
        : customers === null ? <Skeleton rows={6} />
        : filtered.length === 0 ? <EmptyState icon="👥" title="No members found" hint="New members are auto-created at the POS counter when a phone is captured." action={<Button variant="primary" onClick={() => { setQ(""); }}>Clear search</Button>} />
        : (
          <div className="cust-grid">
            {filtered.slice(0, 100).map((c) => (
              <button key={c.phone} className="cust-card" onClick={() => void openProfile(c)}>
                <span className="cust-avatar" style={{ background: TIER_COLORS[c.tier] }}>{c.name[0]}</span>
                <span className="cust-info">
                  <strong>{c.name}</strong>
                  <small>{c.phone}</small>
                </span>
                <span className="cust-stats">
                  <Badge tone="gold">{c.tier}</Badge>
                  <small>LTV {inr(c.lifetime_value, { compact: true })}</small>
                  <small>{c.visit_count} visits · {c.loyalty_points} pts</small>
                </span>
              </button>
            ))}
          </div>
        )}

      <Modal open={!!selected} onClose={() => setSelected(null)} title={selected?.name ?? ""} width={620}>
        {selected && (
          <>
            <div className="digital-member-card" style={{ borderColor: TIER_COLORS[selected.tier] }}>
              <div>
                <strong>APEX PRIVILEGE</strong>
                <div className="dmc-name">{selected.name}</div>
                <div className="muted">{selected.phone} · member since {selected.joined_date ?? "—"}</div>
              </div>
              <div className="dmc-right">
                <Badge tone="gold">{selected.tier}</Badge>
                <div className="qr-placeholder" aria-label="Membership QR code">▣</div>
              </div>
            </div>
            <div className="kpi-grid kpi-grid-3">
              <Card><strong>{inr(selected.lifetime_value)}</strong><div className="muted">Lifetime Value</div></Card>
              <Card><strong>{selected.visit_count}</strong><div className="muted">Total Visits</div></Card>
              <Card><strong>{selected.loyalty_points}</strong><div className="muted">Points Balance</div></Card>
            </div>
            <Card title="Recent Orders">
              {history === null ? <Skeleton rows={3} /> : history.length === 0 ? <p className="muted">No orders yet.</p> : (
                <table className="mini-table">
                  <tbody>
                    {history.slice(0, 8).map((o) => (
                      <tr key={o.bill_number}>
                        <td>{new Date(o.date).toLocaleDateString("en-IN")}</td>
                        <td className="mono">{o.bill_number}</td>
                        <td className="num">{o.items_count} items</td>
                        <td className="num"><strong>{inr(o.grand_total)}</strong></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
            <Card title="Points Adjustment (audit-logged)">
              <div className="inline-form">
                <Input placeholder="+500 bonus / -200 correction" value={adjustPts} onChange={(e) => setAdjustPts(e.target.value)} aria-label="Points adjustment" />
                <Button disabled={!adjustPts} onClick={() => push("info", "Points adjustments require supervisor API wiring — queued for backend endpoint.")}>Apply</Button>
              </div>
            </Card>
          </>
        )}
      </Modal>
    </div>
  );
}
