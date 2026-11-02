// Sales & Transaction Register — filterable table, thermal/A4 reprint, void with manager PIN.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import * as api from "../api/client";
import type { OrderSummary } from "../api/types";
import { useApp, hasRole } from "../store/appStore";
import { Badge, Button, EmptyState, ErrorState, Input, Modal, Select, Skeleton, statusTone, useToast } from "../components/ui";
import { ManagerPinModal } from "../components/ManagerPinModal";
import { inr } from "../lib/format";

export function SalesPage() {
  const app = useApp();
  const { push } = useToast();
  const [orders, setOrders] = useState<OrderSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [payFilter, setPayFilter] = useState("ALL");
  const [detail, setDetail] = useState<OrderSummary | null>(null);
  const [receiptHtml, setReceiptHtml] = useState<string | null>(null);
  const [voidTarget, setVoidTarget] = useState<string | null>(null);
  const canManage = hasRole(app.user, "STORE_MANAGER");

  const load = useCallback(async () => {
    setError(null);
    setOrders(null);
    try { setOrders(await api.listOrders()); }
    catch (e) { setError(e instanceof Error ? e.message : "Failed to load orders"); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const filtered = useMemo(() => {
    if (!orders) return [];
    const lower = q.toLowerCase();
    return orders.filter((o) =>
      (statusFilter === "ALL" || o.status === statusFilter) &&
      (payFilter === "ALL" || o.payment_method === payFilter) &&
      (!lower || o.bill_number.toLowerCase().includes(lower) || o.customer.toLowerCase().includes(lower) || o.cashier.toLowerCase().includes(lower)),
    );
  }, [orders, q, statusFilter, payFilter]);

  const openThermal = async (bill: string) => {
    try {
      const res = await api.getThermalReceipt(bill);
      const html = typeof res === "string" ? res : res.html ?? res.receipt ?? res.text ?? "";
      setReceiptHtml(html);
    } catch (e) { push("error", e instanceof Error ? e.message : "Reprint failed"); }
  };
  const openA4 = async (bill: string) => {
    try {
      const res = await api.getA4Invoice(bill);
      setReceiptHtml(res.html);
    } catch (e) { push("error", e instanceof Error ? e.message : "Invoice fetch failed"); }
  };

  const doVoid = async (managerId: string) => {
    if (!voidTarget) return;
    try {
      await api.voidOrder(voidTarget, "Counter void — authorized by " + managerId, "override");
      push("success", `Bill ${voidTarget} voided`);
      setVoidTarget(null);
      void load();
    } catch (e) { push("error", e instanceof Error ? e.message : "Void failed"); }
  };

  return (
    <div className="page-stack">
      <div className="toolbar">
        <Input placeholder="Search bill no, customer, cashier…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search transactions" />
        <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Status filter">
          {["ALL", "COMPLETED", "RETURNED", "PARTIALLY_RETURNED", "VOIDED"].map((s) => <option key={s}>{s}</option>)}
        </Select>
        <Select value={payFilter} onChange={(e) => setPayFilter(e.target.value)} aria-label="Payment filter">
          {["ALL", "CASH", "UPI", "CARD", "WALLET", "SPLIT"].map((s) => <option key={s}>{s}</option>)}
        </Select>
        <Button onClick={() => void load()}>Refresh</Button>
      </div>

      {error ? <ErrorState message={error} onRetry={load} />
        : orders === null ? <Skeleton rows={8} />
        : filtered.length === 0 ? <EmptyState icon="🧾" title="No transactions match" hint="Adjust filters or start billing at the POS counter." />
        : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr>
                <th>Bill No.</th><th>Date</th><th>Customer</th><th>Cashier</th>
                <th>PAYMENT</th><th>Status</th><th className="num">Items</th><th className="num">Total</th><th>ACTIONS</th>
              </tr></thead>
              <tbody>
                {filtered.slice(0, 200).map((o) => (
                  <tr key={o.bill_number} className={o.status === "VOIDED" ? "row-muted" : ""}>
                    <td><button className="link-btn" onClick={() => setDetail(o)}>{o.bill_number}</button></td>
                    <td>{new Date(o.date).toLocaleString("en-IN")}</td>
                    <td>{o.customer}</td>
                    <td>{o.cashier}</td>
                    <td>{o.payment_method}</td>
                    <td><Badge tone={statusTone(o.status)}>{o.status.replace(/_/g, " ")}</Badge></td>
                    <td className="num">{o.items_count}</td>
                    <td className="num"><strong>{inr(o.grand_total)}</strong></td>
                    <td className="row-actions">
                      <Button size="sm" onClick={() => void openThermal(o.bill_number)}>Thermal</Button>
                      <Button size="sm" onClick={() => void openA4(o.bill_number)}>GST A4</Button>
                      {canManage && o.status === "COMPLETED" && (
                        <Button size="sm" variant="danger" onClick={() => setVoidTarget(o.bill_number)}>Void</Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

      {/* Receipt preview modal */}
      <Modal open={!!receiptHtml} onClose={() => setReceiptHtml(null)} title="Document Preview" width={640}>
        <div className="receipt-preview" dangerouslySetInnerHTML={{ __html: receiptHtml ?? "" }} />
        <div className="modal-actions">
          <Button variant="primary" onClick={() => window.print()}>Print</Button>
        </div>
      </Modal>

      {/* Order detail */}
      <Modal open={!!detail} onClose={() => setDetail(null)} title={`Bill ${detail?.bill_number ?? ""}`} width={520}>
        {detail && (
          <dl className="detail-list">
            <dt>Date</dt><dd>{new Date(detail.date).toLocaleString("en-IN")}</dd>
            <dt>Branch</dt><dd>{detail.branch_name}</dd>
            <dt>Cashier</dt><dd>{detail.cashier}</dd>
            <dt>Customer</dt><dd>{detail.customer}</dd>
            <dt>Items</dt><dd>{detail.items_count}</dd>
            <dt>Savings</dt><dd>{inr(detail.savings)}</dd>
            <dt>Total</dt><dd><strong>{inr(detail.grand_total)}</strong></dd>
            <dt>Status</dt><dd><Badge tone={statusTone(detail.status)}>{detail.status}</Badge></dd>
          </dl>
        )}
      </Modal>

      <ManagerPinModal open={!!voidTarget} onClose={() => setVoidTarget(null)}
        onVerified={(id) => void doVoid(id)} title={`Void ${voidTarget ?? ""}`} />
    </div>
  );
}
