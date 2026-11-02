import React, { useState } from "react";
import { Button, Input, useToast } from "./ui";
import { Modal } from "./ui";
import * as api from "../api/client";

/**
 * Manager override dialog. Verifies the entered PIN against a *different*
 * manager account server-side (two-person rule enforced by backend) and
 * returns the verified user id for audit stamping.
 */
export function ManagerPinModal({ open, onClose, onVerified, title = "Manager Override" }: {
  open: boolean; onClose: () => void; onVerified: (userId: string, name: string) => void; title?: string;
}) {
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { push } = useToast();

  const verify = async () => {
    if (pin.length < 3) { setError("Enter the manager PIN."); return; }
    setBusy(true); setError(null);
    try {
      const res = await api.verifyManagerPin(pin);
      if (!res.valid) { setError("PIN rejected. Another manager must authorize this action."); setBusy(false); return; }
      push("success", `Override authorized by ${res.name ?? "manager"}`);
      setPin("");
      onVerified(res.user_id ?? "", res.name ?? "Manager");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Verification failed.");
    } finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title={title} width={400}>
      <p className="muted">A supervisor or store manager (other than you) must authorize this action. It will be recorded in the audit trail.</p>
      <label htmlFor="mgr-pin">Manager PIN</label>
      <Input id="mgr-pin" type="password" inputMode="numeric" autoFocus maxLength={8} value={pin}
        onChange={(e) => setPin(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && verify()} />
      {error && <div className="login-error" role="alert">{error}</div>}
      <div className="modal-actions">
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" loading={busy} onClick={verify}>Authorize</Button>
      </div>
    </Modal>
  );
}
