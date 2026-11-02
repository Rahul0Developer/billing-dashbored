// Staff management + immutable audit trail (admin only).
import React, { useCallback, useEffect, useState } from "react";
import * as api from "../api/client";
import type { AuditLogEntry, UserRole } from "../api/types";
import { useApp, hasRole } from "../store/appStore";
import { Badge, Button, Card, EmptyState, ErrorState, Input, Select, Skeleton, useToast } from "../components/ui";
import { timeAgo } from "../lib/format";

interface StaffUser { id: string; name: string; username: string; role: UserRole; branch_id: string; is_active: boolean }

export function UsersPage() {
  const app = useApp();
  const { push } = useToast();
  const isAdmin = hasRole(app.user, "ADMIN");
  const [users, setUsers] = useState<StaffUser[] | null>(null);
  const [logs, setLogs] = useState<AuditLogEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", username: "", pin: "", role: "CASHIER" as UserRole, branch_id: "BR-DEL-01" });

  const load = useCallback(async () => {
    setError(null);
    try {
      const [u, l] = await Promise.all([api.listUsers(), api.listAuditLogs(80)]);
      setUsers(u); setLogs(l);
    } catch (e) { setError(e instanceof Error ? e.message : "Failed to load staff data"); }
  }, []);
  useEffect(() => { if (isAdmin) void load(); }, [isAdmin, load]);

  if (!isAdmin) return <EmptyState icon="🛡️" title="Admin-only area" hint="Staff accounts and the audit trail are visible to HQ administrators." />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (users === null) return <Skeleton rows={6} />;

  return (
    <div className="page-stack">
      <div className="two-col">
        <Card title={`Staff Accounts (${users.length})`}>
          <table className="mini-table">
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td><strong>{u.name}</strong><br /><small className="muted">@{u.username}</small></td>
                  <td><Badge tone={u.role === "ADMIN" ? "danger" : u.role === "STORE_MANAGER" ? "gold" : "info"}>{u.role}</Badge></td>
                  <td className="mono">{u.branch_id}</td>
                  <td><Badge tone={u.is_active ? "success" : "neutral"}>{u.is_active ? "ACTIVE" : "DISABLED"}</Badge></td>
                  <td><Button size="sm" variant="ghost" onClick={async () => {
                    try { await api.setUserStatus(u.id, !u.is_active); push("success", `${u.name} ${u.is_active ? "disabled" : "enabled"}`); void load(); }
                    catch (e) { push("error", e instanceof Error ? e.message : "Failed"); }
                  }}>{u.is_active ? "Disable" : "Enable"}</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card title="Add Staff Member">
          <label>Name</label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <label>Username</label><Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
          <label>PIN (numeric)</label><Input type="password" inputMode="numeric" maxLength={8} value={form.pin} onChange={(e) => setForm({ ...form, pin: e.target.value })} />
          <label>Role</label>
          <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}>
            {(["CASHIER", "INVENTORY_MANAGER", "STORE_MANAGER", "ADMIN"] as UserRole[]).map((r) => <option key={r}>{r}</option>)}
          </Select>
          <label>Branch</label>
          <Select value={form.branch_id} onChange={(e) => setForm({ ...form, branch_id: e.target.value })}>
            {(app.branches.length ? app.branches : [{ branch_id: "BR-DEL-01", name: "Apex Main Store" }] ).map((b) => <option key={b.branch_id} value={b.branch_id}>{b.name}</option>)}
          </Select>
          <div className="modal-actions">
            <Button variant="primary" disabled={!form.name || !form.username || !form.pin} onClick={async () => {
              try { await api.createUser(form); push("success", `${form.name} created`); void load(); }
              catch (e) { push("error", e instanceof Error ? e.message : "Create failed"); }
            }}>Create Account</Button>
          </div>
        </Card>
      </div>

      <Card title="Audit Trail — immutable, last 80 events">
        {logs === null ? <Skeleton rows={4} /> : logs.length === 0 ? <EmptyState icon="🛡️" title="No audit events yet" /> : (
          <ul className="audit-list">
            {logs.map((l, i) => (
              <li key={String(l.id ?? i)}>
                <Badge tone={/VOID|DELETE|DISABLE|ADJUST/i.test(String(l.action)) ? "warning" : "neutral"}>{String(l.action)}</Badge>
                <span className="audit-text">{String(l.actor_name ?? l.actor_id)} → {String(l.entity)}: {String(l.details)}</span>
                <time className="muted">{timeAgo(String(l.timestamp))}</time>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
