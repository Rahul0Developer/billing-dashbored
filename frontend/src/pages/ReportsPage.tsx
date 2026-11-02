// Data Exports — CSV report center + catalog import (manager/admin).
import React, { useState } from "react";
import { Card, Button, useToast } from "../components/ui";
import * as api from "../api/client";

const REPORTS = [
  { key: "sales", label: "Sales Register", desc: "Every invoice with payment mode & status", file: "sales.csv" },
  { key: "inventory", label: "Inventory Valuation", desc: "Stock, cost value and retail value per SKU", file: "inventory.csv" },
  { key: "customers", label: "Customer Directory", desc: "Members, tiers, points and lifetime value", file: "customers.csv" },
  { key: "expenses", label: "Expense Ledger", desc: "Operational expenses by category", file: "expenses.csv" },
];

export function ReportsPage() {
  const { push } = useToast();
  const [csv, setCsv] = useState("");
  const [importing, setImporting] = useState(false);

  const doImport = async () => {
    if (!csv.trim()) { push("error", "Paste CSV content first"); return; }
    setImporting(true);
    try {
      const res = await fetch("/api/reports/import/products", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(api.auth.token ? { Authorization: `Bearer ${api.auth.token}` } : {}) },
        body: JSON.stringify({ csv_content: csv }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(String(data.detail ?? `Import failed (${res.status})`));
      push("success", "Catalog imported — products re-indexed.");
      setCsv("");
    } catch (e) { push("error", e instanceof Error ? e.message : "Import failed"); }
    finally { setImporting(false); }
  };

  return (
    <div className="page-stack">
      <Card title="Report Center — scheduled exports">
        <div className="export-grid">
          {REPORTS.map((r) => (
            <div key={r.key} className="export-card">
              <strong>📊 {r.label}</strong>
              <span className="muted">{r.desc}</span>
              <Button variant="primary" size="sm" onClick={() => { api.downloadUrl(`/api/reports/export/${r.key}`, r.file); push("info", `Downloading ${r.file}`); }}>
                ⬇ Download CSV
              </Button>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Bulk Catalog Import (CSV)">
        <p className="muted">Header row required: barcode,sku,name,category,brand,unit,cost_price,selling_price,mrp,tax_rate_percent,stock_quantity</p>
        <textarea className="field csv-area" rows={7} value={csv} onChange={(e) => setCsv(e.target.value)}
          placeholder="8901034567890,SKU-001,Tata Salt 1kg,Tata Groceries,Food,Pack,24,28,30,5,120" />
        <div className="modal-actions">
          <Button variant="primary" loading={importing} onClick={() => void doImport()}>Import Products</Button>
        </div>
      </Card>
    </div>
  );
}
