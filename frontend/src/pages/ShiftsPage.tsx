// Cash Register Shifts & Z-Report — open/close drawer, cash drops, variance.
import React, { useCallback, useEffect, useState } from "react";
import * as api from "../api/client";
import type { ShiftInfo, ZReport } from "../api/types";
import { useApp } from "../store/appStore";
import { Badge, Button, Card, EmptyState, ErrorState, Input, KpiCard, Modal, Skeleton, useToast } from "../components/ui";
import { inr } from "../lib/format";

export function ShiftsPage() {
  const app = useApp();
  const { push } = useToast();
  const [shift, setShift] = useState<ShiftInfo | null | "loading">("loading");
  const [error, setError] = useState<string | null>(null);
  const [openFloat, setOpenFloat] = useState("2000");
  const [dropAmt, setDropAmt] = useState("");
  const [closeOpen, setCloseOpen] = useState(false);
  const [counted, setCounted] = useState("");
  const [reason, setReason] = useState("");
  const [zreport, setZreport] = useState<ZReport | null>(null);
  const [history, setHistory] = useState<Record<string, unknown>[] | null>(null);

  const load = useCallback(async () => {
    if (!app.user) return;
    setError(null);
    try {
      const s = await api.currentShift(app.user.id);
      setShift((s as ShiftInfo).shift_id ? s as ShiftInfo : null);
      setHistory(await api.shiftHistory().catch(() => null));
    } catch (e) { setError(e instanceof Error ? e.message : "Failed to load shift"); setShift(null); }
  }, [app.user]);
  useEffect(() => { void load(); }, [load]);

  const start = async () => {
    try {
      const s = await api.startShift(Number(openFloat) || 0, app.activeBranchId);
      setShift(s); push("success", "Shift opened — drawer ready.");
      void load();
    } catch (e) { push("error", e instanceof Error ? e.message : "Could not open shift"); }
  };
  const drop = async () => {
    try { await api.cashDrop(Number(dropAmt)); push("success", `Cash drop of ${inr(Number(dropAmt))} recorded.`); setDropAmt(""); void load(); }
    catch (e) { push("error", e instanceof Error ? e.message : "Drop failed"); }
  };
  const close = async () => {
    try {
      const z = await api.closeShift(Number(counted), reason || "No variance explanation provided");
      setZreport(z); setCloseOpen(false); setShift(null); push("success", "Z-Report generated."); void load();
    } catch (e) { push("error", e instanceof Error ? e.message : "Close failed"); }
  };

  if (shift === "loading") return <Skeleton rows={6} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="page-stack">
      {!shift ? (
        <Card title="Open New Shift">
          <EmptyState icon="🗄️" title="No active register shift" hint="Count the opening float and open your drawer to start billing." />
          <label htmlFor="float">Opening Cash Float (₹)</label>
          <div className="inline-form">
            <Input id="float" type="number" min={0} value={openFloat} onChange={(e) => setOpenFloat(e.target.value)} />
            <Button variant="primary" onClick={() => void start()}>Open Shift</Button>
          </div>
        </Card>
      ) : (
        <>
          <div className="kpi-grid">
            <KpiCard label="Started At" value={new Date(shift.started_at).toLocaleTimeString("en-IN")} tone="info" />
            <KpiCard label="Bills This Shift" value={String(shift.sales_count ?? 0)} tone="success" />
            <KpiCard label="Expected Cash In Drawer" value={inr(shift.expected_cash)} tone="gold" />
            <KpiCard label="Opening Float" value={inr(shift.opening_float)} tone="neutral" />
          </div>
          <Card title="Cash Operations">
            <div className="inline-form">
              <Input placeholder="Drop amount ₹" type="number" min={1} value={dropAmt} onChange={(e) => setDropAmt(e.target.value)} aria-label="Cash drop amount" />
              <Button onClick={() => void drop()}>💰 Safe Drop</Button>
              <span className="spacer" />
              <Button variant="danger" onClick={() => setCloseOpen(true)}>End Shift &amp; Generate Z-Report</Button>
            </div>
          </Card>
        </>
      )}

      {history && history.length > 0 && (
        <Card title="Historical Shifts">
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Cashier</th><th>Opened</th><th>Closed</th><th className="num">Net Sales</th><th className="num">Variance</th></tr></thead>
              <tbody>
                {history.slice(0, 30).map((h, i) => (
                  <tr key={i}>
                    <td>{String(h.cashier_name ?? "")}</td>
                    <td>{h.started_at ? new Date(String(h.started_at)).toLocaleString("en-IN") : "—"}</td>
                    <td>{h.closed_at ? new Date(String(h.closed_at)).toLocaleString("en-IN") : <Badge tone="success">ACTIVE</Badge>}</td>
                    <td className="num">{inr(Number(h.net_sales ?? h.gross_sales ?? 0))}</td>
                    <td className={`num ${Number(h.variance ?? 0) !== 0 ? "bad" : "good"}`}>{inr(Number(h.variance ?? 0))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Modal open={closeOpen} onClose={() => setCloseOpen(false)} title="Close Shift — Counted Cash" width={440}>
        {shift && (
          <>
            <p className="muted">System expects <strong>{inr(shift.expected_cash)}</strong> in the drawer.</p>
            <label htmlFor="counted">Counted Amount (₹)</label>
            <Input id="counted" type="number" min={0} autoFocus value={counted} onChange={(e) => setCounted(e.target.value)} />
            <label htmlFor="variance-reason">Variance Explanation</label>
            <Input id="variance-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. short ₹120 — coin exchange given to customer" />
            <div className="modal-actions">
              <Button onClick={() => setCloseOpen(false)}>Back</Button>
              <Button variant="primary" loading={!counted} disabled={!counted} onClick={() => void close()}>Generate Z-Report</Button>
            </div>
          </>
        )}
      </Modal>

      <Modal open={!!zreport} onClose={() => setZreport(null)} title={`Z-Report — ${zreport?.cashier_name ?? ""}`} width={560}>
        {zreport && (
          <dl className="detail-list">
            <dt>Gross Sales</dt><dd>{inr(zreport.gross_sales)}</dd>
            <dt>Refunds</dt><dd className="bad">− {inr(zreport.total_refunds)}</dd>
            <dt>Net Sales</dt><dd><strong>{inr(zreport.net_sales)}</strong></dd>
            <dt>Cash / UPI / Card</dt><dd>{inr(zreport.cash_sales)} · {inr(zreport.upi_sales)} · {inr(zreport.card_sales)}</dd>
            <dt>Safe Drops</dt><dd>{inr(zreport.safe_drops)}</dd>
            <dt>Expected Cash</dt><dd>{inr(zreport.expected_cash)}</dd>
            <dt>Counted Cash</dt><dd>{inr(zreport.counted_cash)}</dd>
            <dt>Variance</dt>
            <dd className={Math.abs(zreport.variance) < 0.005 ? "good" : "bad"}>
              <strong>{inr(zreport.variance)}</strong> {Math.abs(zreport.variance) >= 100 && <Badge tone="danger">REVIEW</Badge>}
            </dd>
          </dl>
        )}
      </Modal>
    </div>
  );
}
