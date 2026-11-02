// Multi-Branch Stores — performance cards + comparison. Manager data gated.
import React, { useCallback, useEffect, useState } from "react";
import * as api from "../api/client";
import type { Branch } from "../api/types";
import { useApp, hasRole } from "../store/appStore";
import { Badge, Button, Card, EmptyState, ErrorState, Skeleton, useToast } from "../components/ui";
import { inr } from "../lib/format";

export function BranchesPage() {
  const app = useApp();
  const { push } = useToast();
  const [branches, setBranches] = useState<Branch[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canManage = hasRole(app.user, "STORE_MANAGER");

  const load = useCallback(async () => {
    setError(null);
    try {
      const bs = await api.listBranches();
      setBranches(bs);
      app.setActiveBranchId(app.activeBranchId); // keep selection
    } catch (e) { setError(e instanceof Error ? e.message : "Failed to load branches"); }
  }, [app]);
  useEffect(() => { if (canManage) void load(); }, [canManage, load]);

  if (!canManage) return <EmptyState icon="🔒" title="Multi-branch view is for managers" hint="Ask your store manager to switch this terminal's branch context." />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (branches === null) return <Skeleton rows={4} />;

  const maxSales = Math.max(...branches.map((b) => b.today_sales ?? 0), 1);

  return (
    <div className="page-stack">
      <div className="branch-grid">
        {branches.map((b) => {
          const isActive = b.branch_id === app.activeBranchId;
          return (
            <Card key={b.branch_id} className={isActive ? "branch-active" : ""}
              title={<span>🏬 {b.name} {isActive && <Badge tone="success">CURRENT</Badge>}</span>}
              actions={!isActive && <Button size="sm" onClick={() => { app.setActiveBranchId(b.branch_id); push("success", `Switched to ${b.name}`); }}>Set Active</Button>}>
              <div className="branch-metrics">
                <div><small>TODAY SALES</small><strong>{inr(b.today_sales ?? 0, { compact: true })}</strong></div>
                <div><small>INVENTORY VALUE</small><strong>{inr(b.inventory_value ?? 0, { compact: true })}</strong></div>
                <div><small>LOW STOCK SKUS</small><strong className={(b.low_stock_items ?? 0) > 5 ? "bad" : ""}>{b.low_stock_items ?? 0}</strong></div>
                <div><small>STAFF</small><strong>{b.staff_count ?? 0}</strong></div>
              </div>
              <div className="progress-bar" aria-hidden="true">
                <div style={{ width: `${Math.round(((b.today_sales ?? 0) / maxSales) * 100)}%` }} />
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
