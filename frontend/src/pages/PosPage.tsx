// POS Billing Counter — the heart of the store. Keyboard-first, optimistic UI,
// scan feedback (sound + visual), split tender, live totals, offline queue aware.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as api from "../api/client";
import type { CartTotals, CheckoutResult, Product } from "../api/types";
import { useApp } from "../store/appStore";
import { useI18n } from "../i18n";
import { useHotkeys } from "../hooks/useHotkeys";
import { Badge, Button, EmptyState, Input, Modal, Select, useToast } from "../components/ui";
import { beep, inr, TIER_COLORS } from "../lib/format";

interface DraftLine { barcode: string; quantity: number }

const PAY_KEYS: Record<string, "CASH" | "UPI" | "CARD" | "WALLET" | "SPLIT"> = {
  F4: "CASH", F5: "UPI", F6: "CARD", F7: "WALLET", F8: "SPLIT",
};

export function PosPage() {
  const app = useApp();
  const { t } = useI18n();
  const { push } = useToast();

  // ---- catalog state ----
  const [allProducts, setAllProducts] = useState<Product[]>([]);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("ALL");
  const searchRef = useRef<HTMLInputElement>(null);

  // ---- cart state (draft items; server computes authoritative totals) ----
  const [items, setItems] = useState<DraftLine[]>([]);
  const [totals, setTotals] = useState<CartTotals | null>(null);
  const [calculating, setCalculating] = useState(false);
  const calcSeq = useRef(0);

  // ---- payment state ----
  const [payMethod, setPayMethod] = useState<"CASH" | "UPI" | "CARD" | "WALLET" | "SPLIT">("CASH");
  const [tendered, setTendered] = useState("");
  const [splitRows, setSplitRows] = useState<{ method: string; amount: number }[]>([
    { method: "CASH", amount: 0 }, { method: "UPI", amount: 0 },
  ]);
  const [pointsToRedeem, setPointsToRedeem] = useState(0);
  const [busy, setBusy] = useState(false);

  // ---- feedback / dialogs ----
  const [flash, setFlash] = useState<{ kind: "ok" | "bad"; msg: string } | null>(null);
  const [customerLookup, setCustomerLookup] = useState(false);
  const [custCode, setCustCode] = useState("");
  const [lastSale, setLastSale] = useState<(CheckoutResult & { queued?: boolean }) | null>(null);

  const flashMsg = useCallback((kind: "ok" | "bad", msg: string) => {
    setFlash({ kind, msg });
    beep(kind === "ok" ? "ok" : "error");
    setTimeout(() => setFlash(null), 1400);
  }, []);

  // ---- load catalog once ----
  useEffect(() => {
    void api.listProducts().then(setAllProducts).catch(() => push("error", "Catalog unavailable (offline?)"));
    searchRef.current?.focus();
  }, [push]);

  const categories = useMemo(
    () => ["ALL", ...Array.from(new Set(allProducts.map((p) => p.category))).sort()],
    [allProducts],
  );

  const shelf = useMemo(() => {
    const lower = query.trim().toLowerCase();
    return allProducts
      .filter((p) => category === "ALL" || p.category === category)
      .filter((p) => !lower || p.name.toLowerCase().includes(lower) || p.barcode.includes(lower) || p.brand.toLowerCase().includes(lower))
      .slice(0, 60);
  }, [allProducts, query, category]);

  // ---- debounced server-side total calculation ----
  useEffect(() => {
    if (items.length === 0) { setTotals(null); return; }
    const id = ++calcSeq.current;
    const handle = setTimeout(async () => {
      setCalculating(true);
      try {
        const res = await api.calculateCart({
          items, customer_phone: app.customer?.phone ?? null,
          points_to_redeem: pointsToRedeem, branch_id: app.activeBranchId,
        });
        if (id === calcSeq.current) setTotals(res);
      } catch (e) {
        if (id === calcSeq.current) push("error", e instanceof Error ? e.message : "Cart calculation failed");
      } finally {
        if (id === calcSeq.current) setCalculating(false);
      }
    }, 220);
    return () => clearTimeout(handle);
  }, [items, app.customer, pointsToRedeem, app.activeBranchId, push]);

  // ---- cart mutations ----
  const addItem = useCallback((barcode: string, qty = 1) => {
    const prod = allProducts.find((p) => p.barcode === barcode);
    if (!prod) { flashMsg("bad", `Unknown barcode ${barcode}`); return false; }
    setItems((prev) => {
      const existing = prev.find((l) => l.barcode === barcode);
      const nextQty = (existing?.quantity ?? 0) + qty;
      if (nextQty > prod.stock_quantity) { flashMsg("bad", `${prod.name}: only ${prod.stock_quantity} in stock`); return prev; }
      flashMsg("ok", prod.name);
      return existing
        ? prev.map((l) => (l.barcode === barcode ? { ...l, quantity: nextQty } : l))
        : [...prev, { barcode, quantity: qty }];
    });
    return true;
  }, [allProducts, flashMsg]);

  const changeQty = useCallback((barcode: string, delta: number) => {
    setItems((prev) => prev
      .map((l) => (l.barcode === barcode ? { ...l, quantity: l.quantity + delta } : l))
      .filter((l) => l.quantity > 0));
  }, []);

  const removeItem = useCallback((barcode: string) => {
    setItems((prev) => prev.filter((l) => l.barcode !== barcode));
  }, []);

  const clearCart = useCallback(() => {
    setItems([]); setTotals(null); setTendered(""); setPointsToRedeem(0); setPayMethod("CASH");
    app.setCustomer(null);
  }, [app]);

  // ---- barcode wedge handling: Enter in search box adds exact barcode match ----
  const onSearchEnter = async () => {
    const raw = query.trim();
    if (!raw) return;
    const exact = allProducts.find((p) => p.barcode === raw);
    if (exact) { addItem(exact.barcode); setQuery(""); return; }
    // Membership QR / phone code?
    if (/^\d{6,15}$/.test(raw)) {
      try {
        const cust = await api.recognizeCustomer(raw);
        if (cust) { app.setCustomer(cust); setCustCode(""); flashMsg("ok", `Welcome ${cust.name}`); setQuery(""); return; }
      } catch { /* fall through */ }
    }
    if (shelf.length === 1) { addItem(shelf[0].barcode); setQuery(""); }
    else flashMsg("bad", shelf.length === 0 ? "No product found" : "Multiple matches — click one");
  };

  // ---- checkout ----
  const doCheckout = useCallback(async () => {
    if (!totals || items.length === 0 || busy) return;
    const grand = totals.grand_total;
    let tenderAmt = parseFloat(tendered) || 0;
    let splits: { method: string; amount: number }[] | null = null;
    if (payMethod === "SPLIT") {
      splits = splitRows.filter((s) => s.amount > 0);
      tenderAmt = splits.reduce((a, s) => a + s.amount, 0);
      if (Math.abs(tenderAmt - grand) >= 0.05 && splits.every(s => s.method !== "CASH")) {
        push("error", "Split tenders must cover the grand total"); return;
      }
    } else if (payMethod === "CASH") {
      if (tenderAmt < grand) { push("error", "Tendered cash is less than the bill"); return; }
    } else {
      tenderAmt = grand; // digital rails settle exact
    }
    setBusy(true);
    try {
      const res = await api.checkout({
        items,
        payment_method: payMethod,
        tendered_amount: tenderAmt,
        cashier_id: app.user?.id ?? "CASHIER-01",
        cashier_name: app.user?.name ?? "Cashier",
        customer_phone: app.customer?.phone ?? null,
        customer_name: app.customer?.name ?? null,
        points_to_redeem: pointsToRedeem,
        split_payments: splits,
        branch_id: app.activeBranchId,
      });
      if (res.queued) push("info", "Offline — sale queued and will sync automatically");
      else { setLastSale(res); push("success", `Bill ${res.bill_number} · ${inr(res.grand_total)}`); }
      clearCart();
    } catch (e) {
      push("error", e instanceof Error ? e.message : "Checkout failed");
    } finally { setBusy(false); }
  }, [totals, items, busy, payMethod, tendered, splitRows, app, pointsToRedeem, clearCart, push]);

  // ---- keyboard shortcuts ----
  useHotkeys(useMemo(() => ({
    F2: (e: KeyboardEvent) => { e.preventDefault(); searchRef.current?.focus(); searchRef.current?.select(); },
    F3: (e: KeyboardEvent) => { e.preventDefault(); setCustomerLookup(true); },
    F9: (e: KeyboardEvent) => { e.preventDefault(); void doCheckout(); },
    Escape: () => { setCustomerLookup(false); setLastSale(null); },
    Delete: () => { if (items.length && document.activeElement === document.body) removeItem(items[items.length - 1].barcode); },
  }), [doCheckout, items, removeItem]), [doCheckout, items]);

  const maxRedeemable = app.customer
    ? Math.min(app.customer.loyalty_points, Math.floor((totals?.subtotal ?? 0) / 0.5))
    : 0;

  const changeDue = payMethod === "CASH" ? Math.max(0, (parseFloat(tendered) || 0) - (totals?.grand_total ?? 0)) : 0;

  return (
    <div className="pos-grid">
      {/* ---------- LEFT: catalog ---------- */}
      <section className="pos-catalog" aria-label="Product catalog">
        <div className="pos-searchbar">
          <Input
            ref={searchRef}
            className="pos-search-input"
            placeholder={t("pos.search")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void onSearchEnter()}
            aria-label="Scan barcode or search products"
            autoComplete="off"
          />
          <kbd className="hotkey-hint">F2</kbd>
        </div>
        <div className="chip-row" role="tablist" aria-label="Categories">
          {categories.slice(0, 14).map((c) => (
            <button key={c} role="tab" aria-selected={category === c}
              className={`chip ${category === c ? "chip-active" : ""}`}
              onClick={() => setCategory(c)}>
              {c === "ALL" ? "All" : c}
            </button>
          ))}
        </div>
        <div className="shelf-grid">
          {shelf.length === 0
            ? <EmptyState icon="🔍" title="Nothing found" hint="Try another barcode prefix, brand, or category." />
            : shelf.map((p) => (
              <button key={p.barcode} className={`shelf-item ${p.is_out_of_stock ? "oos" : ""}`}
                onClick={() => addItem(p.barcode)} disabled={p.is_out_of_stock}
                title={`${p.name} · ${p.barcode}`}>
                <span className="shelf-name">{p.name}</span>
                <span className="shelf-meta">
                  <span className="num">{inr(p.selling_price)}</span>
                  <Badge tone={p.is_out_of_stock ? "danger" : p.is_low_stock ? "warning" : "neutral"}>
                    {p.is_out_of_stock ? "OUT" : `${fmtStock(p.stock_quantity)} left`}
                  </Badge>
                </span>
                <span className="shelf-tax muted">{p.tax_rate_percent}% GST</span>
              </button>
            ))}
        </div>
        {flash && <div className={`scan-flash scan-${flash.kind}`} role="status">{flash.kind === "ok" ? "✓ " : "✕ "}{flash.msg}</div>}
      </section>

      {/* ---------- RIGHT: customer + cart + payment ---------- */}
      <section className="pos-right" aria-label="Current sale">
        {/* Customer card */}
        {app.customer ? (
          <div className="cust-card" style={{ borderLeftColor: TIER_COLORS[app.customer.tier] }}>
            <div className="cust-avatar" aria-hidden="true">{app.customer.name.slice(0, 1)}</div>
            <div className="cust-info">
              <strong>{app.customer.name}</strong>
              <small>{app.customer.phone} · <span style={{ color: TIER_COLORS[app.customer.tier] }}>{app.customer.tier}</span></small>
              <div className="cust-stats">
                <span title="Loyalty points">★ {app.customer.loyalty_points}</span>
                <span title="Lifetime value">{inr(app.customer.lifetime_value, { compact: true })}</span>
                <span title="Visits">{app.customer.visit_count} visits</span>
              </div>
            </div>
            <div className="row-actions">
              {maxRedeemable > 0 && (
                <Button size="sm" variant={pointsToRedeem > 0 ? "primary" : "ghost"}
                  onClick={() => setPointsToRedeem(pointsToRedeem > 0 ? 0 : maxRedeemable)}>
                  {pointsToRedeem > 0 ? `Redeem ${pointsToRedeem} pts (-${inr(pointsToRedeem * 0.5)})` : t("pos.redeem")}
                </Button>
              )}
              <Button size="sm" variant="ghost" onClick={() => { app.setCustomer(null); setPointsToRedeem(0); }}>✕</Button>
            </div>
          </div>
        ) : (
          <button className="cust-card cust-empty" onClick={() => setCustomerLookup(true)}>
            👤 {t("pos.walkin")} — <u>F3</u> to identify member
          </button>
        )}

        {/* Cart */}
        <div className="card pos-cart">
          <header className="card-head">
            <h3>{t("pos.cart")} {totals && <span className="muted">· {totals.items_count} items</span>}</h3>
            {items.length > 0 && <Button size="sm" variant="ghost" onClick={clearCart}>Clear</Button>}
          </header>
          <div className="card-body pos-cart-body">
            {items.length === 0 ? (
              <EmptyState icon="🧺" title={t("pos.emptyCart")} hint="Every second counts at the counter — scan, click, or press F2." />
            ) : (
              <table className="data-table cart-table">
                <thead><tr><th>Item</th><th className="num">Price</th><th>Qty</th><th className="num">Total</th><th /></tr></thead>
                <tbody>
                  {(totals?.items ?? []).map((l) => (
                    <tr key={l.barcode}>
                      <td>
                        <span className="cart-item-name">{l.name}</span>
                        {l.is_low_stock && <Badge tone="warning">LOW</Badge>}
                      </td>
                      <td className="num">{inr(l.unit_price)}</td>
                      <td>
                        <span className="qty-stepper">
                          <button className="icon-btn" onClick={() => changeQty(l.barcode, -1)} aria-label="Decrease quantity">−</button>
                          <span className="num qty-val">{l.quantity}</span>
                          <button className="icon-btn" onClick={() => changeQty(l.barcode, 1)} aria-label="Increase quantity">+</button>
                        </span>
                      </td>
                      <td className="num"><strong>{inr(l.total)}</strong></td>
                      <td><button className="icon-btn" onClick={() => removeItem(l.barcode)} aria-label="Remove item">🗑</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Totals */}
          {totals && (
            <div className="pos-totals" aria-live="polite">
              <div className="tot-row"><span>{t("pos.subtotal")}</span><span className="num">{inr(totals.subtotal)}</span></div>
              {totals.total_savings > 0 && <div className="tot-row good"><span>{t("pos.savings")}</span><span className="num">−{inr(totals.total_savings)}</span></div>}
              {totals.order_discount > 0 && <div className="tot-row good"><span>{t("pos.discount")} ({totals.customer_tier})</span><span className="num">−{inr(totals.order_discount)}</span></div>}
              {totals.points_discount > 0 && <div className="tot-row good"><span>Points ({totals.points_redeemed})</span><span className="num">−{inr(totals.points_discount)}</span></div>}
              <div className="tot-row"><span>{t("pos.tax")}</span><span className="num">{inr(totals.total_tax)} <small className="muted">(C {inr(totals.cgst)} + S {inr(totals.sgst)})</small></span></div>
              <div className="tot-row row-total"><span>{t("pos.total")}</span><span className="num">{calculating ? "…" : inr(totals.grand_total)}</span></div>
            </div>
          )}

          {/* Payment panel */}
          <div className="pos-payment">
            <div className="segmented" role="radiogroup" aria-label="Payment method">
              {(["CASH", "UPI", "CARD", "WALLET", "SPLIT"] as const).map((m) => (
                <button key={m} role="radio" aria-checked={payMethod === m}
                  className={payMethod === m ? "seg-active" : ""}
                  onClick={() => setPayMethod(m)}>
                  {m === "CASH" ? "💵" : m === "UPI" ? "📱" : m === "CARD" ? "💳" : m === "WALLET" ? "👛" : "✂️"} {t(`pay.${m.toLowerCase()}`)}
                  <kbd>{Object.keys(PAY_KEYS)[["CASH","UPI","CARD","WALLET","SPLIT"].indexOf(m)]}</kbd>
                </button>
              ))}
            </div>

            {payMethod === "CASH" && (
              <div className="inline-form">
                <label htmlFor="tender">{t("pos.tender")}</label>
                <Input id="tender" type="number" inputMode="decimal" min={0} value={tendered}
                  onChange={(e) => setTendered(e.target.value)} placeholder="0.00" />
                <div className="quick-cash">
                  {[totals?.grand_total ?? 0, 100, 200, 500, 1000, 2000].map((v, i) => (
                    <button key={i} className="chip" onClick={() => setTendered(String(i === 0 ? Math.ceil(v) : v))}>{i === 0 ? "Exact" : inr(v)}</button>
                  ))}
                </div>
                {changeDue > 0 && <div className="change-due" role="status">{t("pos.change")}: <strong>{inr(changeDue)}</strong></div>}
              </div>
            )}

            {payMethod === "SPLIT" && (
              <div className="split-editor">
                {splitRows.map((s, i) => (
                  <div key={i} className="inline-form">
                    <Select value={s.method} aria-label={`Split ${i + 1} method`}
                      onChange={(e) => setSplitRows(splitRows.map((r, j) => (j === i ? { ...r, method: e.target.value } : r)))}>
                      {["CASH", "UPI", "CARD", "WALLET"].map((m) => <option key={m}>{m}</option>)}
                    </Select>
                    <Input type="number" min={0} aria-label={`Split ${i + 1} amount`} value={s.amount || ""}
                      onChange={(e) => setSplitRows(splitRows.map((r, j) => (j === i ? { ...r, amount: parseFloat(e.target.value) || 0 } : r)))} />
                  </div>
                ))}
                <div className="tot-row"><span>Allocated</span><span className="num">{inr(splitRows.reduce((a, s) => a + s.amount, 0))} / {inr(totals?.grand_total ?? 0)}</span></div>
              </div>
            )}

            {(payMethod === "UPI" || payMethod === "CARD" || payMethod === "WALLET") && (
              <p className="muted pay-note">
                {payMethod === "UPI" ? "Generating UPI collect request… customer scans QR or approves intent on phone."
                  : payMethod === "CARD" ? "Swipe/tap on the Pinelabs terminal. Settlement reconciles automatically."
                  : "Wallet debit via linked PSP — confirm OTP on device."}
              </p>
            )}

            <Button variant="primary" size="lg" className="checkout-btn" loading={busy}
              disabled={!totals || items.length === 0} onClick={() => void doCheckout()}>
              {t("pos.checkout")} <kbd>F9</kbd> {totals && `— ${inr(totals.grand_total)}`}
            </Button>
            {!app.online && <p className="offline-note">⚠ Offline mode: sales are queued locally and synced when connectivity returns.</p>}
          </div>
        </div>
      </section>

      {/* ---------- Customer lookup modal ---------- */}
      <Modal open={customerLookup} onClose={() => setCustomerLookup(false)} title={t("pos.customer")} width={420}>
        <label htmlFor="cust-code">Phone / membership code / QR</label>
        <Input id="cust-code" autoFocus inputMode="numeric" maxLength={15} value={custCode}
          onChange={(e) => setCustCode(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void (async () => {
            try {
              const c = await api.recognizeCustomer(custCode.trim());
              if (c) { app.setCustomer(c); setCustomerLookup(false); setCustCode(""); push("success", `Welcome back, ${c.name}`); }
              else push("error", "No member found for that code");
            } catch (e2) { push("error", e2 instanceof Error ? e2.message : "Lookup failed"); }
          })()} />
        <p className="muted">Tip: press F3 anywhere, or scan a membership QR straight into the search box.</p>
      </Modal>

      {/* ---------- Success dialog with receipt actions ---------- */}
      <Modal open={!!lastSale} onClose={() => setLastSale(null)} title="Sale Complete ✓" width={480}>
        {lastSale && (
          <div className="sale-done">
            <div className="done-bill mono">{lastSale.bill_number}</div>
            <div className="done-total num">{inr(lastSale.grand_total)}</div>
            <div className="detail-list">
              <span>Payment</span><b>{lastSale.payment_method}</b>
              <span>Tendered</span><b>{inr(lastSale.tendered_amount)}</b>
              {lastSale.change_amount > 0 && <><span>Change</span><b className="good">{inr(lastSale.change_amount)}</b></>}
              <span>Points earned</span><b>★ {lastSale.points_earned}</b>
            </div>
            <div className="modal-actions">
              <Button onClick={() => window.print()} variant="secondary">🖨 Thermal 80mm</Button>
              <Button onClick={() => { void api.getA4Invoice(lastSale.bill_number).then((r) => { const w = window.open("", "_blank"); if (w) { w.document.write(r.html); w.document.close(); w.print(); } }); }} variant="secondary">A4 GST Invoice</Button>
              <Button variant="primary" onClick={() => setLastSale(null)}>New Sale</Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

function fmtStock(n: number): string { return Number.isInteger(n) ? String(n) : n.toFixed(2); }
