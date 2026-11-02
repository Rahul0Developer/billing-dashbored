// ---- Formatting + a11y helpers ----

export function inr(n: number | undefined | null, opts?: { compact?: boolean }): string {
  if (n === undefined || n === null || Number.isNaN(n)) return "₹0.00";
  if (opts?.compact && Math.abs(n) >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`;
  if (opts?.compact && Math.abs(n) >= 1e5) return `₹${(n / 1e5).toFixed(2)} L`;
  return "₹" + n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function fmtQty(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(3);
}

export function timeAgo(iso: string): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const diff = Date.now() - t;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

/** WebAudio beep for scan feedback — no external assets needed. */
export function beep(kind: "ok" | "error" = "ok"): void {
  try {
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = kind === "ok" ? 880 : 330;
    gain.gain.setValueAtTime(0.08, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.12);
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.13);
    setTimeout(() => void ctx.close(), 300);
  } catch {
    /* audio unsupported — silent */
  }
}

export const TIER_COLORS: Record<string, string> = {
  BRONZE: "#a1662f",
  SILVER: "#8b949e",
  GOLD: "#d4a017",
  PLATINUM: "#4f9dd6",
};
