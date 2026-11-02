// Inventory & Catalog — grid with stock colors, adjustments with reason tracking, transfers.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import * as api from "../api/client";
import type { Branch, Product } from "../api/types";
import { useApp, hasRole } from "../store/appStore";
import { Badge, Button, Card, EmptyState, ErrorState, Input, Modal, Select, Skeleton, useToast } from "../components/ui";
import { inr, fmtQty } from "../lib/format";

const ADJUST_REASONS = ["STOCK_COUNT_CORRECTION", "DAMAGE_LOSS", "THEFT_LOSS", "GOODS_RECEIVED", "RETURN_TO_SUPPLIER", "INTER_BRANCH_TRANSFER"];

export function InventoryPage() {
  const app = useApp();
  const { push } = useToast();
  const [products, setProducts] = useState<Product[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [stockFilter, setStockFilter] = useState("ALL");
  const [adjustTarget, setAdjustTarget] = useState<Product | null>(null);
  const [adjQty, setAdjQty] = useState("");
  const [adjReason, setAdjReason] = useState(ADJUST_REASONS[0]);
  const [transferOpen, setTransferOpen] = useState(false);
  const [branches, setBranches] = useState<Branch[]>([]);
  const canManageInv = hasRole(app.user, "INVENTORY_MANAGER");

  const load = useCallback(async () => {
    setError(null);
    try { setProducts(await api.listProducts()); }
    catch (e) { setError(e instanceof Error ? e.message : "Failed to load inventory"); }
  }, []);
  useEffect(() => {
    void load();
    void api.listBranches().then(setBranches).catch(() => undefined);
  }, [load]);

  const filtered = useMemo(() => {
    if (!products) return [];
    const lower = q.toLowerCase();
    return products.filter((p) =>
      (stockFilter === "ALL" ||
        (stockFilter === "LOW" && p.is_low_stock && !p.is_out_of_stock) ||
        (stockFilter === "OUT" && p.is_out_of_stock)) &&
      (!lower || p.name.toLowerCase().includes(lower) || p.barcode.includes(lower) || p.category.toLowerCase().includes(lower)),
    );
  }, [products, q, stockFilter]);

  const submitAdjust = async () => {
    if (!adjustTarget || !adjQty) return;
    try {
      await api.adjustStock(adjustTarget.barcode, Number(adjQty), adjReason, app.activeBranchId);
      push("success", `Adjusted ${adjustTarget.name} by ${adjQty}`);
      setAdjustTarget(null); setAdjQty("");
      void load();
    } catch (e) { push("error", e instanceof Error ? e.message : "Adjustment failed"); }
  };

  return (
    <div className="page-stack">
      <div className="toolbar">
        <Input placeholder="Search product, barcode, category…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search inventory" />
        <Select value={stockFilter} onChange={(e) => setStockFilter(e.target.value)} aria-label="Stock filter">
          {["ALL", "LOW", "OUT"].map((s) => <option key={s} value={s}>{s === "ALL" ? "All stock states" : s === "LOW" ? "Low stock" : "Out of stock"}</option>)}
        </Select>
        {canManageInv && <Button onClick={() => setTransferOpen(true)}>🔁 Inter-Branch Transfer</Button>}
        <Button onClick={() => api.downloadUrl("/api/reports/export/inventory", "inventory.csv")}>⬇ CSV</Button>
      </div>

      {error ? <ErrorState message={error} onRetry={load} />
        : products === null ? <Skeleton rows={8} />
        : filtered.length === 0 ? <EmptyState icon="📦" title="No products match" hint="Clear filters or import a catalog via Data Exports." />
        : (
          <div className="inv-grid">
            {filtered.slice(0, 120).map((p) => (
              <div key={p.barcode} className={`inv-card ${p.is_out_of_stock ? "out" : p.is_low_stock ? "low" : ""}`}>
                <div className="inv-head">
                  <strong>{p.name}</strong>
                  <Badge tone={p.is_out_of_stock ? "danger" : p.is_low_stock ? "warning" : "success"}>
                    {p.is_out_of_stock ? "OUT" : p.is_low_stock ? "LOW" : "OK"}
                  </Badge>
                </div>
                <div className="inv-meta muted">{p.category} · {p.brand} · {p.tax_rate_percent}% GST</div>
                <div className="inv-numbers">
                  <span className="mono">{p.barcode}</span>
                  <span className="num"><strong>{fmtQty(p.stock_quantity)}</strong> {p.unit}</span>
                  <span className="num">{inr(p.selling_price)} <s className="muted">{inr(p.mrp)}</s></span>
                </div>
                {canManageInv && (
                  <div className="inv-actions">
                    <Button size="sm" onClick={() => setAdjustTarget(p)}>± Adjust</Button>
                    <Button size="sm" variant="ghost" onClick={() => window.print()}>🏷 Shelf Label</Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

      <Modal open={!!adjustTarget} onClose={() => setAdjustTarget(null)} title={`Stock Adjustment — ${adjustTarget?.name ?? ""}`} width={440}>
        <p className="muted">Current stock: <strong>{fmtQty(adjustTarget?.stock_quantity ?? 0)}</strong> {adjustTarget?.unit}. Positive = received, negative = write-off. Reason is audit-logged.</p>
        <label htmlFor="adj-qty">Quantity Change</label>
        <Input id="adj-qty" type="number" step="0.001" autoFocus value={adjQty} onChange={(e) => setAdjQty(e.target.value)} placeholder="+10 or -2" />
        <label htmlFor="adj-reason">Reason</label>
        <Select id="adj-reason" value={adjReason} onChange={(e) => setAdjReason(e.target.value)}>
          {ADJUST_REASONS.map((r) => <option key={r}>{r}</option>)}
        </Select>
        <div className="modal-actions">
          <Button onClick={() => setAdjustTarget(null)}>Cancel</Button>
          <Button variant="primary" disabled={!adjQty} onClick={() => void submitAdjust()}>Apply Adjustment</Button>
        </div>
      </Modal>

      <TransferModal open={transferOpen} onClose={() => setTransferOpen(false)} branches={branches} products={products ?? []} onDone={load} />
    </div>
  );
}

function TransferModal({ open, onClose, branches, products, onDone }: {
  open: boolean; onClose: () => void; branches: Branch[]; products: Product[]; onDone: () => void;
}) {
  const { push } = useToast();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [barcode, setBarcode] = useState("");
  const [qty, setQty] = useState("");
  const submit = async () => {
    try {
      await api.transferStock(from, to, barcode, Number(qty));
      push("success", "Transfer initiated");
      onClose(); onDone();
    } catch (e) { push("error", e instanceof Error ? e.message : "Transfer failed"); }
  };
  return (
    <Modal open={open} onClose={onClose} title="Inter-Branch Stock Transfer" width={480}>
      <Card>
        <label>From branch</label>
        <Select value={from} onChange={(e) => setFrom(e.target.value)}>
          <option value="">Select…</option>
          {branches.map((b) => <option key={b.branch_id} value={b.branch_id}>{b.name}</option>)}
        </Select>
        <label>To branch</label>
        <Select value={to} onChange={(e) => setTo(e.target.value)}>
          <option value="">Select…</option>
          {branches.map((b) => <option key={b.branch_id} value={b.branch_id}>{b.name}</option>)}
        </Select>
        <label>Product barcode</label>
        <Select value={barcode} onChange={(e) => setBarcode(e.target.value)}>
          <option value="">Select product…</option>
          {products.map((p) => <option key={p.barcode} value={p.barcode}>{p.name} ({p.barcode})</option>)}
        </Select>
        <label>Quantity</label>
        <Input type="number" min={0.001} step="0.001" value={qty} onChange={(e) => setQty(e.target.value)} />
        <div className="modal-actions">
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={!from || !to || !barcode || !qty} onClick={() => void submit()}>Initiate Transfer</Button>
        </div>
      </Card>
    </Modal>
  );
}
