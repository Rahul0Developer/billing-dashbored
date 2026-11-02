import React, { useState } from "react";
import { Button, Input, useToast } from "./ui";
import { ApiError } from "../api/client";
import { useI18n } from "../i18n";
import type { SessionUser } from "../api/types";

export function LoginForm({ onLogin }: { onLogin: (u: string, p: string) => Promise<SessionUser> }) {
  const [username, setUsername] = useState("");
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { push } = useToast();
  const { t, lang, setLang } = useI18n();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !pin.trim()) { setError("Enter your username and PIN."); return; }
    setBusy(true);
    setError(null);
    try {
      const u = await onLogin(username.trim(), pin.trim());
      push("success", `Welcome back, ${u.name}!`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.status === 423 ? "Account locked after repeated failures — wait 15 minutes." : err.message);
      } else setError("Unable to reach the server.");
    } finally { setBusy(false); }
  };

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={submit} noValidate>
        <div className="login-brand">
          <div className="brand-logo-circle">🛒</div>
          <h1>APEX RETAIL</h1>
          <span className="store-badge-tag">ENTERPRISE POS &amp; ERP</span>
        </div>
        <h2>{t("login.title")}</h2>
        <label htmlFor="login-user">{t("login.username")}</label>
        <Input id="login-user" autoComplete="username" autoFocus value={username}
          onChange={(e) => setUsername(e.target.value)} placeholder="e.g. rsharma" maxLength={40} />
        <label htmlFor="login-pin">{t("login.pin")}</label>
        <Input id="login-pin" type="password" inputMode="numeric" autoComplete="current-password"
          value={pin} onChange={(e) => setPin(e.target.value)} maxLength={8} />
        {error && <div className="login-error" role="alert">{error}</div>}
        <Button type="submit" variant="primary" size="lg" loading={busy} style={{ width: "100%", marginTop: 8 }}>
          {t("login.signIn")}
        </Button>
        <div className="login-footer">
          <button type="button" className="lang-toggle" onClick={() => setLang(lang === "en" ? "hi" : "en")}>
            {lang === "en" ? "हिन्दी में बदलें" : "Switch to English"}
          </button>
        </div>
      </form>
    </div>
  );
}
